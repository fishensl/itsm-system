"""retired customer device name uniqueness attempt

Revision ID: a5b6c7d8e9f0
Revises: f4a5b6c7d8e9
Create Date: 2026-08-28
"""

from alembic import op
import sqlalchemy as sa


revision = 'a5b6c7d8e9f0'
down_revision = 'f4a5b6c7d8e9'
branch_labels = None
depends_on = None


CONSTRAINT_NAME = 'uq_devices_customer_name'


def _has_constraint(bind):
    inspector = sa.inspect(bind)
    return any(
        item.get('name') == CONSTRAINT_NAME
        for item in inspector.get_unique_constraints('devices')
    )


def _has_duplicate_names(bind):
    return bool(bind.execute(sa.text("""
        SELECT 1
          FROM devices
         WHERE customer_id IS NOT NULL
         GROUP BY customer_id, device_name
        HAVING COUNT(*) > 1
         LIMIT 1
    """)).first())


def upgrade():
    bind = op.get_bind()
    # 此迁移在首次生产发布前发现业务上允许同一客户存在多台同名设备。
    # 对无重复数据的已建开发库保留原行为，由后续迁移统一撤销；生产存在真实
    # 同名资产时跳过错误约束，避免升级中断或迫使删除合法设备。
    if not _has_constraint(bind) and not _has_duplicate_names(bind):
        with op.batch_alter_table('devices', schema=None) as batch_op:
            batch_op.create_unique_constraint(
                CONSTRAINT_NAME, ['customer_id', 'device_name'])


def downgrade():
    bind = op.get_bind()
    if _has_constraint(bind):
        with op.batch_alter_table('devices', schema=None) as batch_op:
            batch_op.drop_constraint(CONSTRAINT_NAME, type_='unique')
