# -*- coding: utf-8 -*-
"""拓扑图蓝图：上传式拓扑图管理 + V20 在线绘制（drawio 集成）

路由前缀为空（沿用 /topologies/* 原路径，从 app.py 迁移而来）。
上传逻辑与原 app.py 完全一致；在线绘制 API 在 P2 接入。
"""
import os
import base64
import hashlib

from flask import (Blueprint, request, redirect, url_for,
                   flash, jsonify, current_app)
from flask_login import login_required, current_user

from models import Topology, Region, db
from utils.permission import require_permission, has_permission

topology_bp = Blueprint('topology', __name__)


def _require_topology_customer(customer_id):
    """拓扑在线编辑与 Vue 列表共用客户数据范围。"""
    from utils.customer_scope import require_customer_access
    require_customer_access(current_user, customer_id)


TOPOLOGY_TEMPLATE_CATALOG = {
    'standard-network-v1.drawio': {
        'name': '网络拓扑图标准模板',
        'description': (
            '含标题栏、常用网络图形区和业务网线/光纤/WAN/VLAN/'
            '设备管理口线/HA/无线标准图例。'
        ),
        'category': 'network',
        'template_type': 'network',
        'template_version': 1,
    },
    'standard-meeting-v1.drawio': {
        'name': '会议拓扑图标准模板',
        'description': (
            '含会场/机柜绘图区、会议常用设备和网络/HDMI/DP/VGA/SDI/'
            '音频/控制/电源标准图例。'
        ),
        'category': 'meeting',
        'template_type': 'meeting',
        'template_version': 1,
    },
}


# ============================ 列表（SSR 已剥离：302 到 SPA） ============================
@topology_bp.route('/topologies', methods=['GET', 'POST'])
@login_required
@require_permission('topology:view')
def topology_list():
    """拓扑图列表（上传/删除已由 Vue SPA /api/topologies/* 接管）"""
    return redirect('/app/topologies')


# ============================ 在线编辑（drawio 集成） ============================
@topology_bp.route('/api/topologies/templates')
@login_required
@require_permission('topology:view')
def api_template_list():
    """在线拓扑模板列表（只读资源，具有拓扑查看权限即可加载）。"""
    tpl_dir = os.path.join(current_app.root_path, 'static', 'templates')
    items = []
    if os.path.isdir(tpl_dir):
        for fname, metadata in TOPOLOGY_TEMPLATE_CATALOG.items():
            f = os.path.join(tpl_dir, fname)
            if os.path.isfile(f):
                items.append({
                    'name': metadata['name'],
                    'description': metadata['description'],
                    'category': metadata['category'],
                    'template_type': metadata['template_type'],
                    'template_version': metadata['template_version'],
                    'file': fname,
                    'url': url_for('static', filename='templates/' + fname),
                })
    category_order = {'network': 0, 'meeting': 1}
    items.sort(key=lambda item: (category_order.get(item['category'], 2), item['name']))
    # 双契约兼容：Vue request() 解包 code/data；editor-shell 历史直连仍读取 ok/items。
    return jsonify({
        'code': 0,
        'data': {'items': items},
        'message': '',
        'ok': True,
        'items': items,
    })


@topology_bp.route('/topologies/editor/<int:id>')
@login_required
@require_permission('topology:view')
def topology_editor(id):
    """在线拓扑编辑器（壳页化：返回静态 editor-shell.html，数据经 editor-meta API 获取）

    id=0 新建；id>0 编辑已有在线图。
    查询参数 import=<topo_id>：从已上传的 Visio/drawio/图片文件导入后在线编辑。
    """
    from flask import send_from_directory
    if id:
        _require_topology_customer(Topology.query.get_or_404(id).customer_id)
    return send_from_directory(
        os.path.join(current_app.root_path, 'static', 'topologies'),
        'editor-shell.html')


