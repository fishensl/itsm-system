# -*- coding: utf-8 -*-
"""Vue SPA 业务 API（运维域：知识库 / 故障 / 报告）

复用 blueprints.vue_api 的 vue_api_bp 蓝图对象与 ok/fail 契约，
避免单一文件膨胀与并行开发冲突。由 blueprints/__init__ 注册。
"""
import os
from datetime import datetime, timedelta

from flask import request, current_app
from flask_login import login_required, current_user
from sqlalchemy import text as sa_text
from sqlalchemy.orm import joinedload

from blueprints.vue_api import vue_api_bp, ok, fail
from models import db
from utils.permission import require_permission


# ==================== 知识库 ====================
KB_CATEGORIES = ['故障案例', '设备手册', '内部规范', '巡检经验']


def _kb_payload(k):
    return {
        'id': k.id,
        'title': k.title,
        'category': k.category or '',
        'created_by': k.created_by or '',
        'view_count': k.view_count or 0,
        'helpful_count': k.helpful_count or 0,
        'is_published': bool(k.is_published),
        'published_label': '已发布' if k.is_published else '未发布',
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
        q = q.filter(_KB.is_published == bool(is_published))
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
