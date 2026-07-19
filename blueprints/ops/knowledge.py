# -*- coding: utf-8 -*-
"""知识库 CRUD + 附件上传/预览/下载/删除"""
import os
from flask import (render_template, request, redirect, url_for,
                   flash, send_from_directory, abort, session)
from flask_login import login_required, current_user
from sqlalchemy import text as sa_text
from models import (Fault, Ticket,
                    KnowledgeBase, KnowledgeAttachment, db)
from utils.pagination import paginate, paginate_render_args
from utils.permission import require_permission
from blueprints.ops import ops_bp


# V7 知识库附件保存目录（目录由 create_app 的 _ensure_runtime_dirs 统一创建，消除导入副作用）
KB_ATTACH_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             'static', 'uploads', 'knowledge')
ALLOWED_KB_EXTS = {'.pdf', '.doc', '.docx', '.xls', '.xlsx',
                   '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.txt'}


def _save_kb_attachments(files, kb_id, uploader):
    """保存知识库多个附件，返回 [(file_name, file_path, ext, size), ...]"""
    saved = []
    if not files:
        return saved
    sub_dir = os.path.join(KB_ATTACH_DIR, str(kb_id))
    os.makedirs(sub_dir, exist_ok=True)
    import uuid as _uuid
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
        size = os.path.getsize(full)
        saved.append((f.filename, rel_path, ext, size))
    return saved


# ============================ 知识库 ============================
@ops_bp.route('/knowledge-base')
@login_required
@require_permission('kb:view')
def knowledge_base_list():
    search = request.args.get('search', '')
    category = request.args.get('category', '')
    page = request.args.get('page', 1, type=int)
    query = KnowledgeBase.query
    if search:
        query = query.filter(KnowledgeBase.title.contains(search) | KnowledgeBase.content.contains(search))
    if category:
        query = query.filter(KnowledgeBase.category == category)
    query = query.order_by(KnowledgeBase.id.desc())
    pag = paginate(query, page=page)
    return render_template('knowledge_base/list.html', **paginate_render_args(pag),
                           search=search, category=category)


@ops_bp.route('/knowledge-base/add', methods=['GET', 'POST'])
@login_required
@require_permission('kb:add')
def knowledge_base_add():
    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()
        if not title:
            flash('标题不能为空', 'danger')
            return redirect(url_for('ops.knowledge_base_add'))
        kb = KnowledgeBase(
            title=title,
            category=request.form.get('category', '其他'),
            content=request.form.get('content', ''),
            tags=request.form.get('tags', ''),
            related_device_type=request.form.get('related_device_type', ''),
            related_ticket_id=int(request.form['related_ticket_id']) if request.form.get('related_ticket_id') else None,
            related_fault_id=int(request.form['related_fault_id']) if request.form.get('related_fault_id') else None,
            is_published=bool(request.form.get('is_published')),
            created_by=current_user.realname or current_user.username,
        )
        db.session.add(kb); db.session.commit()
        # V7：保存附件
        files = request.files.getlist('attachments')
        for fname, fpath, ext, size in _save_kb_attachments(files, kb.id,
                                                             current_user.realname or current_user.username):
            db.session.add(KnowledgeAttachment(
                knowledge_id=kb.id, file_name=fname, file_path=fpath,
                file_ext=ext, file_size=size,
                uploaded_by=current_user.realname or current_user.username,
            ))
        if files:
            db.session.commit()
        flash('知识条目已添加', 'success')
        return redirect(url_for('ops.knowledge_base_list'))
    return render_template('knowledge_base/form.html', kb=None)


