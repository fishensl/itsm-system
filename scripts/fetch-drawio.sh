#!/usr/bin/env bash
# V20 在线拓扑：下载 drawio webapp 到 static/vendor/drawio/
# 用法： bash scripts/fetch-drawio.sh
# 依赖： curl + python3（用于解压 war/zip）
#
# drawio 资源体积较大（~135MB），不入 git，部署时执行本脚本拉取。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TARGET_DIR="$PROJECT_ROOT/static/vendor/drawio"
DRAWIO_VERSION="${DRAWIO_VERSION:-v30.2.7}"
WAR_URL="https://github.com/jgraph/drawio/releases/download/${DRAWIO_VERSION}/draw.war"

echo "[1/4] 目标目录: $TARGET_DIR"
mkdir -p "$TARGET_DIR"

if [ -f "$TARGET_DIR/index.html" ]; then
    echo "[skip] drawio 已存在，如需重新下载请先删除 $TARGET_DIR"
    exit 0
fi

TMP_WAR="$(mktemp -t draw.XXXXXX.war)"
echo "[2/4] 下载 $WAR_URL"
curl -L --fail -o "$TMP_WAR" "$WAR_URL"

echo "[3/4] 解压到 $TARGET_DIR"
python3 -c "
import zipfile, sys
with zipfile.ZipFile('$TMP_WAR') as z:
    z.extractall('$TARGET_DIR')
    print('  解压', len(z.namelist()), '个文件')
"

rm -f "$TMP_WAR"

# 裁剪非必要文件（方程渲染/第三方连接/非中英文 i18n）
echo "[4/4] 裁剪非必要文件"
cd "$TARGET_DIR"
rm -rf META-INF WEB-INF math4 connect
cd resources && ls | grep -vE '^dia\.(txt|js)$|^dia_zh\.txt$|^dia_en\.txt$' | xargs rm -f 2>/dev/null || true
cd "$TARGET_DIR"

echo "[done] drawio 就绪: $TARGET_DIR"
du -sh "$TARGET_DIR" 2>/dev/null || true
