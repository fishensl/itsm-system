"""权限管理工具

V14: get_user_permissions 改为读 DB + 进程级缓存。
    - admin 角色短路：直接返回 PERMISSION_MAP 全部 key
    - 其他角色：Role 表 → role_perms 关系（joinedload 避免 N+1）→ user.extra_permissions 覆盖
    - 缓存键 = role.code，写操作调 invalidate_role(code) 失效
"""
from functools import wraps
from datetime import datetime
from flask import flash, redirect, url_for
from flask_login import current_user
from sqlalchemy.orm import joinedload


# 进程级角色权限缓存：role_code -> frozenset(permission_code)
_role_cache: dict = {}


def invalidate_role(role_code: str) -> None:
    """清除指定角色的缓存。RBAC 写路径必须调用。"""
    if role_code in _role_cache:
        del _role_cache[role_code]


def invalidate_all_roles() -> None:
    """清除所有角色缓存（安全网）。"""
    _role_cache.clear()

# 所有可用的权限 code
PERMISSION_MAP = {
    # 工作台
    'dashboard:view': '工作台-查看',
    # 业务管理
    'customer:view': '客户管理-查看', 'customer:add': '客户管理-新增',
    'customer:edit': '客户管理-编辑', 'customer:delete': '客户管理-删除',
    'region:view': '地区管理-查看', 'region:add': '地区管理-新增',
    'region:edit': '地区管理-编辑', 'region:delete': '地区管理-删除',
    # 运维管理
    'device:view': '设备管理-查看', 'device:add': '设备管理-新增',
    'device:edit': '设备管理-编辑', 'device:delete': '设备管理-删除',
    'topology:view': '拓扑图-查看', 'topology:add': '拓扑图-新增',
    'topology:edit': '拓扑图-编辑', 'topology:delete': '拓扑图-删除',
    'inspection:view': '巡检管理-查看', 'inspection:add': '巡检管理-新增',
    'inspection:edit': '巡检管理-编辑', 'inspection:delete': '巡检管理-删除',
    'inspection:review': '巡检审核-审核',
    'ticket:view': '工单管理-查看', 'ticket:add': '工单管理-新增',
    'ticket:edit': '工单管理-编辑', 'ticket:delete': '工单管理-删除',
    'fault:view': '故障管理-查看', 'fault:add': '故障管理-新增',
    'fault:edit': '故障管理-编辑', 'fault:delete': '故障管理-删除',
    'kb:view': '知识库-查看', 'kb:add': '知识库-新增',
    'kb:edit': '知识库-编辑', 'kb:delete': '知识库-删除',
    # 任务派发
    'task:dispatch': '任务派发-派发', 'task:view_dept': '任务派发-查看部门任务',
    'task:schedule': '任务安排-看板/导入',
    # 部门管理
    'department:view': '部门管理-查看', 'department:edit': '部门管理-编辑',
    # 单位类别
    'category:view': '单位类别-查看', 'category:edit': '单位类别-编辑',
    # 备件管理
    'spare:view': '备件管理-查看', 'spare:add': '备件管理-新增',
    'spare:edit': '备件管理-编辑', 'spare:delete': '备件管理-删除',
    # 销售管理
    'sales:view': '销售管理-查看', 'sales:add': '销售管理-新增',
    'sales:edit': '销售管理-编辑', 'sales:delete': '销售管理-删除',
    # 合同自动巡检
    'contract_auto:manage': '合同自动巡检-管理',
    # 系统设置
    'user:view': '用户管理-查看', 'user:add': '用户管理-新增',
    'user:edit': '用户管理-编辑', 'user:delete': '用户管理-删除',
    'permission:view': '权限管理-查看', 'permission:edit': '权限管理-编辑',
    'report:view': '报告管理-查看',
    'ai:view': 'AI对接-查看', 'ai:edit': 'AI对接-编辑',
    'dashboard:reports': '数据报表-查看',
    'draft:manage': '草稿管理',
}

ADMIN_PERMISSIONS = list(PERMISSION_MAP.keys())

OPERATOR_PERMISSIONS = [
    'dashboard:view',
    'customer:view', 'region:view',
    'device:view', 'device:add', 'device:edit',
    'topology:view',
    'inspection:view', 'inspection:add', 'inspection:edit', 'inspection:review',
    'ticket:view', 'ticket:add', 'ticket:edit',
    'fault:view', 'fault:add', 'fault:edit',
    'kb:view', 'kb:add', 'kb:edit',
    'task:view_dept', 'task:dispatch', 'task:schedule',
    'department:view', 'category:view',
    'contract_auto:manage',
    'spare:view', 'spare:add', 'spare:edit',
    'sales:view',
    'report:view', 'dashboard:reports',
    'draft:manage',
]

