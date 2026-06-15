# -*- coding: utf-8 -*-
"""常用工具蓝图：网络运维计算/解析工具，纯前端实现（V6.1）

所有路由仅返回静态模板，工具计算逻辑全部在前端 JS 完成。
"""
from flask import Blueprint, render_template
from flask_login import login_required

tools_bp = Blueprint('tools', __name__)


@tools_bp.route('/tools')
@login_required
def tools_index():
    """工具集合主页（默认显示 IP 计算器）"""
    return render_template('tools/index.html', tool='ip-calc')


@tools_bp.route('/tools/<tool>')
@login_required
def tools_one(tool):
    """单个工具页面"""
    valid = {'ip-calc', 'subnet', 'mac', 'radix', 'timestamp',
             'base64', 'mtu', 'bandwidth', 'packet'}
    if tool not in valid:
        tool = 'ip-calc'
    return render_template('tools/index.html', tool=tool)
