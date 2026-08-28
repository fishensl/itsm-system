# -*- coding: utf-8 -*-
"""客户层级关系预演/应用脚本（默认只读）。

用法：
    python scripts/normalize_customer_hierarchy.py
    python scripts/normalize_customer_hierarchy.py --relation "子单位=上级单位"
    python scripts/normalize_customer_hierarchy.py --apply

脚本只连接已经存在且名称唯一的客户，不创建客户、不按地区猜上级。 ``--apply``
必须显式给出，且所有关系先通过自指/循环校验后才在一个事务中提交。
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models import AuditLog, Customer, db


DEFAULT_RELATIONS = (
    ('进贤大队', '鄱阳湖水文水资源监测中心'),
    ('外洲大队', '鄱阳湖水文水资源监测中心'),
    ('庐山大队', '鄱阳湖水文水资源监测中心'),
    ('万家埠水文站', '鄱阳湖水文水资源监测中心'),
    ('李家渡水文站', '鄱阳湖水文水资源监测中心'),
    ('鄱阳湖大队', '鄱阳湖水文水资源监测中心'),
    ('鄱阳湖大队都昌站', '鄱阳湖水文水资源监测中心'),
    # 只有总客户已由业务明确建档时才会挂接；不存在时只报告 unresolved。
    ('江西省水利科学院共青城基地', '江西省水利科学院'),
)


def _parse_relation(value):
    if '=' not in value:
        raise argparse.ArgumentTypeError('关系格式必须为 子单位=上级单位')
    child, parent = (part.strip() for part in value.split('=', 1))
    if not child or not parent:
        raise argparse.ArgumentTypeError('子单位和上级单位都不能为空')
    return child, parent


def _would_cycle(child, parent, proposed):
    cursor_id = parent.id
    seen = set()
    while cursor_id and cursor_id not in seen:
        if cursor_id == child.id:
            return True
        seen.add(cursor_id)
        cursor = db.session.get(Customer, cursor_id)
        if not cursor:
            return False
        cursor_id = proposed.get(cursor.id, cursor.parent_id)
    return False


def main(argv=None):
    parser = argparse.ArgumentParser(description='客户层级预演/应用')
    parser.add_argument('--apply', action='store_true', help='实际写入；默认只预演')
    parser.add_argument('--relation', action='append', type=_parse_relation, default=[],
                        metavar='子单位=上级单位', help='追加或覆盖一条明确关系')
    args = parser.parse_args(argv)
    relations = list(DEFAULT_RELATIONS) + list(args.relation)
    # 同一子单位的显式参数覆盖默认关系。
    relations = list({child: parent for child, parent in relations}.items())

    app = create_app()
    with app.app_context():
        customers = Customer.query.order_by(Customer.id).all()
        by_name = {}
        for item in customers:
            by_name.setdefault(item.name, []).append(item)
        proposed = {}
        changes = []
        unresolved = []
        for child_name, parent_name in relations:
            children = by_name.get(child_name, [])
            parents = by_name.get(parent_name, [])
            if len(children) != 1 or len(parents) != 1:
                reasons = []
                if len(children) != 1:
                    reasons.append(f'子单位记录数={len(children)}')
                if len(parents) != 1:
                    reasons.append(f'上级单位记录数={len(parents)}')
                unresolved.append((child_name, parent_name, '，'.join(reasons)))
                continue
            child, parent = children[0], parents[0]
            if child.id == parent.id:
                unresolved.append((child_name, parent_name, '不能自指'))
                continue
            proposed[child.id] = parent.id
            if _would_cycle(child, parent, proposed):
                unresolved.append((child_name, parent_name, '会形成循环层级'))
                proposed.pop(child.id, None)
                continue
            if child.parent_id != parent.id:
                old_parent = db.session.get(Customer, child.parent_id) if child.parent_id else None
                changes.append((child, parent, old_parent))

        print(f'客户总数: {len(customers)}；拟调整: {len(changes)}；无法解析: {len(unresolved)}')
        for child, parent, old_parent in changes:
            print(f'  [change] {child.name}: {old_parent.name if old_parent else "(无)"} -> {parent.name}')
        for child_name, parent_name, reason in unresolved:
            print(f'  [unresolved] {child_name} -> {parent_name}: {reason}')

        if not args.apply:
            db.session.rollback()
            print('\n以上为只读预演；确认关系后再使用 --apply。')
            return 0
        if unresolved:
            db.session.rollback()
            print('\n存在无法解析关系，已拒绝写入。请先补齐或用 --relation 修正。')
            return 2
        for child, parent, old_parent in changes:
            child.parent_id = parent.id
            db.session.add(AuditLog(
                username='normalize_customer_hierarchy.py',
                action='customer:hierarchy-normalize', target_type='customer',
                target_id=child.id,
                detail=f'上级单位: {old_parent.name if old_parent else "(无)"} -> {parent.name}',
                ip='local-script'))
        db.session.commit()
        print(f'\n已提交 {len(changes)} 条客户层级调整。')
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
