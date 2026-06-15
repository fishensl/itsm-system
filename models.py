"""数据库模型 v3 — 增强版（自定义字段+部门+结构化故障+审核+草稿）"""
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


# ============================
# 基础模型
# ============================

class Department(db.Model):
    """部门层级"""
    __tablename__ = 'departments'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True)
    head_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # 部门主管
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    parent = db.relationship('Department', remote_side='Department.id', backref='children')
    head = db.relationship('User', backref='headed_department', foreign_keys=[head_id], lazy=True)


class User(UserMixin, db.Model):
    """系统用户（V13：人员主数据 — 新增 phone/email/certifications）"""
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    realname = db.Column(db.String(64), default='')
    role = db.Column(db.String(32), default='operator')  # admin / operator / sales / viewer
    scope = db.Column(db.String(16), default='department')  # all / department / self
    is_active = db.Column(db.Boolean, default=True)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True)
    # V13：人员主数据扩展字段
    phone = db.Column(db.String(32), default='')
    email = db.Column(db.String(128), default='')
    certifications = db.Column(db.Text, default='[]')  # JSON 数组字符串，参见 utils/cert_options.py
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    department_rel = db.relationship('Department', backref='members', foreign_keys=[department_id])

    def set_password(self, raw_password):
        self.password = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        if check_password_hash(self.password, raw_password):
            return True
        if self.password == raw_password:
            self.password = generate_password_hash(raw_password)
            try:
                db.session.commit()
            except:
                db.session.rollback()
            return True
        return False

    @staticmethod
    def create_with_password(username, password, realname='', role='operator', department_id=None):
        return User(
            username=username,
            password=generate_password_hash(password),
            realname=realname,
            role=role,
            department_id=department_id,
        )

    @property
    def is_supervisor(self):
        """判断用户是否为部门主管"""
        if not self.department_id:
            return False
        dept = Department.query.get(self.department_id)
        return dept and dept.head_id == self.id

    def cert_list(self):
        """证书 JSON 字符串 -> list（防御老数据）"""
        from utils.cert_options import cert_from_json
        return cert_from_json(self.certifications or '')

    def set_cert_list(self, lst):
        """list -> JSON 字符串 写入 certifications"""
        from utils.cert_options import cert_to_json
        self.certifications = cert_to_json(lst)


class CustomerCategory(db.Model):
    """客户所属单位类别（如：水利局、水文局、电力公司）"""
    __tablename__ = 'customer_categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class FormDraft(db.Model):
    """表单自动保存草稿"""
    __tablename__ = 'form_drafts'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    form_type = db.Column(db.String(32), nullable=False)  # inspection / fault / ticket
    related_id = db.Column(db.Integer, nullable=True)        # 编辑已有记录时的ID，新建为null
    form_data_json = db.Column(db.Text, default='{}')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user_rel = db.relationship('User', backref='drafts')


class UserDashboardPreference(db.Model):
    """用户工作台偏好（卡片选择+排序 + 侧栏自定义）"""
    __tablename__ = 'user_dashboard_preferences'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True, index=True)
    cards_json = db.Column(db.Text, default='[]')  # JSON数组: ["ticket","device","customer",...]
    sidebar_json = db.Column(db.Text, default='null')  # JSON: 侧栏启用 + 顺序；null=用系统默认
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user_rel = db.relationship('User', backref='dashboard_pref', uselist=False)


class UserPermission(db.Model):
    """用户级权限覆盖（在角色模板基础上 grant/deny）"""
    __tablename__ = 'user_permissions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    permission_code = db.Column(db.String(64), nullable=False)
    grant_type = db.Column(db.String(8), default='grant')  # 'grant' / 'deny'

    user_rel = db.relationship('User', backref='extra_permissions')


class Permission(db.Model):
    """权限码定义表"""
    __tablename__ = 'permissions'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(128), nullable=False)
    category = db.Column(db.String(32), default='')  # customer/asset/ops/sales/spare/system
    sort_order = db.Column(db.Integer, default=0)


# ============================
# 地区管理
# ============================

class Region(db.Model):
    """地区树"""
    __tablename__ = 'regions'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('regions.id'), nullable=True)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    parent = db.relationship('Region', remote_side='Region.id', backref='children')


# ============================
# 客户管理
# ============================

