"""spare_borrows 表 + tickets.sla_deadline 列

S6 工作流完善：
- spare_borrows：备件借用登记表（借出扣库存、归还回补，流水走 stock_movements）
- tickets.sla_deadline：工单 SLA 截止时间（按优先级创建时计算）

幂等：表不存在才建、列不存在才加。

Revision ID: a3b4c5d6e7f8
Revises: 9da0e1f2a3b4
Create Date: 2026-08-08 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a3b4c5d6e7f8'
down_revision = '9da0e1f2a3b4'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1) spare_borrows 表（不存在才建）
    if 'spare_borrows' not in insp.get_table_names():
        op.create_table(
            'spare_borrows',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('spare_part_id', sa.Integer(),
                      sa.ForeignKey('spare_parts.id'), nullable=False, index=True),
            sa.Column('borrower', sa.String(64), nullable=False),
            sa.Column('borrower_phone', sa.String(32), default=''),
            sa.Column('quantity', sa.Integer(), nullable=False),
            sa.Column('location', sa.String(128), default=''),
            sa.Column('borrow_date', sa.Date(), default=None, index=True),
            sa.Column('expected_return_date', sa.Date(), nullable=True),
            sa.Column('return_date', sa.Date(), nullable=True),
            sa.Column('status', sa.String(16), default='借用中', index=True),
            sa.Column('operator', sa.String(64), default=''),
            sa.Column('remark', sa.Text(), default=''),
            sa.Column('created_at', sa.DateTime(), nullable=True),
        )

    # 2) tickets.sla_deadline 列（缺失才加）
    tickets_cols = {c['name'] for c in insp.get_columns('tickets')}
    if 'sla_deadline' not in tickets_cols:
        op.add_column('tickets', sa.Column('sla_deadline', sa.DateTime(), nullable=True))

    # 3) knowledge_base 发布审核字段（S6：published_by/published_at）
    kb_cols = {c['name'] for c in insp.get_columns('knowledge_base')}
    if 'published_by' not in kb_cols:
        op.add_column('knowledge_base', sa.Column('published_by', sa.String(64), default=''))
    if 'published_at' not in kb_cols:
        op.add_column('knowledge_base', sa.Column('published_at', sa.DateTime(), nullable=True))


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if 'spare_borrows' in insp.get_table_names():
        op.drop_table('spare_borrows')
    tickets_cols = {c['name'] for c in insp.get_columns('tickets')}
    if 'sla_deadline' in tickets_cols:
        op.drop_column('tickets', 'sla_deadline')
    kb_cols = {c['name'] for c in insp.get_columns('knowledge_base')}
    if 'published_by' in kb_cols:
        op.drop_column('knowledge_base', 'published_by')
    if 'published_at' in kb_cols:
        op.drop_column('knowledge_base', 'published_at')
