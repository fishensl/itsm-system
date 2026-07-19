"""perf indexes

W1 性能优化：为高频过滤/关联列补索引。
- devices(customer_id)：客户下设备查询/级联
- devices(brand, model)：固件版本库按型号匹配设备（复合索引）
- inspection_tasks(status / assigned_to_user_id / contract_id)：看板筛选、派单查询、合同任务反查
- inspections(customer_id / review_status)：客户详情、审核列表
- tickets(customer_id / assigned_to)：客户详情、我的待办

已存在索引的列（devices.ip_address 等）不在此重复。幂等：先查后建。

Revision ID: f7a8b9c0d1e2
Revises: 2c3d4e5f6a7b
Create Date: 2026-07-19 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f7a8b9c0d1e2'
down_revision = '2c3d4e5f6a7b'
branch_labels = None
depends_on = None

# (索引名, 表, 列)
_INDEXES = [
    ('ix_devices_customer_id', 'devices', ['customer_id']),
    ('ix_devices_brand_model', 'devices', ['brand', 'model']),
    ('ix_inspection_tasks_status', 'inspection_tasks', ['status']),
    ('ix_inspection_tasks_assigned_to_user_id', 'inspection_tasks', ['assigned_to_user_id']),
    ('ix_inspection_tasks_contract_id', 'inspection_tasks', ['contract_id']),
    ('ix_inspections_customer_id', 'inspections', ['customer_id']),
    ('ix_inspections_review_status', 'inspections', ['review_status']),
    ('ix_tickets_customer_id', 'tickets', ['customer_id']),
    ('ix_tickets_assigned_to', 'tickets', ['assigned_to']),
]


def _existing_indexes(bind, table):
    insp = sa.inspect(bind)
    return {ix['name'] for ix in insp.get_indexes(table)}


def upgrade():
    bind = op.get_bind()
    for name, table, columns in _INDEXES:
        if name not in _existing_indexes(bind, table):
            op.create_index(name, table, columns)


def downgrade():
    bind = op.get_bind()
    for name, table, _columns in _INDEXES:
        if name in _existing_indexes(bind, table):
            op.drop_index(name, table_name=table)
