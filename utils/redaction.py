"""Small, dependency-free redaction boundary for logs and error responses."""
import re


_SENSITIVE_KEY = re.compile(r'(secret|token|password|passwd|api[_-]?key|authorization)', re.I)
_INLINE_SECRET = re.compile(
    r"(?i)(secret|token|password|passwd|api[_-]?key|authorization)"
    r"(\s*[=:]\s*[\"']?)([^\s,;}\"']+)")


def redact_mapping(value):
    if isinstance(value, dict):
        return {
            key: ('***' if _SENSITIVE_KEY.search(str(key)) else redact_mapping(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_mapping(item) for item in value]
    return value


def redact_text(value, limit=500):
    text = str(value or '')
    text = _INLINE_SECRET.sub(lambda match: f'{match.group(1)}{match.group(2)}***', text)
    return text[:limit]
