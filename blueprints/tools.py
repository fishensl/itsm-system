# -*- coding: utf-8 -*-
"""常用工具蓝图：网络运维计算/解析工具

工具计算逻辑全部在前端 JS 完成；仅报文分析的 IP 归属地查询走后端
（依赖 ip2region xdb 数据库，纯前端不便携带）。
"""
import os
from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from flask_login import login_required

tools_bp = Blueprint('tools', __name__)


# 旧工具 key → 新工具/子工具的映射（用于兼容旧书签/外链）
LEGACY_TOOLS = {
    'ip-calc': ('network', 'ip-calc'),
    'subnet': ('network', 'subnet'),
    'mac': ('network', 'mac'),
    'mtu': ('network', 'mtu'),
    'bandwidth': ('network', 'bandwidth'),
    'radix': ('convert', 'radix'),
    'timestamp': ('convert', 'timestamp'),
    'base64': ('convert', 'base64'),
}


# ============== ip2region 单例（懒加载，启动不阻塞） ==============
_xdb_searcher = None
_xdb_init_failed = False


def _get_xdb():
    """懒加载 XdbSearcher，使用 vectorIndex 缓存策略（约 ~256KB 内存）。

    优先使用 pip 包自带的 data/ip2region.xdb；找不到则失败一次后
    永久标记为不可用，后续请求直接返回离线状态，不再重试。
    """
    global _xdb_searcher, _xdb_init_failed
    if _xdb_searcher is not None or _xdb_init_failed:
        return _xdb_searcher
    try:
        from XdbSearchIP.xdbSearcher import XdbSearcher
        import XdbSearchIP as _pkg
        db_path = os.path.join(os.path.dirname(_pkg.__file__),
                               'data', 'ip2region.xdb')
        if not os.path.exists(db_path):
            _xdb_init_failed = True
            return None
        vi = XdbSearcher.loadVectorIndexFromFile(dbfile=db_path)
        _xdb_searcher = XdbSearcher(dbfile=db_path, vectorIndex=vi)
    except Exception:
        _xdb_init_failed = True
        _xdb_searcher = None
    return _xdb_searcher


@tools_bp.route('/tools')
@login_required
def tools_index():
    """工具集合主页（默认显示网络计算工具）"""
    return render_template('tools/index.html', tool='network')


@tools_bp.route('/tools/<tool>')
@login_required
def tools_one(tool):
    """单个工具页面。

    仅保留三个整合工具：network / convert / packet。
    旧的细分 key（ip-calc/mac/...）302 跳转到对应新工具并通过 hash 定位子工具。
    """
    if tool in LEGACY_TOOLS:
        new, sub = LEGACY_TOOLS[tool]
        return redirect(url_for('tools.tools_one', tool=new) + '#' + sub, code=302)
    if tool not in {'network', 'convert', 'packet'}:
        tool = 'network'
    return render_template('tools/index.html', tool=tool)


@tools_bp.route('/api/tools/packet/ip-locate', methods=['POST'])
@login_required
def packet_ip_locate():
    """批量查询公网 IP 的省/市归属（报文分析专用）。

    入参 JSON: {"ips": ["8.8.8.8", "223.83.150.84", ...]}（单次最多 1000 个）。
    返回 JSON: { ip: {country, province, city, isp, label} }。
    xdb 库返回的字段格式：'国家|区域|省|市|ISP'，'0' 表示该层级为空。
    数据库不可用时统一返回 label='离线'，前端据此回退展示。
    """
    payload = request.get_json(silent=True) or {}
    ips = payload.get('ips') or []
    if not isinstance(ips, list):
        return jsonify({}), 400
    # 去重 + 单次上限
    seen = []
    seen_set = set()
    for ip in ips[:5000]:
        if isinstance(ip, str) and ip not in seen_set:
            seen.append(ip)
            seen_set.add(ip)
            if len(seen) >= 1000:
                break

    db = _get_xdb()
    out = {}
    if db is None:
        for ip in seen:
            out[ip] = {'country': '', 'province': '', 'city': '',
                       'isp': '', 'label': '离线'}
        return jsonify(out)

    for ip in seen:
        try:
            raw = db.search(ip) or ''
            parts = raw.split('|')
            # 补齐到 5 段
            while len(parts) < 5:
                parts.append('')
            country = parts[0] if parts[0] and parts[0] != '0' else ''
            province = parts[2] if parts[2] and parts[2] != '0' else ''
            city = parts[3] if parts[3] and parts[3] != '0' else ''
            isp = parts[4] if parts[4] and parts[4] != '0' else ''
            label = '-'.join(p for p in (country, province, city) if p) or '未知'
            out[ip] = {'country': country, 'province': province,
                       'city': city, 'isp': isp, 'label': label}
        except Exception:
            out[ip] = {'country': '', 'province': '', 'city': '',
                       'isp': '', 'label': '未知'}
    return jsonify(out)
