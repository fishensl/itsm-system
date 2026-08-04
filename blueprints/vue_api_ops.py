# -*- coding: utf-8 -*-
"""Vue SPA 业务 API（运维域：知识库 / 故障 / 报告）

复用 blueprints.vue_api 的 vue_api_bp 蓝图对象与 ok/fail 契约，
避免单一文件膨胀与并行开发冲突。由 blueprints/__init__ 注册。
"""
import os
from datetime import datetime, timedelta

from flask import request, current_app
from flask_login import login_required, current_user
from sqlalchemy import text as sa_text, or_
from sqlalchemy.orm import joinedload

from blueprints.vue_api import vue_api_bp, ok, fail
from models import db
from utils.permission import require_permission


# ==================== 知识库 ====================
KB_CATEGORIES = ['故障案例', '设备手册', '内部规范', '巡检经验']


def _kb_payload(k):
    # is_published 存量可能为 NULL：NULL 按「已发布」处理（与模型 default=True 语义一致）
    published = k.is_published is not False
    return {
        'id': k.id,
        'title': k.title,
        'category': k.category or '',
        'created_by': k.created_by or '',
        'view_count': k.view_count or 0,
        'helpful_count': k.helpful_count or 0,
        'is_published': published,
        'published_label': '已发布' if published else '未发布',
        'tags': k.tags or '',
        'created_at': k.created_at.strftime('%Y-%m-%d %H:%M') if k.created_at else '',
    }


@vue_api_bp.route('/api/knowledge-base', methods=['GET'])
@login_required
@require_permission('kb:view')
def api_kb_list():
    """知识库分页列表（DataTable 数据源）"""
    from models import KnowledgeBase as _KB
    page = request.args.get('page', 1, type=int)
    page_size = min(request.args.get('page_size', 20, type=int), 100)
    search = (request.args.get('search') or '').strip()
    category = (request.args.get('category') or '').strip()
    is_published = request.args.get('is_published', type=int)

    q = _KB.query
    if search:
        q = q.filter(_KB.title.contains(search) | _KB.tags.contains(search))
    if category:
        q = q.filter(_KB.category == category)
    if is_published is not None:
        # 存量 NULL 视为已发布：筛选「已发布」时需同时命中 NULL 记录
        if is_published:
            q = q.filter(or_(_KB.is_published == True, _KB.is_published.is_(None)))
        else:
            q = q.filter(_KB.is_published == False)
    total = q.count()
    rows = q.order_by(_KB.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return ok({'items': [_kb_payload(k) for k in rows],
               'total': total, 'page': page, 'page_size': page_size})


@vue_api_bp.route('/api/knowledge-base/<int:kb_id>', methods=['GET'])
@login_required
@require_permission('kb:view')
def api_kb_get(kb_id):
    from models import KnowledgeBase as _KB
    k = _KB.query.get_or_404(kb_id)
    # 浏览次数 +1：原子 UPDATE，避免 read-modify-write 并发丢失（不影响 SSR session 去重逻辑）
    db.session.execute(sa_text(
        'UPDATE knowledge_base SET view_count = COALESCE(view_count, 0) + 1 WHERE id = :kid'),
        {'kid': kb_id})
    k.view_count = (k.view_count or 0) + 1  # 页面展示同步
    db.session.commit()
    payload = _kb_payload(k)
    payload['content'] = k.content or ''
    return ok(payload)


@vue_api_bp.route('/api/knowledge-base', methods=['POST'])
@login_required
@require_permission('kb:add')
def api_kb_create():
    from models import KnowledgeBase as _KB
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    if not title:
        return fail('标题不能为空', 400)
    k = _KB(
        title=title,
        category=data.get('category') or '故障案例',
        content=data.get('content') or '',
        tags=data.get('tags') or '',
        is_published=bool(data.get('is_published', True)),
        created_by=current_user.realname or current_user.username,
    )
    db.session.add(k)
    db.session.commit()
    return ok({'id': k.id})


@vue_api_bp.route('/api/knowledge-base/<int:kb_id>', methods=['PUT'])
@login_required
@require_permission('kb:edit')
def api_kb_update(kb_id):
    from models import KnowledgeBase as _KB
    k = _KB.query.get_or_404(kb_id)
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    if not title:
        return fail('标题不能为空', 400)
    k.title = title
    if 'category' in data:
        k.category = data.get('category') or '故障案例'
    if 'content' in data:
        k.content = data.get('content') or ''
    if 'tags' in data:
        k.tags = data.get('tags') or ''
    if 'is_published' in data:
        k.is_published = bool(data.get('is_published'))
    db.session.commit()
    return ok({'id': k.id})


@vue_api_bp.route('/api/knowledge-base/<int:kb_id>', methods=['DELETE'])
@login_required
@require_permission('kb:delete')
def api_kb_delete(kb_id):
    from models import KnowledgeBase as _KB
    k = _KB.query.get_or_404(kb_id)
    current_app.logger.info(
        '知识条目删除审计(Vue): 用户[%s] 删除[%s](id=%s), IP=%s',
        current_user.username, k.title, k.id, request.remote_addr)
    db.session.delete(k)
    db.session.commit()
    return ok(None)


@vue_api_bp.route('/api/dicts/knowledge', methods=['GET'])
@login_required
@require_permission('kb:view')
def api_kb_dicts():
    return ok({'categories': KB_CATEGORIES})


# ==================== 故障记录 ====================
def _fault_payload(f, customer_map=None):
    return {
        'id': f.id,
        'title': f.title,
        'customer_id': f.customer_id,
        'customer_name': (customer_map or {}).get(f.customer_id, ''),
        'handler': f.handler or '',
        'fault_time': f.fault_time.strftime('%Y-%m-%d %H:%M') if f.fault_time else '',
        'fault_type': f.fault_type or '',
        'result': f.result or '',
        'impact_range': f.impact_range or '',
    }


@vue_api_bp.route('/api/faults', methods=['GET'])
@login_required
@require_permission('fault:view')
def api_fault_list():
    """故障分页列表（DataTable 数据源）"""
    from models import Fault as _F, Customer as _C
    page = request.args.get('page', 1, type=int)
    page_size = min(request.args.get('page_size', 20, type=int), 100)
    search = (request.args.get('search') or '').strip()
    fault_type = (request.args.get('fault_type') or '').strip()
    result = (request.args.get('result') or '').strip()

    q = _F.query
    if search:
        q = q.filter(_F.title.contains(search))
    if fault_type:
        q = q.filter(_F.fault_type == fault_type)
    if result:
        q = q.filter(_F.result == result)
    total = q.count()
    rows = q.order_by(_F.fault_time.desc(), _F.id.desc()) \
        .offset((page - 1) * page_size).limit(page_size).all()
    customer_map = {c.id: c.name for c in _C.query.all()}
    return ok({'items': [_fault_payload(f, customer_map) for f in rows],
               'total': total, 'page': page, 'page_size': page_size})


@vue_api_bp.route('/api/faults/<int:fault_id>', methods=['GET'])
@login_required
@require_permission('fault:view')
def api_fault_get(fault_id):
    from models import Fault as _F
    f = _F.query.get_or_404(fault_id)
    payload = _fault_payload(f, {f.customer_id: f.customer_rel.name if f.customer_rel else ''})
    payload['fault_description'] = f.fault_description or ''
    payload['fault_cause'] = f.fault_cause or ''
    payload['solution'] = f.solution or ''
    payload['recovery_time'] = f.recovery_time.strftime('%Y-%m-%d %H:%M') if f.recovery_time else ''
    payload['created_at'] = f.created_at.strftime('%Y-%m-%d %H:%M') if f.created_at else ''
    return ok(payload)


@vue_api_bp.route('/api/faults', methods=['POST'])
@login_required
@require_permission('fault:add')
def api_fault_create():
    from services.fault_service import create_fault
    data = request.get_json(silent=True) or {}
    try:
        f = create_fault(data, current_user.realname or current_user.username)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '故障创建失败', 400)
    return ok({'id': f.id})