@topology_bp.route('/api/topologies/editor-meta')
@login_required
@require_permission('topology:view')
def api_editor_meta():
    """编辑器壳页数据：客户/地区下拉、clibs 图标库、导入信息、权限标志（替代 Jinja 注入）"""
    import glob
    from urllib.parse import quote
    from utils.customer_scope import customer_dropdown_options
    all_customers = customer_dropdown_options(current_user)
    regions = [{'id': r.id, 'name': r.name} for r in
               Region.query.order_by(Region.parent_id.is_(None).desc(),
                                     Region.parent_id, Region.sort_order, Region.id).all()]

    # 扫描 static/stencils/*.drawio.xml 作为自定义图标库
    stencil_dir = os.path.join(current_app.root_path, 'static', 'stencils')
    clibs = ''
    stencil_urls = []
    if os.path.isdir(stencil_dir):
        stencil_urls = []
        for file_path in sorted(glob.glob(os.path.join(stencil_dir, '*.drawio.xml'))):
            with open(file_path, 'rb') as source:
                version = hashlib.sha256(source.read()).hexdigest()[:12]
            stencil_urls.append(url_for(
                'static', filename='stencils/' + os.path.basename(file_path), v=version))
        base = request.host_url.rstrip('/')
        clibs = ';'.join('U' + quote(base + u, safe='') for u in stencil_urls)

    # 导入模式：从已上传文件导入
    import_info = None
    import_topo_id = request.args.get('import', type=int)
    if import_topo_id:
        t = Topology.query.get_or_404(import_topo_id)
        _require_topology_customer(t.customer_id)
        if t.file_path:
            fp_lower = (t.file_path or '').lower()
            if fp_lower.endswith(('.vsd', '.vsdx')):
                import_type = 'visio'
            elif fp_lower.endswith(('.drawio', '.xml')) and not fp_lower.endswith('.vsdx'):
                import_type = 'drawio'
            elif fp_lower.endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp')):
                import_type = 'image'
            else:
                import_type = None
            if import_type:
                import_info = {
                    'url': url_for('vue_api.api_topology_file_download', topology_id=t.id, kind='original'),
                    'name': t.name,
                    'customer_id': t.customer_id,
                    'region_id': t.region_id,
                    'type': import_type,
                }

    return jsonify({
        'ok': True,
        'diagram_id': request.args.get('id', 0, type=int),
        'customers': all_customers,
        'regions': regions,
        'clibs': clibs,
        'stencil_urls': stencil_urls,
        'stencil_resource_version': hashlib.sha256(
            '|'.join(stencil_urls).encode('utf-8')).hexdigest()[:12],
        'can_add': has_permission('topology:add'),
        'can_edit': has_permission('topology:edit'),
        'template_param': request.args.get('template', ''),
        'default_template': 'standard-network-v1.drawio',
        'import': import_info,
    })


@topology_bp.route('/topologies/api/diagram/<int:id>')
@login_required
@require_permission('topology:view')
def api_diagram_load(id):
    """加载在线拓扑图 XML"""
    t = Topology.query.get_or_404(id)
    _require_topology_customer(t.customer_id)
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
        'template_type': t.template_type or 'legacy',
        'template_version': t.template_version or 1,
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
    from utils.topology_templates import (
        TEMPLATE_VERSION, normalize_template_type, validate_topology_xml)
    try:
        validate_topology_xml(diagram_xml)
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400

    customer_id = data.get('customer_id') or None
    region_id = data.get('region_id') or None
    _require_topology_customer(customer_id)

    if topo_id:
        t = Topology.query.get_or_404(topo_id)
        _require_topology_customer(t.customer_id)
        if t.source != 'draw':
            return jsonify({'ok': False, 'error': '该拓扑图为上传文件，不支持在线编辑'}), 400
        t.name = name
        t.description = data.get('description', '')
        t.customer_id = customer_id
        t.region_id = region_id
        t.diagram_xml = diagram_xml
        if 'template_type' in data:
            try:
                incoming_type = normalize_template_type(data.get('template_type'))
            except ValueError as exc:
                return jsonify({'ok': False, 'error': str(exc)}), 400
            # 旧图仅能通过显式“插入当前标准图例”升级，普通保存保持 legacy。
            if (t.template_type or 'legacy') != 'legacy':
                t.template_type = incoming_type
    else:
        try:
            template_type = normalize_template_type(
                data.get('template_type') or 'network', allow_legacy=False)
        except ValueError as exc:
            return jsonify({'ok': False, 'error': str(exc)}), 400
        t = Topology(
            name=name,
            description=data.get('description', ''),
            customer_id=customer_id,
            region_id=region_id,
            diagram_xml=diagram_xml,
            source='draw',
            file_type='other',
            upload_by=current_user.username,
            template_type=template_type,
            template_version=TEMPLATE_VERSION,
        )
        db.session.add(t)
        db.session.flush()  # 拿到 id，供缩略图命名用

    db.session.commit()
    return jsonify({'ok': True, 'id': t.id})


