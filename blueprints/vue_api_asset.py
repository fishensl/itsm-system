# -*- coding: utf-8 -*-
"""Vue SPA 业务 API（资产域：机柜 / 拓扑 / 网络工具）

复用 blueprints.vue_api 的 vue_api_bp 蓝图对象与 ok/fail 契约。

机柜端点统一走 /api/v2/rack/* 前缀：blueprints/rack（SSR）先注册且模板
templates/rack/index.html 仍在使用 /api/rack/cabinets 等原路径（返回裸 JSON，
非 ok/fail 契约），同 rule 会被 SSR 遮蔽——与 vue_api.py 中
/api/v2/devices/<id>/reveal-password 的处理一致。
"""
import ipaddress
import os
import time
from datetime import date

from flask import request, url_for, current_app
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload, selectinload
from werkzeug.utils import secure_filename

from blueprints.vue_api import vue_api_bp, ok, fail
from models import db
from utils.permission import require_permission
from utils.upload import ALLOWED_IMAGE_EXT

# ==================== 机柜管理 ====================
_U_OCCUPY_LEVEL = ((1.0, '已满', 'danger'), (0.8, '高', 'warning'),
                   (0.5, '中', 'primary'), (0.0, '低', 'info'))


def _rack_payload(r):
    used = sum(i.occupy_u or 0 for i in r.installs)
    used_pct = round(used * 100 / r.total_u, 1) if r.total_u else 0
    used_w = sum(i.rated_w or 0 for i in r.installs)
    level = '低'
    for threshold, label, _c in _U_OCCUPY_LEVEL:
        if used_pct >= threshold * 100:
            level = label
            break
    return {
        'id': r.id,
        'customer_id': r.customer_id,
        'customer_name': r.customer_rel.name if r.customer_rel else '',
        'name': r.name,
        'location': r.location or '',
        'total_u': r.total_u,
        'used_u': used,
        'used_label': f'{used}/{r.total_u or 0}',
        'used_pct': used_pct,
        'usage_level': level,
        'color': r.color,
        'pdu_total_w': r.pdu_total_w,
        'used_w': used_w,
        'remark': r.remark or '',
        'install_count': len(r.installs),
    }