@vue_api_bp.route('/api/faults/<int:fault_id>', methods=['PUT'])
@login_required
@require_permission('fault:edit')
def api_fault_update(fault_id):
    from services.fault_service import update_fault
    data = request.get_json(silent=True) or {}
    try:
        update_fault(fault_id, data)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '故障更新失败', 400)
    return ok({'id': fault_id})


@vue_api_bp.route('/api/faults/<int:fault_id>', methods=['DELETE'])
@login_required
@require_permission('fault:delete')
def api_fault_delete(fault_id):
    from services.fault_service import delete_fault
    from models import Fault as _F
    f = _F.query.get_or_404(fault_id)
    current_app.logger.info(
        '故障删除审计(Vue): 用户[%s] 删除故障[%s](id=%s), IP=%s',
        current_user.username, f.title, f.id, request.remote_addr)
    try:
        delete_fault(fault_id)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '故障删除失败', 400)
    return ok(None)


@vue_api_bp.route('/api/dicts/faults', methods=['GET'])
@login_required
@require_permission('fault:view')
def api_fault_dicts():
    from models import FaultType as _FT, Customer as _C
    fault_types = [{'id': t.id, 'name': t.name}
                   for t in _FT.query.order_by(_FT.sort_order, _FT.id).all()]
    customers = [{'id': c.id, 'name': c.name} for c in _C.query.order_by(_C.name).all()]
    results = ['已解决', '待观察', '未解决']
    return ok({'fault_types': fault_types, 'customers': customers, 'results': results})