class Customer(db.Model):
    """客户"""
    __tablename__ = 'customers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False, index=True)
    contact_person = db.Column(db.String(64), default='')
    phone = db.Column(db.String(32), default='', index=True)
    email = db.Column(db.String(128), default='')
    region_id = db.Column(db.Integer, db.ForeignKey('regions.id'), nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey('customer_categories.id'), nullable=True)  # 单位类别
    city = db.Column(db.String(64), default='')
    address = db.Column(db.String(256), default='')
    level = db.Column(db.String(32), default='常规', index=True)  # 核心/重点/常规（自动计算，可手动覆盖）
    has_onsite = db.Column(db.Boolean, default=False)      # 有无驻场
    has_drill = db.Column(db.Boolean, default=False)       # 有无攻防演练
    inspection_frequency = db.Column(db.String(16), default='')  # 巡检频率
    device_count = db.Column(db.Integer, default=0)        # 关联设备数（冗余快照）
    source = db.Column(db.String(64), default='')           # 转介绍/展会/线上/其他
    remark = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    region_rel = db.relationship('Region', backref='customers', lazy=True)
    category_rel = db.relationship('CustomerCategory', backref='customers', lazy=True)
    devices = db.relationship('Device', backref='customer', lazy='dynamic',
                              cascade='all, delete-orphan')


# ============================
# 设备管理（扩展自 Password 项目）
# ============================

class Device(db.Model):
    """网络设备"""
    __tablename__ = 'devices'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True)
    region_id = db.Column(db.Integer, db.ForeignKey('regions.id'), nullable=True)
    device_name = db.Column(db.String(128), nullable=False)
    device_type = db.Column(db.String(64), default='')
    brand = db.Column(db.String(64), default='')
    model = db.Column(db.String(64), default='')
    serial_number = db.Column(db.String(128), default='')
    network_type = db.Column(db.String(64), default='')      # 内网/外网/DMZ
    ip_address = db.Column(db.String(64), default='', index=True)
    port = db.Column(db.Integer, default=22)
    login_method = db.Column(db.String(32), default='')
    username = db.Column(db.String(128), default='')
    password_encrypted = db.Column(db.Text, default='')
    location = db.Column(db.String(128), default='')
    interface = db.Column(db.String(128), default='')
    os_version = db.Column(db.String(128), default='')
    rule_version = db.Column(db.String(128), default='')
    license_expiry = db.Column(db.Date, nullable=True, index=True)
    cert_expiry_date = db.Column(db.Date, nullable=True)     # 证书到期日
    is_maintenance = db.Column(db.Boolean, default=False)
    is_in_use = db.Column(db.Boolean, default=True, index=True)
    remark = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    region_rel = db.relationship('Region', backref='devices', lazy=True)


class DeviceFirmware(db.Model):
    """设备固件版本库 (V12) — 按品牌+型号管理系统固件/规则库的最新版本与更新说明"""
    __tablename__ = 'device_firmwares'
    id = db.Column(db.Integer, primary_key=True)
    brand = db.Column(db.String(64), nullable=False, default='', index=True)        # 品牌
    model = db.Column(db.String(128), nullable=False, default='', index=True)       # 型号
    firmware_type = db.Column(db.String(32), nullable=False, default='系统固件')     # 系统固件 / 规则库 / BIOS / 其他
    version = db.Column(db.String(64), nullable=False, default='')                  # 版本号
    release_date = db.Column(db.Date, nullable=True)                                # 发布日期
    changelog = db.Column(db.Text, default='')                                      # 更新说明（支持 Markdown）
    download_url = db.Column(db.String(512), default='')                            # 下载地址
    file_size_mb = db.Column(db.Float, default=0)                                   # 文件大小 (MB)
    md5_checksum = db.Column(db.String(64), default='')                             # MD5 校验
    is_latest = db.Column(db.Boolean, default=False, index=True)                    # 是否最新推荐版本（同 brand+model+firmware_type 仅一条 true）
    min_compatible_hardware = db.Column(db.String(256), default='')                 # 最低硬件要求
    upgrade_guide = db.Column(db.Text, default='')                                  # 升级步骤
    remark = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DeviceCredential(db.Model):
    """设备多登录凭证"""
    __tablename__ = 'device_credentials'
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey('devices.id'), nullable=False, index=True)
    login_method = db.Column(db.String(32), default='SSH')
    username = db.Column(db.String(128), default='')
    password_encrypted = db.Column(db.Text, default='')
    status = db.Column(db.String(16), default='normal')  # normal/error
    password_history = db.Column(db.Text, default='[]')  # JSON
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    device_rel = db.relationship('Device', backref='credentials')


class DeviceInterface(db.Model):
    """设备接口信息"""
    __tablename__ = 'device_interfaces'
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey('devices.id'), nullable=False, index=True)
    name = db.Column(db.String(128), default='')
    status = db.Column(db.String(16), default='up')
    ip = db.Column(db.String(64), default='')
    peer_ip = db.Column(db.String(64), default='')
    description = db.Column(db.String(256), default='')

    device_rel = db.relationship('Device', backref='interfaces')


