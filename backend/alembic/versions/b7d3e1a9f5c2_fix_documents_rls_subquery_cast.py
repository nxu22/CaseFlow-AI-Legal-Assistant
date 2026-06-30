"""fix documents RLS subquery cast for empty-string GUC

Revision ID: b7d3e1a9f5c2
Revises: a1b2c3d4e5f6
Create Date: 2026-06-26

Root cause:
  PostgreSQL's query planner evaluates the cost of subqueries in CASE WHEN ELSE
  branches at PLAN TIME, even though the CASE WHEN correctly short-circuits at
  runtime.  The documents policy ELSE branch contains:

      case_id IN (SELECT id FROM cases WHERE firm_id = current_setting(...)::uuid)

  When app.current_tenant = '' (after SET LOCAL + COMMIT, or after RESET),
  current_setting('app.current_tenant', true) returns ''.  During plan-time
  cost estimation, PostgreSQL evaluates '::uuid, which raises:
      InvalidTextRepresentation: invalid input syntax for type uuid: ""

  The outer CASE WHEN guard (nullif(..., '') IS NULL THEN true) correctly
  short-circuits at RUNTIME, but the planner still touches the subquery.

  Other tables (cases, clients, users, intake_sessions) use direct column
  comparisons in their ELSE branch (no subquery) so they are not affected.

Fix:
  Wrap the cast inside the subquery with nullif() as well:
      firm_id = nullif(current_setting('app.current_tenant', true), '')::uuid

  When GUC = '':  nullif('', '') = NULL, NULL::uuid = NULL (no error),
                  firm_id = NULL is always false → no rows leaked.
  When GUC = uuid: behaves identically to before.
"""
from alembic import op

revision = 'b7d3e1a9f5c2'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP POLICY IF EXISTS firm_isolation ON documents")
    op.execute("""
        CREATE POLICY firm_isolation ON documents
        USING (
            CASE
                WHEN nullif(current_setting('app.current_tenant', true), '') IS NULL
                    THEN true
                ELSE case_id IN (
                    SELECT id FROM cases
                    WHERE firm_id = nullif(current_setting('app.current_tenant', true), '')::uuid
                )
            END
        )
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS firm_isolation ON documents")
    op.execute("""
        CREATE POLICY firm_isolation ON documents
        USING (
            CASE
                WHEN nullif(current_setting('app.current_tenant', true), '') IS NULL
                    THEN true
                ELSE case_id IN (
                    SELECT id FROM cases
                    WHERE firm_id = current_setting('app.current_tenant', true)::uuid
                )
            END
        )
    """)
