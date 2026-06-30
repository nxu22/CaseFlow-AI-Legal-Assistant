"""add_firms_and_tenant_firm_id

Revision ID: c3e5f7a9b1d3
Revises: a3f1c8d920e7
Create Date: 2026-06-25

Adds multi-tenant foundation:
  - CREATE TABLE firms
  - ADD COLUMN firm_id (nullable) to users, clients, cases
  - Backfill all existing rows with the demo firm UUID
  - SET NOT NULL on firm_id columns
  - ADD indexes on firm_id columns

The backfill UUID matches DEMO_FIRM_ID in seed.py so that migrating an
existing database and doing a fresh install produce identical results.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c3e5f7a9b1d3'
down_revision: Union[str, Sequence[str], None] = 'a3f1c8d920e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Must match seed.py DEMO_FIRM_ID exactly.
DEMO_FIRM_ID = 'aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa'


def upgrade() -> None:
    # ── Step 1: Create firms table ────────────────────────────────────────────
    op.create_table(
        'firms',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_firms_slug'), 'firms', ['slug'], unique=True)

    # ── Step 2: Insert demo firm (backfill target for existing rows) ──────────
    op.execute(
        f"""
        INSERT INTO firms (id, name, slug, is_active, created_at, updated_at)
        VALUES (
            '{DEMO_FIRM_ID}',
            'CaseFlow Demo Firm',
            'demo-firm',
            true,
            NOW(),
            NOW()
        )
        """
    )

    # ── Step 3: users — add nullable, backfill, constrain ────────────────────
    op.add_column('users', sa.Column('firm_id', sa.UUID(), nullable=True))
    op.execute(f"UPDATE users SET firm_id = '{DEMO_FIRM_ID}'")
    op.alter_column('users', 'firm_id', nullable=False)
    op.create_foreign_key(
        'fk_users_firm_id', 'users', 'firms', ['firm_id'], ['id'],
        ondelete='RESTRICT',
    )
    op.create_index(op.f('ix_users_firm_id'), 'users', ['firm_id'], unique=False)

    # ── Step 4: clients — add nullable, backfill, constrain ──────────────────
    op.add_column('clients', sa.Column('firm_id', sa.UUID(), nullable=True))
    op.execute(f"UPDATE clients SET firm_id = '{DEMO_FIRM_ID}'")
    op.alter_column('clients', 'firm_id', nullable=False)
    op.create_foreign_key(
        'fk_clients_firm_id', 'clients', 'firms', ['firm_id'], ['id'],
        ondelete='RESTRICT',
    )
    op.create_index(op.f('ix_clients_firm_id'), 'clients', ['firm_id'], unique=False)

    # ── Step 5: cases — add nullable, backfill, constrain ────────────────────
    op.add_column('cases', sa.Column('firm_id', sa.UUID(), nullable=True))
    op.execute(f"UPDATE cases SET firm_id = '{DEMO_FIRM_ID}'")
    op.alter_column('cases', 'firm_id', nullable=False)
    op.create_foreign_key(
        'fk_cases_firm_id', 'cases', 'firms', ['firm_id'], ['id'],
        ondelete='RESTRICT',
    )
    op.create_index(op.f('ix_cases_firm_id'), 'cases', ['firm_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_cases_firm_id'), table_name='cases')
    op.drop_constraint('fk_cases_firm_id', 'cases', type_='foreignkey')
    op.drop_column('cases', 'firm_id')

    op.drop_index(op.f('ix_clients_firm_id'), table_name='clients')
    op.drop_constraint('fk_clients_firm_id', 'clients', type_='foreignkey')
    op.drop_column('clients', 'firm_id')

    op.drop_index(op.f('ix_users_firm_id'), table_name='users')
    op.drop_constraint('fk_users_firm_id', 'users', type_='foreignkey')
    op.drop_column('users', 'firm_id')

    op.drop_index(op.f('ix_firms_slug'), table_name='firms')
    op.drop_table('firms')
