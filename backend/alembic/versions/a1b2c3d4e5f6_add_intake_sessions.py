"""add intake_sessions for thread ownership

Revision ID: a1b2c3d4e5f6
Revises: f2b8c4d6e0a1
Create Date: 2026-06-26

LangGraph's checkpoint tables (checkpoints, checkpoint_blobs, etc.) are owned
by PostgresSaver and cannot have a firm_id column added to them. This table is
our authoritative mapping of thread_id -> firm_id, enabling the same
ownership-check pattern used for cases/clients/documents:

    db.query(IntakeSession).filter(
        IntakeSession.thread_id == thread_id,
        IntakeSession.firm_id   == current_user.firm_id,
    ).first()  ->  404 if None

RLS is added with the same CASE WHEN pattern used on the other tenant tables,
giving database-layer defense-in-depth on top of the application-layer check.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = 'a1b2c3d4e5f6'
down_revision = 'f2b8c4d6e0a1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'intake_sessions',
        sa.Column('thread_id',     sa.String(),              nullable=False),
        sa.Column('case_id',       postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('firm_id',       postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at',    sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['case_id'],        ['cases.id'],  ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['firm_id'],        ['firms.id'],  ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'],  ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('thread_id'),
    )
    op.create_index('ix_intake_sessions_firm_id', 'intake_sessions', ['firm_id'])

    # Grant caseflow_app access (same pattern as the other tenant tables).
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE intake_sessions TO caseflow_app")

    # RLS — same CASE WHEN guard used on cases/clients/users/documents.
    op.execute("ALTER TABLE intake_sessions ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY firm_isolation ON intake_sessions
        USING (
            CASE
                WHEN nullif(current_setting('app.current_tenant', true), '') IS NULL
                    THEN true
                ELSE firm_id = current_setting('app.current_tenant', true)::uuid
            END
        )
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS firm_isolation ON intake_sessions")
    op.execute("ALTER TABLE intake_sessions DISABLE ROW LEVEL SECURITY")
    op.drop_index('ix_intake_sessions_firm_id', table_name='intake_sessions')
    op.drop_table('intake_sessions')
