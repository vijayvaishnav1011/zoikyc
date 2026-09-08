"""standardize all existing company client ids to ZOI-<letters>-<15digits>

Revision ID: e2f3a4b5c6d7
Revises: c18e451becd3
Create Date: 2026-09-08 19:35:00.000000

"""
import re
import random
import string
from alembic import op
import sqlalchemy as sa

revision = 'e2f3a4b5c6d7'
down_revision = 'c18e451becd3'
branch_labels = None
depends_on = None

def upgrade():
    conn = op.get_bind()
    companies = conn.execute(sa.text("SELECT id, name, client_id FROM companies")).fetchall()
    client_id_regex = re.compile(r'^ZOI-[A-Z0-9]{2}-\d{15}$')
    used_ids = set()

    for row in companies:
        comp_id = row[0]
        name = row[1]
        current_client_id = row[2]

        if current_client_id and client_id_regex.match(current_client_id):
            used_ids.add(current_client_id)
            continue

        clean_name = re.sub(r'[^a-zA-Z0-9]', '', name or '').upper()
        prefix = clean_name[:2] if len(clean_name) >= 2 else (clean_name + 'ZK')[:2]
        if not prefix:
            prefix = 'ZK'

        while True:
            rand_digits = ''.join(random.choices(string.digits, k=15))
            new_id = f"ZOI-{prefix}-{rand_digits}"
            if new_id not in used_ids:
                used_ids.add(new_id)
                break

        conn.execute(
            sa.text("UPDATE companies SET client_id = :cid WHERE id = :id"),
            {"cid": new_id, "id": comp_id}
        )

def downgrade():
    pass
