# -*- coding: utf-8 -*-
"""拓扑图蓝图：上传式拓扑图管理 + V20 在线绘制（drawio 集成）

路由前缀为空（沿用 /topologies/* 原路径，从 app.py 迁移而来）。
上传逻辑与原 app.py 完全一致；在线绘制 API 在 P2 接入。
"""
import os
import time
import base64
from datetime import date

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, jsonify, current_app)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from models import Topology, Customer, Region, db
from utils.permission import require_permission, has_permission
from utils.upload import ALLOWED_IMAGE_EXT

topology_bp = Blueprint('topology', __name__)


# ============================ 列表 / 上传 ============================
@topology_bp.route('/topologies', methods=['GET', 'POST'])
@login_required
@require_permission('topology:view')
def topology_list():
    if request.method == 'POST':
        f = request.files.get('topo_file')
        if f and f.filename:
            safe_name = secure_filename(f.filename)
            upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'topologies')
            os.makedirs(upload_dir, exist_ok=True)
            f.save(os.path.join(upload_dir, safe_name))
            t = Topology(
                name=request.form.get('name') or safe_name,
                description=request.form.get('description', ''),
                customer_id=request.form.get('customer_id', type=int),
                region_id=request.form.get('region_id', type=int),
                file_path=f'uploads/topologies/{safe_name}',
                file_type='image' if safe_name.lower().endswith(
                    ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp')) else 'other',
                upload_by=current_user.username,
            )
            db.session.add(t)
            db.session.commit()
            flash(f'拓扑图 {t.name} 已上传', 'success')
        return redirect(url_for('topology.topology_list'))
    topologies = Topology.query.order_by(Topology.id.desc()).all()
    all_customers = Customer.query.order_by(Customer.name).all()
    regions = Region.query.order_by(Region.parent_id.is_(None).desc(),
                                    Region.parent_id, Region.sort_order, Region.id).all()
    search = (request.args.get('search') or '').strip().lower()
    if search:
        topologies = [t for t in topologies if
                      search in (t.name or '').lower() or
                      search in (t.description or '').lower() or
                      search in (t.customer_rel.name if t.customer_rel else '').lower()]

    # V6.1.1：相同 客户+名称 合并为一行（多文件类型用图标列表展示）
    grouped_dict = {}
    for t in topologies:
        cust_name = t.customer_rel.name if t.customer_rel else '未关联客户'
        bucket = grouped_dict.setdefault(cust_name, {})
        merged = bucket.setdefault(t.name, {'first': t, 'files': []})
        merged['files'].append(t)
        if (merged['first'].created_at or merged['first'].id) > (t.created_at or t.id):
            merged['first'] = t

    grouped = []
    for cust_name in sorted(grouped_dict.keys(), key=lambda x: (x == '未关联客户', x)):
        items = []
        for topo_name, m in grouped_dict[cust_name].items():
            order = {'image': 0, 'pdf': 1, 'visio': 2, 'other': 3}
            files_sorted = sorted(m['files'], key=lambda x: (order.get(x.file_type, 9), x.id))
            items.append({
                'name': topo_name,
                'first': m['first'],
                'files': files_sorted,
            })
        items.sort(key=lambda x: x['first'].id, reverse=True)
        grouped.append((cust_name, items))

    return render_template('topologies/list.html', topologies=topologies,
                           grouped=grouped, search=search,
                           all_customers=all_customers, regions=regions)


@topology_bp.route('/topologies/delete/<int:id>', methods=['POST'])
@login_required
@require_permission('topology:delete')
def topology_delete(id):
    Topology.query.filter_by(id=id).delete()
    db.session.commit()
    flash('已删除', 'success')
    return redirect(url_for('topology.topology_list'))


@topology_bp.route('/topologies/upload', methods=['POST'])
@login_required
@require_permission('topology:add')
def topology_upload():
    """拓扑图上传（保存到 DB + 静态目录）"""
    f = request.files.get('topo_file')
    if not f or not f.filename:
        flash('请选择文件', 'danger')
        return redirect(url_for('topology.topology_list'))

    name_lower = f.filename.lower()
    if name_lower.endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp')):
        file_type = 'image'
        allowed = ALLOWED_IMAGE_EXT
    elif name_lower.endswith('.pdf'):
        file_type = 'pdf'
        allowed = {'.pdf'}
    elif name_lower.endswith(('.vsd', '.vsdx')):
        file_type = 'visio'
        allowed = {'.vsd', '.vsdx'}
    else:
        file_type = 'other'
        allowed = set()

    ext = os.path.splitext(name_lower)[1]
    if allowed and ext not in allowed:
        flash(f'不支持的文件类型 {ext}', 'danger')
        return redirect(url_for('topology.topology_list'))

    upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'topologies')
    os.makedirs(upload_dir, exist_ok=True)
    safe_name = secure_filename(f.filename) or ('topology' + ext)
    # 防止重名覆盖：加时间戳
    base, e = os.path.splitext(safe_name)
    safe_name = f"{base}_{int(time.time())}{e}"
    full_path = os.path.join(upload_dir, safe_name)
    f.save(full_path)

    customer_id = request.form.get('customer_id', type=int)
    region_id = request.form.get('region_id', type=int)
    topo_type = request.form.get('topo_type', '网络拓扑图')
    user_name = (request.form.get('name') or '').strip()

    # 自动拼接名称：客户名称 + 拓扑图类型 + 年月日
    if not user_name:
        cust_name = ''
        if customer_id:
            c = Customer.query.get(customer_id)
            if c:
                cust_name = c.name
        today_str = date.today().strftime('%Y%m%d')
        user_name = f"{cust_name}{topo_type}{today_str}" if cust_name else f"{topo_type}{today_str}"

    t = Topology(
        name=user_name,
        description=request.form.get('description', ''),
        customer_id=customer_id,
        region_id=region_id,
        file_path=f'uploads/topologies/{safe_name}',
        file_type=file_type,
        upload_by=current_user.username,
    )
    db.session.add(t)
    db.session.commit()
    flash(f'拓扑图「{t.name}」已上传', 'success')
    return redirect(url_for('topology.topology_list'))


