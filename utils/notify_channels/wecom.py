# -*- coding: utf-8 -*-
"""企业微信群机器人 Webhook 通知渠道。

配置（config_json，Webhook 地址入库前经 utils.crypto Fernet 加密）：
    webhook_url_encrypted: 群机器人 Webhook 完整地址（加密存储）

群机器人是群级广播渠道，不按用户企业微信账号逐人寻址；同一事件无论命中多少
接收人，都只向配置的群 Webhook 发送一次。
"""
import logging
import os
from urllib.parse import parse_qs, quote, urlsplit

from utils.redaction import redact_mapping

from .base import ChannelError, NotifyChannel

log = logging.getLogger('itsm.notify.wecom')

WECOM_WEBHOOK_HOST = 'qyapi.weixin.qq.com'
WECOM_WEBHOOK_PATH = '/cgi-bin/webhook/send'


def validate_webhook_url(value):
    """校验企业微信群机器人 Webhook，阻止任意 URL 导致 SSRF。"""
    url = str(value or '').strip()
    try:
        parsed = urlsplit(url)
        port = parsed.port
        keys = parse_qs(parsed.query, keep_blank_values=True).get('key') or []
    except ValueError as exc:
        raise ChannelError('企业微信 Webhook 地址格式不正确') from exc
    if (parsed.scheme != 'https' or parsed.hostname != WECOM_WEBHOOK_HOST or
            port not in (None, 443) or parsed.path != WECOM_WEBHOOK_PATH or
            parsed.username or parsed.password or parsed.fragment or
            len(keys) != 1 or not keys[0].strip()):
        raise ChannelError(
            '请输入企业微信群机器人生成的 HTTPS Webhook 地址')
    return url


class WecomChannel(NotifyChannel):
    channel_type = 'wecom'
    label = '企业微信群机器人'
    capabilities = frozenset({'text', 'markdown', 'file'})
    delivery_scope = 'channel'

    def _webhook_url(self):
        from utils.crypto import decrypt_password
        enc = self.config.get('webhook_url_encrypted') or ''
        if not enc:
            raise ChannelError('企业微信 Webhook 未配置')
        try:
            return validate_webhook_url(decrypt_password(enc))
        except ChannelError:
            raise
        except Exception as exc:
            raise ChannelError(
                '企业微信 Webhook 解密失败（.secret.key 与配置不匹配？）') from exc

    def _send_payload(self, payload):
        try:
            self._request_json(self._webhook_url(), payload)
        except ChannelError as exc:
            log.warning('企业微信群机器人发送失败: %s', exc)
            raise

    def _upload_file(self, file_path):
        if not os.path.isfile(file_path):
            raise ChannelError('测试文件不存在')
        webhook_url = self._webhook_url()
        key = parse_qs(urlsplit(webhook_url).query).get('key', [''])[0]
        upload_url = (
            f'https://{WECOM_WEBHOOK_HOST}/cgi-bin/webhook/upload_media'
            f'?key={quote(key, safe="")}&type=file')
        import requests
        with open(file_path, 'rb') as fp:
            resp = requests.post(
                upload_url,
                files={'media': (os.path.basename(file_path), fp)},
                timeout=15,
            )
        try:
            data = resp.json()
        except ValueError:
            data = {}
        if resp.status_code >= 400 or data.get('errcode') or not data.get('media_id'):
            raise ChannelError(
                f'企业微信文件上传失败：{redact_mapping(data)}')
        return data['media_id']

    def send_text(self, account, title, content, link=''):
        del account  # 群机器人无需用户账号
        text = title
        if content:
            text += f'\n{content}'
        if link:
            text += f'\n{link}'
        self._send_payload({
            'msgtype': 'text',
            'text': {'content': text[:2048]},
        })

    def send_markdown(self, account, title, content, link=''):
        del account
        markdown = f'**{title}**'
        if content:
            markdown += f'\n{content}'
        if link:
            markdown += f'\n> [查看详情]({link})'
        self._send_payload({
            'msgtype': 'markdown',
            'markdown': {'content': markdown[:4096]},
        })

    def send_file(self, account, title, file_path, link=''):
        del account, title, link
        self._send_payload({
            'msgtype': 'file',
            'file': {'media_id': self._upload_file(file_path)},
        })
