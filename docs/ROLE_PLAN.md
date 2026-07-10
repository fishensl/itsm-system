# 角色权限与工作台规划方案

## 一、角色定义（4 个）

| 角色代码 | 中文名 | 关注重点 | 典型用户 |
|----------|--------|----------|----------|
| `admin` | 系统管理员 | 全局视图、所有模块 | IT 主管、系统管理 |
| `operator` | 运维工程师 | 设备状态、待处理工单/巡检 | 一线运维、巡检员 |
| `sales` | 销售人员 | 客户、商机、报价、合同、项目 | 销售经理、客户经理 |
| `viewer` | 查看者 | 只读模式 | 上级领导、审计 |

---

## 二、工作台板块 × 角色矩阵

每个角色看到的工作台板块不同。

| 板块 | admin | operator | sales | viewer |
|------|-------|----------|-------|--------|
| **统计卡片** | 客户/设备/巡检/工单/故障/知识/备件/商机/报价/项目 | 设备/在用设备/待处理工单/待巡检任务/故障/知识 | 客户/商机/报价/合同/项目/成交率 | 客户/设备/工单/项目（只读） |
| **我的待处理** | ✅ 所有 | ✅ 我的工单+巡检+故障 | ✅ 我的商机+客户跟进 | ❌ |
| **设备状态** | ✅ 全部设备 | ✅ 在线/离线/即将到期 | ❌ | ✅ 只读 |
| **业务趋势图** | ✅ 全部 | ✅ 工单/巡检趋势 | ✅ 商机/成交趋势 | ✅ |
| **设备类型分布** | ✅ | ✅ | ❌ | ✅ |
| **商机/合同动态** | ✅ | ❌ | ✅ 重点 | ✅ 只读 |
| **快捷入口** | 全部 | 设备/巡检/工单/知识库 | 客户/商机/报价/合同 | 仅查看类 |
| **AI 智能分析** | ✅ | ✅ 巡检/故障辅助 | ❌ | ❌ |

---

## 三、菜单可见性策略

按要求："菜单都可见 + 路由拦截"

- 侧边栏所有菜单**都显示**（避免不同角色看到的菜单不同造成困惑）
- 用户点击无权限的菜单 → 路由拦截，跳转回工作台 + Flash 错误提示
- 视觉提示：无权限的菜单项加灰色 + 锁图标

但 admin 专属菜单（用户管理/权限管理）仍只对 admin 显示，避免误点。

---

## 四、按钮颗粒度权限

按角色对常见操作的允许情况：

| 操作 | admin | operator | sales | viewer |
|------|-------|----------|-------|--------|
| 客户：新增/编辑 | ✅ | ❌ | ✅ | ❌ |
| 客户：删除 | ✅ | ❌ | ❌ | ❌ |
| 设备：新增/编辑 | ✅ | ✅ | ❌ | ❌ |
| 设备：删除 | ✅ | ❌ | ❌ | ❌ |
| 设备：密码查看 | ✅ | ✅ | ❌ | ❌ |
| 巡检任务：创建/分派 | ✅ | ✅ | ❌ | ❌ |
| 巡检记录：填写/编辑 | ✅ | ✅ | ❌ | ❌ |
| 工单：创建 | ✅ | ✅ | ✅ | ❌ |
| 工单：派单/审核/验收 | ✅ | ✅ | ❌ | ❌ |
| 工单：删除 | ✅ | ❌ | ❌ | ❌ |
| 知识库：发布 | ✅ | ✅ | ❌ | ❌ |
| 知识库：查看 | ✅ | ✅ | ✅ | ✅ |
| 商机/报价/合同/项目 | ✅ | ❌ | ✅ | ❌ |
| 备件管理 | ✅ | ✅ | ❌ | ❌ |
| 销售出库 | ✅ | ❌ | ✅ | ❌ |
| 系统设置 / 用户管理 | ✅ | ❌ | ❌ | ❌ |
| AI 对接配置 | ✅ | ❌ | ❌ | ❌ |
| 数据导出 | ✅ | ✅ | ✅ | ❌ |

---

## 五、技术实现方案

### 5.1 权限工具模块

新建 `utils/permission.py`：