@topology_bp.route('/topologies/api/export-file', methods=['POST'])
@login_required
@require_permission('topology:edit')
def api_diagram_export_file():
    """保存在线拓扑图导出文件（PDF/VSDX/PNG/SVG，data URL 或 svg 字符串 → 文件）

    body: {id, format: 'pdf'|'vsdx'|'png'|'svg', data: 'data:...;base64,...' 或裸 svg 字符串}
    SVG 保存后服务端用 cairosvg 转 PDF（drawio embed 不支持 pdf 导出）。
    """
    data = request.get_json(silent=True) or {}
    topo_id = int(data.get('id') or 0)
    fmt = (data.get('format') or '').lower()
    t = Topology.query.get_or_404(topo_id)
    _require_topology_customer(t.customer_id)
    if t.source != 'draw':
        return jsonify({'ok': False, 'error': '非在线图'}), 400
    if fmt not in ('pdf', 'vsdx', 'png', 'svg'):
        return jsonify({'ok': False, 'error': '不支持的格式: ' + fmt}), 400

    data_url = data.get('data') or ''
    # svg 可能是裸 svg 字符串或 data:image/svg+xml data URL；其余格式均为 data URL
    if fmt == 'svg' and not data_url.startswith('data:'):
        try:
            raw = data_url.encode('utf-8')
        except Exception:
            return jsonify({'ok': False, 'error': 'svg 数据无效'}), 400
    elif ',' in data_url:
        try:
            raw = base64.b64decode(data_url.split(',', 1)[1])
        except Exception:
            return jsonify({'ok': False, 'error': 'base64 解码失败'}), 400
    else:
        return jsonify({'ok': False, 'error': '文件数据无效'}), 400

    upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'topologies')
    os.makedirs(upload_dir, exist_ok=True)
    ext = {'pdf': 'pdf', 'vsdx': 'vsdx', 'png': 'png', 'svg': 'svg'}[fmt]
    fname = f'{fmt}_{t.id}.{ext}'
    with open(os.path.join(upload_dir, fname), 'wb') as f:
        f.write(raw)
    rel_path = f'uploads/topologies/{fname}'
    if fmt == 'pdf':
        t.pdf_path = rel_path
    elif fmt == 'vsdx':
        t.vsdx_path = rel_path
    elif fmt == 'svg':
        t.svg_path = rel_path
        result = {'ok': True, 'path': rel_path, 'format': fmt}
        # drawio embed 不支持 pdf 导出，服务端从 svg 转 pdf（双引擎后备）
        pdf_fname = f'pdf_{t.id}.pdf'
        pdf_full = os.path.join(upload_dir, pdf_fname)
        ok, engine = _svg_to_pdf(raw, pdf_full)
        if ok:
            t.pdf_path = f'uploads/topologies/{pdf_fname}'
            result['pdf'] = 'ok'
        else:
            current_app.logger.warning('SVG→PDF 转换失败: %s', engine)
            result['warning'] = f'SVG 已保存，但 PDF 转换失败: {engine}'
        db.session.commit()
        return jsonify(result)
    else:
        t.thumbnail_path = rel_path
    db.session.commit()
    return jsonify({'ok': True, 'path': rel_path, 'format': fmt})