class CustomField(db.Model):
    """设备自定义字段"""
    __tablename__ = 'custom_fields'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    field_type = db.Column(db.String(16), default='text')  # text/date
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class PasswordHistory(db.Model):
    """设备密码修改历史"""
    __tablename__ = 'password_history'
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey('devices.id'), nullable=False, index=True)
    password_encrypted = db.Column(db.Text, default='')
    changed_by = db.Column(db.String(64), default='')
    remark = db.Column(db.String(256), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    device_rel = db.relationship('Device', backref='password_histories')


class DeviceType(db.Model):
    """设备类型"""
    __tablename__ = 'device_types'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class DeviceSubType(db.Model):
    """设备细分类别（V5: 用于巡检模板匹配）"""
    __tablename__ = 'device_sub_types'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    category = db.Column(db.String(32), default='')   # 服务器/网络设备/安全设备/环控设备/会议设备
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class NetworkType(db.Model):
    """网络类型"""
    __tablename__ = 'network_types'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Brand(db.Model):
    """品牌"""
    __tablename__ = 'brands'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ============================
# 巡检管理 — 新模板体系（任务模板 + 设备模板）
# ============================

# 多对多关联表（V10: 加 sort_order 用于子表排序 3.1, 3.2, ...）
task_device_template_link = db.Table(
    'task_device_template_link',
    db.Column('task_template_id', db.Integer, db.ForeignKey('inspection_task_templates.id'), primary_key=True),
    db.Column('device_template_id', db.Integer, db.ForeignKey('inspection_device_templates.id'), primary_key=True),
    db.Column('sort_order', db.Integer, default=0),
)

class InspectionDeviceTemplate(db.Model):
    """设备检查模板 — 定义某类设备的检查项"""
    __tablename__ = 'inspection_device_templates'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    device_category = db.Column(db.String(32), default='网络设备')  # 服务器/网络设备/安全设备/环控设备/会议设备
    device_sub_type = db.Column(db.String(64), default='')          # 细分类别
    items_json = db.Column(db.Text, default='[]')
    # V6.1.4 富字段结构（向后兼容旧的 {name,method,pass}）：
    # [{
    #   "name": "检查电源情况",
    #   "field_type": "status_note",   # status_note/percentage/ping_test/status_abnormal/text/multiline_text/number/dropdown/image/date/version_check
    #   "description": "检查电源结合是否正常,设备加电是否正常",
    #   "standard_desc": "系统版本不低于V7.0.2,规则库为最新",
    #   "help_text": "登录设备执行 display version 查看",
    #   "default_result": "正常",
    #   "enabled": true,                # 是否启用
    #   "required": true,               # 是否必填
    #   "allow_skip": true,             # 必填时是否允许跳过(填跳过原因)
    #   "skip_reasons": "授权过期无法升级,设备EOL不再支持,客户拒绝升级,其他",
    #   "options": "正常,异常,警告",     # dropdown 选项
    #   "ping_target_default": "10.36.5.60",
    #   "min_version": "V7.0.2",        # version_check 用
    #   "min_rule_version": "IPS-20260101",
    #   "sort_order": 0
    # }, ...]
    is_active = db.Column(db.Boolean, default=True)
    remark = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    task_templates = db.relationship('InspectionTaskTemplate', secondary=task_device_template_link,
                                     back_populates='device_templates', lazy='dynamic')


class InspectionTaskTemplate(db.Model):
    """巡检任务模板 — 定义巡检任务的结构（整份报告骨架）"""
    __tablename__ = 'inspection_task_templates'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    category = db.Column(db.String(32), default='日常巡检')  # 日常巡检/季度巡检/年度巡检/应急巡检
    inspection_type = db.Column(db.String(32), default='月度巡检')  # V10: 月度巡检/季度巡检/攻防演练专项/漏洞扫描专项
    frequency = db.Column(db.String(16), default='')          # 推荐频率
    customer_tier = db.Column(db.String(8), default='all')   # 适用客户级别: all/核心/重点/常规
    sections_json = db.Column(db.Text, default='{}')          # V10: 章节配置 {"sections":[{key,title,enabled},...]}
    is_active = db.Column(db.Boolean, default=True)
    remark = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 通过 secondary 自动加载（不带顺序，保持向后兼容）
    device_templates = db.relationship('InspectionDeviceTemplate', secondary=task_device_template_link,
                                       back_populates='task_templates', lazy='subquery')

    def get_ordered_device_templates(self):
        """按 sort_order 返回有序的设备模板列表（V10）"""
        from sqlalchemy import select
        rows = db.session.execute(
            select(task_device_template_link.c.device_template_id, task_device_template_link.c.sort_order)
            .where(task_device_template_link.c.task_template_id == self.id)
            .order_by(task_device_template_link.c.sort_order, task_device_template_link.c.device_template_id)
        ).all()
        if not rows:
            return []
        ids = [r[0] for r in rows]
        # 按 ids 顺序加载
        dts = InspectionDeviceTemplate.query.filter(InspectionDeviceTemplate.id.in_(ids)).all()
        dt_map = {d.id: d for d in dts}
        return [dt_map[i] for i in ids if i in dt_map]


# 旧模板（降级为只读，逐步迁移到新体系）
class InspectionTemplate(db.Model):
    """巡检模板（旧版，已废弃）"""
    __tablename__ = 'inspection_templates'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    device_type = db.Column(db.String(64), default='')
    device_sub_type = db.Column(db.String(64), default='')
    device_model = db.Column(db.String(128), default='')
    template_category = db.Column(db.String(32), default='网络设备')
    report_section_key = db.Column(db.String(8), default='')
    report_section_name = db.Column(db.String(64), default='')
    items_json = db.Column(db.Text, default='[]')
    is_active = db.Column(db.Boolean, default=True)
    remark = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Inspector(db.Model):
    """巡检人员（V13：瘦身为 User 关联表 — 字段已迁移到 User）

    最终结构：仅保留 user_id / is_active / remark。姓名/电话/邮箱/证书全部从 linked_user 取。
    name/phone/email/certifications 通过 hybrid property 兜底，向后兼容旧模板/服务代码。
    """
    __tablename__ = 'inspectors'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True, index=True)
    is_active = db.Column(db.Boolean, default=True)
    remark = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    linked_user = db.relationship('User', backref='linked_inspectors', foreign_keys=[user_id])

    @property
    def name(self):
        """兼容旧模板：ins.name -> 关联用户的姓名（fallback 到 username）"""
        u = self.linked_user
        if not u:
            return ''
        return u.realname or u.username or ''

    @property
    def phone(self):
        u = self.linked_user
        return (u.phone if u else '') or ''

    @property
    def email(self):
        u = self.linked_user
        return (u.email if u else '') or ''

    @property
    def certifications(self):
        """逗号分隔的证书字符串（向后兼容旧模板的字符串展示）"""
        u = self.linked_user
        if not u:
            return ''
        return ','.join(u.cert_list())


