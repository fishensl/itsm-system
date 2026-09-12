"""Customer group robots: text only, exact HTTPS endpoints, no redirects."""
import base64
import hashlib
import hmac
import re
import time
from urllib.parse import urlsplit, parse_qs, urlencode

from utils.crypto import decrypt_password


class DeliveryError(Exception):
    def __init__(self, code, retryable=False, unknown=False, retry_after=0):
        super().__init__(code)
        self.code, self.retryable, self.unknown = code, retryable, unknown
        self.retry_after = retry_after


def validate_robot(channel, url):
    from utils.notify_channels.wecom import validate_webhook_url
    if channel == 'wecom':
        return validate_webhook_url(url)
    value = str(url or '').strip()
    try:
        parsed = urlsplit(value)
        if parsed.scheme != 'https' or parsed.port not in (None, 443) or parsed.username or parsed.password or parsed.fragment:
            raise ValueError()
        if channel == 'dingtalk':
            params = parse_qs(parsed.query, keep_blank_values=True)
            if parsed.hostname != 'oapi.dingtalk.com' or parsed.path != '/robot/send' or set(params) != {'access_token'} or len(params['access_token']) != 1 or not params['access_token'][0]:
                raise ValueError()
        elif channel == 'feishu':
            if parsed.hostname != 'open.feishu.cn' or parsed.query or not re.fullmatch(r'/open-apis/bot/v2/hook/[a-zA-Z0-9-]+', parsed.path):
                raise ValueError()
        else:
            raise ValueError()
    except ValueError:
        raise DeliveryError('invalid_destination') from None
    return value


def send_robot(binding, title, content):
    import requests
    try:
        url = validate_robot(binding.channel_type, decrypt_password(binding.webhook_encrypted))
        secret = decrypt_password(binding.signing_secret_encrypted) if binding.signing_secret_encrypted else ''
    except Exception:
        raise DeliveryError('invalid_credentials') from None
    text = title + '\n' + content
    if len(text.encode('utf-8')) > 1800:
        text = text.encode('utf-8')[:1600].decode('utf-8', errors='ignore') + '\n（内容较长，请登录服务通知页查看完整记录。）'
    if binding.channel_type == 'feishu':
        payload = {'msg_type': 'text', 'content': {'text': text}}
        if secret:
            timestamp = str(int(time.time()))
            sign = base64.b64encode(hmac.new(f'{timestamp}\n{secret}'.encode(), b'', hashlib.sha256).digest()).decode()
            payload.update(timestamp=timestamp, sign=sign)
    else:
        payload = {'msgtype': 'text', 'text': {'content': text}}
        if binding.channel_type == 'dingtalk' and secret:
            timestamp = str(int(time.time() * 1000))
            sign = base64.b64encode(hmac.new(secret.encode(), f'{timestamp}\n{secret}'.encode(), hashlib.sha256).digest()).decode()
            url += '&' + urlencode({'timestamp': timestamp, 'sign': sign})
    try:
        response = requests.post(url, json=payload, timeout=(3, 8), allow_redirects=False)
    except requests.ConnectTimeout:
        raise DeliveryError('connect_timeout', retryable=True) from None
    except requests.RequestException:
        raise DeliveryError('transport_unknown', unknown=True) from None
    if response.status_code == 429:
        from datetime import datetime, timezone
        from email.utils import parsedate_to_datetime
        wait = 0
        raw = response.headers.get('Retry-After', '')
        try:
            wait = max(0, int(raw))
        except (ValueError, TypeError):
            try:
                wait = max(0, int((parsedate_to_datetime(raw) - datetime.now(timezone.utc)).total_seconds()))
            except (ValueError, TypeError, OverflowError):
                pass
        raise DeliveryError('rate_limited', retryable=True, retry_after=min(wait, 86400))
    if response.status_code >= 500:
        raise DeliveryError('upstream_unknown', unknown=True)
    if response.status_code >= 300:
        raise DeliveryError('http_rejected')
    try:
        data = response.json()
    except ValueError:
        raise DeliveryError('invalid_response', unknown=True) from None
    if not isinstance(data, dict):
        raise DeliveryError('invalid_response', unknown=True)
    code = data.get('code', data.get('StatusCode')) if binding.channel_type == 'feishu' else data.get('errcode')
    if code != 0:
        # Only explicit rate limit errors are retried; other provider errors require attention.
        if code in (45009, 130101, 11232):
            raise DeliveryError('rate_limited', retryable=True)
        raise DeliveryError('provider_rejected' if code is not None else 'invalid_response', unknown=code is None)
