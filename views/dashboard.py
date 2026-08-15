# -*- coding: utf-8 -*-
"""首页仪表盘 + 工作台偏好 API（SSR 首页渲染已剥离，GET / 一律 302 → /app/）"""
from flask import request, jsonify, redirect
from flask_login import login_required, current_user
from models import db, Opportunity, UserDashboardPreference
from utils.decorators import api_view
from utils.compat import deprecated_endpoint
from utils.json_fields import dumps_json, parse_json


# ---------- 首页 ----------
@login_required
def index():
    return redirect('/app/')


# ==================== 商机阶段统计 ====================
@login_required
@api_view
@deprecated_endpoint('/api/dashboard/overview')
def api_dashboard_opp_stages():
    """商机阶段统计（销售工作台用）"""
    from sqlalchemy import func
    stages = ['初步接触', '需求确认', '方案报价', '商务谈判', '成交', '失败']
    rows = db.session.query(Opportunity.stage, func.count(Opportunity.id))\
        .group_by(Opportunity.stage).all()
    stat = {s: 0 for s in stages}
    for s, c in rows:
        if s in stat: stat[s] = c
    return jsonify({'success': True, 'labels': list(stat.keys()), 'values': list(stat.values())})

# ==================== 工作台偏好 API ====================
# 卡片池定义（所有可选卡片）
DASHBOARD_CARD_POOL = {
    'customer':      {'label': '客户总数',   'icon': 'bi-people',         'accent': '#2563eb'},
    'device':        {'label': '设备总数',   'icon': 'bi-router',         'accent': '#059669'},
    'device_online': {'label': '在线设备',   'icon': 'bi-check-circle',   'accent': '#16a34a'},
    'inspection':    {'label': '巡检记录',   'icon': 'bi-clipboard-check','accent': '#7c3aed'},
    'ticket':        {'label': '工单总数',   'icon': 'bi-ticket-detailed','accent': '#f59e0b'},
    'kb':            {'label': '知识条目',   'icon': 'bi-book',           'accent': '#0891b2'},
    'spare':         {'label': '备件档案',   'icon': 'bi-archive',        'accent': '#16a34a'},
    'opp':           {'label': '商机跟进',   'icon': 'bi-lightbulb',      'accent': '#475569'},
    'quote':         {'label': '报价单',     'icon': 'bi-file-earmark-text','accent': '#7c3aed'},
    'contract':      {'label': '合同总数',   'icon': 'bi-file-earmark-lock','accent': '#ea580c'},
    'project':       {'label': '项目',       'icon': 'bi-diagram-3',      'accent': '#db2777'},
    'stock_alert':   {'label': '备件预警',   'icon': 'bi-exclamation-diamond','accent': '#ea580c'},
    'expiring':      {'label': '授权到期',   'icon': 'bi-shield-exclamation','accent': '#db2777'},
    'my_tasks':      {'label': '我的待办',   'icon': 'bi-person-check',   'accent': '#2563eb'},
}

ROLE_DEFAULT_CARDS = {
    'admin':    ['customer', 'device', 'inspection', 'ticket', 'kb', 'spare', 'opp', 'contract', 'project'],
    'operator': ['device', 'my_tasks', 'ticket', 'inspection', 'kb', 'stock_alert', 'expiring'],
    'sales':    ['customer', 'opp', 'quote', 'contract', 'project', 'my_tasks', 'spare'],
    'viewer':   ['customer', 'device', 'ticket', 'project', 'inspection', 'kb'],
}

def get_dashboard_cards(user):
    """获取用户生效的卡片列表（偏好或角色默认）"""
    pref = UserDashboardPreference.query.filter_by(user_id=user.id).first()
    if pref and pref.cards_json:
        cards = parse_json(
            pref.cards_json,
            default=[],
            field_name='user_dashboard_preference.cards_json',
        )
        if isinstance(cards, list) and cards:
            return cards
    return ROLE_DEFAULT_CARDS.get(user.role, ['ticket', 'device', 'customer'])

@deprecated_endpoint('/app/')
@login_required
@api_view
def api_dashboard_preferences():
    pref = UserDashboardPreference.query.filter_by(user_id=current_user.id).first()
    cards = get_dashboard_cards(current_user)
    return jsonify({
        'cards': cards,
        'is_custom': pref is not None and pref.cards_json and len(pref.cards_json) > 2,
        'defaults': ROLE_DEFAULT_CARDS.get(current_user.role, []),
        'pool': {k: v for k, v in DASHBOARD_CARD_POOL.items()},
    })

@deprecated_endpoint('/app/')
@login_required
def api_dashboard_preferences_save():
    data = request.get_json(silent=True) or {}
    card_keys = data.get('cards', [])
    # 过滤无效卡片key
    valid = [k for k in card_keys if k in DASHBOARD_CARD_POOL]
    pref = UserDashboardPreference.query.filter_by(user_id=current_user.id).first()
    if not pref:
        pref = UserDashboardPreference(user_id=current_user.id)
        db.session.add(pref)
    pref.cards_json = dumps_json(valid)
    db.session.commit()
    return jsonify({'success': True, 'cards': valid})

@deprecated_endpoint('/app/')
@login_required
def api_dashboard_preferences_reset():
    pref = UserDashboardPreference.query.filter_by(user_id=current_user.id).first()
    if pref:
        db.session.delete(pref)
        db.session.commit()
    cards = ROLE_DEFAULT_CARDS.get(current_user.role, [])
    return jsonify({'success': True, 'cards': cards})