@vue_api_bp.route('/api/v2/rack/cabinets', methods=['GET'])
@login_required
@require_permission('device:view')
def api_rack_cabinets():
    """机柜分页列表（join 客户名 + installs 聚合：used_u/used_pct/used_w/install_count）"""
    from models import Rack as _R
    page = request.args.get('page', 1, type=int)
    page_size = min(request.args.get('page_size', 20, type=int), 100)
    customer_id = request.args.get('customer_id', type=int)
    search = (request.args.get('search') or '').strip()
    q = _R.query.options(
        selectinload(_R.installs),
        joinedload(_R.customer_rel),
    )
    if customer_id:
        q = q.filter(_R.customer_id == customer_id)
    if search:
        q = q.filter(_R.name.contains(search))
    total = q.count()
    rows = q.order_by(_R.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return ok({'items': [_rack_payload(r) for r in rows],
               'total': total, 'page': page, 'page_size': page_size})


@vue_api_bp.route('/api/v2/rack/cabinets/<int:rack_id>', methods=['GET'])
@login_required
@require_permission('device:view')
def api_rack_cabinet_detail(rack_id):
    """机柜详情（含 installs：device_name 或 manual_*、start_u、occupy_u、rated_w、kind）"""
    from models import Rack as _R, RackInstall as _RI
    r = _R.query.options(
        selectinload(_R.installs).joinedload(_RI.device_rel),
        joinedload(_R.customer_rel),
    ).filter_by(id=rack_id).first_or_404()
    installs = []
    for i in sorted(r.installs, key=lambda x: x.start_u or 0):
        if i.device_id and i.device_rel:
            name = i.device_rel.device_name
            brand = i.device_rel.brand or ''
            model = i.device_rel.model or ''
            ip = i.device_rel.ip_address or ''
            kind = '托管'
        else:
            name = i.manual_name or '(未命名)'
            brand = i.manual_brand or ''
            model = i.manual_model or ''
            ip = i.manual_ip or ''
            kind = '手动'
        installs.append({
            'id': i.id,
            'device_id': i.device_id,
            'name': name,
            'brand': brand,
            'model': model,
            'ip': ip,
            'kind': kind,
            'start_u': i.start_u,
            'occupy_u': i.occupy_u,
            'rated_w': i.rated_w,
            'remark': i.remark or '',
        })
    payload = _rack_payload(r)
    payload['installs'] = installs
    return ok(payload)


@vue_api_bp.route('/api/v2/rack/cabinets', methods=['POST'])
@login_required
@require_permission('device:edit')
def api_rack_cabinet_create():
    from models import Rack as _R
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return fail('机柜名称不能为空', 400)
    if not data.get('customer_id'):
        return fail('请选择所属客户', 400)
    try:
        total_u = int(data.get('total_u') or 42)
        pdu_total_w = int(data.get('pdu_total_w') or 0)
    except (TypeError, ValueError):
        return fail('U 位数/额定功率必须为数字', 400)
    if total_u < 1:
        return fail('机柜总 U 数必须大于 0', 400)
    r = _R(customer_id=int(data['customer_id']), name=name, total_u=total_u,
           color=data.get('color') or '#0d6efd', pdu_total_w=pdu_total_w,
           location=(data.get('location') or '')[:128], remark=data.get('remark') or '')
    db.session.add(r)
    db.session.commit()
    return ok({'id': r.id})


@vue_api_bp.route('/api/v2/rack/cabinets/<int:rack_id>', methods=['PUT'])
@login_required
@require_permission('device:edit')
def api_rack_cabinet_update(rack_id):
    from models import Rack as _R
    r = _R.query.get_or_404(rack_id)
    data = request.get_json(silent=True) or {}
    if 'customer_id' in data:
        if data.get('customer_id'):
            r.customer_id = int(data['customer_id'])
        else:
            return fail('请选择所属客户', 400)
    if 'name' in data:
        name = (data.get('name') or '').strip()
        if not name:
            return fail('机柜名称不能为空', 400)
        r.name = name
    if 'total_u' in data:
        try:
            total_u = int(data['total_u'])
        except (TypeError, ValueError):
            return fail('U 位数必须为数字', 400)
        if total_u < 1:
            return fail('机柜总 U 数必须大于 0', 400)
        r.total_u = total_u
    if 'pdu_total_w' in data:
        try:
            r.pdu_total_w = int(data['pdu_total_w'] or 0)
        except (TypeError, ValueError):
            return fail('额定功率必须为数字', 400)
    if 'color' in data:
        r.color = data.get('color') or r.color
    if 'location' in data:
        r.location = (data.get('location') or '')[:128]
    if 'remark' in data:
        r.remark = data.get('remark') or ''
    db.session.commit()
    return ok(None)


@vue_api_bp.route('/api/v2/rack/cabinets/<int:rack_id>', methods=['DELETE'])
@login_required
@require_permission('device:delete')
def api_rack_cabinet_delete(rack_id):
    """删除机柜（级联删除 installs）"""
    from models import Rack as _R
    r = _R.query.get_or_404(rack_id)
    for i in list(r.installs):
        db.session.delete(i)
    db.session.delete(r)
    db.session.commit()
    return ok(None)


def _check_u_range(rack, start_u, occupy_u):
    if start_u < 1 or start_u + occupy_u - 1 > rack.total_u:
        raise ValueError(f'U 位超出范围（机柜共 {rack.total_u}U）')


def _check_u_conflict(installs, start_u, occupy_u, exclude_id=None):
    """U 位冲突校验（exclude_id 用于调整位置时排除自身）"""
    for other in installs:
        if exclude_id is not None and other.id == exclude_id:
            continue
        s, e = other.start_u, other.start_u + other.occupy_u - 1
        ns, ne = start_u, start_u + occupy_u - 1
        if not (ne < s or ns > e):
            raise ValueError(f'U 位冲突：{s}U-{e}U 已被占用')


@vue_api_bp.route('/api/v2/rack/installs', methods=['POST'])
@login_required
@require_permission('device:edit')
def api_rack_install_create():
    """设备上架（手动/托管；U 位范围与冲突校验）"""
    from models import Rack as _R, RackInstall as _RI
    data = request.get_json(silent=True) or {}
    rack_id = data.get('rack_id')
    if not rack_id:
        return fail('请指定机柜', 400)
    r = _R.query.get_or_404(int(rack_id))
    try:
        start_u = int(data.get('start_u') or 1)
        occupy_u = int(data.get('occupy_u') or 1)
        rated_w = int(data.get('rated_w') or 0)
    except (TypeError, ValueError):
        return fail('U 位/功率参数无效', 400)
    if occupy_u < 1:
        return fail('占用 U 数必须大于 0', 400)
    device_id = data.get('device_id')
    manual_name = (data.get('manual_name') or '').strip()
    if not device_id and not manual_name:
        return fail('请选择设备或填写手动设备名称', 400)
    try:
        _check_u_range(r, start_u, occupy_u)
        _check_u_conflict(r.installs, start_u, occupy_u)
    except ValueError as e:
        return fail(str(e), 400)
    inst = _RI(rack_id=r.id,
               device_id=int(device_id) if device_id else None,
               manual_name=manual_name,
               manual_brand=data.get('manual_brand') or '',
               manual_model=data.get('manual_model') or '',
               manual_ip=data.get('manual_ip') or '',
               start_u=start_u, occupy_u=occupy_u, rated_w=rated_w,
               remark=data.get('remark') or '')
    db.session.add(inst)
    db.session.commit()
    return ok({'id': inst.id})


@vue_api_bp.route('/api/v2/rack/installs/<int:install_id>', methods=['PUT'])
@login_required
@require_permission('device:edit')
def api_rack_install_update(install_id):
    """调整安装位置（冲突校验排除自身）"""
    from models import RackInstall as _RI
    inst = _RI.query.get_or_404(install_id)
    data = request.get_json(silent=True) or {}
    try:
        new_start = int(data.get('start_u') or inst.start_u)
        new_occupy = int(data.get('occupy_u') or inst.occupy_u)
    except (TypeError, ValueError):
        return fail('U 位参数无效', 400)
    if new_occupy < 1:
        return fail('占用 U 数必须大于 0', 400)
    r = inst.rack_rel
    try:
        _check_u_range(r, new_start, new_occupy)
        _check_u_conflict(r.installs, new_start, new_occupy, exclude_id=inst.id)
    except ValueError as e:
        return fail(str(e), 400)
    inst.start_u = new_start
    inst.occupy_u = new_occupy
    if 'rated_w' in data:
        try:
            inst.rated_w = int(data['rated_w'] or 0)
        except (TypeError, ValueError):
            pass
    if 'remark' in data:
        inst.remark = data.get('remark') or ''
    db.session.commit()
    return ok(None)


@vue_api_bp.route('/api/v2/rack/installs/<int:install_id>', methods=['DELETE'])
@login_required
@require_permission('device:delete')
def api_rack_install_delete(install_id):
    """下架"""
    from models import RackInstall as _RI
    inst = _RI.query.get_or_404(install_id)
    db.session.delete(inst)
    db.session.commit()
    return ok(None)


@vue_api_bp.route('/api/v2/rack/devices', methods=['GET'])
@login_required
@require_permission('device:view')
def api_rack_devices():
    """可上架设备（按机柜所属客户过滤，installed 标记是否已上架）"""
    from models import Rack as _R, RackInstall as _RI, Device as _D
    rack_id = request.args.get('rack_id', type=int)
    customer_id = request.args.get('customer_id', type=int)
    if rack_id and not customer_id:
        r = _R.query.get(rack_id)
        customer_id = r.customer_id if r else None
    if not customer_id:
        return ok({'items': []})
    installed = {row[0] for row in db.session.query(_RI.device_id)
                 .filter(_RI.device_id.isnot(None)).all()}
    items = [{'id': d.id, 'name': d.device_name, 'brand': d.brand or '',
              'model': d.model or '', 'ip': d.ip_address or '',
              'installed': d.id in installed}
             for d in _D.query.filter_by(customer_id=customer_id)
             .order_by(_D.device_name).all()]
    return ok({'items': items})


@vue_api_bp.route('/api/dicts/rack', methods=['GET'])
@login_required
@require_permission('device:view')
def api_rack_dicts():
    """机柜下拉字典：客户列表（按关联过滤，防枚举客户名单）"""
    from utils.customer_scope import customer_dropdown_options
    customers = customer_dropdown_options(current_user)
    return ok({'customers': customers})


@vue_api_bp.route('/api/v2/rack/tree', methods=['GET'])
@login_required
@require_permission('device:view')
def api_rack_tree():
    """机柜分组树：地市 → 客户 → 机柜（分组逻辑同 SSR rack_index 三段式）"""
    from models import Rack as _R, Customer as _C, Region as _Region
    racks = _R.query.options(selectinload(_R.installs)).order_by(_R.id.desc()).all()
    by_customer = {}
    for r in racks:
        by_customer.setdefault(r.customer_id, []).append(r)
    cust_ids = [cid for cid in by_customer.keys() if cid is not None]
    cust_map = {}
    if cust_ids:
        for c in _C.query.options(
            joinedload(_C.region_rel).joinedload(_Region.parent)
        ).filter(_C.id.in_(cust_ids)).all():
            cust_map[c.id] = c
    city_data = {}
    for cid, rack_list in by_customer.items():
        c = cust_map.get(cid)
        if c:
            if c.region_rel and c.region_rel.parent:
                city = c.region_rel.parent.name
            elif c.region_rel:
                city = c.region_rel.name
            else:
                city = c.city or '未分配地市'
        else:
            city = '未分配客户'
        city_data.setdefault(city, []).append({
            'id': c.id if c else None,
            'name': c.name if c else '未分配客户',
            'racks': [{'id': r.id, 'name': r.name, 'total_u': r.total_u,
                       'color': r.color or '#0d6efd',
                       'install_count': len(r.installs)}
                      for r in rack_list],
        })
    return ok([{'city': city, 'customers': customers}
               for city, customers in city_data.items()])


# ==================== 拓扑图 ====================
_FILE_TYPE_ORDER = {'image': 0, 'pdf': 1, 'visio': 2, 'drawio': 3, 'other': 4}


def _topo_cust_name(t):
    return t.customer_rel.name if t.customer_rel else '未关联客户'


def _topo_static_url(path):
    return url_for('static', filename=path) if path else ''


def _topo_file_payload(f):
    """单个拓扑图文件（列表行与详情共用，保证两处结构一致）"""
    return {
        'id': f.id,
        'file_type': f.file_type,
        'source': f.source,
        'file_path': f.file_path or '',
        'url': _topo_static_url(f.file_path),
        'thumbnail': _topo_static_url(f.thumbnail_path),
        'pdf': _topo_static_url(f.pdf_path),
        'vsdx': _topo_static_url(f.vsdx_path),
        'svg': _topo_static_url(f.svg_path),
        'upload_by': f.upload_by or '',
        'created_at': f.created_at.strftime('%Y-%m-%d %H:%M') if f.created_at else '',
    }


def _topo_group_payload(name, files):
    """相同 客户+名称 的多文件（image/pdf/visio/drawio）合并为一行"""
    files_sorted = sorted(files, key=lambda x: (_FILE_TYPE_ORDER.get(x.file_type, 9), x.id))
    first = files_sorted[0]
    return {
        'id': first.id,
        'name': name,
        'customer_id': first.customer_id,
        'customer_name': _topo_cust_name(first),
        'type': first.file_type,
        'types': [f.file_type for f in files_sorted],
        'file_count': len(files_sorted),
        'source': first.source,
        'upload_by': first.upload_by or '',
        'has_thumbnail': bool(first.thumbnail_path),
        'files': [_topo_file_payload(f) for f in files_sorted],
        'created_at': first.created_at.strftime('%Y-%m-%d %H:%M') if first.created_at else '',
        'updated_at': (first.updated_at or first.created_at)
        .strftime('%Y-%m-%d %H:%M') if (first.updated_at or first.created_at) else '',
    }


@vue_api_bp.route('/api/topologies', methods=['GET'])
@login_required
@require_permission('topology:view')
def api_topology_list():
    """拓扑图分组列表（名称/客户/类型/更新时间/文件数）"""
    from models import Topology as _T
    page = request.args.get('page', 1, type=int)
    page_size = min(request.args.get('page_size', 20, type=int), 100)
    search = (request.args.get('search') or '').strip()
    q = _T.query.options(joinedload(_T.customer_rel))
    if search:
        q = q.filter(_T.name.contains(search) | _T.description.contains(search))
    rows = q.order_by(_T.id.desc()).all()
    # 按 客户+名称 分组（组内文件类型 icon 列表展示，逻辑同 SSR 列表）
    grouped = {}
    for t in rows:
        grouped.setdefault((_topo_cust_name(t), t.name), []).append(t)
    items = [_topo_group_payload(name, files) for (_, name), files in grouped.items()]
    total = len(items)
    items = items[(page - 1) * page_size: page * page_size]
    return ok({'items': items, 'total': total, 'page': page, 'page_size': page_size})


@vue_api_bp.route('/api/topologies/<int:topo_id>', methods=['GET'])
@login_required
@require_permission('topology:view')
def api_topology_detail(topo_id):
    """拓扑详情：基本信息 + 同组（客户+名称）全部文件的路径/缩略图列表"""
    from models import Topology as _T
    t = _T.query.options(joinedload(_T.customer_rel), joinedload(_T.region_rel))\
        .get_or_404(topo_id)
    group = [x for x in _T.query.options(joinedload(_T.customer_rel))
             .filter(_T.name == t.name).all()
             if _topo_cust_name(x) == _topo_cust_name(t)]
    files = [_topo_file_payload(f) for f in sorted(
        group, key=lambda x: (_FILE_TYPE_ORDER.get(x.file_type, 9), x.id))]
    draw = [f for f in files if f['source'] == 'draw']
    return ok({
        'id': t.id,
        'name': t.name,
        'description': t.description or '',
        'customer_id': t.customer_id,
        'customer_name': _topo_cust_name(t),
        'region_id': t.region_id,
        'region_name': t.region_rel.name if t.region_rel else '',
        'source': t.source,
        'file_count': len(files),
        'files': files,
        'has_editor': bool(draw),
        'editor_id': draw[0]['id'] if draw else (files[0]['id'] if files else t.id),
    })


@vue_api_bp.route('/api/topologies', methods=['POST'])
@login_required
@require_permission('topology:add')
def api_topology_create():
    """新建拓扑图记录（在线图 source=draw 可由 SSR 编辑器绘制）"""
    from models import Topology as _T
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return fail('名称不能为空', 400)
    source = data.get('source') or 'upload'
    if source not in ('upload', 'draw'):
        return fail('非法的来源类型', 400)
    t = _T(name=name,
           description=data.get('description') or '',
           customer_id=data.get('customer_id') or None,
           region_id=data.get('region_id') or None,
           file_type=data.get('file_type') or 'image',
           source=source,
           upload_by=current_user.realname or current_user.username)
    db.session.add(t)
    db.session.commit()
    return ok({'id': t.id})


@vue_api_bp.route('/api/topologies/dicts', methods=['GET'])
@login_required
@require_permission('topology:view')
def api_topology_dicts():
    """拓扑图下拉字典：客户 / 地区（客户按关联过滤，防枚举名单）"""
    from models import Region as _R
    from utils.customer_scope import customer_dropdown_options
    customers = customer_dropdown_options(current_user)
    regions = [{'id': r.id, 'name': r.name} for r in _R.query.order_by(_R.name).all()]
    return ok({'customers': customers, 'regions': regions})


@vue_api_bp.route('/api/topologies/upload', methods=['POST'])
@login_required
@require_permission('topology:add')
def api_topology_upload():
    """拓扑图文件上传（multipart；类型识别 + 自动命名，逻辑同 SSR topology_upload）"""
    from models import Topology as _T, Customer as _C
    f = request.files.get('topo_file')
    if not f or not f.filename:
        return fail('请选择文件', 400)

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
    elif name_lower.endswith(('.drawio', '.xml')) and not name_lower.endswith('.vsdx'):
        file_type = 'drawio'
        allowed = {'.drawio', '.xml'}
    else:
        file_type = 'other'
        allowed = set()

    ext = os.path.splitext(name_lower)[1]
    if allowed and ext not in allowed:
        return fail(f'不支持的文件类型 {ext}', 400)

    upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'topologies')
    os.makedirs(upload_dir, exist_ok=True)
    safe_name = secure_filename(f.filename) or ('topology' + ext)
    base, e = os.path.splitext(safe_name)
    safe_name = f"{base}_{int(time.time())}{e}"
    full_path = os.path.join(upload_dir, safe_name)
    f.save(full_path)

    customer_id = request.form.get('customer_id', type=int)
    region_id = request.form.get('region_id', type=int)
    topo_type = request.form.get('topo_type') or '网络拓扑图'
    user_name = (request.form.get('name') or '').strip()
    if not user_name:
        cust_name = ''
        if customer_id:
            c = _C.query.get(customer_id)
            if c:
                cust_name = c.name
        today_str = date.today().strftime('%Y%m%d')
        user_name = f"{cust_name}{topo_type}{today_str}" if cust_name else f"{topo_type}{today_str}"

    t = _T(
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
    return ok({'id': t.id})


@vue_api_bp.route('/api/topologies/<int:topo_id>', methods=['PUT'])
@login_required
@require_permission('topology:edit')
def api_topology_update(topo_id):
    from models import Topology as _T
    t = _T.query.get_or_404(topo_id)
    data = request.get_json(silent=True) or {}
    if 'name' in data:
        name = (data.get('name') or '').strip()
        if not name:
            return fail('名称不能为空', 400)
        t.name = name
    if 'description' in data:
        t.description = data.get('description') or ''
    if 'customer_id' in data:
        t.customer_id = data.get('customer_id') or None
    if 'region_id' in data:
        t.region_id = data.get('region_id') or None
    db.session.commit()
    return ok(None)


@vue_api_bp.route('/api/topologies/<int:topo_id>', methods=['DELETE'])
@login_required
@require_permission('topology:delete')
def api_topology_delete(topo_id):
    from models import Topology as _T
    t = _T.query.get_or_404(topo_id)
    db.session.delete(t)
    db.session.commit()
    return ok(None)


# ==================== 网络工具（纯函数 JSON 封装） ====================
def _mask_to_bits(mask):
    """子网掩码 → 前缀长度（支持 '255.255.255.0' 或 '24'）"""
    s = str(mask).strip()
    if s.isdigit():
        bits = int(s)
        if 0 <= bits <= 32:
            return bits
        raise ValueError('掩码前缀长度必须在 0~32 之间')
    try:
        octets = [int(x) for x in s.split('.')]
    except ValueError:
        raise ValueError(f'子网掩码无效: {mask}')
    if len(octets) != 4 or any(o < 0 or o > 255 for o in octets):
        raise ValueError(f'子网掩码无效: {mask}')
    full = ''.join(f'{o:08b}' for o in octets)
    if '01' in full:
        raise ValueError(f'子网掩码无效: {mask}')
    return full.count('1')


def _ip_calc(ip_str, mask):
    """IPv4 计算：network/broadcast/first/last/hosts/掩码"""
    bits = _mask_to_bits(mask)
    try:
        net = ipaddress.ip_network(f'{ip_str.strip()}/{bits}', strict=False)
    except ValueError as e:
        raise ValueError(f'IP 地址无效: {e}')
    hosts = list(net.hosts())
    usable = net.num_addresses - 2 if net.prefixlen <= 30 else net.num_addresses
    return {
        'network': str(net.network_address),
        'broadcast': str(net.broadcast_address),
        'first': str(hosts[0]) if hosts else str(net.network_address),
        'last': str(hosts[-1]) if hosts else str(net.network_address),
        'hosts': usable,
        'mask': str(net.netmask),
        'mask_bits': net.prefixlen,
        'cidr': f'{net.network_address}/{net.prefixlen}',
    }


@vue_api_bp.route('/api/tools/ip-calc', methods=['POST'])
@login_required
def api_tools_ip_calc():
    """IP 计算：入参 {ip, mask}（mask 支持前缀长度或点分十进制）或 {cidr}"""
    data = request.get_json(silent=True) or {}
    cidr = (data.get('cidr') or '').strip()
    ip_str = (data.get('ip') or '').strip()
    mask = data.get('mask')
    try:
        if cidr:
            net = ipaddress.ip_network(cidr, strict=False)
            result = _ip_calc(str(net.network_address), net.prefixlen)
        else:
            if not ip_str:
                return fail('请输入 IP 地址', 400)
            if mask in (None, ''):
                return fail('请输入子网掩码', 400)
            result = _ip_calc(ip_str, mask)
    except ValueError as e:
        return fail(str(e), 400)
    return ok(result)


_BASE_FMT = {'2': lambda n: format(n, 'b'), '8': lambda n: format(n, 'o'),
             '10': str, '16': lambda n: format(n, 'X')}


@vue_api_bp.route('/api/tools/convert', methods=['POST'])
@login_required
def api_tools_convert():
    """进制转换：入参 {value, from_base, to_base}，支持 2/8/10/16"""
    data = request.get_json(silent=True) or {}
    try:
        from_base = int(data.get('from_base') or 10)
        to_base = int(data.get('to_base') or 10)
    except (TypeError, ValueError):
        return fail('进制参数无效', 400)
    if from_base not in (2, 8, 10, 16) or to_base not in (2, 8, 10, 16):
        return fail('仅支持 2/8/10/16 进制', 400)
    value = (data.get('value') or '').strip()
    if not value:
        return fail('请输入数值', 400)
    try:
        num = int(value, from_base)
    except ValueError:
        return fail(f'「{value}」不是合法的 {from_base} 进制数', 400)
    return ok({
        'result': _BASE_FMT[str(to_base)](num),
        'to_base': to_base,
        'binary': _BASE_FMT['2'](num),
        'octal': _BASE_FMT['8'](num),
        'decimal': str(num),
        'hex': _BASE_FMT['16'](num),
    })


@vue_api_bp.route('/api/tools/mac-format', methods=['POST'])
@login_required
def api_tools_mac_format():
    """MAC 地址格式化：去分隔符，输出 colon/dash/dot/plain"""
    data = request.get_json(silent=True) or {}
    raw = (data.get('mac') or '').strip()
    if not raw:
        return fail('请输入 MAC 地址', 400)
    if any(c not in '0123456789abcdefABCDEF:-. ' for c in raw):
        return fail('MAC 地址包含非十六进制字符', 400)
    hexs = ''.join(c for c in raw if c in '0123456789abcdefABCDEF').upper()
    if len(hexs) != 12:
        return fail('MAC 地址必须为 12 位十六进制字符', 400)
    pairs = [hexs[i:i + 2] for i in range(0, 12, 2)]
    quads = [hexs[i:i + 4] for i in range(0, 12, 4)]
    return ok({
        'result': ':'.join(pairs),
        'plain': hexs,
        'colon': ':'.join(pairs),
        'dash': '-'.join(pairs),
        'dot': '.'.join(quads),
    })

# ==================== 设备字典（类型/品牌/网络类型/自定义字段） ====================
def _dict_payload(obj, with_type=False):
    item = {'id': obj.id, 'name': obj.name, 'sort_order': obj.sort_order or 0}
    if with_type:
        item['field_type'] = obj.field_type or 'text'
    return item


def _register_device_dict(resource, model, with_type=False):
    """注册一组设备字典 Vue CRUD 端点（/api/device-dicts/<resource>）"""

    @login_required
    @require_permission('device:view')
    def _list():
        items = model.query.order_by(model.sort_order, model.id).all()
        return ok([_dict_payload(i, with_type) for i in items])

    @login_required
    @require_permission('device:edit')
    def _add():
        data = request.get_json(silent=True) or {}
        name = (data.get('name') or '').strip()
        if not name:
            return fail('请输入名称')
        obj = model(name=name, sort_order=int(data.get('sort_order') or 0))
        if with_type:
            obj.field_type = (data.get('field_type') or 'text').strip() or 'text'
        db.session.add(obj)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            return fail('名称已存在')
        return ok({'id': obj.id})

    @login_required
    @require_permission('device:edit')
    def _update(id):
        obj = model.query.get_or_404(id)
        data = request.get_json(silent=True) or {}
        name = (data.get('name') or '').strip()
        if name:
            obj.name = name
        obj.sort_order = int(data.get('sort_order') or 0)
        if with_type and data.get('field_type'):
            obj.field_type = data['field_type'].strip() or 'text'
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            return fail('名称已存在')
        return ok(None)

    @login_required
    @require_permission('device:delete')
    def _delete(id):
        model.query.filter_by(id=id).delete()
        db.session.commit()
        return ok(None)

    vue_api_bp.add_url_rule(f'/api/device-dicts/{resource}', f'device_dict_{resource}_list', _list, methods=['GET'])
    vue_api_bp.add_url_rule(f'/api/device-dicts/{resource}', f'device_dict_{resource}_add', _add, methods=['POST'])
    vue_api_bp.add_url_rule(f'/api/device-dicts/{resource}/<int:id>', f'device_dict_{resource}_update', _update,
                            methods=['PUT'])
    vue_api_bp.add_url_rule(f'/api/device-dicts/{resource}/<int:id>', f'device_dict_{resource}_delete', _delete,
                            methods=['DELETE'])


from models import DeviceType, Brand, NetworkType, CustomField  # noqa: E402
_register_device_dict('types', DeviceType)
_register_device_dict('brands', Brand)
_register_device_dict('network-types', NetworkType)
_register_device_dict('custom-fields', CustomField, with_type=True)

# ==================== 固件版本库 ====================
@vue_api_bp.route('/api/firmwares', methods=['GET'])
@login_required
@require_permission('device:view')
def api_firmware_list():
    from models import DeviceFirmware, Device
    brand = (request.args.get('brand') or '').strip()
    model = (request.args.get('model') or '').strip()
    ftype = (request.args.get('firmware_type') or '').strip()
    q = DeviceFirmware.query
    if brand:
        q = q.filter(DeviceFirmware.brand == brand)
    if model:
        q = q.filter(DeviceFirmware.model == model)
    if ftype:
        q = q.filter(DeviceFirmware.firmware_type == ftype)
    firmwares = q.order_by(
        DeviceFirmware.brand, DeviceFirmware.model,
        DeviceFirmware.firmware_type, DeviceFirmware.is_latest.desc(),
        DeviceFirmware.release_date.desc(),
    ).all()

    from collections import OrderedDict
    grouped = OrderedDict()
    for fw in firmwares:
        key = (fw.brand or '未分类', fw.model or '未分类型号')
        grouped.setdefault(key, OrderedDict()).setdefault(fw.firmware_type or '其他', []).append({
            'id': fw.id,
            'brand': fw.brand,
            'model': fw.model,
            'firmware_type': fw.firmware_type,
            'version': fw.version,
            'release_date': fw.release_date.isoformat() if fw.release_date else '',
            'changelog': fw.changelog or '',
            'download_url': fw.download_url or '',
            'file_size_mb': fw.file_size_mb or 0,
            'md5_checksum': fw.md5_checksum or '',
            'is_latest': bool(fw.is_latest),
            'min_compatible_hardware': fw.min_compatible_hardware or '',
            'upgrade_guide': fw.upgrade_guide or '',
            'remark': fw.remark or '',
        })

    # 每组挂同 brand+model 设备清单（版本对比用）
    group_devices = {k: [] for k in grouped.keys()}
    if grouped:
        from sqlalchemy import and_, or_
        pair_conds = []
        for gbrand, gmodel in grouped.keys():
            b_cond = Device.brand == (gbrand if gbrand != '未分类' else '')
            m_cond = Device.model == (gmodel if gmodel != '未分类型号' else '')
            if gbrand == '未分类':
                b_cond = or_(Device.brand == '', Device.brand.is_(None))
            if gmodel == '未分类型号':
                m_cond = or_(Device.model == '', Device.model.is_(None))
            pair_conds.append(and_(b_cond, m_cond))
        for dev in Device.query.filter(or_(*pair_conds)).all():
            key = (dev.brand or '未分类', dev.model or '未分类型号')
            if key in group_devices:
                group_devices[key].append({
                    'id': dev.id, 'name': dev.device_name,
                    'os_version': dev.os_version or '', 'rule_version': dev.rule_version or '',
                })

    all_brands = sorted(set(b for b, _ in grouped.keys() if b))
    all_models = sorted(set(m for _, m in grouped.keys() if m))
    out = []
    for (gbrand, gmodel), type_map in grouped.items():
        out.append({
            'brand': gbrand, 'model': gmodel,
            'types': [
                {'firmware_type': t, 'items': items} for t, items in type_map.items()
            ],
            'devices': group_devices[(gbrand, gmodel)],
        })
    return ok({'groups': out, 'all_brands': all_brands, 'all_models': all_models,
               'all_types': ['系统固件', '规则库', 'BIOS', '其他']})


def _fw_payload_from(data):
    return {
        'brand': (data.get('brand') or '').strip(),
        'model': (data.get('model') or '').strip(),
        'firmware_type': (data.get('firmware_type') or '系统固件').strip() or '系统固件',
        'version': (data.get('version') or '').strip(),
        'release_date': (data.get('release_date') or '').strip() or None,
        'changelog': (data.get('changelog') or '').strip(),
        'download_url': (data.get('download_url') or '').strip(),
        'file_size_mb': float(data.get('file_size_mb') or 0) or 0,
        'md5_checksum': (data.get('md5_checksum') or '').strip(),
        'is_latest': bool(data.get('is_latest')),
        'min_compatible_hardware': (data.get('min_compatible_hardware') or '').strip(),
        'upgrade_guide': (data.get('upgrade_guide') or '').strip(),
        'remark': (data.get('remark') or '').strip(),
    }


@vue_api_bp.route('/api/firmwares', methods=['POST'])
@login_required
@require_permission('device:edit')
def api_firmware_add():
    from models import DeviceFirmware
    from datetime import date
    data = request.get_json(silent=True) or {}
    p = _fw_payload_from(data)
    if not p['brand'] or not p['model'] or not p['version']:
        return fail('品牌/型号/版本号为必填项')
    if p['release_date']:
        try:
            p['release_date'] = date.fromisoformat(p['release_date'])
        except ValueError:
            return fail('发布日期格式错误（YYYY-MM-DD）')
    else:
        p['release_date'] = None
    if p['is_latest']:
        DeviceFirmware.query.filter_by(brand=p['brand'], model=p['model'],
                                       firmware_type=p['firmware_type']).update({'is_latest': False})
    fw = DeviceFirmware(**p)
    db.session.add(fw)
    db.session.commit()
    return ok({'id': fw.id})


@vue_api_bp.route('/api/firmwares/<int:fw_id>', methods=['PUT'])
@login_required
@require_permission('device:edit')
def api_firmware_update(fw_id):
    from models import DeviceFirmware
    from datetime import date
    fw = DeviceFirmware.query.get_or_404(fw_id)
    data = request.get_json(silent=True) or {}
    p = _fw_payload_from(data)
    if p['brand']:
        fw.brand = p['brand']
    if p['model']:
        fw.model = p['model']
    if p['version']:
        fw.version = p['version']
    fw.firmware_type = p['firmware_type']
    if p['release_date']:
        try:
            fw.release_date = date.fromisoformat(p['release_date'])
        except ValueError:
            return fail('发布日期格式错误（YYYY-MM-DD）')
    else:
        fw.release_date = None
    fw.changelog = p['changelog']
    fw.download_url = p['download_url']
    fw.file_size_mb = p['file_size_mb']
    fw.md5_checksum = p['md5_checksum']
    fw.min_compatible_hardware = p['min_compatible_hardware']
    fw.upgrade_guide = p['upgrade_guide']
    fw.remark = p['remark']
    if p['is_latest'] and not fw.is_latest:
        DeviceFirmware.query.filter(
            DeviceFirmware.brand == fw.brand,
            DeviceFirmware.model == fw.model,
            DeviceFirmware.firmware_type == fw.firmware_type,
            DeviceFirmware.id != fw.id,
        ).update({'is_latest': False})
    fw.is_latest = p['is_latest']
    db.session.commit()
    return ok(None)


@vue_api_bp.route('/api/firmwares/<int:fw_id>', methods=['DELETE'])
@login_required
@require_permission('device:delete')
def api_firmware_delete(fw_id):
    from models import DeviceFirmware
    fw = DeviceFirmware.query.get(fw_id)
    if fw:
        db.session.delete(fw)
        db.session.commit()
    return ok(None)


# ==================== 设备密码导出审核流（V24） ====================
@vue_api_bp.route('/api/v2/devices/export-password-request', methods=['POST'])
@login_required
@require_permission('device:view')
def api_device_export_password_request():
    """提交设备密码导出申请（原因必填 + 审计 + 通知全部 admin）"""
    from models import DeviceExportRequest
    from blueprints.vue_export import resolve_device_columns
    data = request.get_json(silent=True) or {}
    reason = (data.get('reason') or '').strip()
    if not reason:
        return fail('请填写申请原因（必填）', 400)
    filters = data.get('filters') or {}
    try:
        codes = resolve_device_columns(filters.get('preset'), filters.get('columns'))
    except ValueError as e:
        return fail(str(e), 400)
    if 'password' not in codes:
        return fail('导出项目必须包含登录密码列', 400)
    from utils.json_fields import dumps_json
    req = DeviceExportRequest(
        user_id=current_user.id,
        reason=reason[:500],
        filters_json=dumps_json({'search': (filters.get('search') or '').strip(),
                                 'customer_id': filters.get('customer_id'),
                                 'preset': filters.get('preset') or '',
                                 'columns': codes}),
        status='pending',
    )
    db.session.add(req)
    db.session.commit()
    from blueprints.vue_api_sys import audit_log
    audit_log('device:export_request', 'device', req.id, f'申请设备密码导出：{reason[:120]}')
    try:
        from models import User as _U
        from utils.notifications import notify
        for u in _U.query.filter_by(is_active=True).all():
            if u.has_role('admin') and u.id != current_user.id:
                notify(u.id, 'device', '新的设备密码导出申请',
                       f'{current_user.realname or current_user.username} 申请导出设备密码（{codes.count("password") and "含密码列"}）',
                       '/app/system/export-reviews')
    except Exception:
        current_app.logger.warning('设备密码导出申请通知失败')
    return ok({'id': req.id})


@vue_api_bp.route('/api/v2/devices/export-password-requests', methods=['GET'])
@login_required
@require_permission('device:view')
def api_device_export_password_requests():
    """导出申请列表：scope=mine 我的 / scope=all 全部（admin）"""
    from models import DeviceExportRequest
    scope = (request.args.get('scope') or 'mine').strip()
    q = DeviceExportRequest.query.options(
        joinedload(DeviceExportRequest.user_rel))
    if scope != 'all' or not current_user.is_admin:
        q = q.filter(DeviceExportRequest.user_id == current_user.id)
    rows = q.order_by(DeviceExportRequest.id.desc()).limit(100).all()
    return ok({'items': [{
        'id': r.id,
        'reason': r.reason or '',
        'status': r.status,
        'status_label': {'pending': '待审核', 'approved': '已通过', 'rejected': '已驳回'}.get(r.status, r.status),
        'username': r.user_rel.username if r.user_rel else '',
        'realname': r.user_rel.realname if r.user_rel else '',
        'created_at': r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else '',
        'reviewed_at': r.reviewed_at.strftime('%Y-%m-%d %H:%M') if r.reviewed_at else '',
        'review_comment': r.review_comment or '',
        'file_token': r.file_token or '',
        'downloaded': bool(r.downloaded_at),
    } for r in rows]})


@vue_api_bp.route('/api/v2/devices/export-password-reviews', methods=['GET'])
@login_required
def api_device_export_password_reviews():
    """待审核导出申请列表（admin）"""
    if not current_user.is_admin:
        return fail('需要管理员权限', 403)
    from models import DeviceExportRequest
    rows = DeviceExportRequest.query.options(
        joinedload(DeviceExportRequest.user_rel)) \
        .filter_by(status='pending') \
        .order_by(DeviceExportRequest.id.desc()).limit(100).all()
    return ok({'items': [{
        'id': r.id,
        'reason': r.reason or '',
        'username': r.user_rel.username if r.user_rel else '',
        'realname': r.user_rel.realname if r.user_rel else '',
        'created_at': r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else '',
    } for r in rows]})


@vue_api_bp.route('/api/v2/devices/export-password-reviews/<int:req_id>', methods=['POST'])
@login_required
def api_device_export_password_review(req_id):
    """审核导出申请：approve（预生成加密包）/ reject（驳回原因必填）"""
    if not current_user.is_admin:
        return fail('需要管理员权限', 403)
    import secrets
    from datetime import datetime
    from blueprints.vue_export import (save_export_file, DEVICE_EXPORT_COLUMNS, device_export_rows,
                                       build_rack_map, build_pwd_map, device_export_filename)
    from utils.excel_export import export_xlsx
    from models import DeviceExportRequest, Device as _D, Customer as _C, RackInstall as _RI
    from utils.json_fields import parse_json
    from sqlalchemy.orm import selectinload as _sil
    from blueprints.vue_api_sys import audit_log
    req = DeviceExportRequest.query.get_or_404(req_id)
    if req.status != 'pending':
        return fail('该申请已处理', 400)
    data = request.get_json(silent=True) or {}
    action = (data.get('action') or '').strip()
    comment = (data.get('comment') or '').strip()
    if action == 'reject':
        if not comment:
            return fail('驳回时必须填写原因', 400)
        req.status = 'rejected'
        req.reviewed_by_user_id = current_user.id
        req.reviewed_at = datetime.utcnow()
        req.review_comment = comment[:500]
        db.session.commit()
        audit_log('device:export_review', 'device', req.id, f'驳回设备密码导出申请：{comment[:120]}')
        try:
            from utils.notifications import notify
            notify(req.user_id, 'device', '设备密码导出申请已驳回',
                   f'原因：{comment}', '/app/devices?tab=export-requests')
        except Exception:
            current_app.logger.warning('导出申请驳回通知失败')
        return ok(None)
    if action != 'approve':
        return fail('action 必须为 approve 或 reject', 400)

    # ---- 通过：实时取数生成含密码 xlsx → pyzipper AES 加密包 ----
    filters = parse_json(req.filters_json, {}, 'device_export_request.filters_json') or {}
    codes = [str(c) for c in (filters.get('columns') or [])] or [
        c for c, _ in DEVICE_EXPORT_COLUMNS]
    q = _D.query.options(_sil(_D.rack_installs).joinedload(_RI.rack_rel))
    search = (filters.get('search') or '').strip()
    if search:
        q = q.filter(_D.device_name.contains(search) | _D.ip_address.contains(search) |
                     _D.brand.contains(search))
    if filters.get('customer_id'):
        q = q.filter(_D.customer_id == int(filters['customer_id']))
    devices = q.order_by(_D.id.desc()).all()
    customer_map = {c.id: c.name for c in _C.query.all()}
    headers = [dict(DEVICE_EXPORT_COLUMNS)[c] for c in codes]
    rows = device_export_rows(devices, codes, customer_map,
                              build_rack_map(devices), build_pwd_map(devices))
    download_name = device_export_filename(
        customer_map.get(int(filters['customer_id'])) if filters.get('customer_id') else '',
        filters.get('preset') or '')
    tmp_path, _ = export_xlsx(headers, rows, download_name, sheet_name='设备密码表')
    password = secrets.token_urlsafe(8)
    token = save_export_file(tmp_path, download_name, password=password,
                             user_id=req.user_id)
    req.status = 'approved'
    req.reviewed_by_user_id = current_user.id
    req.reviewed_at = datetime.utcnow()
    req.review_comment = comment[:500]
    req.file_token = token
    db.session.commit()
    audit_log('device:export_review', 'device', req.id, f'通过设备密码导出申请（{len(devices)} 台设备）')
    try:
        from utils.notifications import notify
        notify(req.user_id, 'device', '设备密码导出申请已通过',
               f'已生成加密导出包（{len(devices)} 台设备），请在设备页「我的导出申请」中下载',
               '/app/devices?tab=export-requests')
    except Exception:
        current_app.logger.warning('导出申请通过通知失败')
    return ok(None)


@vue_api_bp.route('/api/v2/devices/export-password-download/<token>', methods=['GET'])
@login_required
def api_device_export_password_download(token):
    """一次性下载加密密码包（仅申请人/admin；响应头 X-Export-Password 下发 zip 密码；审计）"""
    from datetime import datetime
    from blueprints.vue_export import serve_export_file
    from blueprints.vue_api_sys import audit_log
    from models import DeviceExportRequest
    req = DeviceExportRequest.query.filter_by(file_token=token).first()
    if not req or req.status != 'approved' or req.downloaded_at:
        return fail('下载链接不存在或已使用', 404)
    if not (current_user.is_admin or current_user.id == req.user_id):
        return fail('无权下载该导出包', 403)
    resp = serve_export_file(token, current_user.id, current_user.is_admin)
    if resp is None:
        return fail('导出文件不存在或已失效', 404)
    from models import ExportFile as _EF
    ef = _EF.query.filter_by(token=token).first()
    if ef and ef.download_name:
        resp.headers['X-Export-Filename'] = ef.download_name
    req.downloaded_at = datetime.utcnow()
    db.session.commit()
    audit_log('device:export_download', 'device', req.id, '下载设备密码导出包')
    return resp
