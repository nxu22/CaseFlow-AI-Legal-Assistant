"""add final_decision and decision_at to intake_sessions

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-06-27
"""
from alembic import op
import sqlalchemy as sa

revision = 'e3f4a5b6c7d8'
down_revision = 'd2e3f4a5b6c7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE TYPE intakedecision AS ENUM ('approved', 'edited', 'rejected')")
    op.add_column(
        'intake_sessions',
        sa.Column('final_decision', sa.Enum('approved', 'edited', 'rejected', name='intakedecision'), nullable=True),
    )
    op.add_column(
        'intake_sessions',
        sa.Column('decision_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('intake_sessions', 'decision_at')
    op.drop_column('intake_sessions', 'final_decision')
    op.execute("DROP TYPE intakedecision")
