"""add token columns to conversations

Revision ID: a1b2c3d4e5f6
Revises: c7f3a92d1e08
Create Date: 2026-04-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'c7f3a92d1e08'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('conversations',
        sa.Column('total_prompt_tokens', sa.Integer(), nullable=False, server_default='0')
    )
    op.add_column('conversations',
        sa.Column('total_completion_tokens', sa.Integer(), nullable=False, server_default='0')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('conversations', 'total_completion_tokens')
    op.drop_column('conversations', 'total_prompt_tokens')
