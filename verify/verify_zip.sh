#!/usr/bin/env bash
# 交付前校验：解压 zip 回比目录、确认包内是修复后的 server.py、抽查 sha256 清单
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG="$(cd "$HERE/.." && pwd)"
NAME="$(basename "$PKG")"
ZIP="$(dirname "$PKG")/$NAME.zip"
TMP="$(mktemp -d)"

cd "$TMP"
unzip -q "$ZIP"
echo "=== 解压后与目录比对（应无输出=完全一致）==="
diff -r "$TMP/$NAME" "$PKG" || true
echo "(diff 结束)"
echo "=== 包内 server.py 是否含修复（max_cycles）==="
grep -c 'max_cycles' "$TMP/$NAME/mcp/gsas2_mcp_server/server.py"
grep -n 'if result is None' "$TMP/$NAME/mcp/gsas2_mcp_server/server.py" || echo "(旧缺陷代码已不在)"
echo "=== 抽查清单一致性（前 3 条）==="
cd "$TMP/$NAME"
head -3 MANIFEST.sha256 | while read -r h f; do
  a=$(sha256sum "$f" | cut -d' ' -f1)
  if [ "$a" = "$h" ]; then printf 'MATCH  %s\n' "$f"; else printf 'MISMATCH  %s\n' "$f"; fi
done
cd "$TMP" && rm -rf "$TMP"
echo "OK: 临时目录已清理"
