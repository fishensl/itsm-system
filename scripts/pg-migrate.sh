#!/usr/bin/env bash
# ============================================================
# ITSM SQLite → PostgreSQL 原地迁移（Ubuntu 24）
# 用法: sudo bash pg-migrate.sh [/path/to/app] [PG库名] [PG用户名]
# 默认: APP_DIR=/home/itsm-system_20260614  PG库=itsm  PG用户=itsm
#
# 流程：备份兜底 → 导出 SQLite 全量包 → 装 PG → 建库/用户 → 改 .env 指向 PG
#       → 停服务 → flask db upgrade 在 PG 建表 → 导入全量包(含 setval 重置序列)
#       → 起服务 → 自检。全程保留 SQLite 文件，失败可用 pg-rollback.sh 回退。
# ============================================================
set -euo pipefail

APP_DIR="${1:-/home/itsm-system_20260614}"
PG_DB="${2:-itsm}"
PG_USER="${3:-itsm}"
VENV="${APP_DIR}/venv"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
SQLITE_DB="${APP_DIR}/instance/itsm.db"
ENV_FILE="${APP_DIR}/.env"
BACKUP_DIR="${APP_DIR}/backups"
EXPORT_ZIP="${BACKUP_DIR}/pre_pg_migration_${TIMESTAMP}.zip"

echo "============================================"
echo "  ITSM SQLite → PostgreSQL 迁移"
echo "  应用目录: ${APP_DIR}"
echo "  PG 库/用户: ${PG_DB} / ${PG_USER}"
echo "  时间: ${TIMESTAMP}"
echo "============================================"

# ---- 0. 前置校验 ----
if [ "$(id -u)" -ne 0 ]; then
    echo "[FATAL] 请用 sudo 运行"; exit 1
fi
if [ ! -d "${APP_DIR}" ]; then
    echo "[FATAL] 应用目录不存在: ${APP_DIR}"; exit 1
fi
if [ ! -x "${VENV}/bin/python" ]; then
    echo "[FATAL] venv 缺失: ${VENV}/bin/python"; exit 1
fi
if [ ! -f "${SQLITE_DB}" ]; then
    echo "[FATAL] SQLite 库不存在: ${SQLITE_DB}（已迁移过？请用 pg-rollback.sh 回退后再试）"; exit 1
fi
if grep -q 'postgresql://' "${ENV_FILE}" 2>/dev/null; then
    echo "[FATAL] .env 已指向 postgresql://，似乎已迁移；如需重做先 pg-rollback.sh"; exit 1
fi

echo ""
echo "本次迁移会短暂停机（约数分钟，取决于数据量）。"
read -rp "确认开始迁移? (输入 yes 继续): " CONFIRM
if [ "${CONFIRM}" != "yes" ]; then
    echo "已取消"; exit 0
fi

mkdir -p "${BACKUP_DIR}"

# ---- 1. 兜底备份：SQLite 文件 + .env + .secret.key 原样打包 ----
echo ""
echo "[1/9] 兜底备份（SQLite 文件 + .env + .secret.key）..."
SHUTTLE="${BACKUP_DIR}/sqlite_shuttle_${TIMESTAMP}.tar.gz"
tar -czf "${SHUTTLE}" -C "${APP_DIR}" instance/itsm.db .env .secret.key 2>/dev/null || true
echo "  已保存: ${SHUTTLE}"

# ---- 2. 导出 SQLite 全量数据包（data_io.build_export_zip）----
echo ""
echo "[2/9] 导出 SQLite 全量数据包..."
SECRET_KEY_VAL=$(grep -E '^ITSM_SECRET_KEY=' "${ENV_FILE}" 2>/dev/null | cut -d= -f2- || true)
ITSM_SECRET_KEY="${SECRET_KEY_VAL}" ITSM_ENV=production FLASK_ENV=production \
  "${VENV}/bin/python" - "${APP_DIR}" "${EXPORT_ZIP}" <<'PYEOF'
import sys, os
app_dir, out_zip = sys.argv[1], sys.argv[2]
os.chdir(app_dir)
from app import app
from utils.data_io import build_export_zip
with app.app_context():
    tmp, size, manifest = build_export_zip(config_only=False)
    import shutil
    shutil.move(tmp, out_zip)
    print(f"  导出包: {out_zip} ({size} 字节, {len(manifest['table_counts'])} 表, {sum(manifest['table_counts'].values())} 行)")
PYEOF
if [ ! -s "${EXPORT_ZIP}" ]; then
    echo "[FATAL] 导出失败，包为空"; exit 1
fi

# ---- 3. 安装 PostgreSQL（若未装）----
echo ""
echo "[3/9] 安装 PostgreSQL（若未装）..."
if ! command -v psql >/dev/null 2>&1; then
    apt-get update -qq
    apt-get install -y -qq postgresql postgresql-client
else
    echo "  已安装: $(psql --version 2>/dev/null | head -1)"
fi
systemctl enable --now postgresql >/dev/null 2>&1 || true

# ---- 4. 创建 PG 库与用户 ----
echo ""
echo "[4/9] 创建 PG 库/用户: ${PG_DB} / ${PG_USER}"
PG_PASSWORD=$(python3 -c "import secrets; print(secrets.token_hex(16))")
# 幂等：用户已存在则改密，库已存在则跳过
sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL || { echo "[FATAL] 建库/用户失败"; exit 1; }
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${PG_USER}') THEN
    CREATE USER ${PG_USER} WITH PASSWORD '${PG_PASSWORD}';
  ELSE
    ALTER USER ${PG_USER} WITH PASSWORD '${PG_PASSWORD}';
  END IF;
