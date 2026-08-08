/** 导出列定义（与后端 blueprints/vue_export.py 的 code 契约一致） */

export interface ExportColumn {
  key: string
  label: string
}

export const DEVICE_EXPORT_COLUMNS: ExportColumn[] = [
  { key: 'customer', label: '客户' },
  { key: 'rack_location', label: '机房位置' },
  { key: 'rack_name', label: '机柜号' },
  { key: 'rack_slot', label: '机柜位置' },
  { key: 'name', label: '名称' },
  { key: 'type', label: '类型' },
  { key: 'brand', label: '品牌' },
  { key: 'model', label: '型号' },
  { key: 'sn', label: '序列号' },
  { key: 'ip', label: 'IP' },
  { key: 'port', label: '端口' },
  { key: 'login_method', label: '登录方式' },
  { key: 'username', label: '登录用户名' },
  { key: 'password', label: '登录密码' },
  { key: 'build_date', label: '建设时间' },
  { key: 'os_version', label: '系统版本' },
  { key: 'rule_version', label: '规则库版本' },
  { key: 'license_start', label: '授权开始' },
  { key: 'license_expiry', label: '授权截止' },
  { key: 'is_maintenance', label: '是否维修' },
  { key: 'is_in_use', label: '是否在用' },
  { key: 'pwd_changed_by', label: '上次修改密码账号' },
  { key: 'pwd_changed_at', label: '上次修改密码时间' },
  { key: 'remark', label: '备注' },
]

/** 设备三预设（默认列集合，字段顺序按业务要求） */
export const DEVICE_PRESETS: { key: string; label: string; columns: string[] }[] = [
  {
    key: 'asset',
    label: '设备资产表',
    columns: ['customer', 'rack_location', 'rack_name', 'rack_slot', 'name', 'type', 'brand',
      'model', 'sn', 'ip', 'build_date', 'is_maintenance', 'is_in_use', 'remark'],
  },
  {
    key: 'password',
    label: '设备密码表',
    columns: ['customer', 'rack_location', 'rack_name', 'rack_slot', 'name', 'type', 'brand',
      'model', 'sn', 'ip', 'port', 'login_method', 'username', 'password', 'is_in_use',
      'pwd_changed_by', 'pwd_changed_at', 'remark'],
  },
  {
    key: 'version',
    label: '网络安全版本控制表',
    columns: ['customer', 'rack_location', 'rack_name', 'rack_slot', 'name', 'type', 'brand',
      'model', 'sn', 'ip', 'build_date', 'os_version', 'rule_version', 'license_start',
      'license_expiry', 'is_in_use', 'remark'],
  },
]

export const INSPECTION_EXPORT_COLUMNS: ExportColumn[] = [
  { key: 'title', label: '标题' },
  { key: 'customer', label: '客户' },
  { key: 'inspector', label: '巡检员' },
  { key: 'inspection_date', label: '巡检日期' },
  { key: 'overall_status', label: '总体状态' },
  { key: 'review_status', label: '审核状态' },
  { key: 'conclusion', label: '结论' },
  { key: 'location', label: '位置' },
  { key: 'created_at', label: '创建时间' },
]

export const TICKET_EXPORT_COLUMNS: ExportColumn[] = [
  { key: 'number', label: '工单号' },
  { key: 'title', label: '标题' },
  { key: 'priority', label: '优先级' },
  { key: 'status', label: '状态' },
  { key: 'customer', label: '客户' },
  { key: 'reporter', label: '报修人' },
  { key: 'assigned_to', label: '处理人' },
  { key: 'created_by', label: '创建人' },
  { key: 'created_at', label: '创建时间' },
  { key: 'completed_at', label: '完成时间' },
]

export const FAULT_EXPORT_COLUMNS: ExportColumn[] = [
  { key: 'title', label: '标题' },
  { key: 'customer', label: '客户' },
  { key: 'handler', label: '处理人' },
  { key: 'fault_time', label: '故障时间' },
  { key: 'fault_type', label: '故障类型' },
  { key: 'result', label: '处理结果' },
  { key: 'recovery_time', label: '恢复时间' },
  { key: 'created_at', label: '创建时间' },
]

export const SPARE_EXPORT_COLUMNS: ExportColumn[] = [
  { key: 'code', label: '备件编码' },
  { key: 'name', label: '名称' },
  { key: 'category', label: '类别' },
  { key: 'specification', label: '规格' },
  { key: 'unit', label: '单位' },
  { key: 'brand', label: '品牌' },
  { key: 'model', label: '型号' },
  { key: 'serial_number', label: '序列号' },
  { key: 'manufacturer', label: '厂家' },
  { key: 'quantity', label: '库存数量' },
  { key: 'min_stock', label: '库存下限' },
  { key: 'remark', label: '备注' },
  { key: 'created_at', label: '创建时间' },
]

export const CUSTOMER_EXPORT_COLUMNS: ExportColumn[] = [
  { key: 'name', label: '客户名称' },
  { key: 'contact_person', label: '联系人' },
  { key: 'phone', label: '电话' },
  { key: 'email', label: '邮箱' },
  { key: 'region', label: '所属地区' },
  { key: 'city', label: '地市' },
  { key: 'address', label: '地址' },
  { key: 'category', label: '单位类别' },
  { key: 'level', label: '客户等级' },
  { key: 'office', label: '办公室' },
  { key: 'has_onsite', label: '有无驻场' },
  { key: 'onsite_contact', label: '驻场联系人' },
  { key: 'onsite_phone', label: '驻场联系方式' },
  { key: 'onsite_office', label: '驻场办公室' },
  { key: 'has_drill', label: '有无攻防演练' },
  { key: 'frequency', label: '巡检频率' },
  { key: 'source', label: '来源' },
  { key: 'remark', label: '备注' },
  { key: 'created_at', label: '创建时间' },
]

/** 资料包项目勾选项（巡检） */
export const INSPECTION_BUNDLE_ITEMS = [
  { key: 'report', label: '现场报告' },
  { key: 'formal_report', label: '正式报告' },
  { key: 'config_zip', label: '完整配置备份包' },
  { key: 'config_text', label: '核心设备文本配置' },
  { key: 'topology', label: '拓扑图' },
  { key: 'asset_list', label: '资产清单' },
]

export const TICKET_BUNDLE_ITEMS = [
  { key: 'report', label: '处理报告（最新版本）' },
]
