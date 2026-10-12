#!/usr/bin/env bash
# 收尾：把备份目录移出包 → 跑本机/包内比对 → 脱敏核查 → 重建 → 校验
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG="$(cd "$HERE/.." && pwd)"
PY="${PY:-D:/app/Anaconda/python.exe}"
PY="$(cygpath -m "$PY")"
PKG_N="$(cygpath -m "$PKG")"
WS="$(dirname "$PKG")"

echo "=== [0] 清理误落包内的文件 ==="
if [ -d "$PKG/_skill_backups_20261012" ]; then
  rm -rf "$WS/_skill_backups_20261012"
  mv "$PKG/_skill_backups_20261012" "$WS/_skill_backups_20261012"
  echo "moved: <PACKAGE>/_skill_backups_20261012 -> <WORKSPACE>/_skill_backups_20261012"
fi
rm -f "$PKG/verify/backup_local_skill.sh.py"
rm -f "$PKG/verify/local_vs_package_diff.txt"
rm -f "$PKG/verify/leak_scan_after_sanitize.txt"
find "$PKG" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true

echo
echo "=== [0b] 日志/核查报告移出包外（作者要求：日志不对外）==="
bash "$PKG/verify/move_logs_outside.sh" | tail -25

echo
echo "=== [1] 本机备份（写到包外）==="
"$PY" "$PKG_N/verify/backup_local_skill.py"

echo
echo "=== [2] 本机 vs 包内 ==="
bash "$PKG/verify/diff_local_vs_package.sh"

echo
echo "=== [3] 脱敏核查 ==="
bash "$PKG/verify/leak_scan.sh"

echo
echo "=== [3b] 附加检查：密钥样式（不写入任何具体值）==="
grep -rniE "api[_-]?key|secret|passwd|password|bearer |private[_-]?key" "$PKG" \
  --exclude-dir=__pycache__ --exclude=leak_scan_after_sanitize.txt \
  --exclude=run_all_checks.sh | head -10 || echo "(0 hits)"

echo
echo "=== [4] 重建清单 + zip ==="
bash "$PKG/verify/finalize_package.sh"

echo
echo "=== [5] 交付校验 ==="
bash "$PKG/verify/verify_zip.sh"

echo
echo "=== [6] 终检：包内不得有日志 / 核查报告 ==="
leftover=$(find "$PKG" \( -name '*.log' -o -name 'leak_scan_after_sanitize.txt' -o -name 'local_vs_package_diff.txt' \) -print)
if [ -z "$leftover" ]; then echo "OK: 0 个日志/核查报告在包内"; else echo "WARN:"; echo "$leftover"; fi
