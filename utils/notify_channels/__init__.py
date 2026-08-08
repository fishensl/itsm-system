# -*- coding: utf-8 -*-
"""多渠道通知平台 - 渠道注册表与统一分发

- registry: channel_type → 适配器类（新增渠道 = 插一个适配器 + 后台加配置记录，事件代码零改动）
- send_all_channels(event_type, ...): 按规则取接收人（事件固定对象 ∪ 规则角色/用户），
  对已启用渠道逐人推送；任一渠道失败仅记日志不阻断。
"""
import logging

from utils.json_fields import parse_json

log = logging.getLogger('itsm.notify')

# 渠道注册表（import 即注册；钉钉/飞书交付适配器，真实联调待凭据）
from .base import NotifyChannel, ChannelError  # noqa: F401
from .wecom import WecomChannel  # noqa: F401
from .dingtalk import DingTalkChannel  # noqa: F401
from .feishu import FeishuChannel  # noqa: F401

_CHANNEL_CLASSES = {
    WecomChannel.channel_type: WecomChannel,
    DingTalkChannel.channel_type: DingTalkChannel,
    FeishuChannel.channel_type: FeishuChannel,
}

# 渠道类型白名单（后台配置页按此渲染表单字段）
CHANNEL_TYPES = ('wecom', 'dingtalk', 'feishu')


def register_channel(cls):
    """注册渠道适配器（dingtalk/feishu 加载时调用）"""
    _CHANNEL_CLASSES[cls.channel_type] = cls
    return cls


def channel_class(channel_type):
    return _CHANNEL_CLASSES.get(channel_type)


def _channel_configs(enabled_only=True):
    """读取启用（或全部）渠道配置，返回 [{channel_type, name, config_json, is_enabled}]"""
    from models import NotifyChannelConfig
    q = NotifyChannelConfig.query.order_by(NotifyChannelConfig.sort_order, NotifyChannelConfig.id)
    rows = q.all()
    out = []
    for r in rows:
        cfg = parse_json(r.config_json or '', default={}, field_name='channel_config')
        if not isinstance(cfg, dict):
            cfg = {}
        out.append({'channel_type': r.channel_type, 'name': r.name or r.channel_type,
                    'config_json': cfg, 'is_enabled': bool(r.is_enabled)})
    if enabled_only:
        out = [x for x in out if x['is_enabled']]
    return out


def channel_instances(enabled_only=True):
    """实例化渠道（跳过未注册类型的配置记录）"""
    for cfg in _channel_configs(enabled_only=enabled_only):
        cls = channel_class(cfg['channel_type'])
        if cls is None:
            continue
        yield cls(cfg, cfg['config_json'])


def _rule_recipient_ids(event_type):
    """读取通知规则接收人：{roles: [...], users: [id...]} → 用户 id 集合"""
    from models import NotifyRule, User
    rule = NotifyRule.query.filter_by(event_type=event_type).first()
    if not rule or not rule.is_enabled:
        return set()
    rec = parse_json(rule.recipients_json or '', default={}, field_name='notify_rule')
    ids = {int(u) for u in (rec.get('users') or []) if u}
    roles = [str(r) for r in (rec.get('roles') or []) if r]
    if roles:
        for u in User.query.filter_by(is_active=True).all():
            if any(u.has_role(r) for r in roles):
                ids.add(u.id)
    return ids


def _target_user_ids(event_type, target_user_ids):
    """事件固定对象 ∪ 规则接收人 → 去重用户 id 列表"""
    ids = set()
    for uid in (target_user_ids or []):
        try:
            ids.add(int(uid))
        except (TypeError, ValueError):
            continue
    try:
        ids |= _rule_recipient_ids(event_type)
    except Exception:
        log.warning('通知规则读取失败 event_type=%s', event_type, exc_info=True)
    return list(ids)


def _account_of(user, channel_type):
    accounts = user.notify_accounts() if hasattr(user, 'notify_accounts') else {}
    return (accounts or {}).get(channel_type) or ''


def _channel_send(ch, mode, account, title, content, link, file_path):
    if mode == 'file' and ch.supports('file'):
        ch.send_file(account, title, file_path, link)
    elif mode == 'markdown' and ch.supports('markdown'):
        ch.send_markdown(account, title, content, link)
    else:
        ch.send_text(account, title, content, link)


def send_all_channels(event_type, title, content='', link='', target_user_ids=None,
                      mode='text', file_path=None):
    """统一分发：全部启用渠道 × 目标用户推送；失败仅记日志不阻断。

    返回 (sent, failed)；sent=推送成功次数，failed=失败次数（无账号/渠道未启用不计）。
    """
    from models import User
    uids = _target_user_ids(event_type, target_user_ids)
    if not uids:
        return 0, 0
    users = User.query.filter(User.id.in_(uids), User.is_active.is_(True)).all()
    channels = list(channel_instances(enabled_only=True))
    sent = failed = 0
    for ch in channels:
        for u in users:
            account = _account_of(u, ch.channel_type)
            if not account:
                continue
            try:
                _channel_send(ch, mode, account, title, content, link, file_path)
                sent += 1
            except Exception as e:
                failed += 1
                log.warning('通知推送失败 channel=%s user=%s: %s', ch.channel_type, u.username, e)
    return sent, failed