class InspectionTask(db.Model):
    """巡检任务"""
    __tablename__ = 'inspection_tasks'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(128), nullable=False)
    task_type = db.Column(db.String(16), default='计划')    # 计划/突发
    status = db.Column(db.String(32), default='待执行')      # 待执行/执行中/已完成/已取消
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    template_id = db.Column(db.Integer, db.ForeignKey('inspection_templates.id'), nullable=True)
    # V11: 关联新任务模板（推荐使用，旧 template_id 保留只读做兼容）
    task_template_id = db.Column(db.Integer, db.ForeignKey('inspection_task_templates.id'), nullable=True)
    planned_start = db.Column(db.Date, nullable=True)
    planned_end = db.Column(db.Date, nullable=True)
    actual_start = db.Column(db.DateTime, nullable=True)
    actual_end = db.Column(db.DateTime, nullable=True)
    inspector_ids = db.Column(db.String(256), default='')     # 逗号分隔的巡检人员 ID 列表
    device_ids_json = db.Column(db.Text, default='[]')         # 设备ID列表
    priority = db.Column(db.String(16), default='中')
    created_by = db.Column(db.String(64), default='')
    # v3 新增：派发 + 来源追踪
    contract_id = db.Column(db.Integer, db.ForeignKey('contracts.id'), nullable=True)         # 来源合同
    source = db.Column(db.String(32), default='手动')          # 手动/合同自动生成
    assigned_to_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)    # 被派发的运维人员
    dispatched_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)          # 派发人（主管）
    dispatched_at = db.Column(db.DateTime, nullable=True)
    template_category = db.Column(db.String(32), default='巡检')  # 巡检/故障处置/攻防演练/其他
    completion_data_json = db.Column(db.Text, default='{}')       # 完成后存储关联数据
    template_ids_json = db.Column(db.Text, default='[]')            # V4: 多模板ID列表
    remark = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    customer_rel = db.relationship('Customer', backref='inspection_tasks')
    template_rel = db.relationship('InspectionTemplate', backref='tasks')
    task_template_rel = db.relationship('InspectionTaskTemplate', backref='tasks', foreign_keys=[task_template_id])
    contract_rel = db.relationship('Contract', backref='generated_tasks')
    assignee_rel = db.relationship('User', foreign_keys=[assigned_to_user_id], backref='assigned_inspection_tasks')
    dispatcher_rel = db.relationship('User', foreign_keys=[dispatched_by], backref='dispatched_inspection_tasks')


