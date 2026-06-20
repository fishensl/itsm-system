#!/usr/bin/env bash
# ============================================================
# ITSM SQLite→PostgreSQL 迁移前体检（Ubuntu 24）
# 用法: sudo bash pg-check.sh [/path/to/app]
# 默认: /home/itsm-system_20260614
# 行为：只读检查，不改任何东西。退出码 0=可迁移，1=有阻断项，2=有警告但可继续
# ============================================================
set -uo pipefail

APP_DIR="${1:-/home/itsm-system_20260614}"
VENV="${APP_DIR}/venv"

WARN_COUNT=0
FAIL_COUNT=0

warn() { echo "[WARN] $*"; WARN_COUNT=$((WARN_COUNT+1)); }
fail() { echo "[FAIL] $*"; FAIL_COUNT=$((FAIL_COUNT+1)); }
ok()   { echo "[ OK ] $*"; }

echo "============================================"
echo "  ITSM → PostgreSQL 迁移前体检"
echo "  目标: ${APP_DIR}"
echo "============================================"
echo ""

# ---- 1. 基本环境 ----
echo "[1/6] 基本环境检查..."
if [ "$(id -u)" -ne 0 ]; then
    fail "请用 sudo 运行（需创建 PG 库/用户、改 .env、重启服务）"
else
    ok "root 权限"
fi

if [ ! -d "${APP_DIR}" ]; then
    fail "应用目录不存在: ${APP_DIR}"
    exit 1
fi
ok "应用目录存在"

if [ ! -x "${VENV}/bin/python" ]; then
    fail "venv 不存在或无 python: ${VENV}/bin/python"
else
    ok "venv 就绪"
fi

if [ ! -f "${APP_DIR}/instance/itsm.db" ]; then
    warn "未找到 instance/itsm.db（可能已是 PG 或未初始化）"
else
    ok "SQLite 数据库存在: instance/itsm.db"
fi

if [ ! -f "${APP_DIR}/.env" ]; then
    warn ".env 不存在，迁移脚本将创建 ITSM_DATABASE_URI"
else
    # 检查当前是否已是 PG（避免重复迁移）
    if grep -q 'postgresql://' "${APP_DIR}/.env" 2>/dev/null; then
        fail ".env 里 ITSM_DATABASE_URI 已是 postgresql://，似乎已迁移过；如需重做请先用 pg-rollback.sh 回到 SQLite"
    else
        ok ".env 当前指向 SQLite（可迁移）"
    fi
fi

# ---- 2. 磁盘空间 ----
echo ""
echo "[2/6] 磁盘空间检查..."
DB_SIZE=$(stat -c%s "${APP_DIR}/instance/itsm.db" 2>/dev/null || echo 0)
AVAIL_KB=$(df -P "${APP_DIR}" | awk 'NR==2{print $4}')
AVAIL_MB=$((AVAIL_KB / 1024))
# 备份包(zip)≈DB+文件；PG 库≈DB；需约 DB*3 的余量
NEED_MB=$(( (DB_SIZE / 1024 / 1024) * 3 + 200 ))
echo "  SQLite DB 大小: $((DB_SIZE/1024/1024)) MB，可用空间: ${AVAIL_MB} MB，建议余量: ${NEED_MB} MB"
if [ "${AVAIL_MB}" -lt "${NEED_MB}" ]; then
    warn "可用空间偏紧（建议 ${NEED_MB} MB，当前 ${AVAIL_MB} MB）"
else
    ok "磁盘空间充足"
fi

# ---- 3. 内存（PG 共享内存）----
echo ""
echo "[3/6] 内存检查..."
MEM_MB=$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo)
if [ "${MEM_MB:-0}" -lt 512 ]; then
    warn "可用内存偏低（${MEM_MB} MB，PG 建议 ≥512 MB）"
else
    ok "可用内存 ${MEM_MB} MB"
fi

# ---- 4. PG 软件包 ----
echo ""
echo "[4/6] PostgreSQL 软件包检查..."
if command -v psql >/dev/null 2>&1; then
    ok "PostgreSQL 已安装: $(psql --version 2>/dev/null | head -1)"
else
    warn "PostgreSQL 未安装（迁移脚本会 apt 安装 postgresql）"
fi

# ---- 5. 代码与依赖 ----
echo ""
echo "[5/6] 代码与依赖检查..."
if [ ! -d "${APP_DIR}/migrations" ]; then
    fail "缺少 migrations/ 目录（Alembic 未初始化）；先 git pull 拿到迁移脚本"
