# -*- coding: utf-8 -*-
"""首页仪表盘 + 工作台偏好 API"""
import json
from datetime import date, timedelta
from flask import (render_template, request, jsonify)
from flask_login import (login_required, current_user)
from models import db, User, Customer, Device, Inspection, Fault, Inspector
from models import Region, Ticket, KnowledgeBase, InspectionTask
from models import SparePart, SpareStock
from models import Opportunity, Quotation, Contract, Project
from models import Department, FormDraft, UserDashboardPreference
from utils.permission import is_supervisor
from utils.decorators import api_view


# ---------- 首页 ----------
@login_required
def index():
    from sqlalchemy import func, or_

    # 强制刷新缓存，确保统计为最新
    db.session.expire_all()

    me = current_user
    role = me.role or 'viewer'
    me_realname = me.realname or me.username

    # ---- 各模块计数 ----
    counts = {
        'customer': Customer.query.count(),
        'device': Device.query.count(),
        'device_in_use': Device.query.filter_by(is_in_use=True).count(),
        'inspection': Inspection.query.count(),
        'inspection_task': InspectionTask.query.count(),
        'inspection_pending': InspectionTask.query.filter(InspectionTask.status.in_(['待执行', '执行中'])).count(),
        'fault': Fault.query.count(),
        'fault_pending': Fault.query.filter(Fault.result != '已解决').count(),
        'ticket': Ticket.query.count(),
        'ticket_pending': Ticket.query.filter(~Ticket.status.in_(['已验收', '已关闭'])).count(),
        'kb': KnowledgeBase.query.count(),
        'spare': SparePart.query.count(),
        'region': Region.query.count(),
        'opp': Opportunity.query.count(),
        'opp_deal': Opportunity.query.filter_by(stage='成交').count(),
        'quote': Quotation.query.count(),
        'contract': Contract.query.count(),
        'project': Project.query.count(),
        'project_active': Project.query.filter_by(status='进行中').count(),
    }

    # 库存预警：用单次聚合查询替换逐项 N+1
    stock_total = db.session.query(
        SparePart.id, SparePart.min_stock,
        func.coalesce(func.sum(SpareStock.quantity), 0)
    ).outerjoin(SpareStock, SpareStock.spare_part_id == SparePart.id
    ).group_by(SparePart.id).all()
    counts['stock_alerts'] = sum(
        1 for _spid, min_s, qty in stock_total if (min_s or 0) > 0 and qty < min_s
    )

    # 客户名映射：先收集各查询涉及的 customer_id，再一次 IN 加载（替代全表 Customer.query.all()）
    _needed_cids = set()

    # ---- 即将到期授权（仅 admin / operator 可看）----
    today = date.today()
    deadline = today + timedelta(days=30)
    expiring_devices = []
    if role in ('admin', 'operator', 'viewer'):
        expiring_devices = Device.query.filter(
            Device.license_expiry.isnot(None),
            Device.license_expiry <= deadline
        ).order_by(Device.license_expiry).limit(8).all()
        _needed_cids.update(d.customer_id for d in expiring_devices if d.customer_id)

    # ---- 我的待处理任务（先取实体，客户名映射构建后再组装展示字典） ----
    my_tasks = []
    my_tickets = []
    my_insp_tasks = []
    my_faults = []
    my_opps = []
    my_contracts = []

    if role in ('admin', 'operator'):
        my_tickets = Ticket.query.filter(
            Ticket.assigned_to.in_([me_realname, me.username]),
            ~Ticket.status.in_(['已验收', '已关闭'])
        ).order_by(Ticket.created_at.desc()).limit(8).all()

        # 巡检任务：通过关联 user_id 查 Inspector（V13 后 name 是 property 不是列，不能 filter_by(name=)）
        insp = Inspector.query.filter_by(user_id=me.id).first()
        my_iid = str(insp.id) if insp else None
        if my_iid:
            # 性能：逗号包裹匹配下推 SQL（,ids, LIKE '%,iid,%'，防 id 12 误匹配 123），
            # 替代先取 50 条再 Python split 过滤的做法
            from sqlalchemy import literal
            haystack = literal(',') + func.coalesce(InspectionTask.inspector_ids, '') + literal(',')
            my_insp_tasks = InspectionTask.query.filter(
                haystack.like(f'%,{my_iid},%'),
                InspectionTask.status.in_(['待执行', '执行中'])
            ).order_by(InspectionTask.id.desc()).limit(5).all()

        # 待处理故障
        my_faults = Fault.query.filter(Fault.result != '已解决').order_by(Fault.fault_time.desc()).limit(5).all()

        for coll in (my_tickets, my_insp_tasks, my_faults):
            _needed_cids.update(x.customer_id for x in coll if x.customer_id)

    elif role == 'sales':
        # 销售看待处理商机
        my_opps = Opportunity.query.filter(
            Opportunity.owner.in_([me_realname, me.username]),
            ~Opportunity.stage.in_(['成交', '失败'])
        ).order_by(Opportunity.expected_close_date.asc().nullslast()).limit(8).all()
        # 销售也看进行中合同
        my_contracts = Contract.query.filter(Contract.status == '执行中').order_by(Contract.end_date.asc().nullslast()).limit(5).all()
        for coll in (my_opps, my_contracts):
            _needed_cids.update(x.customer_id for x in coll if x.customer_id)

    # 最近巡检
    recent_inspections = []
    if role in ('admin', 'operator', 'viewer'):
        recent_inspections = Inspection.query.order_by(Inspection.id.desc()).limit(5).all()
        _needed_cids.update(i.customer_id for i in recent_inspections if i.customer_id)

    # ---- 客户名映射一次加载 + 组装展示字典 ----
    customer_map = ({c.id: c.name for c in Customer.query.filter(Customer.id.in_(_needed_cids)).all()}
                    if _needed_cids else {})

    expiring_devices_data = [{
        'id': d.id, 'device_name': d.device_name,
        'customer_name': customer_map.get(d.customer_id, '-'),
        'license_expiry': d.license_expiry.strftime('%Y-%m-%d') if d.license_expiry else '',
        'remaining_days': (d.license_expiry - today).days if d.license_expiry else 0,
    } for d in expiring_devices]

    for t in my_tickets:
        my_tasks.append({
            'type_label': '工单', 'type_color': 'danger',
            'title': t.title,
            'sub': f"{customer_map.get(t.customer_id, '-')} · {t.priority} · {t.status}",
            'url': f"/tickets/{t.id}",
            'time': t.created_at.strftime('%m-%d %H:%M') if t.created_at else '',
        })
    for t in my_insp_tasks:
        my_tasks.append({
            'type_label': '巡检', 'type_color': 'primary',
            'title': t.title,
            'sub': f"{customer_map.get(t.customer_id, '-')} · {t.status} · {t.task_type}",
            'url': f"/task-schedule/{t.id}",
            'time': (t.planned_start.strftime('%m-%d') if t.planned_start else '') + '~' + (t.planned_end.strftime('%m-%d') if t.planned_end else ''),
        })
    for f in my_faults:
        my_tasks.append({
            'type_label': '故障', 'type_color': 'warning',
            'title': f.title,
            'sub': f"{customer_map.get(f.customer_id, '-')} · {f.fault_type or '-'}",
            'url': f"/faults/{f.id}",
            'time': f.fault_time.strftime('%m-%d %H:%M') if f.fault_time else '',
        })
    for o in my_opps:
        my_tasks.append({
            'type_label': '商机', 'type_color': 'primary',
            'title': o.title,
            'sub': f"{customer_map.get(o.customer_id, '-')} · {o.stage} · {o.expected_amount or 0}",
            'url': "/opportunities",
            'time': o.expected_close_date.strftime('%Y-%m-%d') if o.expected_close_date else '-',
        })
    for c in my_contracts:
        my_tasks.append({
            'type_label': '合同', 'type_color': 'success',
            'title': c.title,
            'sub': f"{customer_map.get(c.customer_id, '-')} · {c.amount or 0}",
            'url': "/contracts",
            'time': c.end_date.strftime('%Y-%m-%d') if c.end_date else '-',
        })

    my_tasks = my_tasks[:8]

    recent_inspections_data = [{
        'id': i.id, 'title': i.title,
        'customer_name': customer_map.get(i.customer_id, '-'),
        'inspection_date': i.inspection_date.strftime('%Y-%m-%d') if i.inspection_date else '',
        'overall_status': i.overall_status,
    } for i in recent_inspections]

    # 设备类型分布
    device_type_stats = []
    if role in ('admin', 'operator', 'viewer'):
        device_type_stats = db.session.query(
            Device.device_type, func.count(Device.id)
        ).group_by(Device.device_type).order_by(func.count(Device.id).desc()).all()

    # ---- 按角色组装统计卡片（从用户偏好或角色默认读取）----
    def card(label, value, sub, icon, accent):
        return {'label': label, 'value': value, 'sub': sub, 'icon': icon, 'accent': accent}

    # 合并故障+工单统计
    ticket_total = counts['ticket'] + counts['fault']
    ticket_pending_total = counts['ticket_pending'] + counts['fault_pending']

    # 卡片数据工厂
    CARD_VALUES = {
        'customer':      lambda: card('客户总数', counts['customer'], f"{counts['region']} 个地区", 'bi-people', '#2563eb'),
        'device':        lambda: card('设备总数', counts['device'], f"在用 {counts['device_in_use']}", 'bi-router', '#059669'),
        'device_online': lambda: card('在线设备', counts['device_in_use'], '可正常通讯', 'bi-check-circle', '#16a34a'),
        'inspection':    lambda: card('巡检记录', counts['inspection'], f"{counts['inspection_pending']} 个待执行任务" if role in ('admin','operator') else f"任务 {counts['inspection_task']}", 'bi-clipboard-check', '#7c3aed'),
        'ticket':        lambda: card('工单总数', ticket_total, f"{ticket_pending_total} 待处理（含遗留故障）", 'bi-ticket-detailed', '#f59e0b'),
        'kb':            lambda: card('知识条目', counts['kb'], '故障案例与手册' if role in ('admin','viewer') else '快速查询', 'bi-book', '#0891b2'),
        'spare':         lambda: card('备件档案' if role!='operator' else '备件预警', counts['spare'] if role!='operator' else counts['stock_alerts'], f"{counts['stock_alerts']} 库存预警" if role!='operator' else f"备件 {counts['spare']} 项", 'bi-archive', '#16a34a' if role!='operator' else '#ea580c'),
        'opp':           lambda: card('商机跟进', counts['opp'], f"{counts['opp_deal']} 成交", 'bi-lightbulb', '#475569'),
        'quote':         lambda: card('报价单', counts['quote'], '草稿/已发送', 'bi-file-earmark-text', '#7c3aed'),
        'contract':      lambda: card('合同总数', counts['contract'], f"{counts['project_active']} 项目执行中", 'bi-file-earmark-lock', '#ea580c'),
        'project':       lambda: card('项目', counts['project'], f"{counts['project_active']} 进行中", 'bi-diagram-3', '#db2777'),
        'stock_alert':   lambda: card('备件预警', counts['stock_alerts'], f"备件 {counts['spare']} 项", 'bi-exclamation-diamond', '#ea580c'),
        'expiring':      lambda: card('即将到期授权', len(expiring_devices_data), '30天内到期', 'bi-shield-exclamation', '#db2777'),
        'my_tasks':      lambda: card('我的待办', len(my_tasks), '工单+巡检' if role in ('admin','operator') else ('商机+合同' if role=='sales' else '待处理'), 'bi-person-check', '#2563eb'),
    }

    # 从偏好或默认生成卡片列表
    preferred_cards = get_dashboard_cards(current_user)
    metrics = []
    for ck in preferred_cards:
        if ck in CARD_VALUES:
            try:
                metrics.append(CARD_VALUES[ck]())
            except Exception:
                pass
    if not metrics:
        # fallback
        metrics = [CARD_VALUES['ticket'](), CARD_VALUES['device'](), CARD_VALUES['customer']()]

    # ---- 快捷入口（按角色）----
    qe = lambda url, title, sub, icon: {'url': url, 'title': title, 'sub': sub, 'icon': icon}
    if role == 'admin':
        quick_entries = [
            qe('/customers', '客户管理', '客户信息维护', 'bi-people'),
            qe('/devices', '设备管理', '设备档案与密码', 'bi-router'),
            qe('/inspections', '巡检管理', '巡检记录与任务', 'bi-clipboard-check'),
            qe('/tickets', '工单管理', '派单/接单/处理', 'bi-ticket-detailed'),
            qe('/knowledge-base', '知识库', '故障案例与手册', 'bi-book'),
            qe('/ai-config', 'AI 对接', '智能巡检与分析', 'bi-robot'),
            qe('/users', '用户管理', '账号与角色', 'bi-people-fill'),
            qe('/dashboard/reports', '数据报表', 'ECharts 可视化', 'bi-bar-chart'),
        ]
    elif role == 'operator':
        quick_entries = [
            qe('/devices', '设备管理', '设备档案与密码', 'bi-router'),
            qe('/tickets', '工单处理', '我的工单', 'bi-ticket-detailed'),
            qe('/task-schedule/', '任务安排', '执行计划巡检', 'bi-tasks'),
            qe('/inspections', '巡检记录', '提交巡检报告', 'bi-clipboard-check'),
            qe('/knowledge-base', '知识库', '快速查询', 'bi-book'),
            qe('/topologies', '拓扑图', '网络结构', 'bi-diagram-3'),
        ]
    elif role == 'sales':
        quick_entries = [
            qe('/customers', '客户管理', '客户信息', 'bi-people'),
            qe('/opportunities', '商机跟进', '阶段推进', 'bi-lightbulb'),
            qe('/quotations', '报价单', '生成报价', 'bi-file-earmark-text'),
            qe('/contracts', '合同管理', '合同执行', 'bi-file-earmark-lock'),
            qe('/projects', '项目管理', '项目进度', 'bi-diagram-3'),
            qe('/tickets', '客户报修', '替客户提单', 'bi-ticket-detailed'),
        ]
    else:
        quick_entries = [
            qe('/customers', '客户管理', '查看客户', 'bi-people'),
            qe('/devices', '设备管理', '查看设备', 'bi-router'),
            qe('/tickets', '工单管理', '查看工单', 'bi-ticket-detailed'),
            qe('/dashboard/reports', '数据报表', '统计分析', 'bi-bar-chart'),
        ]

    # V3: 主管视角数据
    supervisor_data = None
    is_supervisor_user = is_supervisor(current_user)
    if is_supervisor_user and current_user.department_id:
        dept = Department.query.get(current_user.department_id)
        if dept:
            # 部门成员只查一次（原实现成员列表与 dept_user_ids 各查一遍）
            dept_users = User.query.filter_by(department_id=dept.id, is_active=True).all()
            dept_user_ids = [u.id for u in dept_users]
            dept_tasks = InspectionTask.query.filter(
                or_(
                    InspectionTask.assigned_to_user_id.in_(dept_user_ids),
                    InspectionTask.dispatched_by == current_user.id,
                )
            ).order_by(InspectionTask.planned_start.asc()).all()
            today = date.today()
            qm = (today.month - 1) // 3
            q_start = today.replace(month=qm * 3 + 1, day=1)
            # V18: 本季度双侧夹紧，避免把 Q4/明年任务算进"本季度"（老代码漏了上界）
            q_end_month = qm * 3 + 3
            import calendar as _cal
            q_end = today.replace(
                month=q_end_month, day=_cal.monthrange(today.year, q_end_month)[1])
            q_tasks = [t for t in dept_tasks
                       if t.planned_start and q_start <= t.planned_start <= q_end]
            supervisor_data = {
                'dept_name': dept.name,
                'dept_total': len(dept_tasks),
                'dept_pending': len([t for t in dept_tasks if t.status == '待执行' and not t.assigned_to_user_id]),
                'dept_in_progress': len([t for t in dept_tasks if t.status == '执行中']),
                'dept_completed_q': len([t for t in q_tasks if t.status == '已完成']),
                'dept_completion_rate': f"{len([t for t in q_tasks if t.status == '已完成']) * 100 // max(len(q_tasks), 1)}%",
                'dept_members': [{'name': u.realname or u.username, 'id': u.id,
                                  'task_count': len([t for t in dept_tasks if t.assigned_to_user_id == u.id]),
                                  'completed': len([t for t in dept_tasks if t.assigned_to_user_id == u.id and t.status == '已完成'])}
                                 for u in dept_users],
                'quarter_start': q_start.strftime('%Y-%m-%d'),
            }

    # V3: 草稿提醒
    draft_list = []
    if current_user.is_authenticated:
        draft_list = FormDraft.query.filter_by(user_id=current_user.id).order_by(FormDraft.updated_at.desc()).limit(5).all()

    return render_template('index.html',
                           counts=counts,
                           role=role,
                           role_label_text=role,
                           metrics=metrics,
                           quick_entries=quick_entries,
                           my_tasks=my_tasks,
                           my_ticket_count=len(my_tickets),
                           my_insp_task_count=len(my_insp_tasks),
                           my_fault_count=len(my_faults),
                           expiring_devices=expiring_devices_data,
                           recent_inspections=recent_inspections_data,
                           device_type_stats=device_type_stats,
                           is_supervisor_user=is_supervisor_user,
                           supervisor_data=supervisor_data,
                           draft_list=draft_list,
                           card_pool=DASHBOARD_CARD_POOL,
                           preferred_cards=preferred_cards,
                           role_default_cards=ROLE_DEFAULT_CARDS.get(role, []))


