"""add published_artifacts table

Revision ID: c7f3a92d1e08
Revises: 812c30d9b04b
Create Date: 2026-04-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7f3a92d1e08'
down_revision: Union[str, Sequence[str], None] = '812c30d9b04b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'published_artifacts',
        sa.Column('token', sa.String(length=32), nullable=False),
        sa.Column('artifact_id', sa.String(length=128), nullable=False),
        sa.Column('title', sa.String(length=256), nullable=False),
        sa.Column('user_id', sa.String(length=128), nullable=False),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('html_file', sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint('token'),
        sa.UniqueConstraint('artifact_id', name='uq_published_artifacts_artifact_id'),
    )
    op.create_index(op.f('ix_published_artifacts_artifact_id'), 'published_artifacts', ['artifact_id'], unique=True)
    op.create_index(op.f('ix_published_artifacts_user_id'), 'published_artifacts', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_published_artifacts_user_id'), table_name='published_artifacts')
    op.drop_index(op.f('ix_published_artifacts_artifact_id'), table_name='published_artifacts')
    op.drop_table('published_artifacts')
