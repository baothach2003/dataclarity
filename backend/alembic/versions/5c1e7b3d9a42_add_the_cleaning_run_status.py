"""add the cleaning run status

The claim a run holds while its plan executes (PROJECT_PLAN 1G). The column is a
VARCHAR(8) with a CHECK constraint, not a native enum, so "cleaning" (8
characters) fits the existing column and only the constraint changes.

Revision ID: 5c1e7b3d9a42
Revises: 2a9492d9af49
Create Date: 2026-09-22 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '5c1e7b3d9a42'
down_revision: Union[str, Sequence[str], None] = '2a9492d9af49'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Spelled out, not read from app.models: a migration must keep meaning what it
# meant on the day it was written.
BEFORE = ('uploaded', 'profiled', 'planned', 'cleaned', 'analyzed', 'imported',
          'failed', 'expired')
AFTER = ('uploaded', 'profiled', 'planned', 'cleaning', 'cleaned', 'analyzed',
         'imported', 'failed', 'expired')
CONSTRAINT = 'ck_runs_run_status'


def _condition(statuses: Sequence[str]) -> str:
    return "status IN (" + ", ".join(f"'{s}'" for s in statuses) + ")"


def _replace_constraint(statuses: Sequence[str]) -> None:
    # Batch mode: SQLite cannot alter a constraint in place; PostgreSQL gets the
    # plain ALTER statements.
    # op.f: the name is already the conventional one; without it the naming
    # convention would prefix it a second time (ck_runs_ck_runs_run_status).
    with op.batch_alter_table('runs') as batch:
        batch.drop_constraint(op.f(CONSTRAINT), type_='check')
        batch.create_check_constraint(op.f(CONSTRAINT), _condition(statuses))


def upgrade() -> None:
    """Upgrade schema."""
    _replace_constraint(AFTER)


def downgrade() -> None:
    """Downgrade schema."""
    # Nothing can be executing while the schema goes down, and the old
    # constraint would refuse the row: put a claimed run back where it was claimed from.
    op.execute("UPDATE runs SET status = 'planned' WHERE status = 'cleaning'")
    _replace_constraint(BEFORE)