# ==================== 报告中心 ====================
REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'reports')
_REPORT_TABS = ('all', 'inspection', 'fault', 'ticket', 'file')
_REPORT_TYPES = ('inspection', 'fault', 'ticket', 'file')


@vue_api_bp.route('/api/reports', methods=['GET'])
@login_required
@require_permission('report:view')
def api_reports():
    """报告中心聚合：客户分桶 × 巡检/故障/工单/文件，返回 JSON（逻辑对齐 SSR report_list）"""
    from models import Inspection as _I, Fault as _F, Ticket as _T

    tab = (request.args.get('tab') or 'all').strip()
    if tab not in _REPORT_TABS:
        tab = 'all'
    date_from = (request.args.get('date_from') or '').strip()
    date_to = (request.args.get('date_to') or '').strip()
    customer_id = request.args.get('customer_id', type=int)

    # 性能：首次进入（无任何过滤条件）默认只看近 12 个月，避免三表全量扫描
    if not date_from and not date_to and not customer_id:
        date_from = (datetime.now().date() - timedelta(days=365)).isoformat()

    buckets = {}

    def _bucket(cid, name):
        if cid not in buckets:
            buckets[cid] = {
                'id': cid,
                'name': name,
                'counts': {'inspection': 0, 'fault': 0, 'ticket': 0, 'file': 0},
                'items': {'inspection': [], 'fault': [], 'ticket': [], 'file': []},
            }
        return buckets[cid]

    def _push(cid, name, rt, item):
        b = _bucket(cid, name)
        b['counts'][rt] += 1
        b['items'][rt].append(item)

    def _customer_of(rel):
        return (rel.id, rel.name) if rel else (None, '未关联客户')

    if tab in ('all', 'inspection'):
        q = _I.query.options(joinedload(_I.customer_rel))
        if date_from:
            q = q.filter(_I.inspection_date >= date_from)
        if date_to:
            q = q.filter(_I.inspection_date <= date_to)
        if customer_id:
            q = q.filter(_I.customer_id == customer_id)
        for i in q.order_by(_I.inspection_date.desc(), _I.id.desc()).all():
            cid, cname = _customer_of(i.customer_rel)
            _push(cid, cname, 'inspection', {
                'id': i.id, 'title': i.title,
                'inspection_date': i.inspection_date.strftime('%Y-%m-%d') if i.inspection_date else '',
            })

    if tab in ('all', 'fault'):
        q = _F.query.options(joinedload(_F.customer_rel))
        if date_from:
            q = q.filter(_F.fault_time >= date_from)
        if date_to:
            q = q.filter(_F.fault_time <= date_to)
        if customer_id:
            q = q.filter(_F.customer_id == customer_id)
        for f in q.order_by(_F.fault_time.desc(), _F.id.desc()).all():
            cid, cname = _customer_of(f.customer_rel)
            _push(cid, cname, 'fault', {
                'id': f.id, 'title': f.title, 'result': f.result or '',
                'fault_time': f.fault_time.strftime('%Y-%m-%d %H:%M') if f.fault_time else '',
            })

    if tab in ('all', 'ticket'):
        q = _T.query.options(joinedload(_T.customer_rel))
        if date_from:
            q = q.filter(_T.created_at >= date_from)
        if date_to:
            q = q.filter(_T.created_at <= date_to)
        if customer_id:
            q = q.filter(_T.customer_id == customer_id)
        for t in q.order_by(_T.created_at.desc(), _T.id.desc()).all():
            cid, cname = _customer_of(t.customer_rel)
            _push(cid, cname, 'ticket', {
                'id': t.id, 'number': t.number, 'title': t.title,
                'created_at': t.created_at.strftime('%Y-%m-%d %H:%M') if t.created_at else '',
            })

    if tab in ('all', 'file') and os.path.isdir(REPORTS_DIR):
        def _normkey(p):
            return os.path.normcase(os.path.normpath(p)) if p else ''

        file_to_record = {}
        for Mdl in (_I, _F, _T):
            for rec in Mdl.query.options(joinedload(Mdl.customer_rel)).filter(
                    Mdl.report_file.isnot(None), Mdl.report_file != '').all():
                v = (rec.report_file or '').strip()
                if not v:
                    continue
                for c in (v, os.path.basename(v), _normkey(v), _normkey(os.path.basename(v)),
                          _normkey(os.path.join('reports', v))):
                    if c and c not in file_to_record:
                        file_to_record[c] = rec

        for fname in sorted(os.listdir(REPORTS_DIR), reverse=True):
            full = os.path.join(REPORTS_DIR, fname)
            if not os.path.isfile(full):
                continue
            ftype = '巡检' if '巡检' in fname else ('故障' if '故障' in fname else '其他')
            rec = (file_to_record.get(_normkey(full)) or file_to_record.get(_normkey(fname)))
            size = os.path.getsize(full)
            item = {
                'filename': fname,
                'type': ftype + '报告' if ftype != '其他' else '其他',
                'size_display': f'{size / 1024:.1f} KB',
                'create_time': datetime.fromtimestamp(os.path.getmtime(full)).strftime('%Y-%m-%d %H:%M'),
            }
            cid, cname = _customer_of(rec.customer_rel) if rec else (None, '未关联客户')
            _push(cid, cname, 'file', item)

    # 每类型每组最多 100 条（counts 保持真实计数）
    for b in buckets.values():
        for rt in _REPORT_TYPES:
            b['items'][rt] = b['items'][rt][:100]

    # 排序：真实客户按 name，未关联固定末位
    data_order = sorted([v for k, v in buckets.items() if k is not None], key=lambda x: x['name'])
    unassigned = buckets.get(None)
    if unassigned:
        data_order.append(unassigned)

    def _tcount(p, t):
        return p['counts'].get(t, 0)

    tab_stats = {}
    for t in _REPORT_TABS:
        if t == 'all':
            tab_stats[t] = {
                'customers': sum(1 for p in data_order if any(p['counts'].values())),
                'total': sum(sum(p['counts'].values()) for p in data_order),
            }
        else:
            tab_stats[t] = {
                'customers': sum(1 for p in data_order if _tcount(p, t)),
                'total': sum(_tcount(p, t) for p in data_order),
            }

    return ok({'data_order': data_order, 'tab_stats': tab_stats})

