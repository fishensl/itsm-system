"""证书选项 (V13)

集中维护用户管理界面的"资质证书"复选项与解析/序列化辅助函数。
4 大类共 12 个选项，前端按分组渲染 checkbox，后端用白名单过滤非法值。
"""
import json


CERT_CATEGORIES = [
    {'group': '华为',           'items': ['HCIA', 'HCIP', 'HCIE']},
    {'group': 'H3C',            'items': ['H3CNE', 'H3CSE', 'H3CIE']},
    {'group': '软考',           'items': ['网络管理员', '网络工程师', '网络规划设计师']},
    {'group': '国家注册信息安全', 'items': ['CISP', 'CISP-PTE', 'CISP-PTS']},
]

# 扁平合法值集合 — 后端校验白名单
ALL_CERT_VALUES = [v for grp in CERT_CATEGORIES for v in grp['items']]
_VALID_SET = set(ALL_CERT_VALUES)


def parse_cert_form(values):
    """从 request.form.getlist('certifications') 过滤出合法值，去重保序。"""
    if not values:
        return []
    seen = set()
    out = []
    for v in values:
        v = (v or '').strip()
        if v in _VALID_SET and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def cert_to_json(lst):
    """list -> JSON 字符串，存数据库。"""
    try:
        return json.dumps(lst or [], ensure_ascii=False)
    except (TypeError, ValueError):
        return '[]'


def cert_from_json(s):
    """JSON 字符串 -> list。防御 JSONDecodeError 与老的空字符串/逗号分隔字符串。"""
    if not s:
        return []
    s = s.strip()
    if not s:
        return []
    # 标准 JSON
    if s.startswith('['):
        try:
            data = json.loads(s)
            if isinstance(data, list):
                return [str(x) for x in data if x]
        except (json.JSONDecodeError, TypeError):
            pass
    # 老格式兜底：逗号/斜杠/中文逗号分隔
    parts = []
    for raw in s.replace('，', ',').replace('/', ',').replace('、', ',').split(','):
        raw = raw.strip()
        if raw:
            parts.append(raw)
    return parts


def normalize_legacy_certs(s):
    """把老格式自由文本（如 'HCIP/CISP/中级'）映射到合法值，
    返回 (合法 list, 未识别 list)。迁移脚本用。"""
    raw_list = cert_from_json(s) if s else []
    valid = []
    unknown = []
    for v in raw_list:
        if v in _VALID_SET:
            if v not in valid:
                valid.append(v)
        else:
            unknown.append(v)
    return valid, unknown