```python
# 角色 → 模块访问权限
ROLE_PERMISSIONS = {
    'admin': {'*': ['view', 'add', 'edit', 'delete', 'export']},
    'operator': {
        'customer': ['view'],
        'device': ['view', 'add', 'edit', 'export'],
        'inspection': ['view', 'add', 'edit', 'export'],
        'ticket': ['view', 'add', 'edit', 'export'],
        'knowledge': ['view', 'add', 'edit'],
        'spare': ['view', 'add', 'edit'],
        'report': ['view', 'export'],
    },
    'sales': {
        'customer': ['view', 'add', 'edit'],
        'opportunity': ['view', 'add', 'edit', 'delete'],
        'quotation': ['view', 'add', 'edit', 'delete'],
        'contract': ['view', 'add', 'edit', 'delete'],
        'project': ['view', 'add', 'edit'],
        'ticket': ['view', 'add'],
        'sales_order': ['view', 'add', 'edit'],
        'knowledge': ['view'],
    },
    'viewer': {
        'customer': ['view'], 'device': ['view'], 'inspection': ['view'],
        'ticket': ['view'], 'knowledge': ['view'], 'project': ['view'],
        'report': ['view'],
    },
}

def has_permission(user, module, action='view'):
    """检查用户是否有权限"""
    if not user or not user.is_authenticated: return False
    perms = ROLE_PERMISSIONS.get(user.role, {})
    if '*' in perms: return action in perms['*']
    return action in perms.get(module, [])

def require_permission(module, action='view'):
    """装饰器"""
    from functools import wraps
    from flask import flash, redirect, url_for
    from flask_login import current_user
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not has_permission(current_user, module, action):
                flash(f'您没有权限执行此操作（{module}:{action}）', 'danger')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return wrapped
    return decorator

def register_template_helpers(app):
    """注入模板上下文，供 Jinja 使用"""
    @app.context_processor
    def inject():
        return {'has_perm': has_permission}
```

### 5.2 工作台按角色分发

`app.py index()`:

```python
@app.route('/')
@login_required
def index():
    role = current_user.role
    if role == 'sales':
        return _render_sales_dashboard()
    elif role == 'operator':
        return _render_operator_dashboard()
    elif role == 'viewer':
        return _render_viewer_dashboard()
    else:  # admin / 默认
        return _render_admin_dashboard()
```

每个角色对应 1 个 dashboard 模板：
- `templates/dashboard/admin.html`（完整版）
- `templates/dashboard/operator.html`（运维聚焦）
- `templates/dashboard/sales.html`（销售聚焦）
- `templates/dashboard/viewer.html`（只读）

共享 `templates/dashboard/_components.html` 复用面板。

### 5.3 路由拦截

在每个 route 上加装饰器：

```python
@app.route('/devices/delete/<int:id>')
@login_required
@require_permission('device', 'delete')
def device_delete(id):
    ...
```

模块代码：
- `customer` `device` `inspection` `inspection_task` `inspection_template` `inspector`
- `ticket` `knowledge` `region` `topology`
- `spare` `purchase` `sales_order`
- `opportunity` `quotation` `contract` `project`
- `report` `user` `permission` `ai_config`

### 5.4 模板按钮显示控制

模板里用：

```jinja2
{% if has_perm(current_user, 'device', 'delete') %}
<a href="{{ url_for('device_delete', id=d.id) }}" class="btn btn-sm btn-outline-danger">删除</a>
{% endif %}
```

### 5.5 菜单"无权限"灰显

`base.html` 菜单项加 helper：

```jinja2
{% set can_see_device = has_perm(current_user, 'device', 'view') %}
<a class="nav-link {% if not can_see_device %}disabled-link{% endif %}" ...>
```

CSS：
```css
.nav-link.disabled-link { opacity: .4; }
.nav-link.disabled-link::after { content: '🔒'; font-size: 10px; margin-left: 4px; }
```

但 sales 看设备就提示锁，避免感觉缺失菜单。

### 5.6 用户管理页加角色选择

`templates/users/list.html` 弹窗：
```html
<select name="role">
  <option value="admin">系统管理员</option>
  <option value="operator">运维工程师</option>
  <option value="sales">销售人员</option>
  <option value="viewer">查看者</option>
</select>
```

---

## 六、实施步骤

| 步骤 | 内容 | 文件 |
|------|------|------|
| 1 | 创建 `utils/permission.py` | 新建 |
| 2 | app.py 注册模板 helper | 修改 |
| 3 | 工作台按角色分发 + 4 个 dashboard 模板 | 改写 index.html + 新建 4 模板 |
| 4 | 路由加 `@require_permission` 装饰器 | 修改 80+ 路由 |
| 5 | 用户管理增加角色选择 | 修改 users/list.html |
| 6 | 关键页面按钮加 `has_perm` 判断 | 修改 10+ 模板 |
| 7 | 菜单 disabled-link 样式 | 修改 base.html |
| 8 | 测试 4 个角色登录后看到的差异 | 全面测试 |

---

## 七、测试用例

创建 4 个测试用户：
- admin / admin123
- ops01 / ops123 (operator)
- sales01 / sales123 (sales)
- viewer01 / view123 (viewer)

每个用户登录后：
- 看到不同的工作台
- 菜单都可见，但部分灰显
- 点击无权限菜单 → 跳回工作台 + 提示
- 列表页按钮按权限显示