def _preprocess_svg(raw_svg):
    """预处理 SVG：移除 cairosvg/svglib 均不兼容的元素，提高转换成功率。"""
    import re
    svg_str = raw_svg.decode('utf-8') if isinstance(raw_svg, bytes) else raw_svg
    svg_str = re.sub(r'<foreignObject[\s\S]*?</foreignObject>', '', svg_str, flags=re.IGNORECASE)
    svg_str = re.sub(r'@import[^;]+;', '', svg_str)
    svg_str = re.sub(r'[^{}]*:[a-z-]+\s*\{[^}]*\}', '', svg_str)
    return svg_str.encode('utf-8')


def _svg_to_pdf(raw_svg, output_path):
    """SVG → PDF 转换（双引擎后备）。

    优先 cairosvg（Linux 生产环境，质量高）；
    失败后回退 svglib + reportlab（纯 Python，Windows 兼容，无需系统库）。
    """
    cleaned = _preprocess_svg(raw_svg)
    # 引擎 1：cairosvg（需 libcairo 系统库）
    try:
        import cairosvg
        cairosvg.svg2pdf(bytestring=cleaned, write_to=output_path)
        return True, 'cairosvg'
    except Exception as e:
        current_app.logger.info('cairosvg 不可用或转换失败 (%s)，尝试 svglib 后备', e)
    # 引擎 2：svglib + reportlab（纯 Python，无系统库依赖）
    try:
        import tempfile
        from svglib.svglib import svg2rlg
        from reportlab.graphics import renderPDF
        tmp = tempfile.NamedTemporaryFile(suffix='.svg', delete=False)
        tmp.write(cleaned)
        tmp.close()
        drawing = svg2rlg(tmp.name)
        os.unlink(tmp.name)
        if drawing:
            renderPDF.drawToFile(drawing, output_path)
            return True, 'svglib'
        return False, 'svglib 返回空绘图对象'
    except Exception as e:
        return False, f'svglib 也失败: {e}'


@topology_bp.route('/topologies/api/regenerate-pdf/<int:id>', methods=['POST'])
@login_required
@require_permission('topology:edit')
def regenerate_pdf(id):
    """用已保存的 SVG 重新生成 PDF（双引擎后备：cairosvg → svglib）"""
    t = Topology.query.get_or_404(id)
    _require_topology_customer(t.customer_id)
    if t.source != 'draw':
        return jsonify({'ok': False, 'error': '非在线图'}), 400
    if not t.svg_path:
        return jsonify({'ok': False, 'error': '没有 SVG 源文件，请先保存拓扑图'}), 400
    upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'topologies')
    svg_full = os.path.join(upload_dir, os.path.basename(t.svg_path))
    if not os.path.exists(svg_full):
        return jsonify({'ok': False, 'error': 'SVG 文件不存在于磁盘'}), 400
    with open(svg_full, 'rb') as f:
        raw = f.read()
    pdf_fname = f'pdf_{t.id}.pdf'
    pdf_full = os.path.join(upload_dir, pdf_fname)
    ok, engine = _svg_to_pdf(raw, pdf_full)
    if ok:
        t.pdf_path = f'uploads/topologies/{pdf_fname}'
        db.session.commit()
        return jsonify({'ok': True, 'pdf_path': t.pdf_path})
    else:
        current_app.logger.warning('regenerate_pdf 失败: %s', engine)
        return jsonify({'ok': False, 'error': f'PDF 转换失败: {engine}'}), 500


@topology_bp.route('/topologies/download/drawio/<int:id>')
@login_required
@require_permission('topology:view')
def download_drawio(id):
    """下载在线拓扑图的 drawio 格式文件（diagram_xml，新版 Visio 可直接打开）"""
    from flask import Response
    from urllib.parse import quote
    t = Topology.query.get_or_404(id)
    _require_topology_customer(t.customer_id)
    if t.source != 'draw' or not t.diagram_xml:
        flash('该拓扑图不支持 drawio 导出', 'warning')
        return redirect('/app/topologies')
    safe_name = (t.name or 'topology').replace(' ', '_')
    resp = Response(t.diagram_xml, mimetype='application/octet-stream')
    # filename* 支持中文（RFC 5987），octet-stream 强制下载避免浏览器当 XML 显示
    resp.headers['Content-Disposition'] = f"attachment; filename*=UTF-8''{quote(safe_name)}.drawio"
    return resp