# ==================== 巡检人员 ====================
@vue_api_bp.route('/api/inspectors', methods=['GET'])
@login_required
@require_permission('inspection:view')
def api_inspector_list():
    from sqlalchemy import select
    from models import Inspector, User
    inspectors = Inspector.query.order_by(Inspector.id.desc()).all()
    linked_uids = select(Inspector.user_id)
    available = User.query.filter(
        User.is_active == True,
        User.role.in_(['operator', 'admin']),
        ~User.id.in_(linked_uids),
    ).order_by(User.realname).all()
    return ok({
        'inspectors': [
            {
                'id': i.id,
                'user_id': i.user_id,
                'name': i.name,
                'username': i.linked_user.username if i.linked_user else '',
                'role': i.linked_user.role if i.linked_user else '',
                'department_id': i.linked_user.department_id if i.linked_user else None,
                'phone': i.linked_user.phone if i.linked_user else '',
                'email': i.linked_user.email if i.linked_user else '',
                'is_active': bool(i.is_active),
                'remark': i.remark or '',
            }
            for i in inspectors
        ],
        'available_users': [
            {
                'id': u.id,
                'name': u.realname or u.username,
                'username': u.username,
                'role': u.role or '',
                'department_id': u.department_id,
            }
            for u in available
        ],
    })


@vue_api_bp.route('/api/inspectors', methods=['POST'])
@login_required
@require_permission('inspection:edit')
def api_inspector_add():
    from models import Inspector, User
    data = request.get_json(silent=True) or {}
    try:
        user_id = int(data.get('user_id') or 0)
    except (TypeError, ValueError):
        user_id = 0
    if not user_id:
        return fail('请选择用户')
    u = User.query.get(user_id)
    if not u:
        return fail('用户不存在')
    if Inspector.query.filter_by(user_id=user_id).first():
        return fail(f'用户 {u.realname or u.username} 已是巡检人员')
    i = Inspector(user_id=user_id, remark=(data.get('remark') or '').strip(), is_active=True)
    db.session.add(i)
    db.session.commit()
    current_app.logger.info(f'巡检人员添加: user={user_id}')
    return ok({'id': i.id})


@vue_api_bp.route('/api/inspectors/<int:insp_id>', methods=['PUT'])
@login_required
@require_permission('inspection:edit')
def api_inspector_update(insp_id):
    from models import Inspector
    i = Inspector.query.get_or_404(insp_id)
    data = request.get_json(silent=True) or {}
    i.remark = (data.get('remark') or '').strip()
    i.is_active = bool(data.get('is_active', i.is_active))
    db.session.commit()
    return ok(None)


@vue_api_bp.route('/api/inspectors/<int:insp_id>', methods=['DELETE'])
@login_required
@require_permission('inspection:delete')
def api_inspector_delete(insp_id):
    from models import Inspector
    i = Inspector.query.get_or_404(insp_id)
    db.session.delete(i)
    db.session.commit()
    current_app.logger.info(f'巡检人员删除: id={insp_id}')
    return ok(None)

# ==================== 任务模板 ====================
def _task_template_payload(t):
    import json
    try:
        sections = json.loads(t.sections_json or '{}')
    except Exception:
        sections = {}
    return {
        'id': t.id,
        'name': t.name,
        'category': t.category or '',
        'inspection_type': t.inspection_type or '',
        'frequency': t.frequency or '',
        'customer_tier': t.customer_tier or 'all',
        'sections': sections.get('sections', []),
        'is_active': bool(t.is_active),
        'remark': t.remark or '',
        'device_template_ids': [d.id for d in t.get_ordered_device_templates()],
    }


