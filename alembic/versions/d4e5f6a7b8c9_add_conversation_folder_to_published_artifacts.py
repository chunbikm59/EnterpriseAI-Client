"""add conversation_folder to published_artifacts

Revision ID: d4e5f6a7b8c9
Revises: c7f3a92d1e08
Create Date: 2026-05-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'published_artifacts',
        sa.Column('conversation_folder', sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('published_artifacts', 'conversation_folder')
