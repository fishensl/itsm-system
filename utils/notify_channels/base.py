# -*- coding: utf-8 -*-
"""多渠道通知平台 - 渠道适配器基类协议

渠道实现约定：
- channel_type: 唯一标识（wecom/dingtalk/feishu），与 NotifyChannelConfig.channel_type 对应
- capabilities: 能力位集合，⊆ {text, markdown, file}
- send_text/send_markdown/send_file: 按用户通知账号寻址推送；失败抛异常由调度层捕获
  （统一「失败仅记日志不阻断」由 send_all_channels 兜底）
- send_test: 后台「发送测试」入口，返回 (ok, message)
"""
import logging
from utils.redaction import redact_mapping, redact_text

log = logging.getLogger('itsm.notify')


class ChannelError(Exception):
    """渠道推送错误（凭据缺失/接口失败等）"""


class NotifyChannel:
    channel_type = ''
    label = ''
    # 能力位：text / markdown / file
    capabilities = frozenset({'text'})

    def __init__(self, cfg: dict, config_json: dict):
        """cfg: NotifyChannelConfig 记录字段；config_json: 解密后的配置 dict"""
        self.cfg = cfg
        self.config = config_json or {}

    # ---- 发送（子类必须实现） ----
    def send_text(self, account, title, content, link=''):
        raise NotImplementedError

    def send_markdown(self, account, title, content, link=''):
        raise NotImplementedError

    def send_file(self, account, title, file_path, link=''):
        raise NotImplementedError

    def send_test(self, account, mode='text'):
        """发送测试消息；返回 (ok: bool, message: str)"""
        try:
            if mode == 'file':
                import tempfile
                import os
                fd, tmp = tempfile.mkstemp(suffix='.txt', prefix='itsm_notify_test_')
                with os.fdopen(fd, 'w', encoding='utf-8') as fp:
                    fp.write('ITSM 通知渠道测试消息')
                try:
                    self.send_file(account, '渠道测试', tmp)
                finally:
                    os.remove(tmp)
            elif mode == 'markdown':
                self.send_markdown(account, '渠道测试', '**ITSM 通知渠道测试**\n- 时间：正常')
            else:
                self.send_text(account, '渠道测试', 'ITSM 通知渠道测试消息')
            return True, '发送成功'
        except Exception as e:
            return False, redact_text(e) or '发送失败'

    def supports(self, cap):
        return cap in self.capabilities

    # ---- 通用 HTTP 骨架 ----
    def _request_json(self, url, payload=None, headers=None, method='POST'):
        import requests
        kw = {'headers': headers or {}, 'timeout': 8}
        if payload is not None:
            kw['json'] = payload
        resp = requests.request(method, url, **kw)
        try:
            data = resp.json()
        except ValueError:
            data = {}
        if resp.status_code >= 400 or data.get('errcode') or data.get('code'):
            raise ChannelError(f'接口返回 {resp.status_code}: {redact_mapping(data)}')
        return data
