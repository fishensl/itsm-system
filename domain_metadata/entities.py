"""Field schemas for the first unified business entities."""
from domain_metadata.base import EntitySchema, FieldSpec


def F(key, label, **kwargs):
    return FieldSpec(key=key, label=label, **kwargs)


DEVICE_FIELDS = (
    F('device_name', '名称', export_key='name', min_width=160, required=True, sortable=True),
    F('device_type', '类型', export_key='type', width=90, filterable=True),
    F('customer_name', '客户', export_key='customer', min_width=100, filterable=True),
    F('rack_location', '机房位置', min_width=100, group='location'),
    F('rack_name', '机柜号', min_width=90, group='location'),
    F('rack_slot', '机柜U位', min_width=90, group='location'),
    F('location', '安装位置', min_width=120, group='location'),
    F('brand', '品牌', min_width=100, filterable=True),
    F('model', '型号', min_width=120, filterable=True),
    F('serial_number', '序列号', export_key='sn', min_width=130),
    F('network_type', '网络类型', width=90, default_visible=False),
    F('ip_address', 'IP', export_key='ip', min_width=130, filterable=True),
    F('port', '端口', data_type='number', width=70),
    F('login_method', '登录方式', width=90, group='credential'),
    F('username', '登录用户名', min_width=110, group='credential'),
    F('password', '登录密码', group='credential', sensitive=True,
      permission='device:reveal', export_key='password'),
    F('has_password', '已设置密码', data_type='boolean', group='credential'),
    F('interface', '接口', data_type='list', group='network'),
    F('os_version', '系统版本', min_width=110, group='version'),
    F('rule_version', '规则库版本', min_width=110, group='version'),
    F('build_date', '建设时间', data_type='date', min_width=100, group='lifecycle',
      default_visible=False),
    F('license_start', '授权开始', data_type='date', group='lifecycle'),
    F('license_expiry', '授权截止', data_type='date', group='lifecycle'),
    F('cert_expiry_date', '证书到期日期', data_type='date', group='lifecycle'),
    F('license_remaining_days', '授权剩余天数', data_type='number', group='lifecycle'),
    F('is_maintenance', '是否维修', data_type='boolean', width=90,
      value_map={'true': '是', 'false': '否'}),
    F('is_in_use', '是否在用', data_type='boolean', width=90, filterable=True,
      value_map={'true': '是', 'false': '否'}),
    F('pwd_changed_by', '上次修改密码账号', min_width=110, group='audit', default_visible=False),
    F('pwd_changed_at', '上次修改密码时间', data_type='datetime', min_width=130,
      group='audit', default_visible=False),
    F('remark', '备注', min_width=140),
    F('created_at', '创建时间', data_type='datetime', min_width=130, group='audit'),
)

DEVICE_LIST = ('device_name', 'device_type', 'customer_name', 'rack_location', 'rack_name',
               'location', 'brand', 'model', 'serial_number', 'network_type', 'ip_address',
               'port', 'login_method', 'username', 'os_version', 'rule_version', 'build_date',
               'license_start', 'license_expiry', 'cert_expiry_date', 'is_maintenance',
               'is_in_use', 'pwd_changed_by', 'pwd_changed_at', 'remark')
DEVICE_DETAIL = tuple(item.key for item in DEVICE_FIELDS if item.key != 'password')
DEVICE_FORM = ('device_name', 'customer_name', 'device_type', 'brand', 'model', 'serial_number',
               'network_type', 'ip_address', 'port', 'username', 'password', 'login_method',
               'location', 'interface', 'os_version', 'rule_version', 'build_date',
               'license_start', 'license_expiry', 'cert_expiry_date', 'is_maintenance',
               'is_in_use', 'remark')
DEVICE_EXPORT_DEFAULT = ('customer_name', 'rack_location', 'rack_name', 'location', 'device_name',
                         'device_type', 'brand', 'model', 'serial_number', 'ip_address', 'port',
                         'login_method', 'username', 'password', 'build_date', 'os_version',
                         'rule_version', 'license_start', 'license_expiry', 'is_maintenance',
                         'is_in_use', 'pwd_changed_by', 'pwd_changed_at', 'remark')
DEVICE_EXPORT_AVAILABLE = tuple(dict.fromkeys(
    DEVICE_EXPORT_DEFAULT + ('rack_slot', 'network_type', 'interface', 'cert_expiry_date',
                             'created_at')))
DEVICE_EXPORT_PRESETS = {
    'asset': ('customer_name', 'rack_location', 'rack_name', 'location', 'device_name',
              'device_type', 'brand', 'model', 'serial_number', 'ip_address', 'build_date',
              'is_maintenance', 'is_in_use', 'remark'),
    'password': ('customer_name', 'rack_location', 'rack_name', 'location', 'device_name',
                 'device_type', 'brand', 'model', 'serial_number', 'ip_address', 'port',
                 'login_method', 'username', 'password', 'is_in_use', 'pwd_changed_by',
                 'pwd_changed_at', 'remark'),
    'version': ('customer_name', 'rack_location', 'rack_name', 'location', 'device_name',
                'device_type', 'brand', 'model', 'serial_number', 'ip_address', 'build_date',
                'os_version', 'rule_version', 'license_start', 'license_expiry', 'is_in_use',
                'remark'),
}
DEVICE_EXPORT_PRESET_LABELS = {
    'asset': '设备资产表',
    'password': '设备密码表',
    'version': '网络安全版本控制表',
}


