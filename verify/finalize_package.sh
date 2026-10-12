#!/usr/bin/env bash
# 重建 sha256 清单并在包外生成 zip（路径全部相对脚本位置，无本机绝对路径）
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG="$(cd "$HERE/.." && pwd)"
NAME="$(basename "$PKG")"
ZIP="$(dirname "$PKG")/$NAME.zip"

find "$PKG" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$PKG" -name '*.pyc' -delete 2>/dev/null || true

cd "$PKG"
rm -f MANIFEST.sha256
find . -type f | sed 's|^\./||' | sort | while read -r f; do
  printf '%s  %s\n' "$(sha256sum "$f" | cut -d' ' -f1)" "$f" >> MANIFEST.sha256
done
echo "manifest entries: $(wc -l < MANIFEST.sha256)"

rm -f "$ZIP"
cd "$(dirname "$PKG")"
zip -qr "$NAME.zip" "$NAME" -x '*__pycache__*' '*.pyc'
ls -la "$NAME.zip"
unzip -l "$NAME.zip" | tail -3