class Inspection(db.Model):
    """巡检记录（执行结果）"""
    __tablename__ = 'inspections'
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('inspection_tasks.id'), nullable=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    title = db.Column(db.String(128), nullable=False)
    inspector = db.Column(db.String(64), default='')
    # V13: 巡检人员关联（FK 用于追溯归属）+ 冻结快照（保护历史报告免疫改名）
    inspector_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    inspector_name = db.Column(db.String(64), default='')
    inspector_phone = db.Column(db.String(32), default='')
    inspection_date = db.Column(db.Date, default=datetime.utcnow().date, index=True)
    location = db.Column(db.String(256), default='')
    content_json = db.Column(db.Text, default='[]')
    overall_status = db.Column(db.String(32), default='正常', index=True)
    conclusion = db.Column(db.Text, default='')
    sections_json = db.Column(db.Text, default='{}')
    abnormal_items_json = db.Column(db.Text, default='[]')
    report_file = db.Column(db.String(256), default='')
    # v3 新增：自定义字段值 + 审核流程 + 跳过原因
    field_values_json = db.Column(db.Text, default='{}')     # {"设备名": {"检查项": "值"}}
    skip_reasons_json = db.Column(db.Text, default='{}')      # {"检查项": {"reason": "...", "detail": "..."}}
    review_status = db.Column(db.String(16), default='')      # ''(草稿)/待审核/已通过/已退回
    reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    review_comment = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    customer_rel = db.relationship('Customer', backref='inspections')
    task_rel = db.relationship('InspectionTask', backref='records')
    reviewer_rel = db.relationship('User', foreign_keys=[reviewed_by], backref='reviewed_inspections')
    inspector_user_rel = db.relationship('User', foreign_keys=[inspector_user_id])


# ============================
# 故障 / 工单管理
# ============================

