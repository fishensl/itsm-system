# -*- coding: utf-8 -*-
"""知识库发布状态修复：is_published 为 NULL 的存量记录置为已发布。

背景：is_published 列初始 schema 为 nullable=True，存量知识该字段为 NULL，
Vue 列表把 NULL 判为「未发布」→ 全部显示灰色。模型 default=True 语义是
「默认发布」，此处将存量 NULL 补齐为 1（幂等，重跑无副作用）。

用法（项目根目录）：
    python scripts/fix_kb_published.py            # 预览（dry-run，不写库）
    python scripts/fix_kb_published.py --apply    # 实际修复
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models import db, KnowledgeBase


def main():
    dry_run = '--apply' not in sys.argv
    app = create_app()
    with app.app_context():
        null_rows = KnowledgeBase.query.filter(KnowledgeBase.is_published.is_(None))\
            .order_by(KnowledgeBase.id).all()
        total = KnowledgeBase.query.count()
        print(f'knowledge_base 总数: {total}，is_published 为 NULL: {len(null_rows)}')
        if not null_rows:
            print('无需修复。')
            return
        for k in null_rows:
            print(f"  [{'preview' if dry_run else 'fix'}] kb#{k.id} 「{k.title[:40]}」 NULL -> 已发布")
        if dry_run:
            print('\n以上为预览（未写库）。确认后执行: python scripts/fix_kb_published.py --apply')
        else:
            KnowledgeBase.query.filter(KnowledgeBase.is_published.is_(None))\
                .update({'is_published': True}, synchronize_session=False)
            db.session.commit()
            print(f'\n已将 {len(null_rows)} 条存量知识置为已发布。')


if __name__ == '__main__':
    main()
