# -*- coding: utf-8 -*-
"""Customer 业务服务

把客户相关的业务规则从路由层分离出来。
路由层只负责参数接收、权限检查、模板渲染。
"""
import json
from models import db, Customer, Region
from .base import ServiceError, transaction


def parse_extra_fields(customer):
    """把 Customer.extra_fields 反序列化为 [{'name':, 'value':}, ...] 列表。

    兼容旧的 dict 格式（{字段名: 值}）。失败返回空列表。
    """
    if not customer or not customer.extra_fields:
        return []
    try:
        data = json.loads(customer.extra_fields)
    except (ValueError, TypeError):
        return []
    if isinstance(data, list):
        return [{'name': d.get('name', ''), 'value': d.get('value', '')}
                for d in data if isinstance(d, dict) and d.get('name')]
    if isinstance(data, dict):  # 兼容旧格式
        return [{'name': k, 'value': v} for k, v in data.items()]
    return []


def serialize_extra_fields(names, values):
    """把表单提交的字段名/值两个并列数组打包成 JSON 列表（跳过空名）"""
    pairs = []
    for name, value in zip(names or [], values or []):
        name = (name or '').strip()
        if name:
            pairs.append({'name': name, 'value': (value or '').strip()})
    return json.dumps(pairs, ensure_ascii=False) if pairs else ''


def _calculate_tier(device_count, has_onsite, has_drill):
    """根据设备数/驻场/攻防演练自动定级

    核心: >=50 台且(驻场或演练)
    重点: >=30 台 或 驻场 或 演练
    常规: 其余
    """
    if device_count >= 50 and (has_onsite or has_drill):
        return '核心'
    if device_count >= 30 or has_onsite or has_drill:
        return '重点'
    return '常规'


def _resolve_region(region_id):
    """根据 region_id 推导 city 字符串

    - 选了区/县：city = 父地市名称
    - 仅选了市：city = 该市名称
    - 都没选：city = ''
    返回 (city, is_district)
    """
    if not region_id:
        return '', False
    region = Region.query.get(region_id)
    if not region:
        return '', False
    if region.parent_id:
        parent = Region.query.get(region.parent_id)
        return (parent.name if parent else ''), True
    return region.name, False


def _derive_level(c, has_onsite, has_drill, manual_tier):
    """根据 manual_tier / 自动计算 / 区县规则确定 level

    优先级：
    1. 手动指定具体值（核心/重点/常规）→ 用手动值
    2. 手动选 auto → 走自动定级
    3. 区/县客户 → 默认常规
    4. 市级客户 → 走自动定级
    """
    if manual_tier and manual_tier != 'auto':
        return manual_tier
    # auto / 空：先按规则算
    is_district = c.region_id and (Region.query.get(c.region_id) or Region()).parent_id is not None
    if is_district:
        # 区/县且选 auto → 默认常规
        return '常规'
    return _calculate_tier(c.device_count or 0, has_onsite, has_drill)


def _resolve_parent_id(raw, self_id=None):
    """把表单提交的 parent_id 校验并转成 int|None。

    - 空 → None（走自动推导）
    - 指向自己 → ServiceError
    - 指向自己的后代 → ServiceError（防自环）
    - 指向不存在的客户 → ServiceError
    """
    if raw in (None, '', '0', 0):
        return None
    try:
        pid = int(raw)
    except (TypeError, ValueError):
        raise ServiceError('上级单位 ID 无效')
    if pid <= 0:
        return None
    if self_id and pid == self_id:
        raise ServiceError('上级单位不能选自己')
    parent = Customer.query.get(pid)
    if not parent:
        raise ServiceError('上级单位不存在')
    # 自环检测：父→父→…若回到 self_id 则拒绝
    if self_id:
        seen = set()
        cur = parent
        while cur and cur.parent_id and cur.parent_id not in seen:
            if cur.parent_id == self_id:
                raise ServiceError('不能选自己的下级单位作为上级')
            seen.add(cur.parent_id)
            cur = Customer.query.get(cur.parent_id)
    return pid


