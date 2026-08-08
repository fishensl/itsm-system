# -*- coding: utf-8 -*-
"""内外网访问控制：可信网段判定（敏感模块仅限内网/VPN 访问）

- 可信网段存 SystemSetting key 'trusted_networks'（每行一个 CIDR，如 192.168.0.0/16）；
  配置为空 = 全部视为内网（存量部署零配置不锁死）。
- 客户端 IP：优先 X-Real-IP（反代 proxy_set_header X-Real-IP $remote_addr 覆盖伪造值），
  其次 X-Forwarded-For 首段，最后 request.remote_addr。
- 本模块只做判定；外网拦截由 utils/access_guard.py 的 before_request 执行。
"""
import ipaddress

TRUSTED_NETWORKS_KEY = 'trusted_networks'
_DEFAULT_INTERNAL = ('127.0.0.1', '::1', '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')


def get_trusted_networks():
    """读取后台配置的可信网段列表。

    返回 list[str]（含默认回环/私网兜底）或 None（未配置 = 全部视为内网）。
    失败静默回退 None，保证访问控制异常不阻断业务。
    """
    try:
        from models import SystemSetting
        row = SystemSetting.query.get(TRUSTED_NETWORKS_KEY)
    except Exception:
        return None
    if not row or not (row.value or '').strip():
        return None
    lines = [ln.strip() for ln in (row.value or '').splitlines() if ln.strip()]
    return lines or None


def client_ip():
    """获取客户端真实 IP（反代场景）：X-Real-IP 优先 → X-Forwarded-For 首段 → remote_addr"""
    from flask import request
    x_real = request.headers.get('X-Real-IP', '').strip()
    if x_real:
        return x_real.split(',')[0].strip()
    xff = request.headers.get('X-Forwarded-For', '').strip()
    if xff:
        return xff.split(',')[0].strip()
    return request.remote_addr or ''


def ip_in_networks(ip, networks):
    """判断 IP 是否命中任一网段（支持 IPv4/IPv6 CIDR 与精确 IP）。"""
    if not ip or not networks:
        return False
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for net in networks:
        net = (net or '').strip()
        if not net:
            continue
        try:
            if '/' in net:
                network = ipaddress.ip_network(net, strict=False)
            else:
                network = ipaddress.ip_network(net + '/32', strict=False)
        except ValueError:
            continue
        if addr in network:
            return True
    return False


def is_internal_request():
    """当前请求是否来自内网/VPN 可信网段。

    未配置可信网段（None）→ 全部视为内网（兼容存量零配置）。
    """
    networks = get_trusted_networks()
    if networks is None:
        return True
    ip = client_ip()
    if ip_in_networks(ip, _DEFAULT_INTERNAL):
        return True
    return ip_in_networks(ip, networks)
