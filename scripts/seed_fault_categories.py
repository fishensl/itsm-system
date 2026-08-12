# -*- coding: utf-8 -*-
"""故障分类三级体系（九大分类）——幂等播种 + 历史数据清理。

- FAULT_CATEGORY_TREE：一级无序号前缀（网络与通信故障/服务器故障/.../监控系统故障），
  VPN接入故障为网络分类下的独立二级（与内网/互联网/政务网平级）
- clean_fault_categories()：幂等清理历史数据——
    ① 带序号前缀的一级改名（同步 faults/tickets 的 fault_category_level1 字符串）
    ② 删除旧 8 个扁平一级（网络中断/设备故障/...），先置空 tickets.fault_category_id 外键
    ③ 删除旧 VPN 三级（VPN接入（内网）/VPN接入（政务网）），三级分类迁至独立二级
- seed_fault_categories()：幂等播种三级树（函数不自建 app context，由调用方在 app_context 内调用）

用法：
    python scripts/seed_fault_categories.py            # 预览
    python scripts/seed_fault_categories.py --apply    # 清理 + 播种
    python scripts/seed_fault_categories.py --apply --force-update   # 强制修正已有分类层级
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 三级分类树：一级 → {二级: [三级, ...]}（一级不带序号前缀）
FAULT_CATEGORY_TREE = {
    '网络与通信故障': {
        '内网故障': ['单个电脑无法访问内网', '部分电脑无法访问内网', '所有电脑无法访问内网',
                   'DNS/DHCP服务', '内网设备故障', '内网专线/广域网'],
        '互联网故障': ['单个电脑无法上网', '部分电脑无法上网', '所有电脑无法上网',
                    'DNS/DHCP服务', '上网行为管理', '互联网设备故障', '互联网专线'],
        '政务网故障': ['单个电脑无法访问政务网', '部分电脑无法访问政务网', '所有电脑无法访问政务网',
                     'DNS/DHCP服务', '政务网设备故障', '政务网专线'],
        # VPN 与内网/互联网/政务网平级（独立二级）
        'VPN接入故障': ['SSL VPN客户端连接报错', '登录后无法访问内网资源', '虚拟IP冲突',
                      '隧道建立后无流量', '政务网VPN隧道断开', '加密证书过期', '政务移动端VPN接入失败'],
    },
    '服务器故障': {
        '物理服务器硬件': ['开机与电源', '面板告警', '部件故障'],
        '存储系统': ['磁盘阵列', 'SAN/NAS', '容量与寿命'],
        '虚拟化平台': ['宿主机', '虚拟机', '资源池'],
        '操作系统': ['Windows Server'],
    },
    '业务应用系统故障': {
        '网页无法打开': ['浏览器报错', '白屏/无内容', '外网/门户'],
        '应用无法登录': ['登录交互', '系统级限制'],
        '页面显示或查询异常': ['数据展示', '页面样式'],
        '数据库相关错误': ['操作报错'],
        '其他业务问题': ['流程中断'],
    },
    '桌面终端及外设故障': {
        '非国产化终端': ['硬件故障', 'Windows操作系统', '办公软件', '杀毒软件与病毒处置',
                       '外设-打印机/多功能一体机', '外设-显示器', '外设-输入设备',
                       '外设-其他', '电话终端'],
        '国产化终端': ['硬件故障', '统信UOS系统', '麒麟V10系统', '国产办公软件',
                     '杀毒软件与病毒处置', '外设驱动与识别', '兼容性问题'],
    },
    '会议及音视频系统故障': {
        'LED大屏': ['黑屏/断电', '显示异常', '控制与接收'],
        '投影/商用电视': ['投影仪', '电视/大屏显示器'],
        '音频系统': ['麦克风', '功放/音箱', '调音台/处理器'],
        '视频会议': ['平台端', '硬件终端', '音视频质量'],
        '投屏协作': ['无线投屏', '有线投屏'],
        '中控与周边': ['集中控制'],
    },
    '网络安全与策略故障': {
        '策略误拦': ['外网访问', '内网访问'],
        '终端安全': ['防病毒', '准入控制'],
        '安全事件': ['告警处理'],
    },
    '机房动力与环境故障': {
        '供配电': ['UPS', '配电柜/PDU'],
        '空调制冷': ['精密空调'],
        '动环监控': ['传感器', '门禁/视频'],
    },
    '账号权限与访问故障': {
        '账号管理': ['锁定/过期', '生命周期'],
        '权限申请': ['文件夹/打印', '业务系统'],
    },
    '监控系统故障': {
        '摄像头故障': ['单个摄像头无画面（黑屏）', '画面模糊/不清晰', '夜视功能失效',
                      '云台无法转动/控制', '摄像头频繁掉线/重启', '图像偏色/条纹干扰'],
        '录像与存储': ['NVR/DVR无法开机', '硬盘故障/录像丢失', '录像无法回放/搜索',
                      '硬盘满不覆盖', '时间不同步'],
        '监控平台/客户端': ['监控软件无法登录', '实时预览卡顿/延迟', '录像下载失败',
                         '报警联动不生效', '权限不足'],
        '显示与解码': ['解码器无输出', '监控大屏/监视器黑屏', '画面分割异常', '拼接屏拼缝错位'],
    },
}

# 旧一级 → 新一级 改名映射（去掉序号前缀；"八"按业务确认改名）
L1_RENAME_MAP = {
    '一、网络与通信故障': '网络与通信故障',
    '二、服务器故障': '服务器故障',
    '三、业务应用系统故障': '业务应用系统故障',
    '四、桌面终端及外设故障': '桌面终端及外设故障',
    '五、会议及音视频系统故障': '会议及音视频系统故障',
    '六、网络安全与策略故障': '网络安全与策略故障',
    '七、机房动力与环境故障': '机房动力与环境故障',
    '八、账号权限与访问控制故障': '账号权限与访问故障',
    '九、监控系统故障': '监控系统故障',
}

# 历史遗留的旧扁平一级类型（app.py 旧种子遗留），清理删除
OLD_FLAT_L1 = ['网络中断', '设备故障', '安全事件', '链路故障', '电源故障', '配置错误', '性能问题', '其他']

# 旧 VPN 三级（挂在 内网故障/政务网故障 二级下），VPN 升级为独立二级后删除
OLD_VPN_L3 = ['VPN接入（内网）', 'VPN接入（政务网）']


def clean_fault_categories():
    """幂等清理历史分类数据（在调用方 app_context 内执行）。

    ① 带序号前缀的一级改名 + 同步 faults/tickets 的 fault_category_level1 字符串
    ② 置空 tickets.fault_category_id 指向旧扁平/VPN 类型的值（PG FK 前置空）
    ③ 删除旧 VPN 三级（level3 字符串引用一并置空）
    ④ 删除旧 8 个扁平一级（有子级的跳过保留，level1 字符串引用置空）
    :return: (renamed_l1, deleted_flat, deleted_vpn)
    """
    from models import db, FaultType, Fault, Ticket

    renamed, deleted_flat, deleted_vpn = 0, 0, 0

    # ① 一级改名 + 字符串同步
    for old, new in L1_RENAME_MAP.items():
        node = FaultType.query.filter_by(name=old, parent_id=None).first()
        if node and not FaultType.query.filter_by(name=new, parent_id=None).first():
            node.name = new
            db.session.flush()
            renamed += 1
        Fault.query.filter(Fault.fault_category_level1 == old) \
            .update({'fault_category_level1': new}, synchronize_session=False)
        Ticket.query.filter(Ticket.fault_category_level1 == old) \
            .update({'fault_category_level1': new}, synchronize_session=False)

    # ② 置空 fault_category_id 外键（旧扁平 + 旧 VPN 三级）
    old_ids = [t.id for t in FaultType.query
               .filter(FaultType.parent_id.is_(None), FaultType.name.in_(OLD_FLAT_L1)).all()]
    vpn_ids = [t.id for t in FaultType.query
               .filter(FaultType.level == 3, FaultType.name.in_(OLD_VPN_L3)).all()]
    stale_ids = set(old_ids) | set(vpn_ids)
    if stale_ids:
        Ticket.query.filter(Ticket.fault_category_id.in_(stale_ids)) \
            .update({'fault_category_id': None}, synchronize_session=False)

    # ③ 旧 VPN 三级：level3 字符串置空 + 删除记录
    if OLD_VPN_L3:
        Fault.query.filter(Fault.fault_category_level3.in_(OLD_VPN_L3)) \
            .update({'fault_category_level3': ''}, synchronize_session=False)
        Ticket.query.filter(Ticket.fault_category_level3.in_(OLD_VPN_L3)) \
            .update({'fault_category_level3': ''}, synchronize_session=False)
    for name in OLD_VPN_L3:
        for node in FaultType.query.filter_by(name=name, level=3).all():
            db.session.delete(node)
            deleted_vpn += 1

    # ④ 旧扁平一级：level1 字符串置空 + 删除（有子级跳过）
    Fault.query.filter(Fault.fault_category_level1.in_(OLD_FLAT_L1)) \
        .update({'fault_category_level1': ''}, synchronize_session=False)
    Ticket.query.filter(Ticket.fault_category_level1.in_(OLD_FLAT_L1)) \
        .update({'fault_category_level1': ''}, synchronize_session=False)
    for name in OLD_FLAT_L1:
        node = FaultType.query.filter_by(name=name, parent_id=None).first()
        if not node:
            continue
        if FaultType.query.filter_by(parent_id=node.id).first():
            continue  # 有子级（历史挂载过二级），保留不动
        db.session.delete(node)
        deleted_flat += 1

    return renamed, deleted_flat, deleted_vpn


def seed_fault_categories(app=None, force_update=False):
    """幂等播种 fault_types 三级树（按 name+parent 查重，已存在则跳过/更新 level）。

    注意：函数不自行创建 app context——由调用方在 app_context 内调用
    （自建 context 会因 Flask-SQLAlchemy 的 session 绑定 context 栈导致
    种子写在独立 session 上、随 context pop 丢失）。
    :param force_update: 已存在分类的 level/parent_id 不一致时强制修正。
    :return: 新增数量（不提交——由调用方决定 commit/rollback）
    """
    from models import db, FaultType

    created = 0

    def _get_or_create(name, parent_id, level, order):
        nonlocal created
        ft = FaultType.query.filter_by(name=name, parent_id=parent_id).first()
        if ft:
            if force_update:
                changed = False
                if ft.level != level:
                    ft.level = level
                    changed = True
                if parent_id is not None and ft.parent_id != parent_id:
                    ft.parent_id = parent_id
                    changed = True
                if changed:
                    db.session.flush()
            return ft
        ft = FaultType(name=name, parent_id=parent_id, level=level, sort_order=order)
        db.session.add(ft)
        db.session.flush()
        created += 1
        return ft

    for i, (l1, l2_map) in enumerate(FAULT_CATEGORY_TREE.items()):
        n1 = _get_or_create(l1, None, 1, i)
        for j, (l2, l3_list) in enumerate(l2_map.items()):
            n2 = _get_or_create(l2, n1.id, 2, j)
            for k, l3 in enumerate(l3_list):
                _get_or_create(l3, n2.id, 3, k)
    return created


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='清理并播种故障分类三级体系（九大类）')
    parser.add_argument('--apply', action='store_true', help='执行（默认仅预览）')
    parser.add_argument('--force-update', action='store_true', help='强制修正已有分类层级')
    args = parser.parse_args()

    from app import create_app
    from models import db, FaultType

    app = create_app()
    with app.app_context():
        before = FaultType.query.count()
        renamed, deleted_flat, deleted_vpn = clean_fault_categories()
        n = seed_fault_categories(app, force_update=args.force_update)
        after = FaultType.query.count()
        print(f'清理：一级改名 {renamed}，删旧扁平 {deleted_flat}，删旧VPN三级 {deleted_vpn}')
        print(f'播种：新增 {n} 条，当前共 {after} 条（前 {before} → 后 {after}）')
        if args.apply:
            db.session.commit()
            print('已落库。')
        else:
            db.session.rollback()
            if renamed or deleted_flat or deleted_vpn or n > 0:
                print('预览模式：未落库。加 --apply 执行。')
            else:
                print('无需变更（分类已清理并存在）。')