@vue_api_bp.route('/api/task-templates', methods=['GET'])
@login_required
@require_permission('inspection:view')
def api_task_template_list():
    from models import InspectionTaskTemplate, InspectionDeviceTemplate, Customer
    templates = InspectionTaskTemplate.query.order_by(InspectionTaskTemplate.id.desc()).all()
    device_templates = InspectionDeviceTemplate.query.filter_by(is_active=True).order_by(
        InspectionDeviceTemplate.device_category, InspectionDeviceTemplate.id).all()
    customers = Customer.query.order_by(Customer.name).all()
    return ok({
        'templates': [_task_template_payload(t) for t in templates],
        'device_templates': [
            {'id': d.id, 'name': d.name, 'device_category': d.device_category or '',
             'device_sub_type': d.device_sub_type or '', 'items_count': d.total_sub_items}
            for d in device_templates
        ],
        'customers': [{'id': c.id, 'name': c.name} for c in customers],
    })


@vue_api_bp.route('/api/task-templates', methods=['POST'])
@login_required
@require_permission('inspection:edit')
def api_task_template_add():
    from models import InspectionTaskTemplate
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return fail('名称不能为空')
    import json
    sections_json = json.dumps({'sections': data.get('sections') or []}, ensure_ascii=False)
    t = InspectionTaskTemplate(
        name=name,
        category=(data.get('category') or '日常巡检').strip(),
        inspection_type=(data.get('inspection_type') or '月度巡检').strip(),
        frequency=(data.get('frequency') or '').strip(),
        customer_tier=(data.get('customer_tier') or 'all').strip(),
        sections_json=sections_json,
        is_active=True,
        remark=(data.get('remark') or '').strip(),
    )
    db.session.add(t)
    db.session.flush()
    _save_task_template_devices_vue(t, data.get('device_template_ids') or [])
    db.session.commit()
    return ok({'id': t.id})


@vue_api_bp.route('/api/task-templates/<int:tid>', methods=['PUT'])
@login_required
@require_permission('inspection:edit')
def api_task_template_update(tid):
    from models import InspectionTaskTemplate
    t = InspectionTaskTemplate.query.get_or_404(tid)
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if name:
        t.name = name
    t.category = (data.get('category') or t.category).strip()
    t.inspection_type = (data.get('inspection_type') or t.inspection_type).strip()
    t.frequency = (data.get('frequency') or '').strip()
    t.customer_tier = (data.get('customer_tier') or 'all').strip()
    import json
    t.sections_json = json.dumps({'sections': data.get('sections') or []}, ensure_ascii=False)
    t.is_active = bool(data.get('is_active', t.is_active))
    t.remark = (data.get('remark') or '').strip()
    _save_task_template_devices_vue(t, data.get('device_template_ids') or [])
    db.session.commit()
    return ok(None)


def _save_task_template_devices_vue(t, ids):
    from models import task_device_template_link
    cleaned = []
    for x in ids:
        try:
            cleaned.append(int(x))
        except (TypeError, ValueError):
            pass
    t.device_templates = []
    db.session.flush()
    for idx, dt_id in enumerate(cleaned):
        db.session.execute(task_device_template_link.insert().values(
            task_template_id=t.id, device_template_id=dt_id, sort_order=idx))


@vue_api_bp.route('/api/task-templates/<int:tid>', methods=['DELETE'])
@login_required
@require_permission('inspection:delete')
def api_task_template_delete(tid):
    from models import InspectionTaskTemplate
    t = InspectionTaskTemplate.query.get(tid)
    if t:
        t.device_templates = []
        db.session.flush()
        db.session.delete(t)
        db.session.commit()
    return ok(None)


# ==================== 任务模板 — 自动匹配 ====================
@vue_api_bp.route('/api/task-templates/match/<int:cid>', methods=['GET'])
@login_required
@require_permission('inspection:view')
def api_task_template_match(cid):
    from collections import defaultdict
    from models import Device, InspectionDeviceTemplate
    devices = Device.query.filter_by(customer_id=cid, is_in_use=True).all()
    by_cat = defaultdict(list)
    for d in devices:
        cat = (d.device_type or '其他').strip()
        by_cat[cat].append({'id': d.id, 'name': d.device_name, 'brand': d.brand or '',
                            'model': d.model or '', 'ip': d.ip_address or '',
                            'os_version': d.os_version or ''})
    all_templates = InspectionDeviceTemplate.query.filter_by(is_active=True).all()
    tpl_by_cat = defaultdict(list)
    for tpl in all_templates:
        tpl_by_cat[tpl.device_category or '其他'].append(tpl)
    out = []
    for cat, dev_list in sorted(by_cat.items()):
        candidates = []
        for tpl in tpl_by_cat.get(cat, []):
            candidates.append({'id': tpl.id, 'name': tpl.name, 'category': tpl.device_category or '',
                               'sub_type': tpl.device_sub_type or '', 'items_count': tpl.total_sub_items,
                               'match_score': 100})
        for tpl in all_templates:
            if (tpl.device_category or '') == cat:
                continue
            if cat in (tpl.name or '') or cat in (tpl.device_sub_type or ''):
                candidates.append({'id': tpl.id, 'name': tpl.name, 'category': tpl.device_category or '',
                                   'sub_type': tpl.device_sub_type or '', 'items_count': 0,
                                   'match_score': 50})
        candidates.sort(key=lambda x: -x['match_score'])
        out.append({'device_category': cat, 'devices_count': len(dev_list),
                    'devices': dev_list, 'matched_templates': candidates})
    return ok({'groups': out, 'total_devices': len(devices)})


