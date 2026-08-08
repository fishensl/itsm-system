# -*- coding: utf-8 -*-
"""钉钉自建应用渠道（框架交付：配置 appkey/appsecret/agent_id 后启用）

配置（config_json，app_secret 入库前 Fernet 加密）：
    app_key / app_secret_encrypted / agent_id
    address_by: userid（默认）| mobile
寻址：notify_accounts_json["dingtalk"] = 手机号或 userid。
真实推送联调：后台「发送测试」验证（待配置凭据）。
"""
import logging

from .base import NotifyChannel, ChannelError

log = logging.getLogger('itsm.notify.dingtalk')


class DingTalkChannel(NotifyChannel):
    channel_type = 'dingtalk'
    label = '钉钉'
    capabilities = frozenset({'text', 'markdown', 'file'})

    BASE = 'https://oapi.dingtalk.com'
    _token_cache = {}

    def _secret(self):
        from utils.crypto import decrypt_password
        enc = self.config.get('app_secret_encrypted') or ''
        if not enc:
            raise ChannelError('钉钉 AppSecret 未配置')
        try:
            return decrypt_password(enc)
        except Exception:
            raise ChannelError('钉钉 AppSecret 解密失败（.secret.key 与配置不匹配？）')

    def get_access_token(self):
        key = self.config.get('app_key') or ''
        cached = self._token_cache.get(key)
        from time import time
        if cached and cached[1] > time() + 600:
            return cached[0]
        import requests
        resp = requests.get(f'{self.BASE}/gettoken',
                            params={'appkey': key, 'appsecret': self._secret()}, timeout=8)
        data = resp.json()
        token = data.get('access_token')
        if not token:
            raise ChannelError(f'钉钉获取 token 失败：{data}')
        self._token_cache[key] = (token, time() + int(data.get('expires_in', 7200)))
        return token

    def _resolve_userid(self, account):
        if not account:
            raise ChannelError('用户未配置钉钉账号')
        if self.config.get('address_by') == 'mobile':
            userid = self._mobile_to_userid(account)
            if not userid:
                raise ChannelError(f'钉钉未找到手机号 {account} 对应用户')
            return userid
        return account

    def _mobile_to_userid(self, mobile):
        try:
            data = self._request_json(
                f'{self.BASE}/topapi/v2/user/getbymobile?access_token={self.get_access_token()}',
                {'mobile': mobile},
            )
            result = data.get('result') or {}
            return result.get('userid') or ''
        except Exception:
            return ''

    def _send(self, account, msgtype, payload):
        body = {
            'agent_id': int(self.config.get('agent_id') or 0),
            'userid_list': self._resolve_userid(account),
            'msg': {'msgtype': msgtype, msgtype: payload},
        }
        try:
            self._request_json(
                f'{self.BASE}/topapi/message/corpconversation/asyncsend_v2?access_token={self.get_access_token()}',
                body)
        except ChannelError as e:
            log.warning('钉钉发送失败: %s', e)
            raise

    def send_text(self, account, title, content, link=''):
        text = title
        if content:
            text += f'\n{content}'
        if link:
            text += f'\n{link}'
        self._send(account, 'text', {'content': text[:2000]})

    def send_markdown(self, account, title, content, link=''):
        md = f'### {title}\n'
        if content:
            md += f'{content}\n'
        if link:
            md += f'\n[查看详情]({link})'
        self._send(account, 'markdown', {'title': title[:64], 'text': md[:5000]})

    def send_file(self, account, title, file_path, link=''):
        """钉钉文件消息：先上传 media → asyncsend 的 file 消息"""
        import os
        import requests
        token = self.get_access_token()
        with open(file_path, 'rb') as fp:
            resp = requests.post(
                f'{self.BASE}/media/upload?access_token={token}&type=file',
                files={'media': (os.path.basename(file_path), fp)}, timeout=15)
        data = resp.json()
        if not data.get('media_id'):
            raise ChannelError(f'钉钉素材上传失败：{data}')
        self._send(account, 'file', {'media_id': data['media_id']})
