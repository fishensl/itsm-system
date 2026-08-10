"""fault_types 唯一约束切换：name → (name, parent_id)

三级树中不同父级下可重名（如多个二级分类下均有「DNS/DHCP服务」），
name 全局唯一约束会阻止播种。PG 生产切换为组合唯一；SQLite 容错跳过
（测试环境 batch 重建无实际约束，模型层已声明组合唯一）。

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-08-10 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd6e7f8a9b0c1'
down_revision = 'c5d6e7f8a9b0'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == 'sqlite':
        # SQLite 测试环境：无真实全局唯一约束，跳过
        return
    rows = bind.execute(sa.text(
        "SELECT constraint_name FROM information_schema.table_constraints "
        "WHERE table_name='fault_types' AND constraint_type='UNIQUE'")).fetchall()
    names = {r[0] for r in rows}
    if 'fault_types_name_key' in names:
        op.drop_constraint('fault_types_name_key', 'fault_types', type_='unique')
    if 'uq_fault_types_name_parent' not in names:
        op.create_unique_constraint('uq_fault_types_name_parent', 'fault_types',
                                    ['name', 'parent_id'])


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == 'sqlite':
        return
    rows = bind.execute(sa.text(
        "SELECT constraint_name FROM information_schema.table_constraints "
        "WHERE table_name='fault_types' AND constraint_type='UNIQUE'")).fetchall()
    names = {r[0] for r in rows}
    if 'uq_fault_types_name_parent' in names:
        op.drop_constraint('uq_fault_types_name_parent', 'fault_types', type_='unique')
    if 'fault_types_name_key' not in names:
        op.create_unique_constraint('fault_types_name_key', 'fault_types', ['name'])
