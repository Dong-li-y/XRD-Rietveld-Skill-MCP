#!/usr/bin/env bash
# 重新生成 MCP refine 修复补丁：比较包内"修复前原件"与"修复后 server.py"
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRCDIR="$HERE/../mcp/gsas2_mcp_server"
OUT="$HERE/../mcp/patches/refine-return-value-fix.patch"

ORIG="$(ls "$SRCDIR"/server.py.orig-*.bak | head -1)"
cd "$SRCDIR"
diff -u "$(basename "$ORIG")" server.py > "$OUT" || true
wc -l "$OUT"
echo "--- added / removed lines ---"
grep -c '^+' "$OUT" || true
grep -c '^-' "$OUT" || true
