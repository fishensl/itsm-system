# -*- coding: utf-8 -*-
"""系统概览 / schema 修复 / drawio 诊断 / 侧栏 / 导入模板下载 / 客户列表"""
import os
from datetime import date
from flask import (render_template, request, redirect, url_for,
                   flash, send_from_directory, jsonify, current_app)
from flask_login import (login_required, current_user)
from models import db, Customer, Device, Inspection
from models import Region, Ticket
from models import Topology
from models import Department, CustomerCategory, UserDashboardPreference
from utils.pagination import paginate, paginate_render_args
from utils.permission import require_permission, admin_required
from utils.decorators import api_view


# ==================== 简化的 admin 路由（暂留 app.py 后续蓝图化）====================
from models import (User as UserM)
from sqlalchemy.orm import joinedload


@login_required
@admin_required
def repair_schema():
    """一键诊断 + 修复 DB schema：显示 alembic 版本/缺失列，尝试 flask db upgrade，
    并对 alembic 误判 head 但列实际缺失的情况直接 ALTER TABLE 补列。"""
    import io
    import contextlib
    from sqlalchemy import inspect as sqla_inspect, text
    reports = []

    # 关键列及其定义（表名 → (列名, SQL 类型)）— 与 models.py / 迁移保持一致
    CRITICAL_COLUMNS = {
        'inspection_tasks': [
            ('estimated_effort', 'FLOAT'),
            ('actual_effort', 'FLOAT'),
        ],
        'topologies': [
            ('diagram_xml', 'TEXT'),
            ('source', 'VARCHAR(16)'),
            ('thumbnail_path', 'VARCHAR(512)'),
            ('pdf_path', 'VARCHAR(512)'),
            ('vsdx_path', 'VARCHAR(512)'),
            ('updated_at', 'DATETIME'),
        ],
    }

    # 1. 当前 alembic 版本
    try:
        insp = sqla_inspect(db.engine)
        if 'alembic_version' not in (insp.get_table_names()):
            reports.append(('alembic_version', '表不存在（遗留库未接入 Alembic）', 'warn'))
        else:
            ver = db.session.execute(text('SELECT version_num FROM alembic_version')).scalar()
            reports.append(('alembic 当前版本', ver or '(空)', 'info'))
    except Exception as e:
        reports.append(('alembic 查询失败', str(e), 'danger'))

    # 2. 关键列检查 + 缺失则直接 ALTER TABLE 补列
    try:
        insp = sqla_inspect(db.engine)
        existing_tables = set(insp.get_table_names())
        for tbl, cols_def in CRITICAL_COLUMNS.items():
            if tbl not in existing_tables:
                reports.append((f'{tbl} 表', '❌ 表不存在', 'danger'))
                continue
            existing_cols = {c['name'] for c in insp.get_columns(tbl)}
            for col_name, col_type in cols_def:
                if col_name in existing_cols:
                    reports.append((f'{tbl}.{col_name}', '✅ 存在', 'ok'))
                else:
                    # 直接补列（alembic 误判 head 时绕过迁移直接修 schema）
                    try:
                        db.session.execute(text(
                            f'ALTER TABLE {tbl} ADD COLUMN {col_name} {col_type}'))
                        db.session.commit()
                        reports.append((f'{tbl}.{col_name}', '🔧 已补列', 'ok'))
                    except Exception as add_err:
                        db.session.rollback()
                        reports.append((f'{tbl}.{col_name}',
                                        f'❌ 缺失，补列失败: {str(add_err)[:150]}', 'danger'))
    except Exception as e:
        reports.append(('列检查失败', str(e), 'danger'))

    # 3. 尝试 flask db upgrade（补列后跑一次，确保其余迁移到位）
    upgrade_output = []
    try:
        from flask_migrate import upgrade as _migrate_upgrade
        import os as _os
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            _migrate_upgrade(directory=_os.path.join(_os.path.dirname(__file__), 'migrations'))
        upgrade_output = [l for l in buf.getvalue().split('\n') if l.strip()]
        reports.append(('flask db upgrade', '✅ 成功', 'ok'))
    except Exception as e:
        reports.append(('flask db upgrade', '⚠ ' + str(e)[:300], 'warn'))

    return render_template('system/repair_schema.html', reports=reports, upgrade_output=upgrade_output)


@login_required
@admin_required
def drawio_diag():
    """drawio 图标库加载诊断页——探测 iframe 内部状态，定位 clibs 不生效的原因。"""
    import os as _os
    import glob
    from urllib.parse import quote
    stencil_dir = os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'static', 'stencils')
    stencil_urls = []
    clibs = ''
    if _os.path.isdir(stencil_dir):
        stencil_urls = [url_for('static', filename='stencils/' + _os.path.basename(f))
                        for f in sorted(glob.glob(_os.path.join(stencil_dir, '*.drawio.xml')))]
        base = request.host_url.rstrip('/')
        clibs = ';'.join('U' + quote(base + u, safe='') for u in stencil_urls)
    return render_template('system/drawio_diag.html', clibs=clibs, stencil_urls=stencil_urls)


