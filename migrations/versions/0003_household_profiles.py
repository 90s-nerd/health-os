"""Add household profiles and per-user health data."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def upgrade():
    inspector = inspect(op.get_bind())
    profile_columns = {column["name"] for column in inspector.get_columns("app_profile")}
    with op.batch_alter_table("app_profile") as batch:
        if "is_admin" not in profile_columns:
            batch.add_column(sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="0"))
        if "onboarding_completed" not in profile_columns:
            batch.add_column(
                sa.Column("onboarding_completed", sa.Boolean(), nullable=False, server_default="0")
            )
    op.execute(
        "UPDATE app_profile SET is_admin = 1, "
        "onboarding_completed = CASE WHEN pin_hash IS NOT NULL THEN 1 ELSE 0 END "
        "WHERE id = (SELECT MIN(id) FROM app_profile)"
    )

    if "user_settings" not in inspector.get_table_names():
        op.create_table(
            "user_settings",
            sa.Column("profile_id", sa.Integer(), nullable=False),
            sa.Column("key", sa.String(), nullable=False),
            sa.Column("value", sa.Text(), nullable=False),
            sa.ForeignKeyConstraint(["profile_id"], ["app_profile.id"]),
            sa.PrimaryKeyConstraint("profile_id", "key"),
        )
    for key in ("caffeine_cutoff", "weight_milestones", "water_target_ml"):
        op.execute(
            "INSERT OR IGNORE INTO user_settings (profile_id, key, value) "
            f"SELECT p.id, '{key}', COALESCE(s.value, "
            f"'{ {'caffeine_cutoff': '14:00', 'weight_milestones': '94,90,88,85', 'water_target_ml': '2000'}[key] }') "
            "FROM app_profile p LEFT JOIN settings s ON s.key = '" + key + "'"
        )

    scoped = [
        "habits",
        "exercise_sessions",
        "meal_checkins",
        "hydration_entries",
        "caffeine_entries",
        "alcohol_entries",
        "sleep_entries",
        "weight_entries",
        "callout_dismissals",
    ]
    changed_tables = []
    for table in scoped:
        columns = {column["name"] for column in inspect(op.get_bind()).get_columns(table)}
        if "profile_id" in columns:
            continue
        changed_tables.append(table)
        with op.batch_alter_table(table, naming_convention=NAMING) as batch:
            batch.add_column(sa.Column("profile_id", sa.Integer(), nullable=True))
        op.execute(
            f"UPDATE {table} SET profile_id = (SELECT MIN(id) FROM app_profile) "
            "WHERE profile_id IS NULL"
        )
        with op.batch_alter_table(table, naming_convention=NAMING) as batch:
            batch.alter_column("profile_id", nullable=False)
            batch.create_foreign_key(
                f"fk_{table}_profile_id_app_profile", "app_profile", ["profile_id"], ["id"]
            )
            batch.create_index(f"ix_{table}_profile_id", ["profile_id"])

    for table, old_column, constraint_name in (
        ("habits", "key", "uq_habits_profile_id_key"),
        ("sleep_entries", "sleep_date", "uq_sleep_entries_profile_id_sleep_date"),
        ("weight_entries", "entry_date", "uq_weight_entries_profile_id_entry_date"),
    ):
        table_inspector = inspect(op.get_bind())
        uniques = [
            tuple(item["column_names"])
            for item in table_inspector.get_unique_constraints(table)
        ]
        indexes = table_inspector.get_indexes(table)
        uniques.extend(
            tuple(item["column_names"]) for item in indexes if item.get("unique")
        )
        if ("profile_id", old_column) in uniques:
            continue
        old_index = next(
            (
                item
                for item in indexes
                if item.get("unique") and item["column_names"] == [old_column]
            ),
            None,
        )
        if old_index:
            op.drop_index(old_index["name"], table_name=table)
        with op.batch_alter_table(table, naming_convention=NAMING) as batch:
            batch.create_unique_constraint(
                constraint_name, ["profile_id", old_column]
            )


def downgrade():
    raise RuntimeError("Household profile migration cannot be safely downgraded")
