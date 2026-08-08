# -*- coding: utf-8 -*-
"""自动备份配置（SystemSetting 持久化 + 调度器联动）

配置项（key → 默认值）：
    backup_enabled  '0'           是否启用每日自动备份（crontab 时代默认关闭，启用后由调度器执行）
    backup_time     '03:00'       每日执行时刻（HH:MM，本地时区）
    backup_keep     '30'          保留份数（透传 backup.sh 的 ITSM_BACKUP_KEEP）
"""
from models import SystemSetting, db

_KEY_DEFAULTS = {
    'backup_enabled': '0',
    'backup_time': '03:00',
    'backup_keep': '30',
}


def get_backup_config():
    """读全部备份配置（缺失项用默认值）"""
    rows = {s.key: s.value for s in SystemSetting.query.filter(
        SystemSetting.key.in_(_KEY_DEFAULTS)).all()}
    out = {}
    for k, default in _KEY_DEFAULTS.items():
        out[k] = rows.get(k, default)
    return out


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
        row = SystemSetting.query.get(k)
        if row:
            row.value = v
        else:
            db.session.add(SystemSetting(key=k, value=v))
    db.session.commit()
    return True, []


def backup_time_trigger():
    """返回 (hour, minute) cron 参数（供调度器注册）"""
    cfg = get_backup_config()
    hh, mm = cfg['backup_time'].split(':')
    return int(hh), int(mm)
