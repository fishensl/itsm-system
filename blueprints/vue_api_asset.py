# -*- coding: utf-8 -*-
"""Vue SPA 业务 API（资产域：机柜 / 拓扑 / 网络工具）

复用 blueprints.vue_api 的 vue_api_bp 蓝图对象与 ok/fail 契约。

机柜端点统一走 /api/v2/rack/* 前缀：blueprints/rack（SSR）先注册且模板
templates/rack/index.html 仍在使用 /api/rack/cabinets 等原路径（返回裸 JSON，
非 ok/fail 契约），同 rule 会被 SSR 遮蔽——与 vue_api.py 中
/api/v2/devices/<id>/reveal-password 的处理一致。
"""
import ipaddress

from flask import request, url_for
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload, selectinload

from blueprints.vue_api import vue_api_bp, ok, fail
from models import db
from utils.permission import require_permission

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
           remark=data.get('remark') or '')
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
    """机柜下拉字典：客户列表"""
    from models import Customer as _C
    customers = [{'id': c.id, 'name': c.name} for c in _C.query.order_by(_C.name).all()]
    return ok({'customers': customers})


# ==================== 拓扑图 ====================
_FILE_TYPE_ORDER = {'image': 0, 'pdf': 1, 'visio': 2, 'drawio': 3, 'other': 4}


def _topo_cust_name(t):
    return t.customer_rel.name if t.customer_rel else '未关联客户'


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


def _topo_static_url(path):
    return url_for('static', filename=path) if path else ''


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
    files = []
    for f in sorted(group, key=lambda x: (_FILE_TYPE_ORDER.get(x.file_type, 9), x.id)):
        files.append({
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
        })
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
