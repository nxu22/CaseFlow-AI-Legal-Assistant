"""fix RLS policy for empty string current_tenant

Revision ID: f2b8c4d6e0a1
Revises: e9a3d1f8c2b7
Create Date: 2026-06-26

Bug: After SET LOCAL app.current_tenant = 'uuid', when the transaction ends
Postgres resets the custom GUC to '' (empty string) rather than NULL. On the
next request reusing the same pooled connection, current_setting(...) returns
'' and ''::uuid raises InvalidTextRepresentation.

Fix: Replace the IS NULL check with a CASE WHEN that guards the ::uuid cast
behind a nullif, so neither NULL nor '' ever reaches the ::uuid cast.
"""
from alembic import op

revision = 'f2b8c4d6e0a1'
down_revision = 'e9a3d1f8c2b7'
branch_labels = None
depends_on = None

_TENANT_TABLES = ['cases', 'clients', 'users', 'documents']

# Safe policy: CASE WHEN guarantees the ::uuid cast only runs on a non-empty value.
# nullif(x, '') converts '' to NULL so both NULL and '' take the THEN true branch.
_POLICY_TEMPLATE = """
    CREATE POLICY firm_isolation ON {table}
    USING (
        CASE
            WHEN nullif(current_setting('app.current_tenant', true), '') IS NULL
                THEN true
            ELSE firm_id = current_setting('app.current_tenant', true)::uuid
        END
    )
"""

_DOCUMENTS_POLICY = """
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
"""


def upgrade() -> None:
    for table in _TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS firm_isolation ON {table}")

    for table in ['cases', 'clients', 'users']:
        op.execute(_POLICY_TEMPLATE.format(table=table))

    op.execute(_DOCUMENTS_POLICY)


def downgrade() -> None:
    # Restore original policies (will still have the '' bug on pooled connections)
    for table in _TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS firm_isolation ON {table}")

    for table in ['cases', 'clients', 'users']:
        op.execute(f"""
            CREATE POLICY firm_isolation ON {table}
            USING (
                current_setting('app.current_tenant', true) IS NULL
                OR firm_id = current_setting('app.current_tenant', true)::uuid
            )
        """)

    op.execute("""
        CREATE POLICY firm_isolation ON documents
        USING (
            current_setting('app.current_tenant', true) IS NULL
            OR case_id IN (
                SELECT id FROM cases
                WHERE firm_id = current_setting('app.current_tenant', true)::uuid
            )
        )
    """)
