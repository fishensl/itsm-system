"""pg deferrable fks

把全库所有外键约束改为 DEFERRABLE INITIALLY DEFERRED（仅 PG）。

背景：
  utils/data_io.perform_import 在 PG 上用 `SET CONSTRAINTS ALL DEFERRED`
  推迟 FK 校验到 commit，以便清空+回灌大批表时不被循环/自引用外键阻断
  （如 departments.head_id ↔ users.department_id，departments.parent_id
   regions.parent_id）。但该语句只对 DEFERRABLE 约束生效，而默认创建的
  FK 是 NOT DEFERRABLE — 备份导入因此失败。

  本迁移把所有 FK 改为 DEFERRABLE INITIALLY DEFERRED：
    - 平时行为与立即校验一致（仅在事务 commit 时统一检查）
    - perform_import 的 SET CONSTRAINTS ALL DEFERRED 真正生效
    - SQLite 不支持也不需要 DEFERRABLE 语义（PRAGMA foreign_keys=OFF 已兜底），
      该方言下迁移直接跳过

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-26 00:00:00.000000

"""
from alembic import op
from sqlalchemy import inspect as sa_inspect, text


# revision identifiers, used by Alembic.
revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def _alter_all_fks(deferrable: bool):
    """枚举全库 FK，逐个 ALTER 为 DEFERRABLE/NOT DEFERRABLE。

    每条 ALTER 独立 try/except，单条失败仅打印 warning 不中断（保证多次执行幂等
    + 兼容 Alembic 自动命名差异 / 历史手工建的约束）。
    """
    bind = op.get_bind()
    insp = sa_inspect(bind)
    clause = 'DEFERRABLE INITIALLY DEFERRED' if deferrable else 'NOT DEFERRABLE'
    failed = []
    altered = 0
    for tname in insp.get_table_names():
        try:
            fks = insp.get_foreign_keys(tname)
        except Exception as e:
            failed.append(f'{tname}: 读外键失败 {e}')
            continue
        for fk in fks:
            name = fk.get('name')
            if not name:
                continue  # 匿名 FK（PG 罕见，给个保险）
            try:
                # 用双引号包名以支持大小写/特殊字符
                bind.execute(text(
                    f'ALTER TABLE "{tname}" ALTER CONSTRAINT "{name}" {clause}'
                ))
                altered += 1
            except Exception as e:
                failed.append(f'{tname}.{name}: {e}')
    if failed:
        # 用 print 写到 alembic 日志（无 logger 上下文）；非致命，仅提示
        print(f'[pg_deferrable_fks] altered={altered}, skipped/failed={len(failed)}')
        for line in failed:
            print(f'  - {line}')


def upgrade():
    if op.get_bind().dialect.name != 'postgresql':
        return  # SQLite 无此概念
    _alter_all_fks(deferrable=True)


def downgrade():
    if op.get_bind().dialect.name != 'postgresql':
        return
    _alter_all_fks(deferrable=False)
