"""Best-effort security alerts that never alter the protected operation."""
from collections import defaultdict, deque
from datetime import datetime
from threading import Lock
from time import monotonic


_WINDOW_SECONDS = 60
_reveal_events = defaultdict(deque)
_last_alert = {}
_lock = Lock()


def emit_security_event(title, content):
    """Send an admin security event; notification failures remain non-blocking."""
    try:
        from utils.wecom_notify import EVENT_SECURITY, wecom_broadcast
        wecom_broadcast(EVENT_SECURITY, title, content, '/app/system/audit')
    except Exception:
        try:
            from flask import current_app
            current_app.logger.warning('安全事件告警发送失败: %s', title, exc_info=True)
        except Exception:
            pass


def note_password_reveal(user_id, username, device_id, ip):
    """Alert on five password reveals in one minute outside 08:00-19:00.

    Only identifiers and timestamps are retained; plaintext credentials never enter this
    process-local counter. Alerts have a one-minute cooldown per user.
    """
    local_now = datetime.now()
    if 8 <= local_now.hour < 19:
        return
    timestamp = monotonic()
    should_alert = False
    with _lock:
        events = _reveal_events[int(user_id)]
        while events and timestamp - events[0] > _WINDOW_SECONDS:
            events.popleft()
        events.append(timestamp)
        last = _last_alert.get(int(user_id), 0)
        if len(events) >= 5 and timestamp - last >= _WINDOW_SECONDS:
            _last_alert[int(user_id)] = timestamp
            should_alert = True
    if should_alert:
        emit_security_event(
            '非工作时间高频查看设备密码',
            f'用户={username}，设备ID={device_id}，IP={ip}，一分钟内查看次数≥5',
        )
