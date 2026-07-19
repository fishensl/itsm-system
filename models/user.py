# -*- coding: utf-8 -*-
"""用户 / 部门 / 权限体系模型"""
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from models.base import db




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
        # 历史明文数据兼容：校验通过则就地升级为哈希。
        # 副作用提交上移：不再在模型内隐式 commit，由登录流程显式提交（见 views/auth.login）
        if self.password == raw_password:
            self.password = generate_password_hash(raw_password)
            self._plaintext_upgraded = True  # 标记位，login 流程检测后显式 commit
            return True
        return False

    def needs_rehash(self):
        """旧 pbkdf2 哈希标记：登录成功后应升级为 scrypt（werkzeug 3 默认算法）"""
        return (self.password or '').startswith('pbkdf2:')

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
    # V14: 用户级权限覆盖扩展
    granted_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    granted_at = db.Column(db.DateTime, default=datetime.utcnow)
    expire_at = db.Column(db.DateTime, nullable=True)
    remark = db.Column(db.String(256), default='')
    __table_args__ = (
        db.UniqueConstraint('user_id', 'permission_code', name='uq_user_perm'),
        db.Index('ix_up_expire', 'expire_at'),
    )

    user_rel = db.relationship('User', backref='extra_permissions', foreign_keys=[user_id])
    granter_rel = db.relationship('User', backref='granted_user_permissions', foreign_keys=[granted_by_user_id])


class Permission(db.Model):
    """权限码定义表（V14：可停用、可注释）"""
    __tablename__ = 'permissions'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(128), nullable=False)
    category = db.Column(db.String(32), default='')  # customer/asset/ops/sales/spare/system
    sort_order = db.Column(db.Integer, default=0)
    # V14: 扩展
    description = db.Column(db.String(512), default='')
    is_active = db.Column(db.Boolean, default=True)
    is_system = db.Column(db.Boolean, default=False)  # True=utils/permission.py 常量种入
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Role(db.Model):
    """角色（V14：可自定义，不再硬编码 4 个）"""
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, nullable=False)  # 'admin' / 'operator' / 自定义
    name = db.Column(db.String(64), nullable=False)
    description = db.Column(db.String(256), default='')
    is_system = db.Column(db.Boolean, default=False)   # True=内置不可删
    is_active = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    role_perms = db.relationship('RolePermission', backref='role',
                                cascade='all, delete-orphan', lazy='select')
    __table_args__ = (
        db.Index('ix_roles_is_active', 'is_active'),
    )


class RolePermission(db.Model):
    """角色-权限关联（V14）"""
    __tablename__ = 'role_permissions'
    id = db.Column(db.Integer, primary_key=True)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id', ondelete='CASCADE'),
                       nullable=False, index=True)
    permission_code = db.Column(db.String(64), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint('role_id', 'permission_code', name='uq_role_perm'),
    )


