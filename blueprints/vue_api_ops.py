# -*- coding: utf-8 -*-
"""Vue SPA 业务 API（运维域：知识库 / 故障 / 报告）

复用 blueprints.vue_api 的 vue_api_bp 蓝图对象与 ok/fail 契约，
避免单一文件膨胀与并行开发冲突。由 blueprints/__init__ 注册。
"""
import os
from datetime import datetime, timedelta
from urllib.parse import quote

from flask import request, current_app, send_from_directory, abort
from flask_login import login_required, current_user
from sqlalchemy import text as sa_text, or_
from sqlalchemy.orm import joinedload

from blueprints.vue_api import vue_api_bp, ok, fail
from models import db
from utils.permission import require_permission


# ==================== 知识库 ====================
KB_CATEGORIES = ['故障案例', '设备手册', '内部规范', '巡检经验']

# V7 知识库附件保存目录（目录由 create_app 的 _ensure_runtime_dirs 统一创建）
KB_ATTACH_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             'static', 'uploads', 'knowledge')
ALLOWED_KB_EXTS = {'.pdf', '.doc', '.docx', '.xls', '.xlsx',
                   '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.txt'}


def _save_kb_attachments(files, kb_id):
    """保存知识库多个附件，返回 [(file_name, file_path, ext, size), ...]"""
    import uuid as _uuid
    saved = []
    if not files:
        return saved
    sub_dir = os.path.join(KB_ATTACH_DIR, str(kb_id))
    os.makedirs(sub_dir, exist_ok=True)
    for f in files:
        if not f or not f.filename:
            continue
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in ALLOWED_KB_EXTS:
            continue
        safe_name = f'{_uuid.uuid4().hex}{ext}'
        full = os.path.join(sub_dir, safe_name)
        f.save(full)
        rel_path = f'uploads/knowledge/{kb_id}/{safe_name}'
        saved.append((f.filename, rel_path, ext, os.path.getsize(full)))
    return saved


def _get_kb_attachment(kb_id, att_id):
    """取附件并校验归属（跨条目访问一律 404）"""
    from models import KnowledgeAttachment as _KA
    att = _KA.query.get_or_404(att_id)
    if att.knowledge_id != kb_id:
        abort(404)
    return att