@ops_bp.route('/knowledge-base/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@require_permission('kb:edit')
def knowledge_base_edit(id):
    kb = KnowledgeBase.query.get_or_404(id)
    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()
        if not title:
            flash('标题不能为空', 'danger')
            return redirect(url_for('ops.knowledge_base_edit', id=id))
        kb.title = title
        kb.category = request.form.get('category', kb.category or '其他')
        kb.content = request.form.get('content', '')
        kb.tags = request.form.get('tags', '')
        kb.related_device_type = request.form.get('related_device_type', '')
        kb.is_published = bool(request.form.get('is_published'))
        # V7：追加附件
        files = request.files.getlist('attachments')
        for fname, fpath, ext, size in _save_kb_attachments(files, kb.id,
                                                             current_user.realname or current_user.username):
            db.session.add(KnowledgeAttachment(
                knowledge_id=kb.id, file_name=fname, file_path=fpath,
                file_ext=ext, file_size=size,
                uploaded_by=current_user.realname or current_user.username,
            ))
        db.session.commit()
        flash('知识条目已更新', 'success')
        return redirect(url_for('ops.knowledge_base_list'))
    return render_template('knowledge_base/form.html', kb=kb)


@ops_bp.route('/knowledge-base/<int:id>')
@login_required
@require_permission('kb:view')
def knowledge_base_detail(id):
    kb = KnowledgeBase.query.get_or_404(id)
    # 浏览次数 +1：原子 UPDATE，避免 read-modify-write 并发丢失；session 去重（1 小时内同人重复访问不计）
    viewed_key = f'kb_viewed_{id}'
    if not session.get(viewed_key):
        db.session.execute(
            sa_text('UPDATE knowledge_base SET view_count = COALESCE(view_count, 0) + 1 WHERE id = :kid'),
            {'kid': id})
        db.session.commit()
        session[viewed_key] = True
        kb.view_count = (kb.view_count or 0) + 1  # 页面展示同步
    ticket = Ticket.query.get(kb.related_ticket_id) if kb.related_ticket_id else None
    fault = Fault.query.get(kb.related_fault_id) if kb.related_fault_id else None
    return render_template('knowledge_base/detail.html', kb=kb, ticket=ticket, fault=fault)


@ops_bp.route('/knowledge-base/delete/<int:id>', methods=['POST'])
@login_required
@require_permission('kb:delete')
def knowledge_base_delete(id):
    # V7：先删除物理附件
    kb = KnowledgeBase.query.get_or_404(id)
    for att in kb.attachments:
        full = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            'static', att.file_path)
        try:
            if os.path.isfile(full):
                os.remove(full)
        except Exception:
            pass
    db.session.delete(kb)
    db.session.commit()
    flash('已删除', 'success')
    return redirect(url_for('ops.knowledge_base_list'))


# ============== V7 知识库附件端点 ==============
@ops_bp.route('/knowledge-base/<int:kb_id>/attachment/<int:att_id>/preview')
@login_required
@require_permission('kb:view')
def knowledge_base_attachment_preview(kb_id, att_id):
    """PDF/图片浏览器内嵌预览"""
    att = KnowledgeAttachment.query.get_or_404(att_id)
    if att.knowledge_id != kb_id:
        abort(404)
    static_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    full = os.path.join(static_dir, 'static', att.file_path)
    if not os.path.isfile(full):
        abort(404)
    if att.file_ext in ('.pdf',):
        return send_from_directory(os.path.dirname(full), os.path.basename(full),
                                   mimetype='application/pdf')
    if att.file_ext in ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'):
        # 用 send_file + as_attachment=False 内联
        from flask import send_file
        return send_file(full)
    abort(415)  # 不支持预览的类型


@ops_bp.route('/knowledge-base/<int:kb_id>/attachment/<int:att_id>/download')
@login_required
@require_permission('kb:view')
def knowledge_base_attachment_download(kb_id, att_id):
    att = KnowledgeAttachment.query.get_or_404(att_id)
    if att.knowledge_id != kb_id:
        abort(404)
    static_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    full_dir = os.path.join(static_dir, 'static', os.path.dirname(att.file_path))
    return send_from_directory(full_dir, os.path.basename(att.file_path),
                               as_attachment=True, download_name=att.file_name)


@ops_bp.route('/knowledge-base/<int:kb_id>/attachment/<int:att_id>/delete', methods=['POST'])
@login_required
@require_permission('kb:edit')
def knowledge_base_attachment_delete(kb_id, att_id):
    att = KnowledgeAttachment.query.get_or_404(att_id)
    if att.knowledge_id != kb_id:
        abort(404)
    static_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    full = os.path.join(static_dir, 'static', att.file_path)
    try:
        if os.path.isfile(full):
            os.remove(full)
    except Exception:
        pass
    db.session.delete(att)
    db.session.commit()
    flash('附件已删除', 'success')
    return redirect(url_for('ops.knowledge_base_detail', id=kb_id))


