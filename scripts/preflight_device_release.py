#!/usr/bin/env python3
"""设备批量治理发布前只读门禁。

检查：
1. 已归属客户的 ``(customer_id, device_name)`` 是否重复；存在重复时退出码 2，
   防止无设备 ID 的覆盖导入匹配到多行。
2. 同一设备在旧机柜上架记录中是否存在多个不同正功率；仅报告，不猜测回填值。

脚本不修改数据库。生产可显式传 ``--database-uri``，未传时读取环境变量或项目
根目录 ``.env``。``--output`` 可留下 JSON 审批附件。
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sqlalchemy import create_engine, inspect, text


ROOT = Path(__file__).resolve().parents[1]


def _env_database_uri() -> str:
    value = os.environ.get('ITSM_DATABASE_URI', '').strip()
    if value:
        return value
    env_file = ROOT / '.env'
    if env_file.exists():
        for raw_line in env_file.read_text(encoding='utf-8').splitlines():
            line = raw_line.strip()
            if line.startswith('ITSM_DATABASE_URI='):
                return line.split('=', 1)[1].strip().strip('"').strip("'")
    return ''


def _normalize_sqlite_uri(uri: str) -> str:
    prefix = 'sqlite:///'
    if not uri.startswith(prefix):
        return uri
    raw_path = uri[len(prefix):]
    if not raw_path or Path(raw_path).is_absolute():
        return uri
    return f'{prefix}{(ROOT / raw_path).resolve().as_posix()}'


def collect_report(database_uri: str) -> dict:
    engine = create_engine(_normalize_sqlite_uri(database_uri))
    try:
        tables = set(inspect(engine).get_table_names())
        required = {'devices', 'rack_installs'}
        missing = sorted(required - tables)
        if missing:
            raise RuntimeError(f'数据库缺少表：{", ".join(missing)}')
        with engine.connect() as conn:
            duplicate_rows = conn.execute(text("""
                SELECT customer_id, device_name, COUNT(*) AS duplicate_count
                  FROM devices
                 WHERE customer_id IS NOT NULL
                 GROUP BY customer_id, device_name
                HAVING COUNT(*) > 1
                 ORDER BY customer_id, device_name
            """)).mappings().all()
            power_rows = conn.execute(text("""
                SELECT d.id AS device_id, d.device_name,
                       COUNT(DISTINCT ri.rated_w) AS value_count
                  FROM devices d
                  JOIN rack_installs ri ON ri.device_id = d.id
                 WHERE ri.rated_w > 0
                 GROUP BY d.id, d.device_name
                HAVING COUNT(DISTINCT ri.rated_w) > 1
                 ORDER BY d.id
            """)).mappings().all()
            power_conflicts = []
            for row in power_rows:
                values = conn.execute(text("""
                    SELECT DISTINCT rated_w
                      FROM rack_installs
                     WHERE device_id = :device_id AND rated_w > 0
                     ORDER BY rated_w
                """), {'device_id': row['device_id']}).scalars().all()
                power_conflicts.append({
                    'device_id': row['device_id'],
                    'device_name': row['device_name'],
                    'rated_w_values': list(values),
                })
        return {
            'duplicate_customer_device_names': [dict(row) for row in duplicate_rows],
            'rack_power_conflicts': power_conflicts,
            'gate_passed': not duplicate_rows,
        }
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description='设备治理发布前只读预检')
    parser.add_argument('--database-uri', default='', help='数据库连接串；默认读环境变量/.env')
    parser.add_argument('--output', help='可选 JSON 报告路径')
    args = parser.parse_args()
    database_uri = args.database_uri.strip() or _env_database_uri()
    if not database_uri:
        parser.error('未找到 ITSM_DATABASE_URI，请通过 --database-uri、环境变量或 .env 提供')

    report = collect_report(database_uri)
    rendered = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    print(rendered)
    if args.output:
        output = Path(args.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + '\n', encoding='utf-8')
    return 0 if report['gate_passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