else
    ok "migrations/ 目录存在"
fi

if ! "${VENV}/bin/python" -c "import flask_migrate" 2>/dev/null; then
    fail "venv 缺 flask-migrate；先在 ${APP_DIR} 运行: ${VENV}/bin/pip install -r requirements.txt"
else
    ok "flask-migrate 已装"
fi

if ! "${VENV}/bin/python" -c "import psycopg2" 2>/dev/null; then
    fail "venv 缺 psycopg2-binary；先运行: ${VENV}/bin/pip install -r requirements.txt"
else
    ok "psycopg2-binary 已装"
fi

# ---- 6. 数据兼容性扫描（PG 严格项）----
echo ""
echo "[6/6] SQLite 数据兼容性扫描..."
ENV_FILE="${APP_DIR}/.env"
SECRET_KEY_VAL=$(grep -E '^ITSM_SECRET_KEY=' "${ENV_FILE}" 2>/dev/null | cut -d= -f2- || true)
SCAN_OK=1
ITSM_SECRET_KEY="${SECRET_KEY_VAL}" ITSM_ENV=production FLASK_ENV=production \
  "${VENV}/bin/python" - "${APP_DIR}" <<'PYEOF' || SCAN_OK=0
import sys, os
app_dir = sys.argv[1]
os.chdir(app_dir)
from app import app, db
from sqlalchemy import text, inspect
issues = []
with app.app_context():
    insp = inspect(db.engine)
    # 6a. devices.interface 长度（迁移前应已转 Text，但旧数据可能 >128）
    if insp.has_table('devices'):
        long_iface = db.session.execute(text(
            "SELECT COUNT(*) FROM devices WHERE interface IS NOT NULL AND LENGTH(interface) > 128"
        )).scalar() or 0
        if long_iface:
            issues.append(f"devices.interface 有 {long_iface} 行 >128 字符（pg_type_fixes 已转 Text，应无碍，仅提示）")
    # 6b. 重复 customers.name（唯一约束迁移会失败）
    if insp.has_table('customers'):
        dup = db.session.execute(text(
            "SELECT COUNT(*) FROM (SELECT name FROM customers GROUP BY name HAVING COUNT(*)>1) x"
        )).scalar() or 0
        if dup:
            issues.append(f"customers.name 有 {dup} 组重复（迁移会自动改名去重，仅提示）")
    # 6c. 重复 tickets.number
    if insp.has_table('tickets'):
        dup = db.session.execute(text(
            "SELECT COUNT(*) FROM (SELECT number FROM tickets GROUP BY number HAVING COUNT(*)>1) x"
        )).scalar() or 0
        if dup:
            issues.append(f"tickets.number 有 {dup} 组重复（迁移会自动改名去重，仅提示）")
    # 6d. 布尔列里非 0/1 的脏值（PG 严格）
    for tbl, col in [('devices','is_maintenance'),('devices','is_in_use'),('users','is_active')]:
        if insp.has_table(tbl):
            bad = db.session.execute(text(
                f"SELECT COUNT(*) FROM {tbl} WHERE {col} IS NOT NULL AND {col} NOT IN (0,1)"
            )).scalar() or 0
            if bad:
                issues.append(f"{tbl}.{col} 有 {bad} 行非 0/1 的布尔脏值（PG 会拒绝，需先清洗）")
if issues:
    print("\n  数据兼容性问题:")
    for x in issues:
        print("   - " + x)
    sys.exit(1)
print("  无阻断性数据问题")
PYEOF
if [ "${SCAN_OK}" -ne 1 ]; then
    # 扫描脚本内部已区分阻断 vs 提示；这里只把整体标记为告警（提示项不阻断）
    warn "数据扫描发现问题（详见上方；标为「迁移会自动处理」者不阻断，「需先清洗」者须手动修）"
else
    ok "数据扫描通过"
fi

# ---- 汇总 ----
echo ""
echo "============================================"
echo "  体检结果: FAIL=${FAIL_COUNT}  WARN=${WARN_COUNT}"
echo "============================================"
if [ "${FAIL_COUNT}" -gt 0 ]; then
    echo "  存在阻断项，请先修复后再运行 pg-migrate.sh"
    exit 1
fi
if [ "${WARN_COUNT}" -gt 0 ]; then
    echo "  有警告项，确认无碍后可继续迁移"
    exit 2
fi
echo "  一切就绪，可运行: sudo bash ${APP_DIR}/scripts/pg-migrate.sh"
exit 0
