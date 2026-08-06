"""user_regions 用户负责区域关联表

需求：人员管理可选择工程师负责区域（多选），驻场工程师新建工单/巡检/故障时
客户下拉默认过滤并预选对应区域的客户。

Revision ID: b2c3d4e5f6a8
Revises: a5f6e7d8c9b1
Create Date: 2026-08-06 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a8'
down_revision = 'a5f6e7d8c9b1'
branch_labels = None
depends_on = None


def _existing_tables(bind):
    insp = sa.inspect(bind)
    return set(insp.get_table_names())


def upgrade():
    bind = op.get_bind()
    if 'user_regions' in _existing_tables(bind):
        return
    op.create_table(
        'user_regions',
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('region_id', sa.Integer(), sa.ForeignKey('regions.id'), primary_key=True),
    )


def downgrade():
    bind = op.get_bind()
    if 'user_regions' in _existing_tables(bind):
        op.drop_table('user_regions')