class FaultType(db.Model):
    """故障类型"""
    __tablename__ = 'fault_types'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Ticket(db.Model):
    """工单"""
    __tablename__ = 'tickets'
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(32), nullable=False, index=True)  # WO-20260610-001
    source_type = db.Column(db.String(32), default='手动创建')     # 客户报修/巡检发现/手动创建/定期维护
    priority = db.Column(db.String(16), default='中', index=True)
    status = db.Column(db.String(32), default='待派单', index=True)            # 待派单/待接单/处理中/待审核/待验收/已完成/已关闭
    title = db.Column(db.String(256), nullable=False)
    description = db.Column(db.Text, default='')
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True)
    reporter = db.Column(db.String(64), default='')
    reporter_phone = db.Column(db.String(32), default='')
    related_inspection_id = db.Column(db.Integer, db.ForeignKey('inspections.id'), nullable=True)
    related_device_id = db.Column(db.Integer, db.ForeignKey('devices.id'), nullable=True)
    fault_category_id = db.Column(db.Integer, db.ForeignKey('fault_types.id'), nullable=True)
    assigned_to = db.Column(db.String(64), default='')
    assigned_by = db.Column(db.String(64), default='')
    assigned_at = db.Column(db.DateTime, nullable=True)
    accepted_at = db.Column(db.DateTime, nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    diagnosis = db.Column(db.Text, default='')
    solution = db.Column(db.Text, default='')
    result = db.Column(db.String(32), default='')
    audit_status = db.Column(db.String(16), default='')
    audit_by = db.Column(db.String(64), default='')
    audit_at = db.Column(db.DateTime, nullable=True)
    audit_comment = db.Column(db.Text, default='')
    accept_status = db.Column(db.String(16), default='')
    accept_by = db.Column(db.String(64), default='')
    accept_at = db.Column(db.DateTime, nullable=True)
    accept_comment = db.Column(db.Text, default='')
    service_duration = db.Column(db.Integer, default=0)
    report_file = db.Column(db.String(256), default='')
    created_by = db.Column(db.String(64), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # v3 新增：结构化故障字段（为向量化准备）
    fault_category_level1 = db.Column(db.String(64), default='')  # 硬件故障/软件故障/网络故障/安全事件/配置变更/环境问题
    fault_category_level2 = db.Column(db.String(64), default='')  # 子分类
    symptoms_json = db.Column(db.Text, default='[]')               # [{"symptom":"...","detail":"...","duration":"..."}]
    affected_components_json = db.Column(db.Text, default='[]')    # [{"component":"...","role":"...","impact":"..."}]
    resolution_steps_json = db.Column(db.Text, default='[]')       # [{"step":1,"action":"...","result":"..."}]
    root_cause_category = db.Column(db.String(64), default='')    # 配置错误/硬件老化/软件BUG/人为失误/外部攻击/电力故障
    severity_level = db.Column(db.String(16), default='')          # P1/P2/P3/P4
    impact_scope = db.Column(db.String(128), default='')          # 影响范围
    normalized_tags = db.Column(db.String(256), default='')       # 标准化标签（逗号分隔）

    customer_rel = db.relationship('Customer', backref='tickets')
    inspection_rel = db.relationship('Inspection', backref='tickets')
    device_rel = db.relationship('Device', backref='tickets')
    fault_type_rel = db.relationship('FaultType', backref='tickets')


class TicketLog(db.Model):
    """工单日志"""
    __tablename__ = 'ticket_logs'
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id'), nullable=False, index=True)
    action = db.Column(db.String(32), default='')
    operator = db.Column(db.String(64), default='')
    comment = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    ticket_rel = db.relationship('Ticket', backref='logs')


# 保留旧 Fault 模型（兼容现有数据，逐步被 Ticket 取代）
class Fault(db.Model):
    """故障处理记录（旧）"""
    __tablename__ = 'faults'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id'), nullable=True)
    title = db.Column(db.String(128), nullable=False)
    handler = db.Column(db.String(64), default='')
    fault_time = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    fault_type = db.Column(db.String(64), default='')
    fault_description = db.Column(db.Text, default='')
    impact_range = db.Column(db.String(256), default='')
    fault_cause = db.Column(db.Text, default='')
    solution = db.Column(db.Text, default='')
    result = db.Column(db.String(32), default='已解决')
    recovery_time = db.Column(db.DateTime, nullable=True)
    report_file = db.Column(db.String(256), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # v3 新增：结构化故障字段（与 Ticket 一致，为向量化准备）
    fault_category_level1 = db.Column(db.String(64), default='')
    fault_category_level2 = db.Column(db.String(64), default='')
    symptoms_json = db.Column(db.Text, default='[]')
    affected_components_json = db.Column(db.Text, default='[]')
    resolution_steps_json = db.Column(db.Text, default='[]')
    root_cause_category = db.Column(db.String(64), default='')
    severity_level = db.Column(db.String(16), default='')
    impact_scope = db.Column(db.String(128), default='')
    normalized_tags = db.Column(db.String(256), default='')

    customer_rel = db.relationship('Customer', backref='faults')


# ============================
# 知识库
# ============================

class KnowledgeBase(db.Model):
    """知识库"""
    __tablename__ = 'knowledge_base'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(256), nullable=False)
    category = db.Column(db.String(32), default='故障案例')    # 故障案例/设备手册/内部规范/巡检经验
    content = db.Column(db.Text, default='')
    tags = db.Column(db.String(256), default='')
    related_ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id'), nullable=True)
    related_fault_id = db.Column(db.Integer, db.ForeignKey('faults.id'), nullable=True)
    related_device_type = db.Column(db.String(64), default='')
    view_count = db.Column(db.Integer, default=0)
    helpful_count = db.Column(db.Integer, default=0)
    is_published = db.Column(db.Boolean, default=True)
    created_by = db.Column(db.String(64), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    ticket_rel = db.relationship('Ticket', backref='knowledge_entries')
    fault_rel = db.relationship('Fault', backref='knowledge_entries')
    # V7 附件
    attachments = db.relationship(
        'KnowledgeAttachment', backref='knowledge',
        cascade='all, delete-orphan', lazy='dynamic',
    )


class KnowledgeAttachment(db.Model):
    """知识库附件（V7）"""
    __tablename__ = 'knowledge_attachments'
    id = db.Column(db.Integer, primary_key=True)
    knowledge_id = db.Column(db.Integer, db.ForeignKey('knowledge_base.id'), nullable=False, index=True)
    file_name = db.Column(db.String(256), default='')
    file_path = db.Column(db.String(512), default='')
    file_ext = db.Column(db.String(16), default='')
    file_size = db.Column(db.Integer, default=0)
    uploaded_by = db.Column(db.String(64), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ============================
# 备件管理（四合一）
# ============================

class SparePart(db.Model):
    """备件档案"""
    __tablename__ = 'spare_parts'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True, default='')
    name = db.Column(db.String(128), nullable=False)
    category = db.Column(db.String(64), default='')
    specification = db.Column(db.String(128), default='')
    unit = db.Column(db.String(16), default='个')
    min_stock = db.Column(db.Integer, default=0)
    remark = db.Column(db.Text, default='')
    # V6 新增业务字段
    brand = db.Column(db.String(64), default='')             # 品牌
    model = db.Column(db.String(64), default='')             # 型号
    parameters = db.Column(db.Text, default='')              # 详细参数
    manufacturer = db.Column(db.String(64), default='')      # 厂家
    image_path = db.Column(db.String(512), default='')       # 备件图片
    serial_number = db.Column(db.String(128), default='')    # 序列号
    reference_price = db.Column(db.Float, default=0.0)       # 采购参考价
    warranty_months = db.Column(db.Integer, default=0)       # 保修期（月）
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class SpareStock(db.Model):
    """备件库存"""
    __tablename__ = 'spare_stocks'
    id = db.Column(db.Integer, primary_key=True)
    spare_part_id = db.Column(db.Integer, db.ForeignKey('spare_parts.id'), nullable=False, index=True)
    location = db.Column(db.String(128), default='')
    quantity = db.Column(db.Integer, default=0)
    unit_price = db.Column(db.Float, default=0.0)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    spare_part_rel = db.relationship('SparePart', backref='stocks')


class PurchaseOrder(db.Model):
    """采购入库单"""
    __tablename__ = 'purchase_orders'
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(64), default='')
    spare_part_id = db.Column(db.Integer, db.ForeignKey('spare_parts.id'), nullable=True)
    supplier_name = db.Column(db.String(128), default='')
    quantity = db.Column(db.Integer, default=0)
    unit_price = db.Column(db.Float, default=0.0)
    total = db.Column(db.Float, default=0.0)
    purchase_date = db.Column(db.Date, nullable=True)
    operator = db.Column(db.String(64), default='')
    remark = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    spare_part_rel = db.relationship('SparePart', backref='purchases')


class SalesOrder(db.Model):
    """销售出库单"""
    __tablename__ = 'sales_orders'
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(64), default='')
    spare_part_id = db.Column(db.Integer, db.ForeignKey('spare_parts.id'), nullable=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True)
    quantity = db.Column(db.Integer, default=0)
    unit_price = db.Column(db.Float, default=0.0)
    total = db.Column(db.Float, default=0.0)
    sales_date = db.Column(db.Date, nullable=True)
    operator = db.Column(db.String(64), default='')
    invoice_number = db.Column(db.String(128), default='')
    remark = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    spare_part_rel = db.relationship('SparePart', backref='sales')
    customer_rel = db.relationship('Customer', backref='sales_orders')


# ============================
# 销售管理
# ============================

class Opportunity(db.Model):
    """商机跟进"""
    __tablename__ = 'opportunities'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True)
    title = db.Column(db.String(256), nullable=False)
    stage = db.Column(db.String(32), default='初步接触')  # 初步接触/需求确认/方案报价/商务谈判/成交/失败
    expected_amount = db.Column(db.Float, default=0.0)
    expected_close_date = db.Column(db.Date, nullable=True)
    owner = db.Column(db.String(64), default='')
    remark = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    customer_rel = db.relationship('Customer', backref='opportunities')


