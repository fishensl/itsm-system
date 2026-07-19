# -*- coding: utf-8 -*-
"""一次性数据订正：把旧任务标题里「第N季度」(阿拉伯数字) 改为中文写法「第二季度」。

背景：utils/customer_task_generator.py 早期用整数算术拼接季度号，产出「2026年第2季度巡检」，
现已改为中文写法。本脚本回填历史数据，只动 InspectionTask.title，无 schema 变更，故不进 Alembic。

用法（项目根目录）：
    python scripts/fix_quarter_titles.py            # 预览将改动的条数与样例
    python scripts/fix_quarter_titles.py --apply    # 实际写库
"""
import os
import re
import sys

# 让脚本能从项目根目录导入 app / models
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models import db, InspectionTask
from utils.customer_task_generator import QUARTER_CN

app = create_app()

# 第1季度 / 第2季度 ... → 第一季度 / 第二季度 ...
_PATTERN = re.compile(r'第([1-4])季度')


def _convert(title):
    return _PATTERN.sub(lambda m: f'第{QUARTER_CN[int(m.group(1))]}季度', title)


def main(apply=False):
    with app.app_context():
        tasks = (InspectionTask.query
                 .filter(InspectionTask.title.like('%第%季度%'))
                 .all())
        changes = []
        for t in tasks:
            new_title = _convert(t.title)
            if new_title != t.title:
                changes.append((t.id, t.title, new_title))

        print(f'匹配到 {len(tasks)} 条含「第…季度」标题，其中需订正 {len(changes)} 条。')
        for tid, old, new in changes[:20]:
            print(f'  [{tid}] {old}  ->  {new}')
        if len(changes) > 20:
            print(f'  ... 其余 {len(changes) - 20} 条略')

        if not changes:
            print('无需改动。')
            return
        if not apply:
            print('\n这是预览模式。确认无误后加 --apply 实际写库。')
            return

        for tid, old, new in changes:
            t = InspectionTask.query.get(tid)
            t.title = new
        db.session.commit()
        print(f'\n已提交：{len(changes)} 条标题完成订正。')


if __name__ == '__main__':
    main(apply='--apply' in sys.argv)
