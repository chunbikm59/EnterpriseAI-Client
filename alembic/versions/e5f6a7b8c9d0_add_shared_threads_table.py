"""add shared_threads table

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'shared_threads',
        sa.Column('token', sa.String(length=32), nullable=False),
        sa.Column('thread_id', sa.String(length=128), nullable=False),
        sa.Column('user_id', sa.String(length=128), nullable=False),
        sa.Column('conversation_folder', sa.String(length=512), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('token'),
        sa.UniqueConstraint('thread_id'),
    )
    op.create_index('ix_shared_threads_thread_id', 'shared_threads', ['thread_id'])


def downgrade() -> None:
    op.drop_index('ix_shared_threads_thread_id', table_name='shared_threads')
    op.drop_table('shared_threads')