SALES_PERMISSIONS = [
    'dashboard:view',
    'customer:view', 'customer:add', 'customer:edit',
    'region:view', 'category:view', 'department:view',
    'sales:view', 'sales:add', 'sales:edit', 'sales:delete',
    'contract_auto:manage',
    'ticket:view', 'ticket:add',
    'kb:view',
    'spare:view',
    'report:view', 'dashboard:reports',
]

VIEWER_PERMISSIONS = [
    'dashboard:view',
    'customer:view', 'region:view', 'department:view', 'category:view',
    'device:view', 'topology:view',
    'inspection:view', 'ticket:view', 'fault:view',
    'kb:view', 'spare:view', 'sales:view',
    'report:view', 'dashboard:reports',
]

ROLE_PERMISSIONS_MAP = {
    'admin': ADMIN_PERMISSIONS,
    'operator': OPERATOR_PERMISSIONS,
    'sales': SALES_PERMISSIONS,
    'viewer': VIEWER_PERMISSIONS,
}

ROLE_LABELS = {
    'admin': '系统管理员',
    'operator': '运维工程师',
    'sales': '销售人员',
    'viewer': '查看者',
}

# 故障一级分类选项
FAULT_CATEGORY_LEVEL1 = [
    '硬件故障', '软件故障', '网络故障', '安全事件', '配置变更', '环境问题'
]

# 故障二级分类映射
FAULT_CATEGORY_LEVEL2 = {
    '硬件故障': ['电源模块', '硬盘', '内存', '风扇', '主板', '接口卡', '线缆', '其他硬件'],
    '软件故障': ['系统崩溃', '进程异常', '服务中断', '漏洞', '版本问题', '其他软件'],
    '网络故障': ['链路中断', '路由异常', 'DNS故障', 'IP冲突', '带宽异常', '其他网络'],
    '安全事件': ['入侵攻击', '病毒感染', 'DDoS', '异常流量', '未授权访问', '其他安全'],
    '配置变更': ['配置错误', '策略变更', 'ACL变更', '路由变更', '其他配置'],
    '环境问题': ['电力中断', '温度异常', '湿度异常', '水浸', '火灾', '其他环境'],
}

# 根因分类
ROOT_CAUSE_CATEGORIES = [
    '配置错误', '硬件老化', '软件BUG', '人为失误', '外部攻击', '电力故障',
    '自然灾害', '供应商问题', '容量不足', '未知原因',
]

# 严重级别
SEVERITY_LEVELS = ['P1-紧急', 'P2-高', 'P3-中', 'P4-低']

# 巡检频率选项
INSPECTION_FREQUENCY_CHOICES = ['', '每月', '每季度', '每半年', '每年']

# 巡检模板字段类型
FIELD_TYPE_CHOICES = [
    ('text', '单行文本'),
    ('multiline_text', '多行文本'),
    ('dropdown', '下拉选择'),
    ('image', '图片上传'),
    ('number', '数字'),
    ('date', '日期'),
]

