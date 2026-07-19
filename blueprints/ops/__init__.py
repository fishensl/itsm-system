# -*- coding: utf-8 -*-
"""运维管理蓝图包：巡检/工单/故障/知识库/模板/巡检员/报告

单蓝图 ops_bp 拆模块组织，端点名保持 ops.* 不变（模板 url_for 零改动）。
"""
from flask import Blueprint

ops_bp = Blueprint('ops', __name__)

# 子模块路由注册（import 即生效，顺序无关）
from blueprints.ops import inspections  # noqa: F401,E402
from blueprints.ops import task_redirects  # noqa: F401,E402
from blueprints.ops import templates  # noqa: F401,E402
from blueprints.ops import faults  # noqa: F401,E402
from blueprints.ops import tickets  # noqa: F401,E402
from blueprints.ops import knowledge  # noqa: F401,E402
from blueprints.ops import inspectors  # noqa: F401,E402
from blueprints.ops import reports  # noqa: F401,E402
