# -*- coding: utf-8 -*-
"""故障分类三级体系种子（九大分类）——幂等播种 fault_types 三级树。

用法：
    python scripts/seed_fault_categories.py            # 预览
    python scripts/seed_fault_categories.py --apply    # 执行
    python scripts/seed_fault_categories.py --apply --force-update   # 执行并强制更新已有分类的 level

启动时 init_db 已调用 seed_fault_categories(app)（见 app.py），本脚本供部署后单独补种。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 三级分类树：一级 → {二级: [三级, ...]}
FAULT_CATEGORY_TREE = {
    '一、网络与通信故障': {
        '内网故障': ['单个电脑无法访问内网', '部分电脑无法访问内网', '所有电脑无法访问内网',
                   'DNS/DHCP服务', '内网设备故障', '内网专线/广域网', 'VPN接入（内网）'],
        '互联网故障': ['单个电脑无法上网', '部分电脑无法上网', '所有电脑无法上网',
                    'DNS/DHCP服务', '上网行为管理', '互联网设备故障', '互联网专线'],
        '政务网故障': ['单个电脑无法访问政务网', '部分电脑无法访问政务网', '所有电脑无法访问政务网',
                     'DNS/DHCP服务', '政务网设备故障', '政务网专线', 'VPN接入（政务网）'],
    },
    '二、服务器故障': {
        '物理服务器硬件': ['开机与电源', '面板告警', '部件故障'],
        '存储系统': ['磁盘阵列', 'SAN/NAS', '容量与寿命'],
        '虚拟化平台': ['宿主机', '虚拟机', '资源池'],
        '操作系统': ['Windows Server'],
    },
    '三、业务应用系统故障': {
        '网页无法打开': ['浏览器报错', '白屏/无内容', '外网/门户'],
        '应用无法登录': ['登录交互', '系统级限制'],
        '页面显示或查询异常': ['数据展示', '页面样式'],
        '数据库相关错误': ['操作报错'],
        '其他业务问题': ['流程中断'],
    },
    '四、桌面终端及外设故障': {
        '非国产化终端': ['硬件故障', 'Windows操作系统', '办公软件', '杀毒软件与病毒处置',
                       '外设-打印机/多功能一体机', '外设-显示器', '外设-输入设备',
                       '外设-其他', '电话终端'],
        '国产化终端': ['硬件故障', '统信UOS系统', '麒麟V10系统', '国产办公软件',
                     '杀毒软件与病毒处置', '外设驱动与识别', '兼容性问题'],
    },
    '五、会议及音视频系统故障': {
        'LED大屏': ['黑屏/断电', '显示异常', '控制与接收'],
        '投影/商用电视': ['投影仪', '电视/大屏显示器'],
        '音频系统': ['麦克风', '功放/音箱', '调音台/处理器'],
        '视频会议': ['平台端', '硬件终端', '音视频质量'],
        '投屏协作': ['无线投屏', '有线投屏'],
        '中控与周边': ['集中控制'],
    },
    '六、网络安全与策略故障': {
        '策略误拦': ['外网访问', '内网访问'],
        '终端安全': ['防病毒', '准入控制'],
        '安全事件': ['告警处理'],
    },
    '七、机房动力与环境故障': {
        '供配电': ['UPS', '配电柜/PDU'],
        '空调制冷': ['精密空调'],
        '动环监控': ['传感器', '门禁/视频'],
    },
    '八、账号权限与访问控制故障': {
        '账号管理': ['锁定/过期', '生命周期'],
        '权限申请': ['文件夹/打印', '业务系统'],
    },
    '九、监控系统故障': {
        '摄像头故障': ['单个摄像头无画面（黑屏）', '画面模糊/不清晰', '夜视功能失效',
                      '云台无法转动/控制', '摄像头频繁掉线/重启', '图像偏色/条纹干扰'],
        '录像与存储': ['NVR/DVR无法开机', '硬盘故障/录像丢失', '录像无法回放/搜索',
                      '硬盘满不覆盖', '时间不同步'],
        '监控平台/客户端': ['监控软件无法登录', '实时预览卡顿/延迟', '录像下载失败',
                         '报警联动不生效', '权限不足'],
        '显示与解码': ['解码器无输出', '监控大屏/监视器黑屏', '画面分割异常', '拼接屏拼缝错位'],
    },
}


def seed_fault_categories(app=None, force_update=False):
    """幂等播种 fault_types 三级树（按 name+parent 查重，已存在则跳过/更新 level）。

    :param app: Flask app（提供 app_context）；None 时用脚本自身 init。
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

    if app is not None:
        ctx = app.app_context()
    else:
        ctx = None
    try:
        if ctx:
            ctx.push()
        # 一级（保留原 8 个扁平默认类型下的"其他"语义：旧 8 个一级不作为子级）
        for i, (l1, l2_map) in enumerate(FAULT_CATEGORY_TREE.items()):
            n1 = _get_or_create(l1, None, 1, i)
            for j, (l2, l3_list) in enumerate(l2_map.items()):
                n2 = _get_or_create(l2, n1.id, 2, j)
                for k, l3 in enumerate(l3_list):
                    _get_or_create(l3, n2.id, 3, k)
    finally:
        if ctx:
            ctx.pop()
    return created


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='播种故障分类三级体系（九大类）')
    parser.add_argument('--apply', action='store_true', help='执行（默认仅预览）')
    parser.add_argument('--force-update', action='store_true', help='强制修正已有分类层级')
    args = parser.parse_args()

    from app import create_app
    from models import db, FaultType

    app = create_app()
    with app.app_context():
        before = FaultType.query.count()
        n = seed_fault_categories(app, force_update=args.force_update)
        after = FaultType.query.count()
        print(f'故障分类：新增 {n} 条，当前共 {after} 条（前 {before} → 后 {after}）')
        if args.apply:
            db.session.commit()
            print('已落库。')
        else:
            db.session.rollback()
            if n > 0:
                print('预览模式：未落库。加 --apply 执行。')
            else:
                print('无需变更（分类已存在）。')
