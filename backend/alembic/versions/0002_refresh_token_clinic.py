"""refresh tokens remember the clinic they were issued for

Revision ID: 0002
Revises: 305c428b06be
"""

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "305c428b06be"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("refresh_tokens", sa.Column("clinic_id", sa.UUID(), nullable=True))


def downgrade() -> None:
    op.drop_column("refresh_tokens", "clinic_id")