# ==================== 设备检查模板 ====================
DEVICE_CATEGORY_ORDER = ['服务器', '网络设备', '安全设备', '环控设备', '会议设备', '空调', 'UPS', '存储设备', '其他']


def _device_template_payload(t):
    import json
    try:
        items = json.loads(t.items_json or '[]')
    except Exception:
        items = []
    return {
        'id': t.id,
        'name': t.name,
        'device_category': t.device_category or '',
        'device_sub_type': t.device_sub_type or '',
        'items': items if isinstance(items, list) else [],
        'is_active': bool(t.is_active),
        'remark': t.remark or '',
        'total_sub_items': t.total_sub_items,
    }


@vue_api_bp.route('/api/device-check-templates', methods=['GET'])
@login_required
@require_permission('inspection:view')
def api_device_check_template_list():
    from models import InspectionDeviceTemplate
    templates = InspectionDeviceTemplate.query.order_by(
        InspectionDeviceTemplate.device_category, InspectionDeviceTemplate.id).all()
    grouped = {}
    for t in templates:
        grouped.setdefault(t.device_category or '其他', []).append(_device_template_payload(t))
    return ok({'groups': grouped, 'category_order': DEVICE_CATEGORY_ORDER})


@vue_api_bp.route('/api/device-check-templates', methods=['POST'])
@login_required
@require_permission('inspection:edit')
def api_device_check_template_add():
    from models import InspectionDeviceTemplate
    import json
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return fail('模板名称不能为空')
    items = data.get('items')
    if not isinstance(items, list):
        return fail('检查项格式错误')
    t = InspectionDeviceTemplate(
        name=name,
        device_category=(data.get('device_category') or '网络设备').strip(),
        device_sub_type=(data.get('device_sub_type') or '').strip(),
        items_json=json.dumps(items, ensure_ascii=False),
        is_active=bool(data.get('is_active', True)),
        remark=(data.get('remark') or '').strip(),
    )
    db.session.add(t)
    db.session.commit()
    return ok({'id': t.id})


@vue_api_bp.route('/api/device-check-templates/<int:tid>', methods=['PUT'])
@login_required
@require_permission('inspection:edit')
def api_device_check_template_update(tid):
    from models import InspectionDeviceTemplate
    import json
    t = InspectionDeviceTemplate.query.get_or_404(tid)
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return fail('模板名称不能为空')
    items = data.get('items')
    if not isinstance(items, list):
        return fail('检查项格式错误')
    t.name = name
    t.device_category = (data.get('device_category') or t.device_category).strip()
    t.device_sub_type = (data.get('device_sub_type') or '').strip()
    t.items_json = json.dumps(items, ensure_ascii=False)
    t.is_active = bool(data.get('is_active', t.is_active))
    t.remark = (data.get('remark') or '').strip()
    db.session.commit()
    return ok(None)


@vue_api_bp.route('/api/device-check-templates/<int:tid>', methods=['DELETE'])
@login_required
@require_permission('inspection:delete')
def api_device_check_template_delete(tid):
    from models import InspectionDeviceTemplate
    InspectionDeviceTemplate.query.filter_by(id=tid).delete()
    db.session.commit()
    return ok(None)