END \$\$;
SQL
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${PG_DB}'" | grep -q 1; then
    sudo -u postgres createdb -O "${PG_USER}" "${PG_DB}"
    echo "  数据库 ${PG_DB} 已创建"
else
    echo "  数据库 ${PG_DB} 已存在（沿用；若非空请先 DROP 再跑）"
fi
sudo -u postgres psql -d "${PG_DB}" -c "GRANT ALL ON SCHEMA public TO ${PG_USER};" >/dev/null

# ---- 5. 更新 .env 指向 PG（保留原 SQLite 行作注释，便于回滚）----
echo ""
echo "[5/9] 更新 .env 指向 PostgreSQL..."
PG_URI="postgresql://${PG_USER}:${PG_PASSWORD}@localhost:5432/${PG_DB}"
# 旧 URI 行注释掉（若存在），追加新行
if grep -qE '^ITSM_DATABASE_URI=' "${ENV_FILE}" 2>/dev/null; then
    sed -i 's|^ITSM_DATABASE_URI=|# ITSM_DATABASE_URI=|' "${ENV_FILE}"
fi
echo "ITSM_DATABASE_URI=${PG_URI}" >> "${ENV_FILE}"
echo "# 迁移前 SQLite URI（pg-rollback.sh 用此恢复）: sqlite:///$(echo "${APP_DIR}" | sed 's|/|\\/|g')/instance/itsm.db" >> "${ENV_FILE}"
chmod 600 "${ENV_FILE}"
echo "  .env 已更新 ITSM_DATABASE_URI=${PG_URI}"

# ---- 6. 停服务 ----
echo ""
echo "[6/9] 停止 itsm 服务..."
systemctl stop itsm || true
echo "  已停止"

# ---- 7. flask db upgrade 在 PG 建表 + Alembic 接管 ----
echo ""
echo "[7/9] 在 PG 上执行 Alembic 迁移建表..."
ITSM_SECRET_KEY="${SECRET_KEY_VAL}" ITSM_ENV=production FLASK_ENV=production \
  ITSM_DATABASE_URI="${PG_URI}" \
  "${VENV}/bin/python" - "${APP_DIR}" <<'PYEOF'
import sys, os
app_dir = sys.argv[1]
os.chdir(app_dir)  # 确保能 import app（sudo 默认 cwd 是 /root，不 cd 会 ModuleNotFoundError）
from app import app, init_db
init_db()
print('  [OK] PG schema 已建 + seed 完成')
PYEOF

# ---- 8. 导入全量数据包到 PG（data_io.perform_import，含 setval 序列重置）----
echo ""
echo "[8/9] 导入全量数据到 PG..."
ITSM_SECRET_KEY="${SECRET_KEY_VAL}" ITSM_ENV=production FLASK_ENV=production \
  ITSM_DATABASE_URI="${PG_URI}" \
  "${VENV}/bin/python" - "${APP_DIR}" "${EXPORT_ZIP}" <<'PYEOF'
import sys, os
app_dir, in_zip = sys.argv[1], sys.argv[2]
os.chdir(app_dir)
from app import app, db
from utils.data_io import perform_import
with app.app_context():
    try:
        result = perform_import(in_zip, restore_secret_key=True)
        db.session.commit()
        print(f"  [OK] 导入 {result['restored_rows']} 行, {result['restored_files']} 文件, 密钥还原={result['secret_key_restored']}")
        for w in result['warnings'][:5]:
            print(f"   warn: {w}")
    except Exception as e:
        db.session.rollback()
        print(f"  [FAIL] 导入失败: {e}")
        sys.exit(1)
PYEOF
if [ $? -ne 0 ]; then
    echo "[FATAL] 数据导入失败！请用 pg-rollback.sh 回退到 SQLite"
    exit 1
fi

# 修复文件所有权（导入可能以 root 写文件）
chown -R itsm:itsm "${APP_DIR}" 2>/dev/null || true

# ---- 9. 起服务 + 自检 ----
echo ""
echo "[9/9] 启动服务并自检..."
systemctl start itsm
sleep 3
if systemctl is-active --quiet itsm; then
    echo "  itsm 服务已运行"
else
    echo "[FAIL] itsm 服务未起来，查日志: journalctl -u itsm -n 50"
    exit 1
fi

# 自检：确认连的是 PG 且数据量对得上
ITSM_SECRET_KEY="${SECRET_KEY_VAL}" ITSM_ENV=production FLASK_ENV=production \
  ITSM_DATABASE_URI="${PG_URI}" \
  "${VENV}/bin/python" - "${APP_DIR}" <<'PYEOF'
import sys, os
app_dir = sys.argv[1]
os.chdir(app_dir)
from app import app, db
from sqlalchemy import text
with app.app_context():
    dialect = db.engine.dialect.name
    print(f"  当前 dialect: {dialect}")
    assert dialect == 'postgresql', '仍连 SQLite！迁移未生效'
    for t in ('customers','tickets','devices','users'):
        c = db.session.execute(text(f'SELECT COUNT(*) FROM {t}')).scalar()
        print(f"  PG {t}: {c} 行")
PYEOF

echo ""
echo "============================================"
echo "  迁移完成！数据库已切换到 PostgreSQL"
echo "============================================"
echo ""
echo "  SQLite 文件仍保留在: ${SQLITE_DB}（可作回退依据）"
echo "  导出包: ${EXPORT_ZIP}"
echo "  兜底包: ${SHUTTLE}"
echo ""
echo "  如需回退到 SQLite:  sudo bash ${APP_DIR}/scripts/pg-rollback.sh"
echo "  服务状态:           sudo systemctl status itsm"
echo "  日志:               sudo journalctl -u itsm -f"
echo ""
echo "  ⚠️ 确认运行稳定后，建议保留 SQLite 文件至少 7 天再清理。"
