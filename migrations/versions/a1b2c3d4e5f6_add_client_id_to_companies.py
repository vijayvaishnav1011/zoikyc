"""Add client_id to companies table

Revision ID: a1b2c3d4e5f6
Revises: 9417b491361d
Create Date: 2026-08-30 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '9417b491361d'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS client_id VARCHAR(50);")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_companies_client_id ON companies(client_id);")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_companies_client_id;")
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS client_id;")
