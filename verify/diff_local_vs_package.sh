#!/usr/bin/env bash
# 核对"本机安装（全量）"与"包内（脱敏版）"的差异，说明脱敏没有动本机内容。
# 关键词一律不写在本脚本里（由 leak_scan.sh 读包外关键词表完成），避免脚本自泄。
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG="$(cd "$HERE/.." && pwd)"
HH_ROOT="${HERMES_HOME:-$HOME/AppData/Local/Hermes Agent CN Desktop/data/hermes-home}"
case "$HH_ROOT" in *\\*) HH_ROOT="$(cygpath -u "$HH_ROOT" 2>/dev/null || echo "$HH_ROOT")";; esac
HH="$HH_ROOT/skills/xrd-rietveld"
# 报告默认写到包外（作者要求：内部核查报告不随包发布）
OUT="${DIFF_REPORT:-$(dirname "$PKG")/_evidence_20261012/local_vs_package_diff.txt}"
mkdir -p "$(dirname "$OUT")"
PIT_REL="gsas-ii-rietveld-refinement/references/pitfalls-observed.md"

{
  echo "本机安装 vs 包内 skills 差异核对 — $(date '+%Y-%m-%d %H:%M:%S %z')"
  echo "本机：<HERMES_HOME>/skills/xrd-rietveld"
  echo "包内：<PACKAGE>/skills/xrd-rietveld"
  echo
  echo "## 逐文件哈希"
  cd "$PKG/skills/xrd-rietveld"
  find . -type f | sed 's|^\./||' | sort | while read -r f; do
    a=$(sha256sum "$f" 2>/dev/null | cut -d' ' -f1)
    b=$(sha256sum "$HH/$f" 2>/dev/null | cut -d' ' -f1)
    if [ -z "$b" ]; then printf 'MISSING_LOCAL  %s\n' "$f"
    elif [ "$a" = "$b" ]; then printf 'SAME  %s\n' "$f"
    else printf 'DIFF  %s\n' "$f"; fi
  done
  echo
  echo "## 差异性质"
  echo "- DIFF 属预期：包内为脱敏版（真实案例数值 / 项目标识已移除），本机保留全量供自用。"
  echo "- SAME 表示该文件两边一致（未涉及脱敏）。"
  echo "- MISSING_LOCAL 说明本机没有该文件（不应出现）。"
  lsz=$(wc -c < "$HH/$PIT_REL" 2>/dev/null || echo 0)
  psz=$(wc -c < "$PKG/skills/xrd-rietveld/$PIT_REL" 2>/dev/null || echo 0)
  echo
  echo "## 本机完整性（与本包外的备份逐字节比对）"
  BK="$(dirname "$PKG")/_skill_backups_20261012"
  if [ -f "$BK/pitfalls-observed.md.current-20261012" ]; then
    if cmp -s "$HH/$PIT_REL" "$BK/pitfalls-observed.md.current-20261012"; then
      echo "OK：本机 pitfalls-observed.md 与包外备份逐字节相同 → 本机本次未被改动。"
    else
      echo "WARN：本机文件与备份不一致（可能备份后又改过本机文件，请人工确认）。"
    fi
    if [ -f "$BK/pitfalls-observed.md.pre-section9-20261012" ]; then
      a=$(wc -c < "$BK/pitfalls-observed.md.pre-section9-20261012")
      b=$(wc -c < "$BK/pitfalls-observed.md.current-20261012")
      echo "本机文件相对'§9 之前'的增量：$((b - a)) bytes（= 追加的 §9 MCP 包装层一节）"
    fi
  else
    echo "SKIP：包外备份不存在（$BK），无法做逐字节比对。"
  fi
  echo
  echo "## 包内为脱敏版（相对本机）"
  echo "包内 pitfalls-observed.md：$psz bytes（已移除案例数值与项目标识，另加'仪器更改提示'）"
  echo "本机 pitfalls-observed.md：$lsz bytes（保留全量，含真实案例数值，供自用）"
} > "$OUT" 2>&1

echo "SAME/DIFF/MISSING 统计："
grep -c '^SAME' "$OUT" 2>/dev/null | sed 's/^/  SAME    /'
grep -c '^DIFF' "$OUT" 2>/dev/null | sed 's/^/  DIFF    /'
grep -c '^MISSING_LOCAL' "$OUT" 2>/dev/null | sed 's/^/  MISSING /'
grep -E "^(OK|WARN|本机 pitfalls|包内 pitfalls)" "$OUT" || true
echo "报告（包外，不随包发布）：$OUT"
