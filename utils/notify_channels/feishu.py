# -*- coding: utf-8 -*-
"""飞书自建应用渠道（框架交付：配置 app_id/app_secret 后启用）

配置（config_json，app_secret 入库前 Fernet 加密）：
    app_id / app_secret_encrypted
    address_by: user_id（默认，用手机号批量查 user_id）| open_id
寻址：notify_accounts_json["feishu"] = 手机号或 user_id/open_id。
真实推送联调：后台「发送测试」验证（待配置凭据）。
"""
import logging

from .base import NotifyChannel, ChannelError

log = logging.getLogger('itsm.notify.feishu')


class FeishuChannel(NotifyChannel):
    channel_type = 'feishu'
    label = '飞书'
    capabilities = frozenset({'text', 'markdown', 'file'})

    BASE = 'https://open.feishu.cn/open-apis'
    _token_cache = {}

    def _secret(self):
        from utils.crypto import decrypt_password
        enc = self.config.get('app_secret_encrypted') or ''
        if not enc:
            raise ChannelError('飞书 AppSecret 未配置')
        try:
            return decrypt_password(enc)
        except Exception:
            raise ChannelError('飞书 AppSecret 解密失败（.secret.key 与配置不匹配？）')

    def get_tenant_access_token(self):
        key = self.config.get('app_id') or ''
        cached = self._token_cache.get(key)
        from time import time
        if cached and cached[1] > time() + 600:
            return cached[0]
        data = self._request_json(
            f'{self.BASE}/auth/v3/tenant_access_token/internal',
            {'app_id': key, 'app_secret': self._secret()},
            headers={'Content-Type': 'application/json'},
        )
        token = data.get('tenant_access_token')
        if not token:
            raise ChannelError(f'飞书获取 token 失败：{data}')
        self._token_cache[key] = (token, time() + int(data.get('expire', 7200)))
        return token

    def _resolve_receive_id(self, account):
        if not account:
            raise ChannelError('用户未配置飞书账号')
        if self.config.get('address_by') == 'open_id':
            return account
        # 默认按手机号批量查 user_id
        user_id = self._mobile_to_user_id(account)
        if not user_id:
            raise ChannelError(f'飞书未找到手机号 {account} 对应用户')
        return user_id

    def _mobile_to_user_id(self, mobile):
        try:
            data = self._request_json(
                f'{self.BASE}/contact/v3/users/batch_get_id',
                {'mobiles': [mobile], 'user_id_type': 'user_id'},
                headers={'Authorization': f"Bearer {self.get_tenant_access_token()}"},
            )
            users = data.get('data', {}).get('user_list') or []
            return (users[0] or {}).get('user_id') or ''
        except Exception:
            return ''

    def _send(self, account, msgtype, content):
        data = {
            'receive_id': self._resolve_receive_id(account),
            'msg_type': msgtype,
            'content': content,
        }
        try:
            self._request_json(
                f'{self.BASE}/im/v1/messages?receive_id_type=user_id',
                data,
                headers={'Authorization': f"Bearer {self.get_tenant_access_token()}"},
            )
        except ChannelError as e:
            log.warning('飞书发送失败: %s', e)
            raise

    def send_text(self, account, title, content, link=''):
        text = title
        if content:
            text += f'\n{content}'
        if link:
            text += f'\n{link}'
        self._send(account, 'text', {'text': text[:2000]})

    def send_markdown(self, account, title, content, link=''):
        # 飞书富文本 post 消息：标题段落 + 正文 + 链接
        import json
        post = {'zh_cn': {'title': title[:120], 'content': []}}
        if content:
            post['zh_cn']['content'].append([{'tag': 'text', 'text': content[:3000]}])
        if link:
            post['zh_cn']['content'].append([{'tag': 'a', 'text': '查看详情', 'href': link}])
        self._send(account, 'post', json.dumps(post, ensure_ascii=False))

    def send_file(self, account, title, file_path, link=''):
        """飞书文件消息：先上传文件 → 发送 file 消息"""
        import os
        import requests
        token = self.get_tenant_access_token()
        with open(file_path, 'rb') as fp:
            resp = requests.post(
                f'{self.BASE}/im/v1/files',
                headers={'Authorization': f'Bearer {token}'},
                data={'file_type': 'stream', 'file_name': os.path.basename(file_path)},
                files={'file': fp}, timeout=20)
        data = resp.json()
        file_key = (data.get('data') or {}).get('file_key')
        if not file_key:
            raise ChannelError(f'飞书文件上传失败：{data}')
        import json
        self._send(account, 'file', json.dumps({'file_key': file_key}))