TICKET_FIELDS = (
    F('number', '工单号', width=130, sortable=True),
    F('title', '标题', min_width=180, required=True, sortable=True),
    F('status', '状态', width=90, filterable=True),
    F('priority', '优先级', width=80, filterable=True),
    F('severity_level', '严重级别', width=100, filterable=True, default_visible=False),
    F('customer_name', '客户', export_key='customer', min_width=100, filterable=True),
    F('reporter', '报修人', width=100),
    F('reporter_phone', '报修人电话', min_width=120),
    F('related_device_name', '关联设备', min_width=140),
    F('fault_category', '故障分类', min_width=150, filterable=True),
    F('source_type', '来源', width=100, filterable=True),
    F('assigned_to', '处理人', width=90, filterable=True),
    F('created_by', '创建人', width=90),
    F('description', '故障描述', min_width=180, group='handling'),
    F('diagnosis', '故障诊断', min_width=180, group='handling'),
    F('solution', '解决方案', min_width=180, group='handling'),
    F('complete', '资料完整', data_type='boolean', width=100, group='quality'),
    F('audit_status', '审核状态', width=100, group='quality'),
    F('accept_status', '验收状态', width=100, group='quality'),
    F('report_file', '处理报告', data_type='file', group='report'),
    F('contract_exception_reason', '合同例外原因', min_width=180, group='contract'),
    F('sla_deadline', 'SLA截止时间', data_type='datetime', min_width=130, group='sla'),
    F('created_at', '创建时间', data_type='datetime', width=130, sortable=True),
    F('assigned_at', '派单时间', data_type='datetime', width=130),
    F('accepted_at', '接单时间', data_type='datetime', width=130),
    F('completed_at', '完成时间', data_type='datetime', width=130),
)
TICKET_LIST = ('title', 'number', 'status', 'priority', 'severity_level', 'customer_name',
               'reporter', 'fault_category', 'assigned_to', 'complete', 'created_at')
TICKET_DETAIL = tuple(item.key for item in TICKET_FIELDS)
TICKET_FORM = ('title', 'priority', 'severity_level', 'customer_name', 'reporter',
               'reporter_phone', 'related_device_name', 'fault_category', 'description',
               'diagnosis', 'solution', 'source_type', 'contract_exception_reason')
TICKET_EXPORT_DEFAULT = ('number', 'title', 'priority', 'status', 'customer_name', 'reporter',
                         'assigned_to', 'created_by', 'created_at', 'completed_at')
TICKET_EXPORT_AVAILABLE = tuple(dict.fromkeys(TICKET_EXPORT_DEFAULT + TICKET_LIST + TICKET_DETAIL))


FAULT_FIELDS = (
    F('title', '标题', min_width=200, required=True, sortable=True),
    F('customer_name', '客户', export_key='customer', min_width=100, filterable=True),
    F('handler', '处理人', width=90),
    F('fault_time', '故障时间', data_type='datetime', width=130, sortable=True),
    F('fault_type', '故障类型', width=100, filterable=True),
    F('fault_category', '故障分类', min_width=160, filterable=True),
    F('result', '处理结果', width=90, filterable=True),
    F('impact_range', '影响范围', min_width=120),
    F('fault_description', '故障描述', min_width=180, group='handling'),
    F('fault_cause', '故障原因', min_width=180, group='handling'),
    F('solution', '解决方案', min_width=180, group='handling'),
    F('recovery_time', '恢复时间', data_type='datetime', width=130),
    F('ticket_number', '关联工单号', width=130),
    F('created_at', '创建时间', data_type='datetime', width=130),
)
FAULT_LIST = ('title', 'customer_name', 'handler', 'fault_time', 'fault_category', 'fault_type',
              'result', 'impact_range', 'recovery_time', 'ticket_number', 'created_at')
FAULT_DETAIL = FAULT_LIST
FAULT_FORM = ('title', 'customer_name', 'handler', 'fault_time', 'fault_type',
              'fault_category', 'result', 'fault_description', 'fault_cause', 'solution',
              'impact_range', 'recovery_time')
FAULT_EXPORT_DEFAULT = ('title', 'customer_name', 'handler', 'fault_time', 'fault_type',
                        'result', 'recovery_time', 'created_at')
FAULT_EXPORT_AVAILABLE = tuple(dict.fromkeys(FAULT_EXPORT_DEFAULT + FAULT_LIST))


INSPECTION_FIELDS = (
    F('title', '标题', min_width=180, required=True, sortable=True),
    F('customer_name', '客户', export_key='customer', min_width=100, filterable=True),
    F('inspector_name', '巡检人员', export_key='inspector', width=90, filterable=True),
    F('inspection_date', '巡检日期', data_type='date', width=100, sortable=True),
    F('overall_status', '总体状态', width=90, filterable=True),
    F('review_status', '审核状态', width=90, filterable=True),
    F('complete', '资料完整', data_type='boolean', width=100, group='quality'),
    F('report_label', '正式报告', width=80, group='report'),
    F('submitted_report_name', '现场报告', data_type='file', group='report'),
    F('report_file_name', '正式报告', data_type='file', group='report'),
    F('task_title', '关联任务', min_width=160),
    F('conclusion', '结论', min_width=180, group='report'),
    F('location', '位置', min_width=120),
    F('created_at', '创建时间', data_type='datetime', width=130, group='audit'),
)
INSPECTION_LIST = ('title', 'customer_name', 'inspection_date', 'inspector_name',
                   'overall_status', 'review_status', 'complete', 'report_label')
INSPECTION_DETAIL = tuple(item.key for item in INSPECTION_FIELDS)
INSPECTION_FORM = ('title', 'customer_name', 'inspection_date', 'inspector_name',
                   'overall_status', 'conclusion', 'location')
INSPECTION_EXPORT_DEFAULT = ('title', 'customer_name', 'inspector_name', 'inspection_date',
                             'overall_status', 'review_status', 'conclusion', 'location',
                             'created_at')