@login_required
def system_settings():
    """系统概览页：业务统计 + 部署系统信息（CPU/内存/磁盘/版本）"""
    import platform as _plat
    stats = {
        'user_count': UserM.query.filter_by(is_active=True).count(),
        'user_total': UserM.query.count(),
        'department_count': Department.query.count(),
        'customer_count': Customer.query.count(),
        'device_count': Device.query.count(),
        'topology_count': Topology.query.count(),
        'inspection_count': Inspection.query.count(),
        'ticket_count': Ticket.query.count(),
    }
    # 最近 5 个登录用户
    recent_users = UserM.query.options(joinedload(UserM.department_rel))\
        .order_by(UserM.id.desc()).limit(5).all()

    # ==================== V6.1.2 部署系统信息 ====================
    sys_info = {
        # 系统版本
        'os_name': _plat.system(),
        'os_release': _plat.release(),
        'os_version': _plat.version(),
        'os_platform': _plat.platform(),
        'machine': _plat.machine(),
        'hostname': _plat.node(),
        # Python / Flask
        'python_version': _plat.python_version(),
        'python_impl': _plat.python_implementation(),
    }
    # 主要组件版本
    components = {}
    for name, mod in [
        ('Flask', 'flask'), ('Flask-Login', 'flask_login'),
        ('Flask-SQLAlchemy', 'flask_sqlalchemy'), ('Flask-WTF', 'flask_wtf'),
        ('Flask-Limiter', 'flask_limiter'), ('SQLAlchemy', 'sqlalchemy'),
        ('Werkzeug', 'werkzeug'), ('Jinja2', 'jinja2'),
        ('python-docx', 'docx'), ('openpyxl', 'openpyxl'),
        ('cryptography', 'cryptography'), ('psutil', 'psutil'),
    ]:
        try:
            m = __import__(mod)
            components[name] = getattr(m, '__version__', '-')
        except Exception:
            components[name] = '未安装'

    # 数据库版本
    db_info = {'engine': '-', 'version': '-', 'path': '-'}
    try:
        uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
        if uri.startswith('sqlite:///'):
            import sqlite3 as _sqlite3
            db_info['engine'] = 'SQLite'
            db_info['version'] = _sqlite3.sqlite_version
            db_path = uri.replace('sqlite:///', '')
            db_info['path'] = db_path
            # 数据库文件大小
            if os.path.isfile(db_path):
                db_info['size_mb'] = round(os.path.getsize(db_path) / (1024 * 1024), 2)
        elif 'mysql' in uri:
            db_info['engine'] = 'MySQL'
            try:
                with db.engine.connect() as conn:
                    r = conn.execute(db.text('SELECT VERSION()')).scalar()
                    db_info['version'] = str(r)
            except Exception:
                pass
        elif 'postgresql' in uri:
            db_info['engine'] = 'PostgreSQL'
            try:
                with db.engine.connect() as conn:
                    r = conn.execute(db.text('SHOW server_version')).scalar()
                    db_info['version'] = str(r)
            except Exception:
                pass
    except Exception as _e:
        current_app.logger.warning(f'数据库信息获取失败: {_e}')

    # 资源占用（CPU/内存/磁盘）
    resources = {}
    try:
        import psutil as _ps
        cpu_pct = _ps.cpu_percent(interval=0.5)
        cpu_count = _ps.cpu_count(logical=True)
        cpu_count_phy = _ps.cpu_count(logical=False) or cpu_count
        mem = _ps.virtual_memory()
        disk_root = _ps.disk_usage(os.path.abspath(os.sep))
        # 进程信息
        proc = _ps.Process(os.getpid())
        proc_mem = proc.memory_info()
        # 启动时间（系统）
        boot_ts = _ps.boot_time()
        from datetime import datetime as _dt
        boot_str = _dt.fromtimestamp(boot_ts).strftime('%Y-%m-%d %H:%M:%S')
        # 启动时间（应用进程）
        proc_start = _dt.fromtimestamp(proc.create_time()).strftime('%Y-%m-%d %H:%M:%S')

        resources = {
            'cpu_percent': cpu_pct,
            'cpu_count': cpu_count,
            'cpu_count_physical': cpu_count_phy,
            'memory_percent': mem.percent,
            'memory_total_gb': round(mem.total / (1024**3), 2),
            'memory_used_gb': round(mem.used / (1024**3), 2),
            'memory_available_gb': round(mem.available / (1024**3), 2),
            'disk_percent': disk_root.percent,
            'disk_total_gb': round(disk_root.total / (1024**3), 2),
            'disk_used_gb': round(disk_root.used / (1024**3), 2),
            'disk_free_gb': round(disk_root.free / (1024**3), 2),
            'process_memory_mb': round(proc_mem.rss / (1024**2), 2),
            'process_pid': proc.pid,
            'boot_time': boot_str,
            'process_start': proc_start,
            'available': True,
        }
    except Exception as _e:
        current_app.logger.warning(f'资源占用获取失败: {_e}')
        resources = {'available': False, 'error': str(_e)}

    return render_template('system/index.html',
                           stats=stats,
                           recent_users=recent_users,
                           sys_info=sys_info,
                           components=components,
                           db_info=db_info,
                           resources=resources)


    # ==================== 侧栏自定义 ====================