def _kb_attachment_fullpath(att):
    """附件物理路径（realpath 校验必须落在 KB 目录内，防路径穿越）"""
    full = os.path.realpath(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static', att.file_path))
    base = os.path.realpath(KB_ATTACH_DIR)
    if not full.startswith(base + os.sep) or not os.path.isfile(full):
        return None
    return full


def _kb_attachments_payload(atts):
    return [{
        'id': a.id,
        'file_name': a.file_name,
        'file_ext': a.file_ext or '',
        'file_size': a.file_size or 0,
        'uploaded_by': a.uploaded_by or '',
        'created_at': a.created_at.strftime('%Y-%m-%d %H:%M') if a.created_at else '',
    } for a in atts]


def _kb_payload(k, attachments=None):
    # is_published 存量可能为 NULL：NULL 按「已发布」处理（与模型 default=True 语义一致）
    published = k.is_published is not False
    atts = list(k.attachments) if attachments is None else list(attachments)
    return {
        'id': k.id,
        'title': k.title,
        'category': k.category or '',
        'created_by': k.created_by or '',
        'view_count': k.view_count or 0,
        'helpful_count': k.helpful_count or 0,
        'is_published': published,
        'published_label': '已发布' if published else '未发布',
        'published_by': k.published_by or '',
        'published_at': k.published_at.strftime('%Y-%m-%d %H:%M') if k.published_at else '',
        'tags': k.tags or '',
        'created_at': k.created_at.strftime('%Y-%m-%d %H:%M') if k.created_at else '',
        'attachments': _kb_attachments_payload(atts),
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
    # 附件一次 IN 查询分组（dynamic 关系无法 eager load，避免逐行 N+1）
    att_map = {}
    if rows:
        from models import KnowledgeAttachment as _KA
        kb_ids = [k.id for k in rows]
        att_map = {kid: [] for kid in kb_ids}
        for a in _KA.query.filter(_KA.knowledge_id.in_(kb_ids)).order_by(_KA.id).all():
            att_map.setdefault(a.knowledge_id, []).append(a)
    return ok({'items': [_kb_payload(k, att_map.get(k.id, [])) for k in rows],
               'total': total, 'page': page, 'page_size': page_size})


@vue_api_bp.route('/api/knowledge-base/<int:kb_id>', methods=['GET'])
@login_required
@require_permission('kb:view')
def api_kb_get(kb_id):
    from models import KnowledgeBase as _KB
    from flask import session
    k = _KB.query.get_or_404(kb_id)
    # 浏览次数 +1：原子 UPDATE，避免 read-modify-write 并发丢失；
    # session 去重（同人同会话重复访问不计，与旧 SSR 详情页行为一致）
    viewed_key = f'kb_viewed_{kb_id}'
    if not session.get(viewed_key):
        db.session.execute(sa_text(
            'UPDATE knowledge_base SET view_count = COALESCE(view_count, 0) + 1 WHERE id = :kid'),
            {'kid': kb_id})
        k.view_count = (k.view_count or 0) + 1  # 页面展示同步
        db.session.commit()
        session[viewed_key] = True
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
        # S6：默认草稿（False）——知识库发布审核流；显式传 is_published=true 可直发
        is_published=bool(data.get('is_published', False)),
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
        if k.is_published:
            k.published_by = current_user.realname or current_user.username
            k.published_at = datetime.utcnow()
        else:
            # 下架：清发布人/时间，回到草稿
            k.published_by = ''
            k.published_at = None
    db.session.commit()
    return ok({'id': k.id})


@vue_api_bp.route('/api/knowledge-base/<int:kb_id>/publish', methods=['POST'])
@login_required
@require_permission('kb:edit')
def api_kb_publish(kb_id):
    """发布/下架知识库（发布审核流：草稿→发布；幂等）"""
    from models import KnowledgeBase as _KB
    k = _KB.query.get_or_404(kb_id)
    data = request.get_json(silent=True) or {}
    publish = bool(data.get('publish', True))
    k.is_published = publish
    if publish:
        k.published_by = current_user.realname or current_user.username
        k.published_at = datetime.utcnow()
    else:
        k.published_by = ''
        k.published_at = None
    db.session.commit()
    from blueprints.vue_api_sys import audit_log
    audit_log('kb:publish', 'kb', kb_id,
              f'知识库「{k.title}」{"发布" if publish else "下架"}')
    return ok({'id': k.id, 'is_published': k.is_published})


@vue_api_bp.route('/api/knowledge-base/<int:kb_id>', methods=['DELETE'])
@login_required
@require_permission('kb:delete')
def api_kb_delete(kb_id):
    from models import KnowledgeBase as _KB
    k = _KB.query.get_or_404(kb_id)
    current_app.logger.info(
        '知识条目删除审计(Vue): 用户[%s] 删除[%s](id=%s), IP=%s',
        current_user.username, k.title, k.id, request.remote_addr)
    # 先删磁盘物理附件（ORM 级联只删 DB 行）
    for att in list(k.attachments.all()):
        full = _kb_attachment_fullpath(att)
        if full:
            try:
                os.remove(full)
            except OSError:
                pass
    try:
        os.rmdir(os.path.join(KB_ATTACH_DIR, str(k.id)))
    except OSError:
        pass
    db.session.delete(k)
    db.session.commit()
    return ok(None)


# ==================== 知识库附件（V7 恢复：上传/预览/下载/删除） ====================
@vue_api_bp.route('/api/knowledge-base/<int:kb_id>/attachments', methods=['POST'])
@login_required
@require_permission('kb:edit')
def api_kb_attachment_upload(kb_id):
    """知识条目附件上传（multipart 多文件字段 files；扩展名白名单 + uuid 落盘）"""
    from models import KnowledgeBase as _KB, KnowledgeAttachment as _KA
    _KB.query.get_or_404(kb_id)
    files = request.files.getlist('files')
    if not files:
        return fail('未选择文件', 400)
    saved = _save_kb_attachments(files, kb_id)
    if not saved:
        return fail('没有可保存的附件（文件类型仅支持：PDF/Word/Excel/图片/TXT）', 400)
    me = current_user.realname or current_user.username
    for fname, fpath, ext, size in saved:
        db.session.add(_KA(knowledge_id=kb_id, file_name=fname, file_path=fpath,
                           file_ext=ext, file_size=size, uploaded_by=me))
    db.session.commit()
    atts = _KA.query.filter_by(knowledge_id=kb_id).order_by(_KA.id).all()
    return ok({'added': len(saved), 'attachments': _kb_attachments_payload(atts)})


@vue_api_bp.route('/api/knowledge-base/<int:kb_id>/attachments/<int:att_id>/preview', methods=['GET'])
@login_required
@require_permission('kb:view')
def api_kb_attachment_preview(kb_id, att_id):
    """附件在线预览（内联返回，前端 FilePreview 按扩展名渲染 PDF/图片/docx/txt）"""
    att = _get_kb_attachment(kb_id, att_id)
    full = _kb_attachment_fullpath(att)
    if full is None:
        abort(404)
    return send_from_directory(os.path.dirname(full), os.path.basename(full))


@vue_api_bp.route('/api/knowledge-base/<int:kb_id>/attachments/<int:att_id>/download', methods=['GET'])
@login_required
@require_permission('kb:view')
def api_kb_attachment_download(kb_id, att_id):
    """附件下载（原文件名）"""
    att = _get_kb_attachment(kb_id, att_id)
    full = _kb_attachment_fullpath(att)
    if full is None:
        abort(404)
    return send_from_directory(os.path.dirname(full), os.path.basename(full),
                               as_attachment=True, download_name=att.file_name)


@vue_api_bp.route('/api/knowledge-base/<int:kb_id>/attachments/<int:att_id>', methods=['DELETE'])
@login_required
@require_permission('kb:edit')
def api_kb_attachment_delete(kb_id, att_id):
    """删除附件（物理文件 + DB 行）"""
    att = _get_kb_attachment(kb_id, att_id)
    full = _kb_attachment_fullpath(att)
    if full:
        try:
            os.remove(full)
        except OSError:
            pass
    db.session.delete(att)
    db.session.commit()
    return ok(None)


@vue_api_bp.route('/api/dicts/knowledge', methods=['GET'])
@login_required
@require_permission('kb:view')
def api_kb_dicts():
    return ok({'categories': KB_CATEGORIES})


# ==================== 故障记录 ====================
def _fault_payload(f, customer_map=None, ticket_map=None):
    """ticket_map: {ticket_id: number}（列表端点批量构建，避免逐行查工单号）"""
    l1, l2, l3 = f.fault_category_level1 or '', f.fault_category_level2 or '', f.fault_category_level3 or ''
    category = '/'.join(x for x in (l1, l2, l3) if x) or ''
    return {
        'id': f.id,
        'title': f.title,
        'customer_id': f.customer_id,
        'customer_name': (customer_map or {}).get(f.customer_id, ''),
        'handler': f.handler or '',
        'fault_time': f.fault_time.strftime('%Y-%m-%d %H:%M') if f.fault_time else '',
        'fault_type': f.fault_type or '',
        'fault_category_level1': l1,
        'fault_category_level2': l2,
        'fault_category_level3': l3,
        'fault_category': category,
        'result': f.result or '',
        'impact_range': f.impact_range or '',
        'recovery_time': f.recovery_time.strftime('%Y-%m-%d %H:%M') if f.recovery_time else '',
        'created_at': f.created_at.strftime('%Y-%m-%d %H:%M') if f.created_at else '',
        'ticket_id': f.ticket_id,          # S6: 已转工单桥接（前端显示/防重复转单）
        'ticket_number': (ticket_map or {}).get(f.ticket_id, '') if f.ticket_id else '',
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
    category_l1 = (request.args.get('category_l1') or '').strip()
    result = (request.args.get('result') or '').strip()

    q = _F.query
    # S6 数据隔离：按用户范围收窄（Fault 无 created_by/assigned 用户字段时静默不过滤）
    from utils.permission import apply_scope_filter
    q = apply_scope_filter(q, _F, current_user)
    if search:
        q = q.filter(_F.title.contains(search))
    if fault_type:
        q = q.filter(_F.fault_type == fault_type)
    if category_l1:
        q = q.filter(_F.fault_category_level1 == category_l1)
    if result:
        q = q.filter(_F.result == result)
    total = q.count()
    rows = q.order_by(_F.fault_time.desc(), _F.id.desc()) \
        .offset((page - 1) * page_size).limit(page_size).all()
    customer_map = {c.id: c.name for c in _C.query.all()}
    # S6: 已转工单号批量映射（避免逐行查工单号 N+1）
    ticket_map = {}
    tid_set = {f.ticket_id for f in rows if f.ticket_id}
    if tid_set:
        from models import Ticket as _TK
        ticket_map = dict(db.session.query(_TK.id, _TK.number)
                          .filter(_TK.id.in_(tid_set)).all())
    return ok({'items': [_fault_payload(f, customer_map, ticket_map) for f in rows],
               'total': total, 'page': page, 'page_size': page_size})


@vue_api_bp.route('/api/faults/<int:fault_id>', methods=['GET'])
@login_required
@require_permission('fault:view')
def api_fault_get(fault_id):
    from models import Fault as _F
    f = _F.query.get_or_404(fault_id)
    ticket_map = {}
    if f.ticket_id:
        from models import Ticket as _TK
        tk = _TK.query.get(f.ticket_id)
        ticket_map = {f.ticket_id: tk.number} if tk else {}
    payload = _fault_payload(f, {f.customer_id: f.customer_rel.name if f.customer_rel else ''},
                             ticket_map)
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


@vue_api_bp.route('/api/faults/<int:fault_id>/convert', methods=['POST'])
@login_required
@require_permission('ticket:add')
def api_fault_convert(fault_id):
    """故障 → 工单（实时转单；幂等：已转单拒绝）。审计 + 返回工单号。"""
    from services.fault_service import convert_fault_to_ticket
    from models import Fault as _F
    f = _F.query.get_or_404(fault_id)
    try:
        t = convert_fault_to_ticket(fault_id, current_user.realname or current_user.username)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '转工单失败', 400)
    from blueprints.vue_api_sys import audit_log
    audit_log('fault:convert', 'fault', fault_id,
              f'故障「{f.title}」转为工单 #{t.number}')
    current_app.logger.info(
        '故障转工单审计: 用户[%s] 故障[%s](id=%s) → 工单[%s](id=%s), IP=%s',
        current_user.username, f.title, fault_id, t.number, t.id, request.remote_addr)
    return ok({'ticket_id': t.id, 'ticket_number': t.number})


def _fault_category_tree():
    """故障分类三级树（一次查全表，内存按 parent_id 组装）"""
    from models import FaultType as _FT
    rows = _FT.query.order_by(_FT.sort_order, _FT.id).all()
    by_id = {t.id: {'id': t.id, 'name': t.name, 'level': t.level,
                    'parent_id': t.parent_id, 'children': []} for t in rows}
    tree = []
    for t in rows:
        node = by_id[t.id]
        if t.parent_id and t.parent_id in by_id:
            by_id[t.parent_id]['children'].append(node)
        else:
            tree.append(node)
    return tree


@vue_api_bp.route('/api/dicts/faults', methods=['GET'])
@login_required
@require_permission('fault:view')
def api_fault_dicts():
    from utils.customer_scope import customer_dropdown_options
    fault_types = _fault_category_tree()
    customers = customer_dropdown_options(current_user)
    results = ['已解决', '待观察', '未解决']
    return ok({'fault_types': fault_types, 'customers': customers, 'results': results})


# ==================== 故障分类字典 CRUD（三级分级） ====================
def _fault_cat_payload(t):
    return {'id': t.id, 'name': t.name, 'parent_id': t.parent_id,
            'level': t.level, 'sort_order': t.sort_order}


@vue_api_bp.route('/api/fault-categories', methods=['GET'])
@login_required
@require_permission('fault:view')
def api_fault_category_list():
    return ok(_fault_category_tree())


@vue_api_bp.route('/api/fault-categories', methods=['POST'])
@login_required
@require_permission('fault:edit')
def api_fault_category_create():
    from models import FaultType as _FT
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return fail('分类名称不能为空', 400)
    parent_id = int(data['parent_id']) if data.get('parent_id') else None
    level = int(data.get('level') or 1)
    if parent_id:
        parent = _FT.query.get(parent_id)
        if not parent:
            return fail('上级分类不存在', 404)
        level = (parent.level or 1) + 1
        if level > 3:
            return fail('最多支持三级分类', 400)
    if _FT.query.filter_by(name=name, parent_id=parent_id).first():
        return fail('同级下已存在同名分类', 400)
    t = _FT(name=name, parent_id=parent_id, level=level,
            sort_order=int(data.get('sort_order') or 0))
    db.session.add(t)
    db.session.commit()
    return ok({'id': t.id})


@vue_api_bp.route('/api/fault-categories/<int:cat_id>', methods=['PUT'])
@login_required
@require_permission('fault:edit')
def api_fault_category_update(cat_id):
    from models import FaultType as _FT
    t = _FT.query.get_or_404(cat_id)
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if name:
        dup = _FT.query.filter_by(name=name, parent_id=t.parent_id).first()
        if dup and dup.id != t.id:
            return fail('同级下已存在同名分类', 400)
        t.name = name
    if 'parent_id' in data:
        parent_id = int(data['parent_id']) if data.get('parent_id') else None
        if parent_id == t.id:
            return fail('上级分类不能是自身', 400)
        if parent_id:
            parent = _FT.query.get(parent_id)
            if not parent:
                return fail('上级分类不存在', 404)
            t.level = (parent.level or 1) + 1
            if t.level > 3:
                return fail('最多支持三级分类', 400)
        else:
            t.parent_id = None
            t.level = 1
        t.parent_id = parent_id
    if data.get('sort_order') is not None:
        t.sort_order = int(data['sort_order'])
    db.session.commit()
    return ok(None)


@vue_api_bp.route('/api/fault-categories/<int:cat_id>', methods=['DELETE'])
@login_required
@require_permission('fault:edit')
def api_fault_category_delete(cat_id):
    from models import FaultType as _FT, Fault as _F
    t = _FT.query.get_or_404(cat_id)
    if _FT.query.filter_by(parent_id=cat_id).first():
        return fail('该分类下存在子分类，请先删除子分类', 400)
    if _F.query.filter((_F.fault_category_level1 == t.name)
                       | (_F.fault_category_level2 == t.name)
                       | (_F.fault_category_level3 == t.name)).first():
        return fail('该分类已被故障记录引用，无法删除', 400)
    db.session.delete(t)
    db.session.commit()
    return ok(None)


# ==================== 报告中心 ====================
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORTS_DIR = os.path.join(_BASE_DIR, 'reports')
UPLOADS_DIR = os.path.join(_BASE_DIR, 'static', 'uploads')
_REPORT_TABS = ('all', 'inspection', 'fault', 'ticket', 'file')


def _customer_of(rel):
    return (rel.id, rel.name) if rel else (None, '未关联客户')


def _date_in_window(d, date_from, date_to):
    if not d:
        return True
    d = d.date() if isinstance(d, datetime) else d
    return (not date_from or str(d) >= date_from) and (not date_to or str(d) <= date_to)


def _as_dt(v):
    """统一排序时间：date/datetime → datetime（None 用最小时间兜底）"""
    if isinstance(v, datetime):
        return v
    if v:
        return datetime.combine(v, datetime.min.time())
    return datetime.min


def _report_download(rel_path):
    """把记录的报告路径解析为 (文件名, 下载 URL)；支持 reports/ 根目录与 static/uploads 两种存储。"""
    if not rel_path:
        return None
    v = str(rel_path).strip().replace('\\', '/')
    if not v:
        return None
    name = os.path.basename(v)
    root_full = os.path.realpath(os.path.join(REPORTS_DIR, name))
    root_base = os.path.realpath(REPORTS_DIR)
    if root_full.startswith(root_base + os.sep) and os.path.isfile(root_full):
        return (name, '/reports/' + quote(name))
    if v.startswith('static/uploads/'):
        upload_rel = v[len('static/'):]
    elif v.startswith('uploads/'):
        upload_rel = v
    else:
        upload_rel = 'uploads/' + name
    upload_full = os.path.realpath(os.path.join(UPLOADS_DIR, upload_rel[len('uploads/'):]))
    upload_base = os.path.realpath(UPLOADS_DIR)
    if upload_full.startswith(upload_base + os.sep) and os.path.isfile(upload_full):
        return (name, '/api/reports/file/' + quote(upload_rel[len('uploads/'):]))
    return None


def _scan_report_files(date_from, date_to, customer_id, search):
    """扫描 reports/ 与 static/uploads 下报告目录，返回报告文件行（含归属客户）。

    文件反查索引覆盖：正式报告（report_file）、工程师上传现场报告（submitted_report）、
    提交版本留档（submission_versions.report_file）。
    """
    from models import Inspection as _I, Fault as _F, Ticket as _T, SubmissionVersion as _SV

    def _normkey(p):
        return os.path.normcase(os.path.normpath(p)) if p else ''

    file_to_record = {}

    def _index_file(v, rec):
        v = (v or '').strip().replace('\\', '/')
        if not v:
            return
        cands = {v, os.path.basename(v), _normkey(v), _normkey(os.path.basename(v))}
        if not v.startswith('uploads/'):
            cands.add(_normkey(os.path.join('uploads', v)))
        for c in cands:
            if c and c not in file_to_record:
                file_to_record[c] = rec

    def _scan_model(Mdl, cols):
        conds = [getattr(Mdl, c).isnot(None) & (getattr(Mdl, c) != '') for c in cols]
        for rec in Mdl.query.options(joinedload(Mdl.customer_rel)).filter(or_(*conds)).all():
            for c in cols:
                _index_file(getattr(rec, c), rec)

    _scan_model(_I, ('report_file', 'submitted_report'))
    _scan_model(_F, ('report_file',))
    _scan_model(_T, ('report_file',))

    # 提交版本里的历史报告文件（补漏：旧数据可能只在版本里留档）
    sv_rows = _SV.query.filter(_SV.report_file.isnot(None), _SV.report_file != '').all()
    if sv_rows:
        recs = {}
        for et, Mdl in (('inspection', _I), ('ticket', _T)):
            ids = [r.entity_id for r in sv_rows if r.entity_type == et]
            if not ids:
                continue
            for rec in Mdl.query.options(joinedload(Mdl.customer_rel)).filter(Mdl.id.in_(ids)).all():
                recs[(et, rec.id)] = rec
        for sv in sv_rows:
            rec = recs.get((sv.entity_type, sv.entity_id))
            if rec:
                _index_file(sv.report_file, rec)

    scan_dirs = [REPORTS_DIR]
    for sub in ('inspection_reports', 'ticket_reports'):
        d = os.path.join(UPLOADS_DIR, sub)
        if os.path.isdir(d):
            scan_dirs.append(d)

    out = []
    for d in scan_dirs:
        if not os.path.isdir(d):
            continue
        for root, _subs, names in os.walk(d):
            for fname in sorted(names, reverse=True):
                full = os.path.join(root, fname)
                if not os.path.isfile(full):
                    continue
                mtime = datetime.fromtimestamp(os.path.getmtime(full))
                if not _date_in_window(mtime, date_from, date_to):
                    continue
                rec = file_to_record.get(_normkey(full)) or file_to_record.get(_normkey(fname))
                if customer_id:
                    if not rec or rec.customer_id != customer_id:
                        continue
                if search and search not in fname:
                    continue
                ftype = '巡检' if '巡检' in fname else ('故障' if '故障' in fname else '其他')
                cid, cname = _customer_of(rec.customer_rel) if rec else (None, '未关联客户')
                if d == REPORTS_DIR:
                    url = '/reports/' + quote(fname)
                else:
                    rel = os.path.relpath(full, UPLOADS_DIR).replace(os.sep, '/')
                    url = '/api/reports/file/' + quote(rel)
                size = os.path.getsize(full)
                out.append({
                    'customer_id': cid, 'customer_name': cname,
                    'id': full, 'type': 'file',
                    'title': fname,
                    'date': mtime.strftime('%Y-%m-%d %H:%M'),
                    'status': ftype + '报告' if ftype != '其他' else '其他',
                    'report_name': fname,
                    'report_url': url,
                    'has_report': True,
                    'size_display': f'{size / 1024:.1f} KB',
                    'deletable': d == REPORTS_DIR,
                    '_sort_dt': mtime,
                })
    return out


@vue_api_bp.route('/api/reports/file/<path:rel_path>')
@login_required
@require_permission('report:view')
def api_report_file_download(rel_path):
    """报告中心通用下载：static/uploads 下上传的报告文件（realpath 防路径穿越）"""
    full = os.path.realpath(os.path.join(UPLOADS_DIR, rel_path))
    base = os.path.realpath(UPLOADS_DIR)
    if not full.startswith(base + os.sep) or not os.path.isfile(full):
        return fail('文件不存在', 404)
    return send_from_directory(os.path.dirname(full), os.path.basename(full), as_attachment=True)


@vue_api_bp.route('/api/reports', methods=['GET'])
@login_required
@require_permission('report:view')
def api_reports():
    """报告中心统一列表：巡检/故障/工单/报告文件四类记录分页聚合（列表式，每行可下载报告）。

    对齐 DataTable 契约返回 {items, total, stats}；文件反查索引覆盖正式报告（report_file）
    与工程师上传现场报告（submitted_report / submission_versions），修复「有报告却显示无报告」。
    """
    from models import Inspection as _I, Fault as _F, Ticket as _T

    tab = (request.args.get('tab') or 'all').strip()
    if tab not in _REPORT_TABS:
        tab = 'all'
    date_from = (request.args.get('date_from') or '').strip()
    date_to = (request.args.get('date_to') or '').strip()
    customer_id = request.args.get('customer_id', type=int)
    search = (request.args.get('search') or '').strip()
    page = max(1, request.args.get('page', 1, type=int))
    page_size = min(200, max(1, request.args.get('page_size', 20, type=int)))

    # 性能：首次进入（无任何过滤条件）默认只看近 12 个月，避免三表全量扫描
    if not date_from and not date_to and not customer_id:
        date_from = (datetime.now().date() - timedelta(days=365)).isoformat()

    rows = []

    def _add(cid, cname, payload):
        rows.append({'customer_id': cid, 'customer_name': cname, **payload})

    if tab in ('all', 'inspection'):
        q = _I.query.options(joinedload(_I.customer_rel))
        if date_from:
            q = q.filter(_I.inspection_date >= date_from)
        if date_to:
            q = q.filter(_I.inspection_date <= date_to)
        if customer_id:
            q = q.filter(_I.customer_id == customer_id)
        if search:
            q = q.filter(_I.title.ilike(f'%{search}%'))
        for i in q.order_by(_I.inspection_date.desc(), _I.id.desc()).all():
            cid, cname = _customer_of(i.customer_rel)
            rep = _report_download(i.report_file) or _report_download(i.submitted_report)
            _add(cid, cname, {
                'id': i.id, 'type': 'inspection',
                'title': i.title,
                'date': i.inspection_date.strftime('%Y-%m-%d') if i.inspection_date else '',
                'status': i.review_status or '',
                'report_name': rep[0] if rep else '',
                'report_url': rep[1] if rep else '',
                'has_report': bool(rep),
                'size_display': '',
                '_sort_dt': _as_dt(i.inspection_date),
            })

    if tab in ('all', 'fault'):
        q = _F.query.options(joinedload(_F.customer_rel))
        if date_from:
            q = q.filter(_F.fault_time >= date_from)
        if date_to:
            q = q.filter(_F.fault_time <= date_to)
        if customer_id:
            q = q.filter(_F.customer_id == customer_id)
        if search:
            q = q.filter(_F.title.ilike(f'%{search}%'))
        for f in q.order_by(_F.fault_time.desc(), _F.id.desc()).all():
            cid, cname = _customer_of(f.customer_rel)
            rep = _report_download(f.report_file)
            _add(cid, cname, {
                'id': f.id, 'type': 'fault',
                'title': f.title,
                'date': f.fault_time.strftime('%Y-%m-%d %H:%M') if f.fault_time else '',
                'status': f.result or '',
                'report_name': rep[0] if rep else '',
                'report_url': rep[1] if rep else '',
                'has_report': bool(rep),
                'size_display': '',
                '_sort_dt': _as_dt(f.fault_time),
            })

    if tab in ('all', 'ticket'):
        q = _T.query.options(joinedload(_T.customer_rel))
        if date_from:
            q = q.filter(_T.created_at >= date_from)
        if date_to:
            q = q.filter(_T.created_at <= date_to)
        if customer_id:
            q = q.filter(_T.customer_id == customer_id)
        if search:
            q = q.filter(_T.title.ilike(f'%{search}%'))
        for t in q.order_by(_T.created_at.desc(), _T.id.desc()).all():
            cid, cname = _customer_of(t.customer_rel)
            rep = _report_download(t.report_file)
            _add(cid, cname, {
                'id': t.id, 'type': 'ticket',
                'title': f'{t.number} · {t.title}',
                'date': t.created_at.strftime('%Y-%m-%d %H:%M') if t.created_at else '',
                'status': t.status or '',
                'report_name': rep[0] if rep else '',
                'report_url': rep[1] if rep else '',
                'has_report': bool(rep),
                'size_display': '',
                '_sort_dt': _as_dt(t.created_at),
            })

    if tab in ('all', 'file'):
        rows.extend(_scan_report_files(date_from, date_to, customer_id, search))

    # 统一按时间倒序（记录按各自日期，文件按修改时间）
    rows.sort(key=lambda r: r.get('_sort_dt') or datetime.min, reverse=True)
    for r in rows:
        r.pop('_sort_dt', None)

    total = len(rows)
    stats = {'customers': len({r['customer_id'] for r in rows}), 'total': total}
    items = rows[(page - 1) * page_size: page * page_size]
    return ok({'items': items, 'total': total, 'stats': stats})

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
    try:
        required = json.loads(t.required_assets_json or '{}')
    except Exception:
        required = {}
    return {
        'id': t.id,
        'name': t.name,
        'category': t.category or '',
        'inspection_type': t.inspection_type or '',
        'frequency': t.frequency or '',
        'customer_tier': t.customer_tier or 'all',
        'sections': sections.get('sections', []),
        'required_assets': required,
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
        required_assets_json=json.dumps(data.get('required_assets') or {}, ensure_ascii=False),
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
    if 'required_assets' in data:
        t.required_assets_json = json.dumps(data.get('required_assets') or {}, ensure_ascii=False)
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
        'reviewing': sum(1 for t in items if t['status'] == '待审核'),
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
        groups = {st: [t for t in items if t['status'] == st] for st in ('待执行', '执行中', '待审核', '已完成')}
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
    # V28: 客户合同过期门禁 → 合同审批态（需部门主管审核放行）
    from utils.constants import TASK_CONTRACT_REVIEW, TASK_PENDING
    from utils.customer_contract import contract_expired as _ce
    from models import Customer as _C
    status = TASK_PENDING
    exception_reason = (data.get('contract_exception_reason') or '').strip()
    cust = _C.query.get(int(customer_id)) if customer_id else None
    if cust is not None and _ce(cust):
        if not exception_reason:
            return fail('该客户合同已过期，请填写合同例外原因后提交（需部门主管审核）')
        status = TASK_CONTRACT_REVIEW
    t = _IT(
        title=title,
        task_type=(data.get('task_type') or '计划').strip() or '计划',
        status=status,
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
        contract_exception_status='待审核' if status == TASK_CONTRACT_REVIEW else '',
        contract_exception_reason=exception_reason,
        contract_exception_by=(current_user.realname or current_user.username),
        contract_exception_at=local_now() if status == TASK_CONTRACT_REVIEW else None,
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
        from services.task_schedule_service import apply_task_status
        try:
            apply_task_status(t, data['status'])
        except ValueError as e:
            db.session.rollback()
            return fail(str(e), 400)
    if data.get('assignee_id') is not None:
        old_uid = t.assigned_to_user_id
        t.assigned_to_user_id = data['assignee_id'] or None
        t.dispatched_by = t.dispatched_by or current_user.id
        t.dispatched_at = t.dispatched_at or local_now()
        # 事件源：任务指派通知（新指派且非本人）
        new_uid = t.assigned_to_user_id
        if new_uid and new_uid != old_uid and new_uid != current_user.id:
            try:
                from utils.notifications import notify
                notify(new_uid, 'inspection', f'新任务指派：{t.title}',
                       f'计划时间 {t.planned_start or "-"} ~ {t.planned_end or "-"}，请及时处理',
                       '/app/task-schedule')
                from utils.wecom_notify import wecom_broadcast, EVENT_INSPECTION_ASSIGN
                wecom_broadcast(EVENT_INSPECTION_ASSIGN,
                                f'巡检任务指派：{t.title}',
                                f'计划时间 {t.planned_start or "-"} ~ {t.planned_end or "-"}，请及时处理',
                                '/app/task-schedule',
                                target_user_ids=[new_uid])
            except Exception:
                current_app.logger.warning('任务指派通知失败 task_id=%s', task_id)
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
    if t.records:
        return fail('该任务已有巡检记录，请先删除关联记录再删除任务', 400)
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
        from services.task_schedule_service import apply_task_status
        if value not in ('待执行', '执行中', '待审核', '已完成', '已取消'):
            return fail('非法的状态', 400)
        for t in tasks:
            try:
                apply_task_status(t, value)
            except ValueError as e:
                db.session.rollback()
                return fail(str(e), 400)
    elif action == 'assign':
        for t in tasks:
            t.assigned_to_user_id = value or None
            t.dispatched_by = t.dispatched_by or current_user.id
            t.dispatched_at = t.dispatched_at or local_now()
    elif action == 'delete':
        for t in tasks:
            if t.records:
                db.session.rollback()
                return fail(f'任务「{t.title}」已有巡检记录，请先删除关联记录再删除任务', 400)
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
