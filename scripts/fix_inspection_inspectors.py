# -*- coding: utf-8 -*-
"""存量巡检记录巡检人员修正：inspector_name 按任务指派工程师刷新。

背景：upload_report_for_task 曾把巡检人员记为「上传者」，管理员代传时
记录显示为管理员而非任务派发的工程师（已修复，仅影响新记录）。
本脚本一次性修正存量记录：
- 仅处理 task_id 有值且任务存在指派工程师的记录
- 手动创建（无 task_id）或任务未指派的记录跳过
- 幂等：inspector_name 已等于指派者姓名的跳过

用法（项目根目录）：
    python scripts/fix_inspection_inspectors.py            # 预览（dry-run）
    python scripts/fix_inspection_inspectors.py --apply    # 实际修正
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models import db, Inspection


def main():
    dry_run = '--apply' not in sys.argv
    app = create_app()
    with app.app_context():
        rows = Inspection.query.filter(Inspection.task_id.isnot(None))\
            .order_by(Inspection.id).all()
        fixed = skipped = 0
        for i in rows:
            task = i.task_rel
            if not task or not task.assigned_to_user_id:
                skipped += 1  # 未关联任务或任务未指派
                continue
            assignee = task.assignee_rel
            if not assignee:
                skipped += 1
                continue
            expect = assignee.realname or assignee.username or ''
            if not expect or i.inspector_name == expect:
                skipped += 1
                continue
            print(f'  [fix] inspection#{i.id} 「{i.title}」 '
                  f'巡检人员: {i.inspector_name or "(空)"} -> {expect}')
            if not dry_run:
                i.inspector_name = expect
                i.inspector = expect
                i.inspector_user_id = task.assigned_to_user_id
                fixed += 1
            else:
                fixed += 1
        if not dry_run:
            db.session.commit()
        print(f'\n共检查 {len(rows)} 条关联任务的巡检记录：修正 {fixed} 条，跳过 {skipped} 条。')
        if dry_run:
            print('以上为预览（未写库）。确认后执行: python scripts/fix_inspection_inspectors.py --apply')


if __name__ == '__main__':
    main()