class Quotation(db.Model):
    """报价单"""
    __tablename__ = 'quotations'
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(64), default='')
    opportunity_id = db.Column(db.Integer, db.ForeignKey('opportunities.id'), nullable=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True)
    items_json = db.Column(db.Text, default='[]')
    total_amount = db.Column(db.Float, default=0.0)
    valid_until = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(16), default='草稿')  # 草稿/已发送/已接受/已拒绝
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    opportunity_rel = db.relationship('Opportunity', backref='quotations')
    customer_rel = db.relationship('Customer', backref='quotations')


class Contract(db.Model):
    """合同管理"""
    __tablename__ = 'contracts'
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(64), default='')
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True)
    opportunity_id = db.Column(db.Integer, db.ForeignKey('opportunities.id'), nullable=True)
    title = db.Column(db.String(256), nullable=False)
    amount = db.Column(db.Float, default=0.0)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(32), default='执行中')  # 草签/已签/执行中/已完成/已终止
    file_path = db.Column(db.String(256), default='')
    content_json = db.Column(db.Text, default='{}')
    # v3 新增：巡检自动生成配置
    inspection_frequency = db.Column(db.String(32), default='')  # ''/每月/每季度/每半年/每年
    inspection_template_id = db.Column(db.Integer, db.ForeignKey('inspection_templates.id'), nullable=True)
    last_generated_date = db.Column(db.Date, nullable=True)       # 上次生成日，防重复
    auto_generate_tasks = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    customer_rel = db.relationship('Customer', backref='contracts')
    opportunity_rel = db.relationship('Opportunity', backref='contracts')
    template_rel = db.relationship('InspectionTemplate', backref='contracts_with_template')


class Project(db.Model):
    """项目管理"""
    __tablename__ = 'projects'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(256), nullable=False)
    contract_id = db.Column(db.Integer, db.ForeignKey('contracts.id'), nullable=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True)
    manager = db.Column(db.String(64), default='')
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(32), default='未启动')  # 未启动/进行中/已完成/已暂停
    progress = db.Column(db.Integer, default=0)
    budget = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    contract_rel = db.relationship('Contract', backref='projects')
    customer_rel = db.relationship('Customer', backref='projects')


# ============================
# AI 对接 + 设备扩展
# ============================

