# -*- coding: utf-8 -*-
"""部署系统信息采集（SSR 系统概览与 Vue /api/system/overview 共用）

返回 {sys_info, components, db_info, resources}：
- sys_info: OS / 主机名 / Python 版本等
- components: 主要组件版本（Flask / SQLAlchemy / psutil ...）
- db_info: 数据库引擎 / 版本 / 路径 / 文件大小
- resources: psutil 资源占用（CPU/内存/磁盘/进程），不可用时 available=False
"""
import os
from datetime import datetime
import platform as _plat

# ==================== 部署系统信息 ====================


def _collect_sys_info():
    return {
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


def _collect_components():
    from importlib import metadata as _md
    # 主要组件版本（优先 importlib.metadata：避免 __version__ 弃用警告；未安装回退检测）
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
            components[name] = _md.version(name)
        except Exception:
            try:
                m = __import__(mod)
                components[name] = getattr(m, '__version__', '-')
            except Exception:
                components[name] = '未安装'
    return components


def _collect_db_info():
    from flask import current_app
    from models import db
    db_info = {'engine': '-', 'version': '-', 'path': '-'}
    try:
        uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
        # PG-only：生产/开发均为 PostgreSQL（SQLite/MySQL 分支已随 SQLite 剥离移除）
        if 'postgresql' in uri:
            db_info['engine'] = 'PostgreSQL'
            db_info['path'] = uri.split('@')[-1] if '@' in uri else uri
            try:
                with db.engine.connect() as conn:
                    r = conn.execute(db.text('SHOW server_version')).scalar()
                    db_info['version'] = str(r)
            except Exception:
                pass
    except Exception as _e:
        current_app.logger.warning(f'数据库信息获取失败: {_e}')
    return db_info


def _collect_resources():
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
        boot_str = datetime.fromtimestamp(boot_ts).strftime('%Y-%m-%d %H:%M:%S')
        # 启动时间（应用进程）
        proc_start = datetime.fromtimestamp(proc.create_time()).strftime('%Y-%m-%d %H:%M:%S')

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
        resources = {'available': False, 'error': str(_e)}
    return resources


def collect_deployment_info():
    """系统概览部署信息：系统/组件/数据库/资源占用"""
    return {
        'sys_info': _collect_sys_info(),
        'components': _collect_components(),
        'db_info': _collect_db_info(),
        'resources': _collect_resources(),
    }
