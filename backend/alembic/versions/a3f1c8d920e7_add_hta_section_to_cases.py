"""add_hta_section_to_cases

Revision ID: a3f1c8d920e7
Revises: 6158f22554eb
Create Date: 2026-06-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f1c8d920e7'
down_revision: Union[str, Sequence[str], None] = '6158f22554eb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('cases', sa.Column('hta_section', sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column('cases', 'hta_section')
