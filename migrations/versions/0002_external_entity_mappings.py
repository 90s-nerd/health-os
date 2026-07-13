"""Rename the legacy platform-specific entity mapping table."""

from alembic import op
from sqlalchemy import inspect

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    tables = inspect(op.get_bind()).get_table_names()
    if "home_assistant_entity_mappings" in tables and "external_entity_mappings" not in tables:
        op.rename_table("home_assistant_entity_mappings", "external_entity_mappings")


def downgrade():
    tables = inspect(op.get_bind()).get_table_names()
    if "external_entity_mappings" in tables and "home_assistant_entity_mappings" not in tables:
        op.rename_table("external_entity_mappings", "home_assistant_entity_mappings")