# ============================ 在线编辑（drawio 集成） ============================
@topology_bp.route('/topologies/editor/<int:id>')
@login_required
@require_permission('topology:view')
def topology_editor(id):
    """在线拓扑编辑器

    id=0 新建；id>0 编辑已有在线图。
    查询参数 import=<topo_id>：从已上传的 Visio/图片文件导入后在线编辑（另存为新在线图）。
    """
    import glob
    all_customers = Customer.query.order_by(Customer.name).all()
    regions = Region.query.order_by(Region.parent_id.is_(None).desc(),
                                    Region.parent_id, Region.sort_order, Region.id).all()

    # 扫描 static/stencils/*.drawio.xml 作为自定义图标库
    stencil_dir = os.path.join(current_app.root_path, 'static', 'stencils')
    clibs = ''
    stencil_urls = []
    if os.path.isdir(stencil_dir):
        stencil_urls = [url_for('static', filename='stencils/' + os.path.basename(f))
                        for f in sorted(glob.glob(os.path.join(stencil_dir, '*.drawio.xml')))]
        clibs = ';'.join('U:' + u for u in stencil_urls)

    # 导入模式：从已上传文件导入
    import_url = None
    import_name = None
    import_customer_id = None
    import_region_id = None
    import_type = None  # visio | image | None
    import_topo_id = request.args.get('import', type=int)
    if import_topo_id:
        t = Topology.query.get_or_404(import_topo_id)
        if t.file_path:
            import_url = url_for('static', filename=t.file_path)
            import_name = t.name
            import_customer_id = t.customer_id
            import_region_id = t.region_id
            fp_lower = (t.file_path or '').lower()
            if fp_lower.endswith(('.vsd', '.vsdx')):
                import_type = 'visio'
            elif fp_lower.endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp')):
                import_type = 'image'

    return render_template('topologies/editor.html',
                           diagram_id=id, all_customers=all_customers, regions=regions,
                           clibs=clibs, stencil_urls=stencil_urls,
                           import_url=import_url, import_name=import_name,
                           import_customer_id=import_customer_id,
                           import_region_id=import_region_id,
                           import_type=import_type)


