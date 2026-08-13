# -*- coding: utf-8 -*-
"""自动备份配置（SystemSetting 持久化 + 调度器联动）

配置项（key → 默认值）：
    backup_enabled  '0'           是否启用每日自动备份（crontab 时代默认关闭，启用后由调度器执行）
    backup_time     '03:00'       每日执行时刻（HH:MM，本地时区）
    backup_keep     '30'          保留份数（透传 backup.sh 的 ITSM_BACKUP_KEEP）
"""
from models import SystemSetting, db
from datetime import datetime, timezone

_KEY_DEFAULTS = {
    'backup_enabled': '0',
    'backup_time': '03:00',
    'backup_keep': '30',
}

_STATUS_DEFAULTS = {
    'backup_last_attempt_at': '',
    'backup_last_success_at': '',
    'backup_last_failure_at': '',
    'backup_last_error': '',
    'backup_consecutive_failures': '0',
    'backup_last_duration_seconds': '',
}


def _upsert(key, value):
    row = SystemSetting.query.get(key)
    if row:
        row.value = str(value)
    else:
        db.session.add(SystemSetting(key=key, value=str(value)))


def get_backup_config():
    """读全部备份配置（缺失项用默认值）"""
    rows = {s.key: s.value for s in SystemSetting.query.filter(
        SystemSetting.key.in_(_KEY_DEFAULTS)).all()}
    out = {}
    for k, default in _KEY_DEFAULTS.items():
        out[k] = rows.get(k, default)
    return out


def get_backup_status():
    """返回最近调度结果与 RPO 健康度，不包含命令输出或文件路径。"""
    keys = tuple(_STATUS_DEFAULTS) + tuple(_KEY_DEFAULTS)
    rows = {s.key: s.value for s in SystemSetting.query.filter(
        SystemSetting.key.in_(keys)).all()}
    enabled = rows.get('backup_enabled', _KEY_DEFAULTS['backup_enabled']) == '1'
    last_success = rows.get('backup_last_success_at', '')
    age_hours = None
    if last_success:
        try:
            success_at = datetime.fromisoformat(last_success.replace('Z', '+00:00'))
            if success_at.tzinfo is None:
                success_at = success_at.replace(tzinfo=timezone.utc)
            age_hours = round((datetime.now(timezone.utc) - success_at).total_seconds() / 3600, 1)
        except ValueError:
            age_hours = None
    try:
        failures = max(0, int(rows.get('backup_consecutive_failures', '0') or 0))
    except (TypeError, ValueError):
        failures = 0
    if not enabled:
        health = 'disabled'
    elif failures:
        health = 'failed'
    elif age_hours is None:
        health = 'never'
    elif age_hours > 26:
        health = 'stale'
    else:
        health = 'ok'
    return {
        'enabled': enabled,
        'health': health,
        'last_attempt_at': rows.get('backup_last_attempt_at', ''),
        'last_success_at': last_success,
        'last_failure_at': rows.get('backup_last_failure_at', ''),
        'last_error': rows.get('backup_last_error', ''),
        'consecutive_failures': failures,
        'last_duration_seconds': rows.get('backup_last_duration_seconds', ''),
        'rpo_age_hours': age_hours,
    }


def record_backup_result(success: bool, error: str = '', duration_seconds=None):
    """持久化一次自动备份结果；错误信息会压缩并截断，避免泄露命令上下文。"""
    now = datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
    current = get_backup_status()
    _upsert('backup_last_attempt_at', now)
    if duration_seconds is not None:
        _upsert('backup_last_duration_seconds', round(float(duration_seconds), 1))
    if success:
        _upsert('backup_last_success_at', now)
        _upsert('backup_last_error', '')
        _upsert('backup_consecutive_failures', 0)
    else:
        safe_error = ' '.join(str(error or '未知错误').split())[:500]
        _upsert('backup_last_failure_at', now)
        _upsert('backup_last_error', safe_error)
        _upsert('backup_consecutive_failures', current['consecutive_failures'] + 1)
    db.session.commit()
    return get_backup_status()


def save_backup_config(data):
    """保存备份配置（幂等 upsert）。返回 (ok, errors)"""
    errors = []
    updates = {}
    if 'backup_enabled' in data:
        v = str(data['backup_enabled']).strip()
        if v not in ('0', '1'):
            errors.append('自动备份开关取值非法')
        else:
            updates['backup_enabled'] = v
    if 'backup_time' in data:
        v = str(data['backup_time']).strip()
        parts = v.split(':')
        if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit() \
                or not (0 <= int(parts[0]) <= 23) or not (0 <= int(parts[1]) <= 59):
            errors.append('备份时间须为 HH:MM（24 小时制）')
        else:
            updates['backup_time'] = f'{int(parts[0]):02d}:{int(parts[1]):02d}'
    if 'backup_keep' in data:
        v = str(data['backup_keep']).strip()
        if not v.isdigit() or not (1 <= int(v) <= 365):
            errors.append('保留份数须为 1-365 的整数')
        else:
            updates['backup_keep'] = v
    if errors:
        return False, errors
    for k, v in updates.items():
        _upsert(k, v)
    db.session.commit()
    return True, []


def backup_time_trigger():
    """返回 (hour, minute) cron 参数（供调度器注册）"""
    cfg = get_backup_config()
    hh, mm = cfg['backup_time'].split(':')
    return int(hh), int(mm)
