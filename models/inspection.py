# -*- coding: utf-8 -*-
"""巡检域模型（模板/任务/记录/巡检员）"""
from datetime import datetime
from models.base import db


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

    # ---- V14: 检查项子项目（自定义组合）支持 ----
    # 新格式（向后兼容）：
    #   {"name": "电源检查", "description": "...", "enabled": true, "required": true, "allow_skip": false,
    #    "sub_items": [
    #        {"label":"状态", "field_type":"status_note", "required":true, "options":"正常,异常", ...},
    #        {"label":"照片", "field_type":"image", "required":false, ...}
    #    ]}
    # 旧格式：{"name":"...", "field_type":"status_note", ...} —— get_normalized_items() 会自动将其
    # 包装成 sub_items: [{label: 主项目 name, field_type: 旧 field_type, ...继承父字段}]，
    # 让下游消费方（巡检表单 / 报告生成器）只需处理一种结构。

    def get_normalized_items(self):
        """返回标准化后的检查项列表：每个项目都保证含一个非空 sub_items 数组。
        旧格式（顶层 field_type）的项目会被自动包装为单元素 sub_items。"""
        import json as _json
        try:
            items = _json.loads(self.items_json or '[]') or []
        except Exception:
            return []
        out = []
        for it in items:
            if not isinstance(it, dict):
                continue
            subs = it.get('sub_items')
            if isinstance(subs, list) and len(subs) > 0:
                out.append(it)
                continue
            # 旧格式包装
            wrapped = dict(it)
            wrapped['sub_items'] = [{
                'label': '',  # 空标签 → 渲染时使用主项目名
                'field_type': it.get('field_type', 'text'),
                'required': it.get('required', False),
                'allow_skip': it.get('allow_skip', False),
                'skip_reasons': it.get('skip_reasons', ''),
                'options': it.get('options', ''),
                'help_text': it.get('help_text', ''),
                'default_result': it.get('default_result', ''),
                'ping_target_default': it.get('ping_target_default', ''),
                'min_version': it.get('min_version', ''),
                'min_rule_version': it.get('min_rule_version', ''),
                'placeholder': it.get('placeholder', ''),
                'sort_order': 0,
            }]
            out.append(wrapped)
        return out

    @property
    def total_sub_items(self):
        """统计所有子项目总数（用于卡片显示真实检查点数量）。"""
        return sum(len(it.get('sub_items') or [{}]) for it in self.get_normalized_items())


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
    status = db.Column(db.String(32), default='待执行', index=True)      # 待执行/执行中/已完成/已取消
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    template_id = db.Column(db.Integer, db.ForeignKey('inspection_templates.id'), nullable=True)
    # V11: 关联新任务模板（推荐使用，旧 template_id 保留只读做兼容）
    task_template_id = db.Column(db.Integer, db.ForeignKey('inspection_task_templates.id'), nullable=True)
    planned_start = db.Column(db.Date, nullable=True)
    planned_end = db.Column(db.Date, nullable=True)
    actual_start = db.Column(db.DateTime, nullable=True)
    actual_end = db.Column(db.DateTime, nullable=True)
    # 预估工作量（单位：人天，允许 0.5 半天）。None=未设置，便于老数据兼容
    estimated_effort = db.Column(db.Float, nullable=True)
    # 实际工作量（单位：人天）。任务执行中/完成后记录，用于与预估对比评估难度与效率
    actual_effort = db.Column(db.Float, nullable=True)
    inspector_ids = db.Column(db.String(256), default='')     # 逗号分隔的巡检人员 ID 列表
    device_ids_json = db.Column(db.Text, default='[]')         # 设备ID列表
    priority = db.Column(db.String(16), default='中')
    created_by = db.Column(db.String(64), default='')
    # v3 新增：派发 + 来源追踪
    contract_id = db.Column(db.Integer, db.ForeignKey('contracts.id'), nullable=True, index=True)  # 来源合同
    source = db.Column(db.String(32), default='手动')          # 手动/合同自动生成
    assigned_to_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)  # 被派发的运维人员
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
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False, index=True)
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
    review_status = db.Column(db.String(16), default='', index=True)      # ''(草稿)/待审核/已通过/已退回
    reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    review_comment = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    customer_rel = db.relationship('Customer', backref='inspections')
    task_rel = db.relationship('InspectionTask', backref='records')
    reviewer_rel = db.relationship('User', foreign_keys=[reviewed_by], backref='reviewed_inspections')
    inspector_user_rel = db.relationship('User', foreign_keys=[inspector_user_id])


