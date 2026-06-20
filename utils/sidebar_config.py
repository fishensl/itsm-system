# -*- coding: utf-8 -*-
"""
侧栏分组配置（数据化）

每个一级分组是一个 dict：
  key: 唯一 ID（用于存储用户偏好 / 对应 nav group）
  title: 显示名
  icon: Bootstrap Icons 类
  default_order: 默认排序（数字越小越靠前；相同则按定义先后）
  children: 子项 [{name, url, icon, perm}, ...] （用于显示在系统管理页的预览/编辑）

默认顺序（最新要求）：
  工作台 → 运维管理 → 资产管理 → 销售管理 → 客户管理 → 备件管理 → 系统管理
"""
import json
from flask import current_app
from models import db, UserDashboardPreference


# 完整侧栏分组（默认含 7 个）
SIDEBAR_GROUPS = [
    {
        'key': 'workbench',
        'title': '工作台',
        'icon': 'bi-speedometer2',
        'default_order': 10,
        'single_link': {'name': '工作台', 'url': '/', 'icon': 'bi-speedometer2', 'perm': 'dashboard:view'},
    },
    {
        'key': 'ops',
        'title': '运维管理',
        'icon': 'bi-tools',
        'default_order': 20,
        'children': [
            # 主要功能：工单与故障
            {'name': '工单管理', 'url': '/tickets', 'icon': 'bi-ticket-detailed', 'perm': 'ticket:view'},
            {'name': '故障记录', 'url': '/faults', 'icon': 'bi-exclamation-triangle', 'perm': 'fault:view'},
            # 主要功能：巡检链路（派发 → 任务 → 人员 → 记录）
            {'name': '任务派发', 'url': '/task-dispatch', 'icon': 'bi-send', 'perm': 'task:view_dept'},
            {'name': '巡检任务', 'url': '/inspection-tasks', 'icon': 'bi-list-check', 'perm': 'inspection:view'},
            {'name': '巡检人员', 'url': '/inspectors', 'icon': 'bi-person-gear', 'perm': 'inspection:view'},
            {'name': '巡检记录', 'url': '/inspections', 'icon': 'bi-clipboard-data', 'perm': 'inspection:view'},
            # 模板（配置类）
            {'name': '任务模板', 'url': '/task-templates', 'icon': 'bi-file-earmark-text', 'perm': 'inspection:view'},
            {'name': '设备模板', 'url': '/device-check-templates', 'icon': 'bi-gear-wide-connected', 'perm': 'inspection:view'},
            # 报告类放最后
            {'name': '报告管理', 'url': '/reports', 'icon': 'bi-folder2-open', 'perm': 'report:view'},
        ],
    },
    {
        'key': 'kb',
        'title': '知识库',
        'icon': 'bi-book',
        'default_order': 25,  # 介于运维管理和资产管理之间
        'children': [
            # 入口
            {'name': '全部知识', 'url': '/knowledge-base', 'icon': 'bi-journal-text', 'perm': 'kb:view'},
            # 主要使用场景分类
            {'name': '故障处置', 'url': '/knowledge-base?category=故障处置', 'icon': 'bi-tools', 'perm': 'kb:view'},
            {'name': '技术手册', 'url': '/knowledge-base?category=技术手册', 'icon': 'bi-book-half', 'perm': 'kb:view'},
            {'name': '项目经验', 'url': '/knowledge-base?category=项目经验', 'icon': 'bi-folder-check', 'perm': 'kb:view'},
            {'name': '业务经验', 'url': '/knowledge-base?category=业务经验', 'icon': 'bi-briefcase', 'perm': 'kb:view'},
            # 操作放最后
            {'name': '新增知识', 'url': '/knowledge-base/add', 'icon': 'bi-plus-circle', 'perm': 'kb:add'},
        ],
    },
    {
        'key': 'dev',
        'title': '资产管理',
        'icon': 'bi-router',
        'default_order': 30,
        'children': [
            # 核心：设备
            {'name': '设备列表', 'url': '/devices', 'icon': 'bi-hdd-rack', 'perm': 'device:view'},
            # 关联：网络结构
            {'name': '拓扑图', 'url': '/topologies', 'icon': 'bi-diagram-3', 'perm': 'topology:view'},
            # V6.1: 机柜管理
            {'name': '机柜管理', 'url': '/rack', 'icon': 'bi-building', 'perm': 'device:view'},
            # V12: 固件版本库
            {'name': '固件版本库', 'url': '/device-firmwares', 'icon': 'bi-cpu', 'perm': 'device:view'},
            # 字典/配置类放后
            {'name': '设备类型', 'url': '/device-types', 'icon': 'bi-tags', 'perm': 'device:view'},
            {'name': '品牌管理', 'url': '/device-brands', 'icon': 'bi-c-circle', 'perm': 'device:view'},
            {'name': '网络类型', 'url': '/device-network-types', 'icon': 'bi-diagram-2', 'perm': 'device:view'},
            {'name': '自定义字段', 'url': '/device-custom-fields', 'icon': 'bi-columns', 'perm': 'device:view'},
        ],
    },
    {
        'key': 'sales',
        'title': '销售管理',
        'icon': 'bi-graph-up',
        'default_order': 40,
        'children': [
            # 销售链路：线索 → 报价 → 合同 → 项目
            {'name': '商机跟进', 'url': '/opportunities', 'icon': 'bi-lightbulb', 'perm': 'sales:view'},
            {'name': '报价单', 'url': '/quotations', 'icon': 'bi-file-earmark-text', 'perm': 'sales:view'},
            {'name': '合同管理', 'url': '/contracts', 'icon': 'bi-file-earmark-lock', 'perm': 'sales:view'},
            {'name': '项目管理', 'url': '/projects', 'icon': 'bi-folder', 'perm': 'sales:view'},
            # 配置类：合同关联的运维配置（跨域）
            {'name': '合同巡检配置', 'url': '/contract-tasks', 'icon': 'bi-calendar-check', 'perm': 'contract_auto:manage'},
        ],
    },
    {
        'key': 'customer',
        'title': '客户管理',
        'icon': 'bi-people',
        'default_order': 50,  # 在销售管理下、备件管理上
        'children': [
            # 核心
            {'name': '客户列表', 'url': '/customers', 'icon': 'bi-person-lines-fill', 'perm': 'customer:view'},
            # 字典/分类放后
            {'name': '地区管理', 'url': '/regions', 'icon': 'bi-geo-alt', 'perm': 'region:view'},
            {'name': '单位类别', 'url': '/customer-categories', 'icon': 'bi-bookmark-star', 'perm': 'category:view'},
            {'name': '自定义字段', 'url': '/customer-custom-fields', 'icon': 'bi-columns', 'perm': 'customer:view'},
        ],
    },
    {
        'key': 'spare',
        'title': '备件管理',
        'icon': 'bi-boxes',
        'default_order': 60,  # 在客户管理下、系统管理上
        'children': [
            # 核心
            {'name': '备件档案', 'url': '/spare-parts', 'icon': 'bi-archive', 'perm': 'spare:view'},
            # 关联：备件的库存
            {'name': '库存管理', 'url': '/spare-stocks', 'icon': 'bi-layers', 'perm': 'spare:view'},
            # 流程
            {'name': '采购入库', 'url': '/purchase-orders', 'icon': 'bi-dolly', 'perm': 'spare:view'},
            {'name': '销售出库', 'url': '/sales-orders', 'icon': 'bi-truck', 'perm': 'spare:view'},
        ],
    },
    {
        # V6.1: 常用工具 — 网络运维常用计算/解析工具，纯前端实现
        'key': 'tools',
        'title': '常用工具',
        'icon': 'bi-tools',
        'default_order': 65,  # 在备件管理和系统管理之间
        'children': [
            {'name': 'IP地址计算器', 'url': '/tools/ip-calc', 'icon': 'bi-calculator', 'perm': None},
            {'name': '子网划分工具', 'url': '/tools/subnet', 'icon': 'bi-diagram-3', 'perm': None},
            {'name': 'MAC地址工具', 'url': '/tools/mac', 'icon': 'bi-hdd-network', 'perm': None},
            {'name': '进制转换', 'url': '/tools/radix', 'icon': 'bi-123', 'perm': None},
            {'name': '时间戳转换', 'url': '/tools/timestamp', 'icon': 'bi-clock', 'perm': None},
            {'name': 'Base64编解码', 'url': '/tools/base64', 'icon': 'bi-file-earmark-code', 'perm': None},
            {'name': 'MTU计算器', 'url': '/tools/mtu', 'icon': 'bi-rulers', 'perm': None},
            {'name': '带宽计算器', 'url': '/tools/bandwidth', 'icon': 'bi-speedometer', 'perm': None},
            {'name': '报文分析', 'url': '/tools/packet', 'icon': 'bi-search', 'perm': None},
        ],
    },
    {
        'key': 'sys',
        'title': '系统管理',
        'icon': 'bi-gear',
        'default_order': 70,
        'children': [
            # 入口
            {'name': '系统概览', 'url': '/system', 'icon': 'bi-speedometer', 'perm': 'dashboard:view'},
            # 主要功能：账号（用户 → 部门 → 权限 紧邻）
            {'name': '用户管理', 'url': '/users', 'icon': 'bi-people-fill', 'perm': 'user:view'},
            {'name': '部门管理', 'url': '/departments/', 'icon': 'bi-diagram-3', 'perm': 'department:view'},
            {'name': '权限管理', 'url': '/permissions', 'icon': 'bi-shield-lock', 'perm': 'permission:view'},
            # 集成/配置
            {'name': 'AI 对接', 'url': '/ai-config', 'icon': 'bi-robot', 'perm': 'ai:view'},
            # 数据备份/恢复（页面内 admin_required 限制）
            {'name': '数据备份', 'url': '/system/backup', 'icon': 'bi-shield-lock', 'perm': None},
            # 个人化配置放最后
            {'name': '侧栏自定义', 'url': '/system/sidebar', 'icon': 'bi-list-columns-reverse', 'perm': None},
        ],
    },
]


