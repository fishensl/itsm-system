# -*- coding: utf-8 -*-
"""巡检模板 / 设备检查模板 / 任务模板只读 API（SSR CRUD 已由 Vue SPA /api/* 接管）"""
import json
from flask import jsonify
from flask_login import login_required, current_user
from models import (InspectionTemplate, InspectionDeviceTemplate, Device)
from utils.permission import require_permission
from blueprints.ops import ops_bp


@ops_bp.route('/api/inspection-templates', methods=['GET'])
@login_required
@require_permission('inspection:view')
def api_inspection_templates():
    """供编辑弹窗和巡检表单引用：返回所有巡检模板的完整 V11 字段。"""
    out = []
    for t in InspectionTemplate.query.order_by(InspectionTemplate.id.desc()).all():
        try:
            items = json.loads(t.items_json or '[]')
        except Exception:
            items = []
        out.append({
            'id': t.id,
            'name': t.name,
            'device_type': t.device_type or '',
            'device_model': t.device_model or '',
            'template_category': t.template_category or '',
            'report_section_name': t.report_section_name or '',
            'is_active': bool(t.is_active),
            'items': items,
        })
    return jsonify(out)


# ============================ 任务模板 — 自动匹配 API ============================
@ops_bp.route('/api/customers/<int:cid>/match-device-templates')
@login_required
@require_permission('inspection:view')
def api_match_device_templates(cid):
    """V10: 按客户设备清单自动匹配设备检查模板
    - 查客户所有在用设备 → 按 device_type 大类去重分组
    - 查所有启用的设备检查模板 → 按 device_category 匹配
    - 返回每个大类下的设备数 + 匹配到的模板列表（命中分越高越靠前）
    """
    from collections import defaultdict
    from utils.customer_scope import require_customer_access
    require_customer_access(current_user, cid)
    devices = Device.query.filter_by(customer_id=cid, is_in_use=True).all()
    # 按 device_type 分组
    by_cat = defaultdict(list)
    for d in devices:
        cat = (d.device_type or '其他').strip()
        by_cat[cat].append({
            'id': d.id, 'name': d.device_name,
            'brand': d.brand or '', 'model': d.model or '',
            'ip': d.ip_address or '', 'os_version': d.os_version or '',
        })
    # 加载所有设备模板
    all_templates = InspectionDeviceTemplate.query.filter_by(is_active=True).all()
    tpl_by_cat = defaultdict(list)
    for tpl in all_templates:
        tpl_by_cat[tpl.device_category or '其他'].append(tpl)

    out = []
    for cat, dev_list in sorted(by_cat.items()):
        # 同类匹配：device_category 完全一致 (高分) > device_sub_type 子串 (中分)
        candidates = []
        # 高分：device_category 完全等于 cat
        for tpl in tpl_by_cat.get(cat, []):
            candidates.append({
                'id': tpl.id, 'name': tpl.name,
                'category': tpl.device_category, 'sub_type': tpl.device_sub_type or '',
                # 修复：曾用 len(items_json) 数 JSON 字符串字符数；total_sub_items 才是子检查项条数
                'items_count': tpl.total_sub_items,
                'match_score': 100,
            })
        # 中分：其他模板里子类型包含此 cat
        for tpl in all_templates:
            if (tpl.device_category or '') == cat:
                continue
            if cat in (tpl.name or '') or cat in (tpl.device_sub_type or ''):
                candidates.append({
                    'id': tpl.id, 'name': tpl.name,
                    'category': tpl.device_category, 'sub_type': tpl.device_sub_type or '',
                    'items_count': 0,
                    'match_score': 50,
                })
        candidates.sort(key=lambda x: -x['match_score'])
        out.append({
            'device_category': cat,
            'devices_count': len(dev_list),
            'devices': dev_list,
            'matched_templates': candidates,
        })
    return jsonify({'groups': out, 'total_devices': len(devices)})
