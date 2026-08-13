# -*- coding: utf-8 -*-
"""面向知识库富文本的无依赖 HTML 白名单净化。"""
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlsplit


_VOID_TAGS = frozenset({'br', 'hr', 'img'})
_ALLOWED_TAGS = frozenset({
    'p', 'br', 'div', 'span', 'strong', 'b', 'em', 'i', 'u', 's', 'del',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'ul', 'ol', 'li',
    'pre', 'code', 'hr', 'a', 'img', 'table', 'thead', 'tbody', 'tfoot',
    'tr', 'th', 'td',
})
_DROP_CONTENT_TAGS = frozenset({'script', 'style', 'iframe', 'object', 'embed', 'svg', 'math'})
_GLOBAL_ATTRS = frozenset({'title'})
_TAG_ATTRS = {
    'a': frozenset({'href', 'target', 'rel'}),
    'img': frozenset({'src', 'alt', 'width', 'height'}),
    'ol': frozenset({'start'}),
    'th': frozenset({'colspan', 'rowspan'}),
    'td': frozenset({'colspan', 'rowspan'}),
}


def _safe_url(value, *, image=False):
    """只允许 HTTP(S)、安全相对地址；链接额外允许 mailto。"""
    candidate = ''.join(ch for ch in (value or '').strip() if ord(ch) >= 32)
    if not candidate or candidate.startswith('//'):
        return False
    parsed = urlsplit(candidate)
    allowed = {'http', 'https'} if image else {'http', 'https', 'mailto'}
    if parsed.scheme:
        return parsed.scheme.lower() in allowed
    return candidate.startswith(('/', './', '../', '#', '?')) or ':' not in candidate.split('/', 1)[0]


class _WhitelistSanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.parts = []
        self._drop_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in _DROP_CONTENT_TAGS:
            self._drop_depth += 1
            return
        if self._drop_depth or tag not in _ALLOWED_TAGS:
            return
        allowed = _GLOBAL_ATTRS | _TAG_ATTRS.get(tag, frozenset())
        cleaned = []
        for raw_name, raw_value in attrs:
            name = (raw_name or '').lower()
            value = raw_value or ''
            if name not in allowed or name.startswith('on'):
                continue
            if name == 'href' and not _safe_url(value):
                continue
            if name == 'src' and not _safe_url(value, image=True):
                continue
            if name == 'target' and value not in ('_blank', '_self'):
                continue
            if name in ('width', 'height', 'colspan', 'rowspan', 'start'):
                if not value.isdigit() or int(value) > 10000:
                    continue
            cleaned.append((name, value))
        if tag == 'a' and any(name == 'target' and value == '_blank' for name, value in cleaned):
            cleaned = [(name, value) for name, value in cleaned if name != 'rel']
            cleaned.append(('rel', 'noopener noreferrer'))
        suffix = ''.join(f' {name}="{escape(value, quote=True)}"' for name, value in cleaned)
        self.parts.append(f'<{tag}{suffix}>')

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in _DROP_CONTENT_TAGS:
            if self._drop_depth:
                self._drop_depth -= 1
            return
        if not self._drop_depth and tag in _ALLOWED_TAGS and tag not in _VOID_TAGS:
            self.parts.append(f'</{tag}>')

    def handle_data(self, data):
        if not self._drop_depth:
            self.parts.append(escape(data, quote=False))

    def handle_entityref(self, name):
        if not self._drop_depth:
            self.parts.append(f'&{name};')

    def handle_charref(self, name):
        if not self._drop_depth:
            self.parts.append(f'&#{name};')


def sanitize_html(value):
    """返回适合通过 ``v-html`` 展示的白名单 HTML。"""
    parser = _WhitelistSanitizer()
    parser.feed(value or '')
    parser.close()
    return ''.join(parser.parts)