def get_default_groups():
    """返回默认顺序的分组（用于未自定义用户）"""
    return sorted(SIDEBAR_GROUPS, key=lambda g: g['default_order'])


def get_user_sidebar_groups(user):
    """获取用户的侧栏分组（按用户偏好 + 默认）

    返回: 排序后的分组列表；
    每项: { key, title, icon, enabled, children, single_link }
    """
    pref = UserDashboardPreference.query.filter_by(user_id=user.id).first()
    user_layout = None
    if pref and pref.sidebar_json:
        try:
            user_layout = json.loads(pref.sidebar_json)
        except (json.JSONDecodeError, TypeError):
            pass

    # 默认顺序 + 默认全启用
    if not user_layout:
        return [
            {
                'key': g['key'],
                'title': g['title'],
                'icon': g['icon'],
                'enabled': True,
                'single_link': g.get('single_link'),
                'children': g.get('children', []),
            }
            for g in get_default_groups()
        ]

    # 用户自定义：按 user_layout 给定的 keys 顺序遍历 + 标记 enabled
    custom = user_layout.get('groups', [])
    custom_map = {item['key']: item for item in custom}
    # 完整列表：先按用户给定的 key 顺序（如果用户偏好里有），再用默认顺序补齐缺失项
    custom_order = [item['key'] for item in custom if item['key'] in {g['key'] for g in SIDEBAR_GROUPS}]
    default_order = [g['key'] for g in get_default_groups()]
    # 合并：用户顺序在前 + 默认未出现的补后
    merged_order = list(custom_order) + [k for k in default_order if k not in custom_order]

    groups_out = []
    for key in merged_order:
        cfg = next((g for g in SIDEBAR_GROUPS if g['key'] == key), None)
        if not cfg:
            continue
        if key in custom_map:
            enabled = custom_map[key].get('enabled', True)
        else:
            # 新增的分组（系统升级后用户未设置过），默认启用
            enabled = True
        groups_out.append({
            'key': key,
            'title': cfg['title'],
            'icon': cfg['icon'],
            'enabled': enabled,
            'single_link': cfg.get('single_link'),
            'children': cfg.get('children', []),
        })
    return groups_out


def save_user_sidebar(user, groups_data):
    """保存用户侧栏偏好

    groups_data: [{'key': 'ops', 'enabled': True}, ...]
    """
    payload = {'groups': [{'key': g['key'], 'enabled': g.get('enabled', True)} for g in groups_data]}
    pref = UserDashboardPreference.query.filter_by(user_id=user.id).first()
    if not pref:
        pref = UserDashboardPreference(user_id=user.id)
        db.session.add(pref)
    pref.sidebar_json = json.dumps(payload, ensure_ascii=False)
    db.session.commit()
    return True
