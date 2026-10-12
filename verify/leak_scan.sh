#!/usr/bin/env bash
# 脱敏核查：按本地关键词表（包外）逐组扫描包内文本，报告命中情况。
# 关键词表默认位置：与包同级目录下的 _sanitize_keywords.txt（不随包发布）
# 注意：报告本身不写任何本机绝对路径，也不参与扫描（否则会自引）。
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG="$(cd "$HERE/.." && pwd)"
KEYWORDS="${LEAK_KEYWORDS:-$(dirname "$PKG")/_sanitize_keywords.txt}"
# 核查报告默认写到包外（作者要求：日志/内部报告不随包发布）
OUT="${LEAK_REPORT:-$(dirname "$PKG")/_evidence_20261012/leak_scan_after_sanitize.txt}"
mkdir -p "$(dirname "$OUT")"
SELF="$(basename "$OUT")"
USER_NAME="$(basename "$(cd ~ && pwd)")"

if [ ! -f "$KEYWORDS" ]; then
  echo "关键词表不存在：$KEYWORDS" >&2
  echo "（该表刻意放在包外；缺表时本脚本只做用户名路径检查）" >&2
fi

scoped_grep() {  # scoped_grep <ERE>   → 命中行（把包路径前缀换成 <PACKAGE>）
  grep -rniE "$1" --exclude-dir=__pycache__ --exclude="$SELF" "$PKG" 2>/dev/null \
    | sed "s|$PKG/|<PACKAGE>/|g"
}

group() {  # group <N> → 第 N 组关键词（# 开头为注释）
  [ -f "$KEYWORDS" ] || return 1
  awk -F'|' -v want="$1" '
    /^[[:space:]]*#/ {next}
    /^[[:space:]]*$/ {next}
    {n++; if (n==want) {print; exit}}' "$KEYWORDS"
}

{
  echo "脱敏核查报告 — $(date '+%Y-%m-%d %H:%M:%S %z')"
  echo "包目录：<PACKAGE>（本报告刻意不写本机绝对路径）"
  echo "关键词表：<包外文件，与包同级，不随包发布>"
  echo

  labels=("课题组标识（样品/配比/相名/项目名）" \
          "课题组测量与精修数值" \
          "项目目录名 / 报告文件名" \
          "第三方作者个人路径" \
          "个人姓名 / 原机构署名（应为空，署名已改为机构）")
  i=1
  failed=0
  for label in "${labels[@]}"; do
    pat="$(group "$i" || true)"
    echo "## [$i] $label"
    if [ -z "$pat" ]; then
      echo "SKIP: 关键词表缺失"
    else
      hits="$(scoped_grep "$pat")"
      n=$(printf '%s' "$hits" | grep -c . || true)
      if [ "$n" -eq 0 ]; then
        echo "PASS: 0 hits"
      else
        failed=$((failed+1))
        echo "FAIL: $n hit(s)（显示前 20 行）"
        printf '%s\n' "$hits" | head -20
      fi
    fi
    echo
    i=$((i+1))
  done

  echo "## [6] 本机用户名路径（Users\\<user> / Users/<user>）"
  hits="$(grep -rnF -e "Users\\$USER_NAME" -e "Users/$USER_NAME" \
            --exclude-dir=__pycache__ --exclude="$SELF" "$PKG" 2>/dev/null \
          | sed "s|$PKG/|<PACKAGE>/|g")"
  n=$(printf '%s' "$hits" | grep -c . || true)
  if [ "$n" -eq 0 ]; then echo "PASS: 0 hits"; else
    failed=$((failed+1)); echo "FAIL: $n hit(s)"; printf '%s\n' "$hits" | head -20
  fi
  echo

  echo "## 结论"
  if [ "$failed" -eq 0 ]; then
    echo "ALL PASS —— 包内未发现课题组数据标识、测量值、项目名或本机用户名路径。"
  else
    echo "存在 $failed 组未通过，请修复后重跑。"
  fi
  echo
  echo "说明：包内保留的数值仅来自 GSAS-II 官方 PbSO4 样例（公开数据）与通用数学常数（如 2.3548、5.5452）。"
} > "$OUT" 2>&1

grep -E "^(## |PASS|FAIL|ALL PASS|存在|SKIP)" "$OUT" || true
echo "报告（包外，不随包发布）：$OUT"
