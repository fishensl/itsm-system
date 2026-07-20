"""contract task_template_id

W4-D3 旧模板下线第一步：contracts 增加 task_template_id（指向新任务模板），
并按「模板名匹配」把存量 contract.inspection_template_id（旧模板）迁移过来：
- 已有同名 InspectionTaskTemplate → 直接关联
- 无同名 → 以旧模板名为其创建一个最小新任务模板（name + category=日常）再关联

幂等：先查后改；旧 inspection_template_id 列保留（只读回退，后续版本再删）。

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-07-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a8b9c0d1e2f3'
down_revision = 'f7a8b9c0d1e2'
branch_labels = None
depends_on = None


def _existing_columns(bind, table):
    insp = sa.inspect(bind)
    return {c['name'] for c in insp.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    cols = _existing_columns(bind, 'contracts')
    if 'task_template_id' not in cols:
        with op.batch_alter_table('contracts', schema=None) as batch_op:
            batch_op.add_column(sa.Column('task_template_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                'fk_contracts_task_template_id',
                'inspection_task_templates', ['task_template_id'], ['id'])
        # 注意：索引必须在 batch 块外创建——SQLite 批处理内 create_index 会在新列生效前执行而失败
        idx = {i['name'] for i in sa.inspect(bind).get_indexes('contracts')}
        if 'ix_contracts_task_template_id' not in idx:
            op.create_index('ix_contracts_task_template_id', 'contracts', ['task_template_id'])

    # ---- 数据迁移：按模板名匹配/创建新任务模板并回填 ----
    meta = sa.MetaData()
    contracts = sa.Table('contracts', meta, autoload_with=bind)
    legacy_tpls = sa.Table('inspection_templates', meta, autoload_with=bind)
    task_tpls = sa.Table('inspection_task_templates', meta, autoload_with=bind)

    rows = bind.execute(sa.select(
        contracts.c.id, contracts.c.inspection_template_id, contracts.c.task_template_id
    ).where(contracts.c.inspection_template_id.isnot(None))).all()

    for cid, legacy_id, existing_tt in rows:
        if existing_tt:
            continue  # 已迁移
        legacy = bind.execute(sa.select(legacy_tpls.c.name, legacy_tpls.c.is_active)
                              .where(legacy_tpls.c.id == legacy_id)).first()
        if not legacy:
            continue
        tpl_name = legacy[0]
        tt = bind.execute(sa.select(task_tpls.c.id)
                          .where(task_tpls.c.name == tpl_name)).first()
        if tt:
            tt_id = tt[0]
        else:
            # 创建最小新任务模板（名称一致，category=日常，is_active 跟随旧模板）
            bind.execute(task_tpls.insert().values(
                name=tpl_name, category='日常', sections_json='{}',
                is_active=bool(legacy[1]),
            ))
            tt_id = bind.execute(sa.select(task_tpls.c.id)
                                 .where(task_tpls.c.name == tpl_name)).first()[0]
        bind.execute(contracts.update().where(contracts.c.id == cid)
                     .values(task_template_id=tt_id))


def downgrade():
    bind = op.get_bind()
    cols = _existing_columns(bind, 'contracts')
    if 'task_template_id' in cols:
        with op.batch_alter_table('contracts', schema=None) as batch_op:
            batch_op.drop_column('task_template_id')