class AIConfig(db.Model):
    """AI 对接配置"""
    __tablename__ = 'ai_config'
    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(32), default='OpenAI')      # OpenAI/Anthropic/Ollama/自定义
    api_endpoint = db.Column(db.String(256), default='')
    api_key_encrypted = db.Column(db.Text, default='')
    model_name = db.Column(db.String(64), default='gpt-4')
    max_tokens = db.Column(db.Integer, default=2048)
    temperature = db.Column(db.Float, default=0.7)
    inspection_prompt_template = db.Column(db.Text, default='')
    fault_prompt_template = db.Column(db.Text, default='')
    is_enabled = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DeviceConfigBackup(db.Model):
    """设备配置备份"""
    __tablename__ = 'device_config_backups'
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey('devices.id'), nullable=False, index=True)
    backup_type = db.Column(db.String(32), default='运行配置')   # 启动配置/运行配置/全部配置
    config_content = db.Column(db.Text, default='')
    backup_method = db.Column(db.String(32), default='手动输入')  # 自动抓取/手动输入/文件上传/SSH采集/Telnet采集/SNMP采集
    backup_date = db.Column(db.Date, nullable=True)
    file_path = db.Column(db.String(256), default='')
    checksum = db.Column(db.String(64), default='')
    created_by = db.Column(db.String(64), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    device_rel = db.relationship('Device', backref='config_backups')


class Topology(db.Model):
    """网络拓扑图"""
    __tablename__ = 'topologies'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True)
    region_id = db.Column(db.Integer, db.ForeignKey('regions.id'), nullable=True)
    name = db.Column(db.String(256), nullable=False)
    description = db.Column(db.Text, default='')
    file_path = db.Column(db.String(512), default='')
    file_type = db.Column(db.String(32), default='image')    # visio/image/pdf/other
    upload_by = db.Column(db.String(64), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    customer_rel = db.relationship('Customer', backref='topologies')
    region_rel = db.relationship('Region', backref='topologies')


class DeviceCollectTask(db.Model):
    """设备远程采集任务"""
    __tablename__ = 'device_collect_tasks'
    id = db.Column(db.Integer, primary_key=True)
    task_type = db.Column(db.String(32), default='配置备份')   # 配置备份/状态采集/SNMP巡检
    device_id = db.Column(db.Integer, db.ForeignKey('devices.id'), nullable=False, index=True)
    protocol = db.Column(db.String(16), default='SSH')        # SSH/Telnet/SNMPv2c/SNMPv3
    commands_json = db.Column(db.Text, default='[]')
    snmp_oids_json = db.Column(db.Text, default='[]')
    status = db.Column(db.String(16), default='pending')       # pending/running/success/failed
    result_json = db.Column(db.Text, default='{}')
    error_message = db.Column(db.Text, default='')
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_by = db.Column(db.String(64), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    device_rel = db.relationship('Device', backref='collect_tasks')


# ============================
# 机柜管理（V6.1）
# ============================

class RackLocation(db.Model):
    """机柜位置（楼栋/楼层）"""
    __tablename__ = 'rack_locations'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True, index=True)
    building = db.Column(db.String(64), default='')        # 楼栋
    floor = db.Column(db.String(32), default='')           # 楼层
    remark = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    customer_rel = db.relationship('Customer', backref='rack_locations')


class Rack(db.Model):
    """机柜"""
    __tablename__ = 'racks'
    id = db.Column(db.Integer, primary_key=True)
    location_id = db.Column(db.Integer, db.ForeignKey('rack_locations.id'), nullable=True, index=True)
    name = db.Column(db.String(64), nullable=False)         # 机柜编号/名称
    total_u = db.Column(db.Integer, default=42)             # 总 U 数
    color = db.Column(db.String(16), default='#0d6efd')     # 显示颜色
    pdu_total_w = db.Column(db.Integer, default=0)          # PDU 额定总功率（W）
    remark = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    location_rel = db.relationship('RackLocation', backref='racks')


class RackInstall(db.Model):
    """设备上架记录（在机柜中的位置）"""
    __tablename__ = 'rack_installs'
    id = db.Column(db.Integer, primary_key=True)
    rack_id = db.Column(db.Integer, db.ForeignKey('racks.id'), nullable=False, index=True)
    device_id = db.Column(db.Integer, db.ForeignKey('devices.id'), nullable=True, index=True)  # 关联到设备表
    # 当 device_id 为空时表示手动录入（机柜中存在但不在主设备表的设备）
    manual_name = db.Column(db.String(128), default='')     # 手动设备名
    manual_brand = db.Column(db.String(64), default='')
    manual_model = db.Column(db.String(64), default='')
    manual_ip = db.Column(db.String(64), default='')
    start_u = db.Column(db.Integer, default=1)              # 起始 U 位（从 1 开始）
    occupy_u = db.Column(db.Integer, default=1)             # 占用 U 数
    rated_w = db.Column(db.Integer, default=0)              # 额定功耗（W）
    remark = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    rack_rel = db.relationship('Rack', backref='installs')
    device_rel = db.relationship('Device', backref='rack_installs')