# ==================== 任务安排（Vue 看板） ====================
@vue_api_bp.route('/api/task-schedule', methods=['GET'])
@login_required
@require_permission('task:schedule')
def api_task_schedule_board():
    """任务安排：按状态/按工程师视图 + KPI + 期间/客户/负责人筛选（对齐 SSR 看板口径）"""
    from blueprints.task_schedule import (_base_query, _apply_filters, _effective_request_args,
                                          _engineers_with_tasks, is_overdue)
    from models import Customer as _C, User as _U

    args = _effective_request_args(request.args)[0]
    query = _apply_filters(_base_query(), args)
    view = (request.args.get('view') or 'engineer').strip()
    tasks = query.all()
    today = __import__('datetime').date.today()

    # 看板排序：逾期最前 → 执行中 → 待执行 → 已完成 → 已取消；同级按截止时间升序，最后 id 降序
    from datetime import date as _date
    from utils.constants import TASK_SORT_PRIORITY
    tasks = sorted(tasks, key=lambda t: (
        0 if is_overdue(t, today) else 1,
        TASK_SORT_PRIORITY.get(t.status, 9),
        t.planned_end or _date.max,
        -t.id,
    ))

    customer_map = {c.id: c.name for c in _C.query.all()}
    user_map = {u.id: u for u in _U.query.all()}

    def payload(t):
        u = user_map.get(t.assigned_to_user_id)
        return {
            'id': t.id,
            'title': t.title,
            'status': t.status,
            'priority': t.priority or '',
            'task_type': t.task_type or '',
            'customer_id': t.customer_id,
            'customer_name': customer_map.get(t.customer_id, ''),
            'assignee_id': t.assigned_to_user_id,
            'assignee_name': (u.realname or u.username) if u else '',
            'planned_start': t.planned_start.isoformat() if t.planned_start else '',
            'planned_end': t.planned_end.isoformat() if t.planned_end else '',
            'estimated_effort': t.estimated_effort,
            'actual_effort': t.actual_effort,
            'overdue': is_overdue(t, today),
            'source': t.source or '',
            'remark': t.remark or '',
        }

    items = [payload(t) for t in tasks]
    engineers = [{'id': u.id, 'name': u.realname or u.username} for u in _engineers_with_tasks()]

    kpi = {
        'total': len(items),
        'pending': sum(1 for t in items if t['status'] == '待执行'),
        'running': sum(1 for t in items if t['status'] == '执行中'),
        'done': sum(1 for t in items if t['status'] == '已完成'),
        'overdue': sum(1 for t in items if t['overdue']),
        'est_effort': round(sum(t['estimated_effort'] or 0 for t in items), 2),
        'act_effort': round(sum(t['actual_effort'] or 0 for t in items), 2),
    }

    if view == 'engineer':
        groups = {}
        for eng in engineers:
            groups[str(eng['id'])] = [t for t in items if t['assignee_id'] == eng['id']]
        groups['__unassigned__'] = [t for t in items if not t['assignee_id']]
        data = {'engineer_groups': groups, 'engineers': engineers, 'view': 'engineer'}
    else:
        groups = {st: [t for t in items if t['status'] == st] for st in ('待执行', '执行中', '已完成')}
        data = {'status_groups': groups, 'engineers': engineers, 'view': 'status'}
    data['tasks'] = items
    data['kpi'] = kpi
    data['customers'] = [{'id': c.id, 'name': c.name} for c in _C.query.order_by(_C.name).all()]
    return ok(data)


@vue_api_bp.route('/api/task-schedule', methods=['POST'])
@login_required
@require_permission('task:schedule')
def api_task_schedule_quick_add():
    from models import InspectionTask as _IT
    from blueprints.task_schedule import local_now
    data = request.get_json(silent=True) or {}
    title = (data.get('title') or '').strip()
    customer_id = data.get('customer_id')
    if not title:
        return fail('任务描述不能为空')
    if not customer_id:
        return fail('请选择客户')
    from datetime import date as _date
    planned_start = _date.fromisoformat(data['planned_start']) if data.get('planned_start') else None
    planned_end = _date.fromisoformat(data['planned_end']) if data.get('planned_end') else None
    t = _IT(
        title=title,
        task_type=(data.get('task_type') or '计划').strip() or '计划',
        status='待执行',
        customer_id=customer_id,
        planned_start=planned_start,
        planned_end=planned_end,
        priority=(data.get('priority') or '中').strip() or '中',
        estimated_effort=float(data['estimated_effort']) if data.get('estimated_effort') is not None else None,
        assigned_to_user_id=data.get('assignee_id') or None,
        dispatched_by=current_user.id,
        dispatched_at=local_now(),
        source='手动',
        template_category=(data.get('template_category') or '巡检').strip() or '巡检',
        remark=(data.get('remark') or '').strip(),
        created_by=(current_user.realname or current_user.username),
    )
    db.session.add(t)
    db.session.commit()
    return ok({'id': t.id})


