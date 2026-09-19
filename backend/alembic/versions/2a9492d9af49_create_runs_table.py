"""create runs table

Revision ID: 2a9492d9af49
Revises: 
Create Date: 2026-09-19 21:29:20.297632

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2a9492d9af49'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('runs',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('filename', sa.Text(), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('status', sa.Enum('uploaded', 'profiled', 'planned', 'cleaned', 'analyzed', 'imported', 'failed', 'expired', name='run_status', native_enum=False, create_constraint=True), nullable=False),
    # Plain DateTime on purpose: app.models.base.UtcDateTime stores naive UTC
    # in exactly this type, and a migration must not import the models.
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('error_code', sa.String(length=32), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_runs'))
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('runs')