@login_required
@api_view  # POST 路由需要豁免 CSRF（前端用 fetch + JSON body）
def system_sidebar():
    """侧栏自定义页面 / 保存"""
    from utils.sidebar_config import (SIDEBAR_GROUPS, get_user_sidebar_groups, save_user_sidebar)
    if request.method == 'POST':
        # 提交顺序 + 启用/禁用
        payload = request.get_json(silent=True) or {}
        groups_data = payload.get('groups', [])
        if not isinstance(groups_data, list):
            return jsonify({'success': False, 'message': '参数错误'}), 400
        save_user_sidebar(current_user, groups_data)
        return jsonify({'success': True, 'message': '侧栏设置已保存'})
    # GET：渲染编辑页面
    current_groups = get_user_sidebar_groups(current_user)
    return render_template('system/sidebar.html',
                           all_groups=SIDEBAR_GROUPS,
                           current_groups=current_groups)


@login_required
@api_view
def api_sidebar_reset():
    """重置为默认"""
    from models import db
    pref = UserDashboardPreference.query.filter_by(user_id=current_user.id).first()
    if pref:
        pref.sidebar_json = None
        db.session.commit()
    return jsonify({'success': True, 'message': '已重置为系统默认'})


@login_required
def dashboard_reports():
    return redirect(url_for('ops.report_list'))


@login_required
@require_permission('report:view')
def download_template(module):
    """下载批量导入模板 Excel"""
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

    header_font = Font(name='微软雅黑', bold=True, size=11, color='FFFFFF')
    header_fill = PatternFill(start_color='1890FF', end_color='096DD9', fill_type='solid')
    header_align = Alignment(horizontal='center', vertical='center')
    thin_border = Border(left=Side(style='thin'), right=Side(style='thin'),
                         top=Side(style='thin'), bottom=Side(style='thin'))

    templates = {
        'customer': {
            'name': '客户导入模板',
            'headers': ['客户名称', '联系人', '电话', '邮箱', '所属地区', '地市', '地址',
                        '单位类别', '客户等级',
                        '办公室', '有无驻场', '驻场联系人', '驻场联系方式', '驻场办公室',
                        '有无攻防演练', '巡检频率',
                        '来源', '备注'],
        },
        'device': {
            'name': '设备导入模板',
            'headers': ['所属客户', '设备名称', '设备类型', '品牌', '型号', '序列号', 'IP地址', '端口',
                        '登录用户名', '登录密码', '登录方式', '安装位置', '系统版本',
                        '授权开始日期', '授权截止日期', '规则库版本', '是否维修', '是否在用', '备注'],
        },
        'inspection': {
            'name': '巡检记录导入模板',
            'headers': ['客户名称', '标题', '巡检人员', '巡检日期', '巡检地点', '总体状态', '结论', '备注'],
        },
        'fault': {
            'name': '故障记录导入模板',
            'headers': ['客户名称', '标题', '处理人', '故障时间', '故障类型', '故障描述', '故障原因', '解决方案', '处理结果'],
        },
        'spare': {
            'name': '备件导入模板',
            'headers': ['编码', '名称', '分类', '规格', '单位', '最低库存', '备注'],
        },
        'stock': {
            'name': '库存导入模板',
            'headers': ['备件名称', '位置', '数量', '单价'],
        },
    }

    tpl = templates.get(module)
    if not tpl:
        flash('不支持的导入模板类型', 'danger')
        return redirect(url_for('index'))

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = tpl['name']

    for col_idx, h in enumerate(tpl['headers'], 1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = thin_border
        ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = max(len(h) * 2.5, 18)

    import tempfile
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
    wb.save(tmp.name)
    tmp.close()

    return send_from_directory(
        os.path.dirname(tmp.name),
        os.path.basename(tmp.name),
        as_attachment=True,
        download_name=f'{tpl["name"]}_{date.today().isoformat()}.xlsx'
    )


# ==================== 客户管理 ====================
@login_required
@require_permission('customer:view')
def customer_list():
    search = request.args.get('search', '')
    category_id = request.args.get('category_id', type=int)
    page = request.args.get('page', 1, type=int)
    query = Customer.query
    if search:
        query = query.filter(
            Customer.name.contains(search) |
            Customer.contact_person.contains(search) |
            Customer.phone.contains(search)
        )
    if category_id:
        query = query.filter_by(category_id=category_id)
    # 预加载 region_rel 及其 parent，避免列表渲染时 N+1
    from sqlalchemy.orm import joinedload
    query = query.options(joinedload(Customer.region_rel).joinedload(Region.parent))
    query = query.order_by(Customer.id.desc())
    pag = paginate(query, page=page)
    categories = CustomerCategory.query.order_by(CustomerCategory.sort_order).all()
    return render_template('customers/list.html', **paginate_render_args(pag), search=search,
                          categories=categories, current_category_id=category_id or 0)


