#!/usr/bin/env bash
# 把"运行日志 / 内部核查报告"移出包外（按作者要求：日志不对外），包内只留脚本与公开样例结果
set -eu
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG="$(cd "$HERE/.." && pwd)"
EVID="$(dirname "$PKG")/_evidence_20261012"
mkdir -p "$EVID"

echo "=== 移出包外（-> <WORKSPACE>/_evidence_20261012/）==="
for f in mcp_e2e_pbso4_run.log mcp_e2e_pbso4_AFTER_FIX.log mcp_e2e_converged.log \
         probe_gpx_state.log leak_scan_after_sanitize.txt local_vs_package_diff.txt; do
  if [ -f "$PKG/verify/$f" ]; then
    mv "$PKG/verify/$f" "$EVID/$f"
    echo "  moved: verify/$f"
  fi
done

echo
echo "=== 包内 verify/ 现状 ==="
find "$PKG/verify" -type f | sed "s|$PKG/|  |" | sort
echo
echo "=== 包外证据目录 ==="
find "$EVID" -type f | sed "s|$EVID/|  |" | sort
echo
echo "=== 检查：包内是否还有 .log / 核查报告（应为空）==="
find "$PKG" -name '*.log' -o -name 'leak_scan_after_sanitize.txt' -o -name 'local_vs_package_diff.txt' | sed 's/^/  /' || true
echo "(end)"