SPARE_FIELDS = (
    F('name', '名称', min_width=160, required=True, sortable=True),
    F('code', '备件编码', width=110, sortable=True),
    F('category', '类别', width=90, filterable=True),
    F('specification', '规格', min_width=120),
    F('unit', '单位', width=60),
    F('brand', '品牌', width=90, filterable=True),
    F('model', '型号', min_width=100),
    F('serial_number', '序列号', min_width=130),
    F('manufacturer', '厂家', min_width=110),
    F('total_stock', '库存数量', export_key='quantity', data_type='number', width=90),
    F('min_stock', '库存下限', data_type='number', width=90),
    F('stock_alert_label', '预警', width=90, group='inventory'),
    F('reference_price', '参考价', data_type='money', width=100, group='commercial'),
    F('warranty_months', '质保月数', data_type='number', width=90, group='lifecycle'),
    F('remark', '备注', min_width=140),
    F('created_at', '创建时间', data_type='datetime', width=130, group='audit'),
)
SPARE_LIST = ('name', 'code', 'category', 'brand', 'model', 'unit', 'min_stock',
              'total_stock', 'stock_alert_label')
SPARE_DETAIL = tuple(item.key for item in SPARE_FIELDS)
SPARE_FORM = ('name', 'code', 'category', 'brand', 'model', 'specification', 'unit',
              'min_stock', 'reference_price', 'warranty_months', 'manufacturer',
              'serial_number', 'remark')
SPARE_EXPORT_DEFAULT = ('code', 'name', 'category', 'specification', 'unit', 'brand',
                        'model', 'serial_number', 'manufacturer', 'total_stock', 'min_stock',
                        'remark', 'created_at')


CUSTOMER_FIELDS = (
    F('name', '客户名称', required=True, min_width=180, sortable=True),
    F('contact_person', '联系人', min_width=100),
    F('phone', '电话', min_width=120),
    F('email', '邮箱', min_width=160),
    F('region_name', '所属地区', export_key='region', min_width=120, filterable=True),
    F('city', '地市', width=100, filterable=True),
    F('address', '地址', min_width=180),
    F('category_name', '单位类别', export_key='category', min_width=110, filterable=True),
    F('level', '客户等级', width=90, filterable=True),
    F('office', '办公室', min_width=110),
    F('office_room', '办公室门牌号', min_width=120),
    F('map_location', '地图定位', min_width=160),
    F('has_onsite', '有无驻场', data_type='boolean', width=90),
    F('onsite_contact', '驻场联系人', min_width=110),
    F('onsite_phone', '驻场联系方式', min_width=120),
    F('onsite_office', '驻场办公室', min_width=110),
    F('has_drill', '有无攻防演练', data_type='boolean', width=110),
    F('inspection_frequency', '巡检频率', export_key='frequency', width=100),
    F('source', '来源', min_width=100),
    F('contract_start_date', '合同开始日期', data_type='date', width=110, group='contract'),
    F('contract_end_date', '合同结束日期', data_type='date', width=110, group='contract'),
    F('contract_status', '合同状态', width=100, group='contract'),
    F('device_count', '设备数量', data_type='number', width=90, group='statistics'),
    F('inspection_count', '巡检数量', data_type='number', width=90, group='statistics'),
    F('ticket_count', '工单数量', data_type='number', width=90, group='statistics'),
    F('remark', '备注', min_width=140),
    F('created_at', '创建时间', data_type='datetime', width=130, group='audit'),
)
CUSTOMER_LIST = ('name', 'region_name', 'city', 'level', 'contract_status', 'device_count')
CUSTOMER_DETAIL = tuple(item.key for item in CUSTOMER_FIELDS)
CUSTOMER_FORM = ('name', 'contact_person', 'phone', 'email', 'region_name', 'city', 'address',
                 'category_name', 'level', 'office_room', 'map_location', 'has_onsite',
                 'onsite_contact', 'onsite_phone', 'onsite_office', 'has_drill',
                 'inspection_frequency', 'source', 'contract_start_date', 'contract_end_date',
                 'remark')
# Keep the legacy default export stable; richer detail fields are opt-in through export_available.
CUSTOMER_EXPORT_DEFAULT = ('name', 'contact_person', 'phone', 'email', 'region_name', 'city',
                           'address', 'category_name', 'level', 'office', 'has_onsite',
                           'onsite_contact', 'onsite_phone', 'onsite_office', 'has_drill',
                           'inspection_frequency', 'source', 'remark', 'created_at')
CUSTOMER_EXPORT_AVAILABLE = tuple(dict.fromkeys(
    CUSTOMER_EXPORT_DEFAULT + ('office_room', 'map_location', 'contract_start_date',
                               'contract_end_date', 'contract_status', 'device_count',
                               'inspection_count', 'ticket_count')))


# Sales pipeline: list and edit dialogs use the same labels and formats.
OPPORTUNITY_FIELDS = (
    F('title', '商机标题', min_width=200, required=True, sortable=True),
    F('customer_id', '客户', data_type='relation', required=True),
    F('customer_name', '客户', min_width=120, filterable=True),
    F('stage', '阶段', width=100, filterable=True),
    F('expected_amount', '预计金额', data_type='money', width=110),
    F('expected_close_date', '预计成交日', data_type='date', width=110),
    F('owner', '负责人', width=90, filterable=True),
    F('remark', '备注', min_width=160),
    F('created_at', '创建时间', data_type='datetime', width=140, group='audit'),
)
OPPORTUNITY_LIST = ('title', 'customer_name', 'stage', 'expected_amount',
                    'expected_close_date', 'owner')
OPPORTUNITY_FORM = ('title', 'customer_id', 'stage', 'expected_amount',
                    'expected_close_date', 'owner', 'remark')

QUOTATION_FIELDS = (
    F('number', '报价单号', min_width=130, required=True, sortable=True),
    F('customer_id', '客户', data_type='relation', required=True),
    F('customer_name', '客户', min_width=120, filterable=True),
    F('opportunity_id', '关联商机', data_type='relation'),
    F('opportunity_title', '关联商机', min_width=140),
    F('total_amount', '总金额', data_type='money', width=110),
    F('status', '状态', width=90, filterable=True),
    F('valid_until', '有效期至', data_type='date', width=110),
    F('items', '报价明细', data_type='list', group='detail'),
    F('created_at', '创建时间', data_type='datetime', width=140, group='audit'),
)
QUOTATION_LIST = ('number', 'customer_name', 'opportunity_title', 'total_amount',
                  'status', 'valid_until')
