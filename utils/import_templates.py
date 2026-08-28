# -*- coding: utf-8 -*-
"""批量导入模板注册表。

模板表头与导入字段映射在此处保持单一真源。统计、审核、创建时间、密码审计等
只读/派生字段不进入导入模板；其余可编辑字段必须同时出现在模板和导入处理器中。
"""


IMPORT_TEMPLATE_FIELDS = {
    'customer': (
        ('客户名称', 'name'), ('联系人', 'contact_person'), ('电话', 'phone'),
        ('邮箱', 'email'), ('所属地区', 'region_name'), ('地市', 'city'),
        ('地址', 'address'), ('单位类别', 'category_name'), ('客户等级', 'level'),
        ('办公室', 'office'), ('办公室门牌号', 'office_room'),
        ('地图定位', 'map_location'), ('有无驻场', 'has_onsite'),
        ('驻场联系人', 'onsite_contact'), ('驻场联系方式', 'onsite_phone'),
        ('驻场办公室', 'onsite_office'), ('有无攻防演练', 'has_drill'),
        ('巡检频率', 'inspection_frequency'), ('合同开始日期', 'contract_start_date'),
        ('合同结束日期', 'contract_end_date'), ('来源', 'source'), ('备注', 'remark'),
    ),
    'device': (
        # 客户是导入归属字段；其后的设备字段严格跟随设备列表/列设置顺序。
        # 占用U数虽由列表聚合进“起始U位”显示，导入时仍需紧邻起始U位填写。
        ('客户', 'customer_name'), ('名称', 'device_name'), ('类型', 'device_type'),
        ('机房位置', 'rack_location'), ('机柜号', 'rack_name'),
        ('安装位置', 'location'), ('起始U位', 'rack_start_u'),
        ('占用U数', 'rack_occupy_u'), ('电源配置', 'power_supply'),
        ('品牌', 'brand'), ('型号', 'model'), ('序列号', 'serial_number'),
        ('IP', 'ip_address'), ('网络类型', 'network_type'), ('端口', 'port'),
        ('登录方式', 'login_method'), ('登录用户名', 'username'),
        ('登录密码', 'password'), ('接口', 'interface'), ('系统版本', 'os_version'),
        ('规则库版本', 'rule_version'), ('建设时间', 'build_date'),
        ('授权开始日期', 'license_start'), ('授权截止日期', 'license_expiry'),
        ('证书到期日期', 'cert_expiry_date'), ('是否维修', 'is_maintenance'),
        ('是否在用', 'is_in_use'), ('备注', 'remark'),
    ),
    'inspection': (
        ('客户名称', 'customer_name'), ('标题', 'title'),
        ('巡检人员', 'inspector'), ('巡检日期', 'inspection_date'),
        ('巡检地点', 'location'), ('总体状态', 'overall_status'),
        ('结论', 'conclusion'),
    ),
    'fault': (
        ('客户名称', 'customer_name'), ('标题', 'title'), ('处理人', 'handler'),
        ('故障时间', 'fault_time'), ('故障类型', 'fault_type'),
        ('故障分类', 'fault_category'), ('故障描述', 'fault_description'),
        ('影响范围', 'impact_range'), ('故障原因', 'fault_cause'),
        ('解决方案', 'solution'), ('处理结果', 'result'),
        ('恢复时间', 'recovery_time'),
    ),
    'spare': (
        ('编码', 'code'), ('名称', 'name'), ('分类', 'category'),
        ('品牌', 'brand'), ('型号', 'model'), ('规格', 'specification'),
        ('单位', 'unit'), ('最低库存', 'min_stock'),
        ('参考价', 'reference_price'), ('质保月数', 'warranty_months'),
        ('厂家', 'manufacturer'), ('序列号', 'serial_number'), ('备注', 'remark'),
    ),
    'stock': (
        ('备件名称', 'spare_name'), ('位置', 'location'),
        ('数量', 'quantity'), ('单价', 'unit_price'),
    ),
}


IMPORT_TEMPLATES = {
    'customer': {
        'name': '客户导入模板',
        'permission': 'customer:add',
        'example': [
            '示例客户（导入前请删除）', '张三', '13800000000', 'demo@example.com',
            '', '鹰潭市', '示例地址', '', '常规', '', 'A栋301', '', '否', '', '', '',
            '否', '每季度', '2026-01-01', '2026-12-31', '', '',
        ],
    },
    'device': {
        'name': '设备导入模板',
        'permission': 'device:add',
        'example': [
            '示例客户（须已存在）', '示例设备（导入前请删除）', '交换机',
            '中心机房', '1', '正面', 27, 4, '双电源', '示例品牌', '示例型号',
            'SN-DEMO', '192.0.2.1', '内网', 22, 'SSH', 'admin', '',
            'GE0/0/1、GE0/0/2', '', '',
            '2026-01-01', '2026-01-01', '2026-12-31', '2026-12-31', '否', '是', '',
        ],
    },
    'inspection': {
        'name': '巡检记录导入模板',
        'permission': 'inspection:add',
        'example': [
            '示例客户（须已存在）', '季度巡检（导入前请删除）', '张工', '2026-08-28',
            '中心机房', '正常', '无异常',
        ],
    },
    'fault': {
        'name': '故障记录导入模板',
        'permission': 'fault:add',
        'example': [
            '示例客户（须已存在）', '交换机离线（导入前请删除）', '李工',
            '2026-08-28 09:30', '网络故障', '网络/链路/中断', '设备不可达',
            '业务中断30分钟', '链路异常', '恢复链路', '已解决', '2026-08-28 10:00',
        ],
    },
    'spare': {
        'name': '备件导入模板',
        'permission': 'spare:add',
        'example': [
            'SP-DEMO', '示例备件（导入前请删除）', '光模块', '示例品牌', 'SFP-GE',
            '千兆', '个', 5, 100, 12, '示例厂家', 'SN-DEMO', '',
        ],
    },
    'stock': {
        'name': '库存导入模板',
        'permission': 'spare:add',
        'example': ['已存在的备件名称', 'A柜-01', 10, 100],
    },
}


# 兼容已经下载或人工维护的旧模板表头。新下载模板只展示上面的统一标签，
# 导入读取仍接受历史名称，避免仅因表头规范化而破坏存量 Excel。
IMPORT_TEMPLATE_HEADER_ALIASES = {
    'device': {
        '所属客户': 'customer_name',
        '客户名称': 'customer_name',
        '设备名称': 'device_name',
        '设备类型': 'device_type',
        'IP地址': 'ip_address',
    },
}


for _module, _definition in IMPORT_TEMPLATES.items():
    _definition['fields'] = IMPORT_TEMPLATE_FIELDS[_module]
    _definition['headers'] = [header for header, _field in _definition['fields']]


def get_import_template(module):
    """按模块名返回模板定义；未知模块返回 ``None``。"""
    return IMPORT_TEMPLATES.get(module)


def get_import_field_mapping(module):
    """返回 ``表头 -> 内部字段`` 映射；未知模块返回空字典。"""
    mapping = dict(IMPORT_TEMPLATE_FIELDS.get(module, ()))
    mapping.update(IMPORT_TEMPLATE_HEADER_ALIASES.get(module, {}))
    return mapping
