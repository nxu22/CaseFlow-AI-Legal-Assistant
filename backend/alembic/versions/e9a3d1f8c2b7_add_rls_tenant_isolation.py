"""add RLS tenant isolation

Revision ID: e9a3d1f8c2b7
Revises: c3e5f7a9b1d3
Create Date: 2026-06-26

Defense-in-depth: database-layer Row Level Security on top of the
application-layer firm_id filters added in the previous migration.

Role design:
  caseflow      – Docker bootstrap superuser, used only by Alembic migrations.
                  Superusers always bypass RLS (can't be changed), so this
                  role must NOT be used by the running application.
  caseflow_app  – Non-superuser, non-owner application role. RLS applies to
                  it by default (no FORCE needed). The app's DATABASE_URL
                  must point here; Alembic's DATABASE_URL stays on caseflow.

Policy design:
  The IS NULL branch on every policy lets the tenant variable be absent for
  unauthenticated paths (login) and for Alembic itself. Once an authenticated
  request executes SET LOCAL app.current_tenant, the firm_id branch filters
  all rows automatically.
"""
from alembic import op

revision = 'e9a3d1f8c2b7'
down_revision = 'c3e5f7a9b1d3'
branch_labels = None
depends_on = None

_TENANT_TABLES = ['cases', 'clients', 'users', 'documents']


def upgrade() -> None:
    # Step 1: Create non-superuser application role if it doesn't exist.
    # The DO block is needed because Postgres has no CREATE ROLE IF NOT EXISTS.
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT FROM pg_catalog.pg_roles WHERE rolname = 'caseflow_app'
            ) THEN
                CREATE ROLE caseflow_app WITH LOGIN PASSWORD 'caseflow_app_dev';
            END IF;
        END $$
    """)

    # Step 2: Grant the application role the privileges it needs.
    op.execute("GRANT CONNECT ON DATABASE caseflow_mb TO caseflow_app")
    op.execute("GRANT USAGE ON SCHEMA public TO caseflow_app")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE "
        "ON ALL TABLES IN SCHEMA public TO caseflow_app"
    )

    # Step 3: Enable RLS on every tenant-scoped table.
    # No FORCE needed: caseflow_app is not the table owner, so RLS applies
    # to it automatically without FORCE ROW LEVEL SECURITY.
    for table in _TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")

    # Step 4: Create per-table isolation policies.
    # The IS NULL branch lets the variable be absent (login flow, Alembic).
    # Once SET LOCAL app.current_tenant is executed, firm_id branch filters.

    op.execute("""
        CREATE POLICY firm_isolation ON cases
        USING (
            current_setting('app.current_tenant', true) IS NULL
            OR firm_id = current_setting('app.current_tenant', true)::uuid
        )
    """)

    op.execute("""
        CREATE POLICY firm_isolation ON clients
        USING (
            current_setting('app.current_tenant', true) IS NULL
            OR firm_id = current_setting('app.current_tenant', true)::uuid
        )
    """)

    # users: IS NULL bypass is required so get_current_user can look up the
    # user by id before the tenant context has been set on the session.
    op.execute("""
        CREATE POLICY firm_isolation ON users
        USING (
            current_setting('app.current_tenant', true) IS NULL
            OR firm_id = current_setting('app.current_tenant', true)::uuid
        )
    """)

    # documents has no firm_id column; protect transitively via cases.
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


def downgrade() -> None:
    for table in reversed(_TENANT_TABLES):
        op.execute(f"DROP POLICY IF EXISTS firm_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.execute("REVOKE SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public FROM caseflow_app")
    op.execute("REVOKE USAGE ON SCHEMA public FROM caseflow_app")
    op.execute("REVOKE CONNECT ON DATABASE caseflow_mb FROM caseflow_app")
    op.execute("DROP ROLE IF EXISTS caseflow_app")