QUOTATION_FORM = ('number', 'opportunity_id', 'customer_id', 'total_amount',
                  'valid_until', 'status', 'items')

CONTRACT_FIELDS = (
    F('number', '合同编号', width=120, sortable=True),
    F('title', '合同标题', min_width=180, required=True, sortable=True),
    F('customer_id', '客户', data_type='relation', required=True),
    F('customer_name', '客户', min_width=110, filterable=True),
    F('amount', '合同金额', data_type='money', width=110),
    F('status', '状态', width=90, filterable=True),
    F('start_date', '开始日期', data_type='date', width=100),
    F('end_date', '结束日期', data_type='date', width=100),
    F('inspection_frequency', '巡检频率', width=100, group='inspection'),
    F('task_template_id', '任务模板', data_type='relation', group='inspection'),
    F('auto_generate_tasks', '自动巡检', data_type='boolean', width=90,
      group='inspection', value_map={'true': '是', 'false': '否'}),
    F('created_at', '创建时间', data_type='datetime', width=140, group='audit'),
)
CONTRACT_LIST = ('number', 'title', 'customer_name', 'amount', 'status', 'start_date',
                 'end_date', 'auto_generate_tasks')
CONTRACT_FORM = ('number', 'title', 'customer_id', 'amount', 'status', 'start_date',
                 'end_date', 'inspection_frequency', 'task_template_id',
                 'auto_generate_tasks')

PROJECT_FIELDS = (
    F('name', '项目名称', min_width=180, required=True, sortable=True),
    F('customer_id', '客户', data_type='relation', required=True),
    F('customer_name', '客户', min_width=110, filterable=True),
    F('contract_id', '关联合同', data_type='relation'),
    F('contract_title', '关联合同', min_width=130),
    F('manager', '负责人', width=90, filterable=True),
    F('status', '状态', width=90, filterable=True),
    F('progress', '进度(%)', data_type='number', width=80),
    F('budget', '预算', data_type='money', width=110),
    F('start_date', '开始日期', data_type='date', width=100),
    F('end_date', '结束日期', data_type='date', width=100),
    F('created_at', '创建时间', data_type='datetime', width=140, group='audit'),
)
PROJECT_LIST = ('name', 'customer_name', 'contract_title', 'manager', 'status',
                'progress', 'budget')
PROJECT_FORM = ('name', 'contract_id', 'customer_id', 'manager', 'status',
                'start_date', 'end_date', 'progress', 'budget')


# Inventory transactions: archive, stock, orders and borrowing share canonical wording.
SPARE_STOCK_FIELDS = (
    F('spare_part_id', '备件', data_type='relation', required=True),
    F('spare_part_name', '备件', min_width=180, sortable=True),
    F('location', '库位', min_width=110),
    F('quantity', '数量', data_type='number', width=90),
    F('unit_price', '单价', data_type='money', width=110),
    F('updated_at', '更新时间', data_type='datetime', width=140, group='audit'),
)
SPARE_STOCK_LIST = ('spare_part_name', 'location', 'quantity', 'unit_price', 'updated_at')
SPARE_STOCK_FORM = ('spare_part_id', 'location', 'quantity', 'unit_price')

PURCHASE_ORDER_FIELDS = (
    F('spare_part_id', '备件', data_type='relation', required=True),
    F('spare_part_name', '备件', min_width=160),
    F('supplier', '供应商', min_width=120),
    F('supplier_name', '供应商', min_width=120),
    F('quantity', '数量', data_type='number', width=80, required=True),
    F('unit_price', '单价', data_type='money', width=100),
    F('total', '总额', data_type='money', width=110),
    F('purchase_date', '采购日期', data_type='date', width=100),
    F('operator', '经办人', width=90),
    F('remark', '备注', min_width=160),
)
PURCHASE_ORDER_LIST = ('spare_part_name', 'supplier_name', 'quantity', 'unit_price',
                       'total', 'purchase_date', 'operator')
PURCHASE_ORDER_FORM = ('spare_part_id', 'quantity', 'unit_price', 'supplier',
                       'purchase_date', 'remark')

SALES_ORDER_FIELDS = (
    F('spare_part_id', '备件', data_type='relation', required=True),
    F('spare_part_name', '备件', min_width=150),
    F('customer_id', '客户', data_type='relation', required=True),
    F('customer_name', '客户', min_width=130),
    F('quantity', '数量', data_type='number', width=80, required=True),
    F('unit_price', '单价', data_type='money', width=100),
    F('total', '总额', data_type='money', width=110),
    F('sales_date', '销售日期', data_type='date', width=100),
    F('operator', '经办人', width=90),
    F('remark', '备注', min_width=160),
)
SALES_ORDER_LIST = ('spare_part_name', 'customer_name', 'quantity', 'unit_price',
                    'total', 'sales_date', 'operator')
SALES_ORDER_FORM = ('spare_part_id', 'customer_id', 'quantity', 'unit_price',
                    'sales_date', 'remark')

SPARE_BORROW_FIELDS = (
    F('spare_part_id', '备件', data_type='relation', required=True),
    F('part_name', '备件', min_width=140),
    F('borrower', '借用人', width=90, required=True),
    F('borrower_phone', '联系电话', min_width=110),
    F('quantity', '数量', data_type='number', width=70, required=True),
    F('location', '库位', min_width=90),
    F('borrow_date', '借出日期', data_type='date', width=100),
    F('expected_return_date', '预计归还日期', data_type='date', width=110),
    F('return_date', '实际归还日期', data_type='date', width=110),
    F('status', '状态', width=80, filterable=True),
    F('operator', '经办人', width=80),
    F('remark', '备注', min_width=160),
)
SPARE_BORROW_LIST = ('part_name', 'borrower', 'borrower_phone', 'quantity', 'location',
                     'borrow_date', 'expected_return_date', 'status', 'operator')
