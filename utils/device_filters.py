"""设备列表、树、普通导出和密码审核导出共用筛选。"""
from sqlalchemy import and_, or_, not_
from domain_metadata.device_categories import DEVICE_CATEGORIES


NON_ROOM_VALUE = '__non_room__'


def normalize_room_locations(raw):
    if raw in (None, ''):
        return []
    values = raw if isinstance(raw, (list, tuple, set)) else [raw]
    return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def apply_device_filters(query, device_model, rack_install_model, filters):
    """仅施加业务筛选；数据范围必须由调用方先行施加。"""
    search = str(filters.get('search') or '').strip()
    if search:
        query = query.filter(
            device_model.device_name.contains(search) |
            device_model.ip_address.contains(search) |
            device_model.brand.contains(search))
    for key in ('brand', 'model', 'device_type'):
        value = str(filters.get(key) or '').strip()
        if value:
            query = query.filter(getattr(device_model, key) == value)
    category = str(filters.get('device_category') or '').strip()
    if category:
        keywords = DEVICE_CATEGORIES.get(category, {}).get('keywords', ())
        # 未知类别不放宽为全量导出。
        query = query.filter(or_(*(device_model.device_type.ilike(f'%{word}%')
                                   for word in keywords)) if keywords else False)
    customer_id = filters.get('customer_id')
    if customer_id not in (None, ''):
        query = query.filter(device_model.customer_id == int(customer_id))
    if filters.get('is_in_use') not in (None, ''):
        query = query.filter(device_model.is_in_use == bool(int(filters['is_in_use'])))

    device_ids = filters.get('device_ids') or []
    if device_ids:
        query = query.filter(device_model.id.in_([int(value) for value in device_ids]))

    rack_model = rack_install_model.rack_rel.property.mapper.class_
    rooms = normalize_room_locations(filters.get('room_locations') or filters.get('room_location'))
    location_scope = str(filters.get('location_scope') or '').strip()
    if location_scope == 'non_room' and NON_ROOM_VALUE not in rooms:
        rooms.append(NON_ROOM_VALUE)
    include_non_room = NON_ROOM_VALUE in rooms
    actual_rooms = [value for value in rooms if value != NON_ROOM_VALUE]
    has_installs = device_model.rack_installs.any()
    has_named_rack_room = device_model.rack_installs.any(
        rack_install_model.rack_rel.has(and_(
            rack_model.location.isnot(None), rack_model.location != '')))
    room_conditions = []
    if actual_rooms:
        room_conditions.extend((
            device_model.rack_installs.any(
                rack_install_model.rack_rel.has(rack_model.location.in_(actual_rooms))),
            and_(not_(has_installs), device_model.rack_location.in_(actual_rooms)),
        ))
    if include_non_room:
        room_conditions.append(or_(
            and_(has_installs, not_(has_named_rack_room)),
            and_(not_(has_installs), or_(
                device_model.rack_location.is_(None), device_model.rack_location == '')),
        ))
    if location_scope == 'room' and not actual_rooms:
        room_conditions.append(or_(
            has_named_rack_room,
            and_(not_(has_installs), device_model.rack_location.isnot(None),
                 device_model.rack_location != ''),
        ))
    if room_conditions:
        query = query.filter(or_(*room_conditions))
    return query
