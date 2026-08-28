"""设备覆盖导入发布门禁（模拟迁移前数据库，因此不创建新唯一约束）。"""
from sqlalchemy import create_engine, text

from scripts.preflight_device_release import collect_report


def _legacy_database(tmp_path, assigned=True):
    path = tmp_path / 'legacy.db'
    uri = f'sqlite:///{path.as_posix()}'
    engine = create_engine(uri)
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE devices (
                id INTEGER PRIMARY KEY, customer_id INTEGER NULL, device_name VARCHAR(128) NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE rack_installs (
                id INTEGER PRIMARY KEY, device_id INTEGER NULL, rated_w INTEGER NULL
            )
        """))
        customer_id = 1 if assigned else None
        conn.execute(text("""
            INSERT INTO devices (id, customer_id, device_name)
            VALUES (1, :customer_id, '同名设备'), (2, :customer_id, '同名设备')
        """), {'customer_id': customer_id})
        conn.execute(text("""
            INSERT INTO rack_installs (id, device_id, rated_w)
            VALUES (1, 1, 300), (2, 1, 500)
        """))
    engine.dispose()
    return uri


def test_duplicate_name_blocks_and_power_conflict_is_reported(tmp_path):
    report = collect_report(_legacy_database(tmp_path, assigned=True))
    assert report['gate_passed'] is False
    assert report['duplicate_customer_device_names'][0]['duplicate_count'] == 2
    assert report['rack_power_conflicts'][0]['rated_w_values'] == [300, 500]


def test_unassigned_same_name_does_not_block_id_only_update_rule(tmp_path):
    report = collect_report(_legacy_database(tmp_path, assigned=False))
    assert report['gate_passed'] is True
    assert report['duplicate_customer_device_names'] == []