SPARE_BORROW_FORM = ('spare_part_id', 'borrower', 'borrower_phone', 'quantity',
                     'expected_return_date', 'remark')


KNOWLEDGE_FIELDS = (
    F('title', '标题', min_width=220, required=True, sortable=True),
    F('category', '分类', width=100, filterable=True),
    F('tags', '标签', data_type='list', min_width=140),
    F('content', '内容', data_type='longtext', min_width=220),
    F('attachments', '附件', data_type='list', min_width=200),
    F('view_count', '查看数', data_type='number', width=80),
    F('helpful_count', '有用数', data_type='number', width=80),
    F('is_published', '是否发布', data_type='boolean'),
    F('published_label', '发布状态', width=90, filterable=True),
    F('created_by', '创建人', width=100),
    F('created_at', '创建时间', data_type='datetime', width=130, group='audit'),
)
KNOWLEDGE_LIST = ('title', 'category', 'attachments', 'view_count', 'helpful_count',
                  'published_label', 'created_by', 'created_at')
KNOWLEDGE_FORM = ('title', 'category', 'tags', 'content', 'attachments', 'is_published')

INSPECTOR_FIELDS = (
    F('user_id', '系统用户', data_type='relation', required=True),
    F('name', '姓名', min_width=120, sortable=True),
    F('username', '用户名', min_width=120),
    F('phone', '手机', min_width=130),
    F('email', '邮箱', min_width=180),
    F('is_active', '状态', data_type='boolean', width=90,
      value_map={'true': '启用', 'false': '停用'}),
    F('remark', '备注', min_width=140),
)
INSPECTOR_LIST = ('name', 'username', 'phone', 'email', 'is_active', 'remark')
INSPECTOR_FORM = ('user_id', 'is_active', 'remark')

CUSTOMER_CATEGORY_FIELDS = (
    F('name', '类别名称', min_width=200, required=True, sortable=True),
    F('sort_order', '排序', data_type='number', width=100),
)

AUDIT_LOG_FIELDS = (
    F('created_at', '时间', data_type='datetime', width=150, sortable=True),
    F('username', '操作人', width=100, filterable=True),
    F('action', '操作', width=130, filterable=True),
    F('target_type', '对象', width=90, filterable=True),
    F('detail', '详情', min_width=220),
    F('ip', 'IP', width=130),
)

USER_FIELDS = (
    F('username', '用户名', min_width=110, required=True, sortable=True),
    F('realname', '姓名', width=90),
    F('roles', '角色', data_type='list', width=180),
    F('department_id', '部门', data_type='relation'),
    F('department_name', '部门', min_width=100),
    F('region_ids', '负责区域', data_type='list'),
    F('region_names', '负责区域', data_type='list', min_width=130),
    F('customer_ids', '关联客户', data_type='list'),
    F('customer_names', '关联客户', data_type='list', min_width=130),
    F('is_active', '状态', data_type='boolean', width=80,
      value_map={'true': '启用', 'false': '停用'}),
    F('phone', '电话', min_width=110),
    F('email', '邮箱', min_width=160),
    F('wecom_account', '企业微信账号', min_width=130),
    F('vpn_account', 'VPN账号', min_width=110, default_visible=False),
    F('password', '密码', sensitive=True, permission='user:edit'),
    F('certifications', '资质证书', data_type='list'),
    F('mfa_enabled', '登录MFA', data_type='boolean', width=90, group='security'),
    F('mfa_op_enabled', '操作码', data_type='boolean', width=90, group='security'),
    F('created_at', '创建时间', data_type='datetime', width=100, group='audit'),
)
USER_LIST = ('username', 'realname', 'roles', 'department_name', 'region_names',
             'customer_names', 'is_active', 'phone', 'vpn_account', 'mfa_enabled',
             'mfa_op_enabled', 'created_at')
USER_FORM = ('username', 'realname', 'roles', 'department_id', 'phone', 'email',
             'wecom_account', 'vpn_account', 'region_ids', 'customer_ids', 'password',
             'is_active', 'certifications')

ROLE_FIELDS = (
    F('name', '名称', min_width=120, required=True, sortable=True),
    F('code', '代码', min_width=120, required=True),
    F('description', '描述', min_width=160),
    F('sort_order', '排序', data_type='number', width=70),
    F('is_active', '启用', data_type='boolean', width=80,
      value_map={'true': '启用', 'false': '停用'}),
    F('is_system', '内置角色', data_type='boolean', width=90),
    F('user_count', '用户数', data_type='number', width=80),
    F('perm_count', '权限数', data_type='number', width=80),
    F('permissions', '权限', data_type='list'),
)
ROLE_LIST = ('name', 'code', 'description', 'sort_order', 'is_active', 'user_count',
             'perm_count')
ROLE_FORM = ('code', 'name', 'description', 'sort_order', 'is_active')

INSPECTION_TASK_FIELDS = (
    F('title', '任务标题', min_width=200, required=True, sortable=True),
    F('status', '状态', width=100, filterable=True),
    F('priority', '优先级', width=80, filterable=True),
    F('task_type', '任务类型', width=100),
    F('customer_name', '客户', min_width=120, filterable=True),
    F('assigned_to', '负责人', width=100),
    F('assigned_to_name', '负责人', width=100),
    F('planned_start', '计划开始', data_type='date', width=110),
    F('planned_end', '计划结束', data_type='date', width=110),
    F('estimated_effort', '预计工时', data_type='number', width=90),
    F('actual_effort', '实际工时', data_type='number', width=90),
    F('source', '来源', width=100),
    F('remark', '备注', min_width=160),
)

