"""Add provider identities, per-user time metadata, and durable reminder scheduling."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {column["name"] for column in inspect(op.get_bind()).get_columns(table)}


def upgrade():
    profile_columns = _columns("app_profile")
    with op.batch_alter_table("app_profile") as batch:
        if "timezone_source" not in profile_columns:
            batch.add_column(
                sa.Column("timezone_source", sa.String(), nullable=False, server_default="imported")
            )
        if "timezone_confirmed_at" not in profile_columns:
            batch.add_column(sa.Column("timezone_confirmed_at", sa.DateTime(timezone=True)))
        if "temporary_timezone" not in profile_columns:
            batch.add_column(sa.Column("temporary_timezone", sa.String()))
        if "temporary_timezone_expires_at" not in profile_columns:
            batch.add_column(sa.Column("temporary_timezone_expires_at", sa.DateTime(timezone=True)))

    if "user_identities" not in inspect(op.get_bind()).get_table_names():
        op.create_table(
            "user_identities",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("app_profile.id"), nullable=False),
            sa.Column("provider", sa.String(), nullable=False),
            sa.Column("provider_subject", sa.String(), nullable=False),
            sa.Column("provider_username", sa.String()),
            sa.Column("provider_display_name", sa.String()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_login_at", sa.DateTime(timezone=True)),
            sa.UniqueConstraint("provider", "provider_subject"),
        )
        op.create_index("ix_user_identities_user_id", "user_identities", ["user_id"])
        op.create_index("ix_user_identities_provider", "user_identities", ["provider"])
    op.execute(
        "INSERT INTO user_identities "
        "(user_id, provider, provider_subject, provider_username, provider_display_name, created_at, updated_at) "
        "SELECT id, 'pin', 'profile:' || id, NULL, display_name, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP "
        "FROM app_profile WHERE pin_hash IS NOT NULL AND NOT EXISTS ("
        "SELECT 1 FROM user_identities i WHERE i.provider = 'pin' AND i.user_id = app_profile.id)"
    )
    op.execute("UPDATE app_profile SET is_admin = 0")
    op.execute("UPDATE app_profile SET must_change_pin = 0")

    completion_columns = _columns("task_completions")
    with op.batch_alter_table("task_completions") as batch:
        if "user_local_date" not in completion_columns:
            batch.add_column(sa.Column("user_local_date", sa.Date()))
        if "timezone_at_completion" not in completion_columns:
            batch.add_column(sa.Column("timezone_at_completion", sa.String()))
    op.execute(
        "UPDATE task_completions SET "
        "user_local_date = (SELECT task_date FROM daily_tasks WHERE daily_tasks.id = task_completions.daily_task_id), "
        "timezone_at_completion = (SELECT p.timezone FROM daily_tasks d JOIN habits h ON h.id = d.habit_id "
        "JOIN app_profile p ON p.id = h.profile_id WHERE d.id = task_completions.daily_task_id) "
        "WHERE user_local_date IS NULL"
    )

    reminder_columns = _columns("reminder_rules")
    reminder_fields = (
        ("local_time", sa.Time()),
        ("days_of_week", sa.String(), "0,1,2,3,4,5,6"),
        ("timezone_behavior", sa.String(), "follow_user_timezone"),
        ("fixed_timezone", sa.String()),
        ("urgent_bypasses_quiet_hours", sa.Boolean(), "0"),
        ("last_sent_at_utc", sa.DateTime(timezone=True)),
        ("next_run_at_utc", sa.DateTime(timezone=True)),
        ("created_at", sa.DateTime(timezone=True)),
        ("updated_at", sa.DateTime(timezone=True)),
    )
    with op.batch_alter_table("reminder_rules") as batch:
        for item in reminder_fields:
            name, column_type, *default = item
            if name not in reminder_columns:
                batch.add_column(
                    sa.Column(name, column_type, server_default=default[0] if default else None)
                )
        if "next_run_at_utc" not in reminder_columns:
            batch.create_index("ix_reminder_rules_next_run_at_utc", ["next_run_at_utc"])

    if "notification_deliveries" not in inspect(op.get_bind()).get_table_names():
        op.create_table(
            "notification_deliveries",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("rule_id", sa.Integer(), sa.ForeignKey("reminder_rules.id"), nullable=False),
            sa.Column("profile_id", sa.Integer(), sa.ForeignKey("app_profile.id"), nullable=False),
            sa.Column("scheduled_for_utc", sa.DateTime(timezone=True), nullable=False),
            sa.Column("attempted_at_utc", sa.DateTime(timezone=True)),
            sa.Column("status", sa.String(), nullable=False, server_default="pending"),
            sa.Column("error", sa.Text()),
            sa.UniqueConstraint("rule_id", "scheduled_for_utc"),
        )
        op.create_index("ix_notification_deliveries_rule_id", "notification_deliveries", ["rule_id"])
        op.create_index(
            "ix_notification_deliveries_profile_id", "notification_deliveries", ["profile_id"]
        )


def downgrade():
    raise RuntimeError("Identity and time migration cannot be safely downgraded")
