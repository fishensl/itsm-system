"""customer office + onsite contact

新增客户字段：
  - customers.office: 客户办公室
  - customers.onsite_contact: 驻场联系人
  - customers.onsite_phone: 驻场联系方式
  - customers.onsite_office: 驻场办公室

Revision ID: 6e2d88637a8d
Revises: cb9d639a430f
Create Date: 2026-06-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6e2d88637a8d'
down_revision = 'cb9d639a430f'
branch_labels = None
depends_on = None


_NEW_COLS = (
    ('office', sa.String(length=128)),
    ('onsite_contact', sa.String(length=64)),
    ('onsite_phone', sa.String(length=32)),
    ('onsite_office', sa.String(length=128)),
)


def _existing_columns(bind, table):
    insp = sa.inspect(bind)
    return {c['name'] for c in insp.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    existing = _existing_columns(bind, 'customers')
    with op.batch_alter_table('customers', schema=None) as batch_op:
        for name, type_ in _NEW_COLS:
            if name not in existing:
                batch_op.add_column(sa.Column(name, type_, nullable=True,
                                              server_default=''))


def downgrade():
    bind = op.get_bind()
    existing = _existing_columns(bind, 'customers')
    with op.batch_alter_table('customers', schema=None) as batch_op:
        for name, _type in reversed(_NEW_COLS):
            if name in existing:
                batch_op.drop_column(name)
