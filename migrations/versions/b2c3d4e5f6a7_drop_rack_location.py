"""drop rack location layer

机柜改为直接归属客户后，废弃「机柜位置（楼栋/楼层）」层：
  - 删除 racks.location_id 列
  - 删除 rack_locations 表

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-21 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def _existing_columns(bind, table):
    insp = sa.inspect(bind)
    return {c['name'] for c in insp.get_columns(table)}


def _has_table(bind, table):
    return sa.inspect(bind).has_table(table)


def upgrade():
    bind = op.get_bind()

    rack_cols = _existing_columns(bind, 'racks')
    if 'location_id' in rack_cols:
        with op.batch_alter_table('racks', schema=None) as batch_op:
            # 索引名可能不存在，忽略错误
            try:
                batch_op.drop_index('ix_racks_location_id')
            except Exception:
                pass
            batch_op.drop_column('location_id')

    if _has_table(bind, 'rack_locations'):
        op.drop_table('rack_locations')


def downgrade():
    bind = op.get_bind()

    if not _has_table(bind, 'rack_locations'):
        op.create_table(
            'rack_locations',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('customer_id', sa.Integer(), nullable=True),
            sa.Column('building', sa.String(length=64), nullable=True),
            sa.Column('floor', sa.String(length=32), nullable=True),
            sa.Column('remark', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['customer_id'], ['customers.id']),
            sa.PrimaryKeyConstraint('id'),
        )

    rack_cols = _existing_columns(bind, 'racks')
    if 'location_id' not in rack_cols:
        with op.batch_alter_table('racks', schema=None) as batch_op:
            batch_op.add_column(sa.Column('location_id', sa.Integer(), nullable=True))