@vue_api_bp.route('/api/task-schedule/<int:task_id>', methods=['PUT'])
@login_required
@require_permission('task:schedule')
def api_task_schedule_update(task_id):
    from models import InspectionTask as _IT
    from datetime import date as _date
    from blueprints.task_schedule import local_now
    t = _IT.query.get_or_404(task_id)
    data = request.get_json(silent=True) or {}
    if data.get('title') is not None:
        t.title = (data['title'] or '').strip() or t.title
    if data.get('status') is not None:
        new_status = data['status']
        if new_status not in ('待执行', '执行中', '已完成', '已取消'):
            return fail(f'非法的状态: {new_status}', 400)
        if new_status == '执行中' and not t.actual_start:
            t.actual_start = local_now()
        if new_status == '已完成' and not t.actual_end:
            t.actual_end = local_now()
        t.status = new_status
    if data.get('assignee_id') is not None:
        t.assigned_to_user_id = data['assignee_id'] or None
        t.dispatched_by = t.dispatched_by or current_user.id
        t.dispatched_at = t.dispatched_at or local_now()
    if data.get('planned_start') is not None:
        t.planned_start = _date.fromisoformat(data['planned_start']) if data['planned_start'] else None
    if data.get('planned_end') is not None:
        t.planned_end = _date.fromisoformat(data['planned_end']) if data['planned_end'] else None
    if data.get('estimated_effort') is not None:
        t.estimated_effort = float(data['estimated_effort']) if data['estimated_effort'] not in (None, '') else None
    if data.get('actual_effort') is not None:
        t.actual_effort = float(data['actual_effort']) if data['actual_effort'] not in (None, '') else None
    if data.get('priority') is not None:
        t.priority = (data['priority'] or '中').strip() or '中'
    if data.get('remark') is not None:
        t.remark = (data['remark'] or '').strip()
    db.session.commit()
    return ok(None)


@vue_api_bp.route('/api/task-schedule/<int:task_id>', methods=['DELETE'])
@login_required
@require_permission('task:schedule')
def api_task_schedule_delete(task_id):
    from models import InspectionTask as _IT
    t = _IT.query.get_or_404(task_id)
    db.session.delete(t)
    db.session.commit()
    return ok(None)


@vue_api_bp.route('/api/task-schedule/batch', methods=['POST'])
@login_required
@require_permission('task:schedule')
def api_task_schedule_batch():
    from models import InspectionTask as _IT
    from blueprints.task_schedule import local_now
    data = request.get_json(silent=True) or {}
    ids = [int(x) for x in (data.get('ids') or []) if str(x).isdigit()]
    action = (data.get('action') or '').strip()
    value = data.get('value')
    if not ids:
        return fail('请先选择任务')
    tasks = _IT.query.filter(_IT.id.in_(ids)).all()
    if action == 'status':
        if value not in ('待执行', '执行中', '已完成', '已取消'):
            return fail('非法的状态', 400)
        for t in tasks:
            if value == '执行中' and not t.actual_start:
                t.actual_start = local_now()
            if value == '已完成' and not t.actual_end:
                t.actual_end = local_now()
            t.status = value
    elif action == 'assign':
        for t in tasks:
            t.assigned_to_user_id = value or None
            t.dispatched_by = t.dispatched_by or current_user.id
            t.dispatched_at = t.dispatched_at or local_now()
    elif action == 'delete':
        for t in tasks:
            db.session.delete(t)
    else:
        return fail(f'未知操作: {action}', 400)
    db.session.commit()
    return ok({'count': len(tasks)})


@vue_api_bp.route('/api/task-schedule/import-template', methods=['GET'])
@login_required
@require_permission('task:schedule')
def api_task_schedule_import_template():
    """下载导入模板（xlsx，base64 返回）"""
    import base64
    from utils.excel_export import export_xlsx
    from blueprints.task_schedule import EXCEL_HEADERS
    rows = [['示例客户A', '示例客户A2026年二季度巡检', '中', '2026-04-01', '2026-06-30', '已完成',
             '张三', '2026-06-15', '1', '1.5']]
    tmp_path, download_name = export_xlsx(EXCEL_HEADERS, rows, filename='任务安排导入模板.xlsx',
                                          sheet_name='成员分工安排表')
    with open(tmp_path, 'rb') as fh:
        b64 = base64.b64encode(fh.read()).decode('ascii')
    try:
        os.remove(tmp_path)
    except OSError:
        pass
    return ok({'filename': download_name, 'content': b64})


@vue_api_bp.route('/api/task-schedule/import', methods=['POST'])
@login_required
@require_permission('task:schedule')
def api_task_schedule_import():
    """批量导入 Excel（复用 SSR 导入逻辑：从 blueprints.task_schedule.import_excel 抽取为公共函数）"""
    from services.task_schedule_service import import_task_excel
    f = request.files.get('importFile')
    if not f:
        return fail('请选择 Excel 文件')
    try:
        result = import_task_excel(f, current_user)
    except ValueError as e:
        db.session.rollback()
        return fail(str(e))
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('任务安排导入失败(Vue)')
        return fail(f'导入失败：{e}')
    msg_parts = [f'新增 {result["created"]}', f'更新 {result["updated"]}']
    if result['new_customer_names']:
        msg_parts.append(f'自动创建客户 {len(result["new_customer_names"])} 个')
    if result['skipped']:
        msg_parts.append(f'跳过 {result["skipped"]} 行（' + '；'.join(result['skip_reasons'][:5]) + '）')
    return ok({'message': '导入完成：' + '；'.join(msg_parts)})