@topology_bp.route('/topologies/api/diagram/<int:id>')
@login_required
@require_permission('topology:view')
def api_diagram_load(id):
    """加载在线拓扑图 XML"""
    t = Topology.query.get_or_404(id)
    if t.source != 'draw':
        return jsonify({'ok': False, 'error': '该拓扑图为上传文件，不支持在线编辑'}), 400
    return jsonify({
        'ok': True,
        'id': t.id,
        'name': t.name,
        'description': t.description or '',
        'customer_id': t.customer_id,
        'region_id': t.region_id,
        'diagram_xml': t.diagram_xml or '',
    })


@topology_bp.route('/topologies/api/diagram', methods=['POST'])
@login_required
def api_diagram_save():
    """保存在线拓扑图（新建或更新）

    新建需 topology:add，更新需 topology:edit。
    body: {id?, name, description, customer_id, region_id, diagram_xml}
    """
    data = request.get_json(silent=True) or {}
    topo_id = int(data.get('id') or 0)
    required_perm = 'topology:edit' if topo_id else 'topology:add'
    if not has_permission(required_perm):
        return jsonify({'ok': False, 'error': '权限不足（需要：' + required_perm + '）'}), 403

    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'ok': False, 'error': '名称不能为空'}), 400
    diagram_xml = data.get('diagram_xml') or ''
    if not diagram_xml.strip():
        return jsonify({'ok': False, 'error': '图内容为空'}), 400

    customer_id = data.get('customer_id') or None
    region_id = data.get('region_id') or None

    if topo_id:
        t = Topology.query.get_or_404(topo_id)
        if t.source != 'draw':
            return jsonify({'ok': False, 'error': '该拓扑图为上传文件，不支持在线编辑'}), 400
        t.name = name
        t.description = data.get('description', '')
        t.customer_id = customer_id
        t.region_id = region_id
        t.diagram_xml = diagram_xml
    else:
        t = Topology(
            name=name,
            description=data.get('description', ''),
            customer_id=customer_id,
            region_id=region_id,
            diagram_xml=diagram_xml,
            source='draw',
            file_type='other',
            upload_by=current_user.username,
        )
        db.session.add(t)
        db.session.flush()  # 拿到 id，供缩略图命名用

    db.session.commit()
    return jsonify({'ok': True, 'id': t.id})


@topology_bp.route('/topologies/api/export-file', methods=['POST'])
@login_required
@require_permission('topology:edit')
def api_diagram_export_file():
    """保存在线拓扑图导出文件（PDF/VSDX/PNG 缩略图，base64 data URL → 文件）

    body: {id, format: 'pdf'|'vsdx'|'png', data: 'data:...;base64,...'}
    """
    data = request.get_json(silent=True) or {}
    topo_id = int(data.get('id') or 0)
    fmt = (data.get('format') or '').lower()
    t = Topology.query.get_or_404(topo_id)
    if t.source != 'draw':
        return jsonify({'ok': False, 'error': '非在线图'}), 400
    if fmt not in ('pdf', 'vsdx', 'png'):
        return jsonify({'ok': False, 'error': '不支持的格式: ' + fmt}), 400

    data_url = data.get('data') or ''
    if ',' not in data_url:
        return jsonify({'ok': False, 'error': '文件数据无效'}), 400
    try:
        raw = base64.b64decode(data_url.split(',', 1)[1])
    except Exception:
        return jsonify({'ok': False, 'error': 'base64 解码失败'}), 400

    upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'topologies')
    os.makedirs(upload_dir, exist_ok=True)
    ext = {'pdf': 'pdf', 'vsdx': 'vsdx', 'png': 'png'}[fmt]
    fname = f'{fmt}_{t.id}.{ext}'
    with open(os.path.join(upload_dir, fname), 'wb') as f:
        f.write(raw)
    rel_path = f'uploads/topologies/{fname}'
    if fmt == 'pdf':
        t.pdf_path = rel_path
    elif fmt == 'vsdx':
        t.vsdx_path = rel_path
    else:
        t.thumbnail_path = rel_path
    db.session.commit()
    return jsonify({'ok': True, 'path': rel_path, 'format': fmt})