TASK_TEMPLATE_FIELDS = (
    F('name', '模板名称', min_width=180, required=True, sortable=True),
    F('category', '类别', width=100, filterable=True),
    F('inspection_type', '巡检类型', width=120),
    F('frequency', '推荐频率', width=90),
    F('customer_tier', '适用客户级别', width=110),
    F('device_template_ids', '关联设备模板', data_type='list', min_width=160),
    F('sections', '章节配置', data_type='list'),
    F('required_assets', '必传资料', data_type='object'),
    F('remark', '备注', min_width=160),
    F('is_active', '状态', data_type='boolean', width=80,
      value_map={'true': '启用', 'false': '停用'}),
)
TASK_TEMPLATE_LIST = ('name', 'category', 'inspection_type', 'frequency', 'customer_tier',
                      'device_template_ids', 'is_active')
TASK_TEMPLATE_FORM = ('name', 'category', 'inspection_type', 'frequency', 'customer_tier',
                      'sections', 'device_template_ids', 'required_assets', 'remark', 'is_active')

DEVICE_EXPORT_REQUEST_FIELDS = (
    F('created_at', '申请时间', data_type='datetime', width=140, sortable=True),
    F('username', '申请账号', width=110),
    F('realname', '申请人', width=100),
    F('reason', '申请原因', min_width=200),
    F('status_label', '状态', width=90, filterable=True),
    F('reviewed_at', '审核时间', data_type='datetime', width=140),
    F('review_comment', '审核意见', min_width=150),
    F('downloaded', '已下载', data_type='boolean', width=80),
)

CONFIG_BACKUP_FIELDS = (
    F('backup_type', '备份类型', width=100, filterable=True),
    F('backup_method', '备份来源', width=100, filterable=True),
    F('backup_date', '备份日期', data_type='date', width=100, sortable=True),
    F('config_content', '配置内容', data_type='text'),
    F('file_name', '备份文件', min_width=150),
    F('checksum', '校验值', min_width=100),
    F('created_by', '创建人', min_width=90),
    F('created_at', '创建时间', data_type='datetime', width=140, sortable=True),
)

PASSWORD_HISTORY_FIELDS = (
    F('id', '记录号', data_type='number', width=70),
    F('changed_by', '修改人', width=120),
    F('created_at', '修改时间', data_type='datetime', width=150, sortable=True),
    F('remark', '备注', min_width=100),
)

FIRMWARE_FIELDS = (
    F('brand', '品牌', width=110, required=True, filterable=True),
    F('model', '型号', min_width=130, required=True, filterable=True),
    F('firmware_type', '固件类型', width=110, required=True, filterable=True),
    F('version', '版本号', width=140, required=True),
    F('release_date', '发布日期', data_type='date', width=110, sortable=True),
    F('file_size_mb', '文件大小(MB)', data_type='number', width=110),
    F('is_latest', '最新版本', data_type='boolean', width=90),
    F('download_url', '下载地址', min_width=180),
    F('md5_checksum', 'MD5 校验', min_width=150),
    F('min_compatible_hardware', '最低硬件要求', min_width=160),
    F('changelog', '更新说明', min_width=180),
    F('upgrade_guide', '升级步骤', min_width=180),
    F('remark', '备注', min_width=160),
)

DEVICE_DICTIONARY_FIELDS = (
    F('name', '名称', min_width=200, required=True),
    F('field_type', '字段类型', width=120),
    F('sort_order', '排序', data_type='number', width=80),
)

RACK_FIELDS = (
    F('name', '机柜名称', min_width=140, required=True),
    F('customer_name', '所属客户', min_width=120, filterable=True),
    F('location', '机房位置', min_width=120),
    F('total_u', '总U数', data_type='number', width=80),
    F('pdu_total_w', 'PDU功率(W)', data_type='number', width=110),
    F('color', '显示颜色', width=100),
    F('remark', '备注', min_width=160),
)

RACK_INSTALL_FIELDS = (
    F('start_u', '起始U位', data_type='number', width=90),
    F('occupy_u', '占用U数', data_type='number', width=90),
    F('name', '设备名称', min_width=140, required=True),
    F('brand', '品牌', width=100),
    F('model', '型号', width=110),
    F('ip', 'IP', min_width=110),
    F('kind', '来源', width=70),
    F('rated_w', '功耗(W)', data_type='number', width=80),
    F('remark', '备注', min_width=140),
)

TOPOLOGY_FIELDS = (
    F('name', '名称', min_width=260, required=True),
    F('description', '描述', min_width=160),
    F('customer_name', '客户', min_width=120, filterable=True),
    F('region_name', '地区', width=100, filterable=True),
    F('file_type', '拓扑图类型', width=110),
    F('file_name', '文件', min_width=160),
    F('upload_by', '上传人', width=100),
    F('created_at', '上传时间', data_type='datetime', width=140, sortable=True),
)

NOTIFY_RULE_FIELDS = (
    F('label', '通知类型', min_width=140),
    F('event_type', '事件标识', min_width=180),
    F('roles', '接收角色', data_type='list', min_width=200),
    F('users', '接收用户', data_type='list', min_width=220),
    F('is_enabled', '启用', data_type='boolean', width=80),
)

REVIEW_CHECKLIST_FIELDS = (
    F('sort_order', '顺序', data_type='number', width=70),
    F('name', '检查项名称', min_width=220, required=True),
    F('enabled', '启用', data_type='boolean', width=90),
)

REPORT_FIELDS = (
    F('type', '类型', width=90, filterable=True),
    F('title', '标题 / 文件名', min_width=200, sortable=True),
    F('customer_name', '客户', min_width=100, filterable=True),
    F('date', '日期', data_type='datetime', width=140, sortable=True),
    F('status', '状态', width=90, filterable=True),
    F('report', '报告文件', min_width=180),
)


