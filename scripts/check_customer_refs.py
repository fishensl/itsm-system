# -*- coding: utf-8 -*-
"""客户删除阻塞诊断：定位引用该客户的全部记录（含"幽灵设备"），并可选解除。

典型场景：客户详情显示「设备数 1」但设备管理列表为空 → 删除客户报
「仍有关联设备」。原因可能是 devices 表存在 customer_id 指向该客户的残留行，
或 customers.device_count 冗余快照残留。本脚本两类问题都能定位。

用法（项目根目录）：
    python scripts/check_customer_refs.py <客户ID|客户名称>          # 预览（只读）
    python scripts/check_customer_refs.py 鄱阳湖水文水资源监测中心 --apply \
        --unlink-ghost-devices    # 把幽灵设备 customer_id 置空并重算两客户计数
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models import (db, Customer, Device, Ticket, Inspection, Fault, Topology,
                    Opportunity, Quotation, Contract, Project, SalesOrder,
                    Rack, RackInstall)


def _find_customer(key):
    """按 ID 或名称（精确/模糊）查找客户"""
    if key.isdigit():
        c = Customer.query.get(int(key))
        if c:
            return [c]
    exact = Customer.query.filter_by(name=key).first()
    if exact:
        return [exact]
    fuzzy = Customer.query.filter(Customer.name.contains(key)).order_by(Customer.id).all()
    return fuzzy


def collect_refs(c):
    """收集该客户的全部引用，返回 {'blocking': [...], 'soft': [...], 'ghost_devices': [...]}"""
    blocking = []
    soft = []
    cid = c.id

    devices = Device.query.filter_by(customer_id=cid).all()
    ghost_devices = [d for d in devices]
    if devices:
        blocking.append(f'devices 表 {len(devices)} 台（幽灵设备，设备管理列表通常能查到，'
                        f'可 --unlink-ghost-devices 解除）')

    def _chk(model, label, col='customer_id', **extra):
        q = model.query.filter(getattr(model, col) == cid)
        for k, v in extra.items():
            q = q.filter(getattr(model, k) == v)
        n = q.count()
        if n:
            blocking.append(f'{label}: {n} 条')

    _chk(Opportunity, '商机')
    _chk(Quotation, '报价单')
    _chk(Contract, '合同')
    _chk(Project, '项目')
    _chk(SalesOrder, '备件销售单')
    _chk(Rack, '机柜')
    if RackInstall.query.join(Rack, Rack.id == RackInstall.rack_id)\
            .filter(Rack.customer_id == cid).count():
        blocking.append('上架记录（机柜归属该客户）: 存在')

    # 软引用：删除时会自动置空，不阻塞
    for model, label in [(Ticket, '工单'), (Inspection, '巡检'), (Fault, '故障'),
                         (Topology, '拓扑图')]:
        n = model.query.filter_by(customer_id=cid).count()
        if n:
            soft.append(f'{label}: {n} 条（删除时自动置空，不阻塞）')

    return {'blocking': blocking, 'soft': soft, 'ghost_devices': ghost_devices,
            'device_count_snapshot': c.device_count or 0}


def print_report(c, refs):
    print(f'客户: {c.name} (id={c.id}, level={c.level or "-"}, '
          f'device_count快照={refs["device_count_snapshot"]})')
    print('  [阻塞项]')
    if refs['blocking']:
        for b in refs['blocking']:
            print(f'    X {b}')
    else:
        print('    无（可正常删除）')
    print('  [软引用]')
    for s in refs['soft']:
        print(f'    - {s}')
    if not refs['soft']:
        print('    无')
    if refs['ghost_devices']:
        print('  [幽灵设备明细]')
        for d in refs['ghost_devices']:
            print(f"    - id={d.id} name={d.device_name!r} type={d.device_type or '-'} "
                  f"brand={d.brand or '-'} ip={d.ip_address or '-'} in_use={d.is_in_use}")
    else:
        print('  [幽灵设备明细] 无（device_count 为纯快照残留，点系统概览「修复设备数」即可）')


def unlink_ghost_devices(c, dry_run=True):
    """把幽灵设备 customer_id 置空（不删数据），重算原客户与目标设备新归属（无）计数"""
    devices = Device.query.filter_by(customer_id=c.id).all()
    for d in devices:
        print(f'  [unlink] 设备 id={d.id} 「{d.device_name}」 customer_id: {c.id} -> None')
        if not dry_run:
            d.customer_id = None
    if not dry_run:
        db.session.commit()
        from services.device_service import sync_customer_device_count
        sync_customer_device_count(c.id)
    return len(devices)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    apply_flag = '--apply' in sys.argv
    unlink_flag = '--unlink-ghost-devices' in sys.argv
    if not args:
        print(__doc__)
        sys.exit(1)
    app = create_app()
    with app.app_context():
        cands = _find_customer(args[0])
        if not cands:
            print(f'未找到客户: {args[0]}')
            sys.exit(1)
        if len(cands) > 1:
            print('匹配到多个客户：')
            for c in cands:
                print(f'  id={c.id} name={c.name}')
            print('请用客户 ID 精确指定。')
            sys.exit(1)
        c = cands[0]
        refs = collect_refs(c)
        print_report(c, refs)
        if unlink_flag:
            if not refs['ghost_devices']:
                print('\n无幽灵设备可解除。若仅 device_count 快照残留，'
                      '请调用 POST /api/system/repair-device-counts 或系统概览「修复设备数」。')
            else:
                print(f'\n--- 解除幽灵设备（{"APPLY 写库" if apply_flag else "预览，加 --apply 写库"}）---')
                n = unlink_ghost_devices(c, dry_run=not apply_flag)
                print(f'共解除 {n} 台，客户 device_count 已重算。')
        elif refs['blocking'] and not apply_flag:
            print('\n提示: 阻塞项含 devices 时用 --apply --unlink-ghost-devices 解除；'
                  '其他业务引用需在对应模块处理后重试。'
                  '快照残留可用 POST /api/system/repair-device-counts 一键修复。')


if __name__ == '__main__':
    main()
