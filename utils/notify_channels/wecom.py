# -*- coding: utf-8 -*-
"""企业微信自建应用渠道（默认启用）

配置（config_json，secret 入库前经 utils.crypto Fernet 加密）：
    corpid: 企业 ID
    agent_id: 自建应用 AgentId
    secret_encrypted: 应用 Secret（加密存储）
    address_by: userid（默认）| mobile
寻址：notify_accounts_json["wecom"] 为用户企微账号
（userid 或手机号，依 address_by 转换；开启「通讯录同步」后 userid=企业账号）。
"""
import logging

from .base import NotifyChannel, ChannelError

log = logging.getLogger('itsm.notify.wecom')


class WecomChannel(NotifyChannel):
    channel_type = 'wecom'
    label = '企业微信'
    capabilities = frozenset({'text', 'markdown', 'file'})

    BASE = 'https://qyapi.weixin.qq.com/cgi-bin'
    _token_cache = {}   # {agent_key: (token, expire_ts)}

    # ---- 配置与凭据 ----
    def _secret(self):
        from utils.crypto import decrypt_password
        enc = self.config.get('secret_encrypted') or ''
        if not enc:
            raise ChannelError('企业微信 Secret 未配置')
        try:
            return decrypt_password(enc)
        except Exception:
            raise ChannelError('企业微信 Secret 解密失败（.secret.key 与配置不匹配？）')

    def _key(self):
        return f"{self.config.get('corpid')}:{self.config.get('agent_id')}"

    def get_access_token(self):
        """获取并缓存 access_token（2 小时过期，提前 10 分钟刷新）"""
        key = self._key()
        cached = self._token_cache.get(key)
        from time import time
        if cached and cached[1] > time() + 600:
            return cached[0]
        corpid = (self.config.get('corpid') or '').strip()
        agent_id = (self.config.get('agent_id') or '').strip()
        if not corpid or not agent_id:
            raise ChannelError('企业微信 Corpid / AgentId 未配置')
        import requests
        resp = requests.get(
            f'{self.BASE}/gettoken',
            params={'corpid': corpid, 'corpsecret': self._secret()}, timeout=8)
        data = resp.json()
        token = data.get('access_token')
        if not token:
            raise ChannelError(f'企业微信获取 token 失败：{data}')
        self._token_cache[key] = (token, time() + data.get('expires_in', 7200))
        return token

    def _resolve_account(self, account):
        """按 address_by 解析用户寻址；mobile → userid"""
        if not account:
            raise ChannelError('用户未配置企业微信账号')
        if self.config.get('address_by') == 'mobile':
            userid = self._mobile_to_userid(account)
            if not userid:
                raise ChannelError(f'企业微信未找到手机号 {account} 对应用户')
            return userid
        return account

    def _mobile_to_userid(self, mobile):
        try:
            data = self._request_json(
                f'{self.BASE}/user/getuserid?access_token={self.get_access_token()}',
                {'mobile': mobile},
            )
            return data.get('userid') or ''
        except Exception:
            return ''

    def _send(self, account, msgtype, payload, media_file=None):
        token = self.get_access_token()
        if media_file:
            upload = self._upload_media(token, media_file)
            if msgtype == 'image':
                payload = {'media_id': upload}
            else:
                payload = {'media_id': upload}
        body = {
            'touser': self._resolve_account(account),
            'msgtype': msgtype,
            'agentid': int(self.config.get('agent_id') or 0),
        }
        body[msgtype] = payload
        try:
            self._request_json(f'{self.BASE}/message/send?access_token={token}', body)
        except ChannelError as e:
            log.warning('企微发送失败: %s', e)
            raise

    def _upload_media(self, token, file_path):
        """上传临时素材 → media_id"""
        import os
        import requests
        if not os.path.isfile(file_path):
            raise ChannelError('测试文件不存在')
        file_type = 'image' if file_path.lower().endswith(
            ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp')) else 'file'
        with open(file_path, 'rb') as fp:
            resp = requests.post(
                f'{self.BASE}/media/upload?access_token={token}&type={file_type}',
                files={'media': (os.path.basename(file_path), fp)}, timeout=15)
        data = resp.json()
        if data.get('errcode'):
            raise ChannelError(f'企微素材上传失败：{data}')
        return data.get('media_id')

    # ---- 发送实现 ----
    def send_text(self, account, title, content, link=''):
        text = title
        if content:
            text += f'\n{content}'
        if link:
            text += f'\n{link}'
        self._send(account, 'text', {'content': text[:2048]})

    def send_markdown(self, account, title, content, link=''):
        md = f'**{title}**'
        if content:
            md += f'\n{content}'
        if link:
            md += f'\n> [查看详情]({link})'
        self._send(account, 'markdown', {'content': md[:2048]})

    def send_file(self, account, title, file_path, link=''):
        # 企微 file 消息限 20MB，通过媒体上传后以 file 消息发送
        self._send(account, 'file', {}, media_file=file_path)
