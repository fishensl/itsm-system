"""权限与角色初始化（V14）

幂等执行：启动时由 init_db() 调用；任何时候重跑都不会破坏现有数据。

真源策略：
  - 权限码：utils/permission.py 的 PERMISSION_MAP
  - 角色：   4 个系统角色（admin/operator/sales/viewer）+ 4 套默认权限

行为：
  - permissions 表：PERMISSION_MAP 里有 → INSERT/UPDATE（is_system=True）
  - roles 表：4 个系统角色固定种入（is_system=True）
  - role_permissions：admin 角色不写（依赖 get_user_permissions 中的 admin 短路）
  - 用户级 UserPermission：不动

注：schema 演进（加列/加约束）已由 Alembic（flask-migrate）接管，见 migrations/。
    本模块只负责 seed 数据，不再做任何 PRAGMA/ALTER 操作。
"""
from models import db, Role, RolePermission, Permission


# 角色元信息：code -> (name, description, sort_order)
ROLE_DEFS = [
    ('admin',    '系统管理员',  '拥有系统全部权限', 1),
    ('operator', '运维工程师',  '负责设备/巡检/工单/故障/知识库等运维操作', 2),
    ('sales',    '销售人员',    '负责客户/商机/报价/合同/销售等业务', 3),
    ('viewer',   '查看者',      '只读权限，查看数据不能修改', 4),
]


def _category_from_code(code: str) -> str:
    """从权限 code 推断分类（如 'customer:view' -> 'customer'）"""
    if ':' in code:
        return code.split(':', 1)[0]
    return 'system'


def seed_all(app=None) -> None:
    """种入 51 个权限码 + 4 个系统角色 + 默认 role_permissions。"""
    if app is not None:
        with app.app_context():
            _seed_all_impl()
    else:
        _seed_all_impl()


def _seed_all_impl() -> None:
    # 1. 权限码
    from utils.permission import PERMISSION_MAP, ROLE_PERMISSIONS_MAP

    # 分类映射（更细粒度）
    CATEGORY_LABELS = {
        'dashboard': '工作台', 'customer': '客户管理', 'region': '地区管理',
        'device': '设备管理', 'topology': '拓扑图', 'inspection': '巡检管理',
        'ticket': '工单管理', 'fault': '故障管理', 'kb': '知识库',
        'task': '任务派发', 'department': '部门管理', 'category': '单位类别',
        'spare': '备件管理', 'sales': '销售管理', 'contract_auto': '合同自动巡检',
        'user': '用户管理', 'permission': '权限管理', 'report': '数据报表',
        'ai': 'AI 对接', 'draft': '草稿管理', 'system': '系统设置',
    }

    existing_perms = {p.code: p for p in Permission.query.all()}
    for code, name in PERMISSION_MAP.items():
        cat = _category_from_code(code)
        if code in existing_perms:
            p = existing_perms[code]
            # 只更新 label/category，is_system 一旦 True 不再覆盖
            updated = False
            if p.name != name:
                p.name = name; updated = True
            new_cat = cat
            if p.category != new_cat:
                p.category = new_cat; updated = True
            if not p.is_system:
                p.is_system = True; updated = True
            # 不再强制 is_active=True：尊重管理员对系统权限的停用操作，
            # 否则每次重启都会把被停用的权限重新激活
            # 不动 description（用户可能改过）
        else:
            p = Permission(
                code=code, name=name, category=cat,
                is_system=True, is_active=True,
            )
            db.session.add(p)
    db.session.commit()

    # 2. 系统角色
    existing_roles = {r.code: r for r in Role.query.all()}
    for code, name, desc, sort_order in ROLE_DEFS:
        if code in existing_roles:
            r = existing_roles[code]
            # 保持 is_system=True
            if not r.is_system:
                r.is_system = True
        else:
            r = Role(code=code, name=name, description=desc,
                    is_system=True, is_active=True, sort_order=sort_order)
            db.session.add(r)
            db.session.flush()  # 拿到 id
    db.session.commit()

    # 3. 角色-权限（admin 角色跳过：依赖 get_user_permissions 短路）
    for role_code, perm_codes in ROLE_PERMISSIONS_MAP.items():
        if role_code == 'admin':
            continue  # admin 走短路
        role = Role.query.filter_by(code=role_code).first()
        if not role:
            continue
        # 已有权限码集合
        existing_pair = {(rp.permission_code) for rp in role.role_perms}
        target = set(perm_codes)
        # 缺失的加上
        for code in target - existing_pair:
            db.session.add(RolePermission(role_id=role.id, permission_code=code))
        # 多余的（不在 PERMISSION_MAP 或 role 默认列表）不删（用户可能自定义过）
    db.session.commit()
