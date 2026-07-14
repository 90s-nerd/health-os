"""Scope reminder, integration mapping, and audit records to a household member."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0004"
down_revision = "0003"
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
    for table in ("reminder_rules", "external_entity_mappings", "audit_events"):
        columns = {column["name"] for column in inspect(op.get_bind()).get_columns(table)}
        if "profile_id" in columns:
            continue
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
        ("reminder_rules", "key", "uq_reminder_rules_profile_id_key"),
        (
            "external_entity_mappings",
            "metric",
            "uq_external_entity_mappings_profile_id_metric",
        ),
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
    raise RuntimeError("Per-user operation scoping cannot be safely downgraded")