@transaction
def create_customer(data, device_count=0):
    """新增客户

    :param data: dict 含 name/contact_person/phone/email/region_id/category_id/
                       level/has_onsite/has_drill/inspection_frequency/source/address/remark
    :param device_count: 关联设备数（用于定级）
    :raises ServiceError: 校验失败
    """
    name = (data.get('name') or '').strip()
    if not name:
        raise ServiceError('客户名称不能为空')
    if Customer.query.filter_by(name=name).first():
        raise ServiceError(f'客户 "{name}" 已存在')

    # region_id 优先取 district（区/县），回退到 city（市级客户）
    region_id = data.get('region_id') or data.get('city_id') or None

    c = Customer(
        name=name,
        contact_person=data.get('contact_person') or '',
        phone=data.get('phone') or '',
        email=data.get('email') or '',
        region_id=int(region_id) if region_id else None,
        category_id=int(data['category_id']) if data.get('category_id') else None,
        parent_id=_resolve_parent_id(data.get('parent_id')),
        city='',  # 由 region 推导
        office=data.get('office') or '',
        has_onsite=data.get('has_onsite') == 'on',
        onsite_contact=data.get('onsite_contact') or '',
        onsite_phone=data.get('onsite_phone') or '',
        onsite_office=data.get('onsite_office') or '',
        has_drill=data.get('has_drill') == 'on',
        inspection_frequency=data.get('inspection_frequency') or '',
        source=data.get('source') or '',
        address=data.get('address') or '',
        remark=data.get('remark') or '',
    )
    # 推导 city
    c.city, _ = _resolve_region(c.region_id)
    # 定级
    c.level = _derive_level(c, c.has_onsite, c.has_drill, data.get('level'))
    # 自定义字段值（路由已序列化好放入 data['extra_fields']）
    c.extra_fields = data.get('extra_fields') or ''

    db.session.add(c)
    return c


@transaction
def update_customer(customer_id, data):
    """更新客户"""
    c = Customer.query.get_or_404(customer_id)
    name = (data.get('name') or '').strip()
    if not name:
        raise ServiceError('客户名称不能为空')
    # 重名检测
    if name != c.name and Customer.query.filter_by(name=name).first():
        raise ServiceError(f'客户 "{name}" 已被其他记录使用')

    region_id = data.get('region_id') or data.get('city_id') or None
    c.name = name
    c.contact_person = data.get('contact_person') or ''
    c.phone = data.get('phone') or ''
    c.email = data.get('email') or ''
    c.region_id = int(region_id) if region_id else None
    c.category_id = int(data['category_id']) if data.get('category_id') else None
    c.parent_id = _resolve_parent_id(data.get('parent_id'), self_id=c.id)
    c.city = ''
    c.office = data.get('office') or ''
    c.has_onsite = data.get('has_onsite') == 'on'
    c.onsite_contact = data.get('onsite_contact') or ''
    c.onsite_phone = data.get('onsite_phone') or ''
    c.onsite_office = data.get('onsite_office') or ''
    c.has_drill = data.get('has_drill') == 'on'
    c.inspection_frequency = data.get('inspection_frequency') or ''
    c.source = data.get('source') or ''
    c.address = data.get('address') or ''
    c.remark = data.get('remark') or ''
    c.city, _ = _resolve_region(c.region_id)
    c.level = _derive_level(c, c.has_onsite, c.has_drill, data.get('level'))
    c.extra_fields = data.get('extra_fields') or ''
    return c


def get_customer_with_regions(customer_id=None):
    """获取表单渲染所需的地区数据

    :return: dict 含 top_level_regions / selected_city_id / district_regions
    """
    top_level = Region.query.filter_by(parent_id=None)\
        .order_by(Region.sort_order, Region.id).all()
    if customer_id is None:
        return {
            'top_level_regions': top_level,
            'district_regions': [],
            'selected_city_id': None,
        }
    c = Customer.query.get(customer_id)
    if not c or not c.region_id:
        return {
            'top_level_regions': top_level,
            'district_regions': [],
            'selected_city_id': None,
        }
    region = Region.query.get(c.region_id)
    if region and region.parent_id:
        # 区/县客户：city 选父级
        return {
            'top_level_regions': top_level,
            'district_regions': Region.query.filter_by(parent_id=region.parent_id)
                .order_by(Region.sort_order, Region.id).all(),
            'selected_city_id': region.parent_id,
        }
    # 市级客户：city 选自己
    return {
        'top_level_regions': top_level,
        'district_regions': Region.query.filter_by(parent_id=c.region_id)
            .order_by(Region.sort_order, Region.id).all(),
        'selected_city_id': c.region_id,
    }


@transaction
def delete_customer(customer_id):
    """删除客户（保留用于兼容；新代码建议软删除）"""
    c = Customer.query.get_or_404(customer_id)
    if c.devices.count() > 0:
        raise ServiceError(f'客户 "{c.name}" 仍有关联设备，无法删除')
    # 置空引用该客户的工单/巡检/故障，避免悬挂外键（SQLite 默认不强制 FK）
    from models import Ticket, Inspection, Fault
    Ticket.query.filter_by(customer_id=customer_id).update({'customer_id': None})
    Inspection.query.filter_by(customer_id=customer_id).update({'customer_id': None})
    Fault.query.filter_by(customer_id=customer_id).update({'customer_id': None})
    db.session.delete(c)
