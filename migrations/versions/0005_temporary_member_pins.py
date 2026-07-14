"""Require household members to replace their admin-issued temporary PIN."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    columns = {
        column["name"] for column in inspect(op.get_bind()).get_columns("app_profile")
    }
    if "must_change_pin" not in columns:
        with op.batch_alter_table("app_profile") as batch:
            batch.add_column(
                sa.Column(
                    "must_change_pin",
                    sa.Boolean(),
                    nullable=False,
                    server_default="0",
                )
            )


def downgrade():
    with op.batch_alter_table("app_profile") as batch:
        batch.drop_column("must_change_pin")