# ==================== 设备密码管理 ====================
@login_required
@api_view
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
        try:
            cards = json.loads(pref.cards_json)
            if isinstance(cards, list) and len(cards) > 0:
                return cards
        except (json.JSONDecodeError, TypeError):
            pass
    return ROLE_DEFAULT_CARDS.get(user.role, ['ticket', 'device', 'customer'])

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

@login_required
@api_view
def api_dashboard_preferences_save():
    data = request.get_json(silent=True) or {}
    card_keys = data.get('cards', [])
    # 过滤无效卡片key
    valid = [k for k in card_keys if k in DASHBOARD_CARD_POOL]
    pref = UserDashboardPreference.query.filter_by(user_id=current_user.id).first()
    if not pref:
        pref = UserDashboardPreference(user_id=current_user.id)
        db.session.add(pref)
    pref.cards_json = json.dumps(valid)
    db.session.commit()
    return jsonify({'success': True, 'cards': valid})

@login_required
@api_view
def api_dashboard_preferences_reset():
    pref = UserDashboardPreference.query.filter_by(user_id=current_user.id).first()
    if pref:
        db.session.delete(pref)
        db.session.commit()
    cards = ROLE_DEFAULT_CARDS.get(current_user.role, [])
    return jsonify({'success': True, 'cards': cards})

