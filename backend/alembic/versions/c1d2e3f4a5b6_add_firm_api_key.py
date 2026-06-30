"""add api_key column to firms for MCP server authentication

Revision ID: c1d2e3f4a5b6
Revises: b7d3e1a9f5c2
Create Date: 2026-06-26

Purpose:
  Each firm's MCP server subprocess authenticates itself at startup by presenting
  FIRM_API_KEY from its environment.  resolve_firm_id() in mcp_server.py queries
  this column once at startup and stores the firm_id as a process-level constant,
  so every subsequent tool call can SET LOCAL app.current_tenant without re-querying.

  Column is nullable so existing firms that don't use MCP are unaffected.
  UNIQUE constraint ensures no two firms share a key.
"""
import sqlalchemy as sa
from alembic import op

revision = 'c1d2e3f4a5b6'
down_revision = 'b7d3e1a9f5c2'
branch_labels = None
depends_on = None

DEMO_FIRM_ID  = 'aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa'
JONES_LAW_ID  = 'bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb'

DEMO_API_KEY  = 'demo-firm-api-key-2026'
JONES_API_KEY = 'jones-law-api-key-2026'


def upgrade() -> None:
    op.add_column(
        'firms',
        sa.Column('api_key', sa.String(64), nullable=True),
    )
    op.create_unique_constraint('uq_firms_api_key', 'firms', ['api_key'])
    op.create_index('ix_firms_api_key', 'firms', ['api_key'])

    # Backfill api_key for both known firms (idempotent: UPDATE only touches rows
    # that already exist; new-install path is handled by seed.py).
    op.execute(
        f"UPDATE firms SET api_key = '{DEMO_API_KEY}'  WHERE id = '{DEMO_FIRM_ID}'"
    )
    op.execute(
        f"UPDATE firms SET api_key = '{JONES_API_KEY}' WHERE id = '{JONES_LAW_ID}'"
    )


def downgrade() -> None:
    op.drop_index('ix_firms_api_key', table_name='firms')
    op.drop_constraint('uq_firms_api_key', 'firms', type_='unique')
    op.drop_column('firms', 'api_key')