def get_user_permissions(user):
    """获取用户权限列表（角色模板 + 用户级 grant/deny）

    V14: 从 DB 读，用进程级缓存。
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return []

    role_code = getattr(user, 'role', 'viewer') or 'viewer'

    # 1) admin 短路：直接返回 PERMISSION_MAP 全部 key
    if role_code == 'admin':
        return list(PERMISSION_MAP.keys())

    # 2) 角色权限（带缓存）
    base = set(_get_cached_role_perms(role_code))

    # 3) 用户级 grant/deny 覆盖（每次查，不缓存 —— 用户级操作少）
    if hasattr(user, 'extra_permissions') and user.extra_permissions:
        now = datetime.utcnow()
        for up in user.extra_permissions:
            # 过期过滤
            if up.expire_at and up.expire_at < now:
                continue
            if up.grant_type == 'grant':
                base.add(up.permission_code)
            elif up.grant_type == 'deny':
                base.discard(up.permission_code)
    return list(base)


def _get_cached_role_perms(role_code: str) -> frozenset:
    """从缓存或 DB 拿角色的权限码集合。"""
    if role_code in _role_cache:
        return _role_cache[role_code]

    # 缓存未命中，查 DB
    from models import Role
    role = (Role.query
            .options(joinedload(Role.role_perms))
            .filter_by(code=role_code, is_active=True)
            .first())
    if not role:
        # 角色不存在/未激活：fallback 到 viewer
        if role_code != 'viewer':
            return _get_cached_role_perms('viewer')
        # viewer 也没有（极端情况）→ 返回空集
        result = frozenset()
    else:
        # 排除被停用的权限码
        from models import Permission
        active_codes = {p.code for p in Permission.query.filter_by(is_active=True).all()}
        result = frozenset(
            rp.permission_code for rp in role.role_perms
            if rp.permission_code in active_codes
        )
    _role_cache[role_code] = result
    return result


def get_effective_permissions(user):
    """获取用户实际生效的权限，返回 (permission_codes, scope) 元组"""
    return get_user_permissions(user), get_user_scope(user)


def get_user_scope(user):
    """获取用户数据范围"""
    if not user or not getattr(user, 'is_authenticated', False):
        return 'self'
    role = getattr(user, 'role', 'viewer')
    scope = getattr(user, 'scope', 'department')
    if role == 'admin' or scope == 'all':
        return 'all'
    return scope


def apply_scope_filter(query, model, user, customer_id_field='customer_id'):
    """根据用户 scope 过滤查询（部门级别数据隔离）

    用法: query = apply_scope_filter(query, InspectionTask, current_user)
    """
    scope = get_user_scope(user)
    if scope == 'all':
        return query

    from models import User as UModel
    from sqlalchemy import or_

    if scope == 'department' and getattr(user, 'department_id', None):
        dept_user_ids = [u.id for u in UModel.query.filter_by(
            department_id=user.department_id, is_active=True).all()]
        dept_user_names = [u.realname or u.username for u in UModel.query.filter_by(
            department_id=user.department_id, is_active=True).all()]
        conditions = []
        if hasattr(model, 'created_by'):
            conditions.append(model.created_by.in_(dept_user_names))
        if hasattr(model, 'assigned_to'):
            conditions.append(model.assigned_to.in_(dept_user_names))
        if hasattr(model, 'assigned_to_user_id'):
            conditions.append(model.assigned_to_user_id.in_(dept_user_ids))
        if hasattr(model, 'dispatched_by'):
            conditions.append(model.dispatched_by == user.id)
        if hasattr(model, 'customer_id') and customer_id_field:
            # 部门也看关联到该部门的客户数据（通过region或直接关联）
            pass  # 客户级过滤由业务层决定
        if conditions:
            return query.filter(or_(*conditions))

    if scope == 'self' and hasattr(model, 'assigned_to'):
        me_name = getattr(user, 'realname', '') or getattr(user, 'username', '')
        return query.filter(model.assigned_to == me_name)
    if scope == 'self' and hasattr(model, 'assigned_to_user_id'):
        return query.filter(model.assigned_to_user_id == user.id)
    if scope == 'self' and hasattr(model, 'created_by'):
        me_name = getattr(user, 'realname', '') or getattr(user, 'username', '')
        return query.filter(model.created_by == me_name)

    return query


SCOPE_LABELS = {
    'all': '全部数据',
    'department': '本部门',
    'self': '仅自己',
}


def has_permission(code, user=None):
    """模板中检查权限"""
    if user is None:
        user = current_user
    return code in get_user_permissions(user)


def role_label(role):
    return ROLE_LABELS.get(role, role)


def is_supervisor(user=None):
    """判断用户是否为部门主管"""
    if user is None:
        user = current_user
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if not getattr(user, 'department_id', None):
        return False
    from models import Department
    dept = Department.query.get(user.department_id)
    return dept is not None and dept.head_id == user.id


def require_permission(code):
    """权限验证装饰器"""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('login'))
            perms = get_user_permissions(current_user)
            if code not in perms:
                flash('权限不足，需要：' + PERMISSION_MAP.get(code, code), 'danger')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated
    return decorator


def admin_required(f):
    """装饰器：要求当前用户是 admin 角色"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('需要管理员权限', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated


def register_template_functions(app):
    """注册模板全局函数"""
    @app.context_processor
    def inject_permissions():
        return {
            'has_perm': has_permission,
            'perm_map': PERMISSION_MAP,
            'role_label': role_label,
            'role_labels': ROLE_LABELS,
            'is_supervisor_user': is_supervisor,
            'fault_category_level1': FAULT_CATEGORY_LEVEL1,
            'fault_category_level2': FAULT_CATEGORY_LEVEL2,
            'root_cause_categories': ROOT_CAUSE_CATEGORIES,
            'severity_levels': SEVERITY_LEVELS,
            'inspection_frequency_choices': INSPECTION_FREQUENCY_CHOICES,
            'field_type_choices': FIELD_TYPE_CHOICES,
            'scope_labels': SCOPE_LABELS,
            'get_user_scope': get_user_scope,
        }