ENTITY_SCHEMAS = {
    'device': EntitySchema('device', '设备', 'device:view', DEVICE_FIELDS, {
        'list': DEVICE_LIST, 'detail': DEVICE_DETAIL, 'form': DEVICE_FORM,
        'export_default': DEVICE_EXPORT_DEFAULT, 'export_available': DEVICE_EXPORT_AVAILABLE,
    }, export_presets=DEVICE_EXPORT_PRESETS,
        export_preset_labels=DEVICE_EXPORT_PRESET_LABELS),
    'ticket': EntitySchema('ticket', '工单', 'ticket:view', TICKET_FIELDS, {
        'list': TICKET_LIST, 'detail': TICKET_DETAIL, 'form': TICKET_FORM,
        'export_default': TICKET_EXPORT_DEFAULT, 'export_available': TICKET_EXPORT_AVAILABLE,
    }),
    'fault': EntitySchema('fault', '故障', 'fault:view', FAULT_FIELDS, {
        'list': FAULT_LIST, 'detail': FAULT_DETAIL, 'form': FAULT_FORM,
        'export_default': FAULT_EXPORT_DEFAULT, 'export_available': FAULT_EXPORT_AVAILABLE,
    }),
    'inspection': EntitySchema('inspection', '巡检', 'inspection:view', INSPECTION_FIELDS, {
        'list': INSPECTION_LIST, 'detail': INSPECTION_DETAIL, 'form': INSPECTION_FORM,
        'export_default': INSPECTION_EXPORT_DEFAULT,
        'export_available': INSPECTION_EXPORT_DEFAULT,
    }),
    'spare': EntitySchema('spare', '备件', 'spare:view', SPARE_FIELDS, {
        'list': SPARE_LIST, 'detail': SPARE_DETAIL, 'form': SPARE_FORM,
        'export_default': SPARE_EXPORT_DEFAULT, 'export_available': SPARE_EXPORT_DEFAULT,
    }),
    'customer': EntitySchema('customer', '客户', 'customer:view', CUSTOMER_FIELDS, {
        'list': CUSTOMER_LIST, 'detail': CUSTOMER_DETAIL, 'form': CUSTOMER_FORM,
        'export_default': CUSTOMER_EXPORT_DEFAULT,
        'export_available': CUSTOMER_EXPORT_AVAILABLE,
    }),
    'opportunity': EntitySchema('opportunity', '商机', 'sales:view', OPPORTUNITY_FIELDS, {
        'list': OPPORTUNITY_LIST, 'detail': tuple(item.key for item in OPPORTUNITY_FIELDS),
        'form': OPPORTUNITY_FORM,
    }),
    'quotation': EntitySchema('quotation', '报价单', 'sales:view', QUOTATION_FIELDS, {
        'list': QUOTATION_LIST, 'detail': tuple(item.key for item in QUOTATION_FIELDS),
        'form': QUOTATION_FORM,
    }),
    'contract': EntitySchema('contract', '合同', 'sales:view', CONTRACT_FIELDS, {
        'list': CONTRACT_LIST, 'detail': tuple(item.key for item in CONTRACT_FIELDS),
        'form': CONTRACT_FORM,
    }),
    'project': EntitySchema('project', '项目', 'sales:view', PROJECT_FIELDS, {
        'list': PROJECT_LIST, 'detail': tuple(item.key for item in PROJECT_FIELDS),
        'form': PROJECT_FORM,
    }),
    'spare_stock': EntitySchema('spare_stock', '备件库存', 'spare:view', SPARE_STOCK_FIELDS, {
        'list': SPARE_STOCK_LIST, 'detail': tuple(item.key for item in SPARE_STOCK_FIELDS),
        'form': SPARE_STOCK_FORM,
    }),
    'purchase_order': EntitySchema('purchase_order', '采购单', 'spare:view',
                                   PURCHASE_ORDER_FIELDS, {
        'list': PURCHASE_ORDER_LIST, 'detail': tuple(item.key for item in PURCHASE_ORDER_FIELDS),
        'form': PURCHASE_ORDER_FORM,
    }),
    'sales_order': EntitySchema('sales_order', '销售单', 'spare:view', SALES_ORDER_FIELDS, {
        'list': SALES_ORDER_LIST, 'detail': tuple(item.key for item in SALES_ORDER_FIELDS),
        'form': SALES_ORDER_FORM,
    }),
    'spare_borrow': EntitySchema('spare_borrow', '备件借用', 'spare:view',
                                 SPARE_BORROW_FIELDS, {
        'list': SPARE_BORROW_LIST, 'detail': tuple(item.key for item in SPARE_BORROW_FIELDS),
        'form': SPARE_BORROW_FORM,
    }),
    'knowledge': EntitySchema('knowledge', '知识库', 'kb:view', KNOWLEDGE_FIELDS, {
        'list': KNOWLEDGE_LIST, 'detail': tuple(item.key for item in KNOWLEDGE_FIELDS),
        'form': KNOWLEDGE_FORM,
    }),
    'inspector': EntitySchema('inspector', '巡检人员', 'inspection:view', INSPECTOR_FIELDS, {
        'list': INSPECTOR_LIST, 'detail': tuple(item.key for item in INSPECTOR_FIELDS),
        'form': INSPECTOR_FORM,
    }),
    'customer_category': EntitySchema('customer_category', '客户类别', 'category:view',
                                      CUSTOMER_CATEGORY_FIELDS, {
        'list': ('name', 'sort_order'), 'detail': ('name', 'sort_order'),
        'form': ('name', 'sort_order'),
    }),
    'audit_log': EntitySchema('audit_log', '审计日志', 'user:view', AUDIT_LOG_FIELDS, {
        'list': tuple(item.key for item in AUDIT_LOG_FIELDS),
        'detail': tuple(item.key for item in AUDIT_LOG_FIELDS),
    }),
    'user': EntitySchema('user', '用户', 'user:view', USER_FIELDS, {
        'list': USER_LIST, 'detail': tuple(item.key for item in USER_FIELDS if item.key != 'password'),
        'form': USER_FORM,
    }),
    'role': EntitySchema('role', '角色', 'permission:view', ROLE_FIELDS, {
        'list': ROLE_LIST, 'detail': tuple(item.key for item in ROLE_FIELDS),
        'form': ROLE_FORM,
    }),
    'inspection_task': EntitySchema('inspection_task', '巡检任务', 'inspection:view',
                                    INSPECTION_TASK_FIELDS, {
        'list': tuple(item.key for item in INSPECTION_TASK_FIELDS),
        'detail': tuple(item.key for item in INSPECTION_TASK_FIELDS),
        'form': ('title', 'priority', 'task_type', 'customer_name', 'assigned_to',
                 'planned_start', 'planned_end', 'estimated_effort', 'remark'),
    }),
    'task_template': EntitySchema('task_template', '任务模板', 'inspection:view',
                                  TASK_TEMPLATE_FIELDS, {
        'list': TASK_TEMPLATE_LIST, 'detail': tuple(item.key for item in TASK_TEMPLATE_FIELDS),
        'form': TASK_TEMPLATE_FORM,
    }),
    'device_export_request': EntitySchema(
        'device_export_request', '设备密码导出申请', 'device:view',
        DEVICE_EXPORT_REQUEST_FIELDS, {
            'list': tuple(item.key for item in DEVICE_EXPORT_REQUEST_FIELDS),
            'detail': tuple(item.key for item in DEVICE_EXPORT_REQUEST_FIELDS),
        }),
    'device_export_review': EntitySchema(
        'device_export_review', '设备密码导出审核', 'device:export_review',
        DEVICE_EXPORT_REQUEST_FIELDS, {
            'list': tuple(item.key for item in DEVICE_EXPORT_REQUEST_FIELDS),
            'detail': tuple(item.key for item in DEVICE_EXPORT_REQUEST_FIELDS),
        }),
    'config_backup': EntitySchema('config_backup', '设备配置备份', 'device:view',
                                  CONFIG_BACKUP_FIELDS, {
        'list': tuple(item.key for item in CONFIG_BACKUP_FIELDS),
        'detail': tuple(item.key for item in CONFIG_BACKUP_FIELDS),
        'form': ('backup_type', 'config_content', 'file_name'),
    }),
    'password_history': EntitySchema('password_history', '设备密码历史', 'device:view',
                                     PASSWORD_HISTORY_FIELDS, {
        'list': tuple(item.key for item in PASSWORD_HISTORY_FIELDS),
        'detail': tuple(item.key for item in PASSWORD_HISTORY_FIELDS),
    }),
    'firmware': EntitySchema('firmware', '固件版本', 'device:view', FIRMWARE_FIELDS, {
        'list': ('version', 'release_date', 'file_size_mb', 'changelog'),
        'detail': tuple(item.key for item in FIRMWARE_FIELDS),
        'form': tuple(item.key for item in FIRMWARE_FIELDS),
    }),
    'device_dictionary': EntitySchema('device_dictionary', '设备字典', 'device:view',
                                      DEVICE_DICTIONARY_FIELDS, {
        'list': tuple(item.key for item in DEVICE_DICTIONARY_FIELDS),
        'detail': tuple(item.key for item in DEVICE_DICTIONARY_FIELDS),
        'form': tuple(item.key for item in DEVICE_DICTIONARY_FIELDS),
    }),
    'rack': EntitySchema('rack', '机柜', 'device:view', RACK_FIELDS, {
        'list': tuple(item.key for item in RACK_FIELDS),
        'detail': tuple(item.key for item in RACK_FIELDS),
        'form': tuple(item.key for item in RACK_FIELDS),
    }),
    'rack_install': EntitySchema('rack_install', '机柜上架设备', 'device:view',
                                 RACK_INSTALL_FIELDS, {
        'list': tuple(item.key for item in RACK_INSTALL_FIELDS),
        'detail': tuple(item.key for item in RACK_INSTALL_FIELDS),
        'form': tuple(item.key for item in RACK_INSTALL_FIELDS),
    }),
    'topology': EntitySchema('topology', '拓扑图', 'topology:view', TOPOLOGY_FIELDS, {
        'list': ('name', 'description', 'upload_by', 'created_at'),
        'detail': tuple(item.key for item in TOPOLOGY_FIELDS),
        'form': ('file_type', 'name', 'description', 'customer_name', 'region_name', 'file_name'),
    }),
    'notify_rule': EntitySchema('notify_rule', '通知规则', 'notify:view', NOTIFY_RULE_FIELDS, {
        'list': tuple(item.key for item in NOTIFY_RULE_FIELDS),
        'detail': tuple(item.key for item in NOTIFY_RULE_FIELDS),
        'form': ('roles', 'users', 'is_enabled'),
    }),
    'review_checklist': EntitySchema('review_checklist', '巡检审核清单', 'inspection:view',
                                    REVIEW_CHECKLIST_FIELDS, {
        'list': tuple(item.key for item in REVIEW_CHECKLIST_FIELDS),
        'form': ('name', 'enabled'),
    }),
    'review_checklist_config': EntitySchema(
        'review_checklist_config', '巡检审核清单配置', 'permission:edit',
        REVIEW_CHECKLIST_FIELDS, {
            'list': tuple(item.key for item in REVIEW_CHECKLIST_FIELDS),
            'form': ('name', 'enabled'),
        }),
    'contract_inspection_task': EntitySchema(
        'contract_inspection_task', '合同巡检任务', 'contract_auto:manage',
        INSPECTION_TASK_FIELDS, {
            'list': tuple(item.key for item in INSPECTION_TASK_FIELDS),
            'detail': tuple(item.key for item in INSPECTION_TASK_FIELDS),
        }),
    'report': EntitySchema('report', '报告', 'report:view', REPORT_FIELDS, {
        'list': tuple(item.key for item in REPORT_FIELDS),
        'detail': tuple(item.key for item in REPORT_FIELDS),
    }),
}
