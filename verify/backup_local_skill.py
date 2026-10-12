#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给本机 skill 文件补一份"改动前"备份（按"改前先复制原件"的惯例）。

只读本机安装目录、只写**包外**备份目录，绝不修改任何本机 skill 内容。
备份落地位置：与本包同级的 _skill_backups_<日期>/（即 dirname(PACKAGE) 下），不进包。
脚本本身不含任何真实用户名/绝对路径（用 expanduser + 环境变量推导）。
"""
import io
import os
import shutil
import sys

HOME = os.path.expanduser("~")
HERMES_HOME = os.environ.get("HERMES_HOME") or os.path.join(
    HOME, "AppData", "Local", "Hermes Agent CN Desktop", "data", "hermes-home")
HERMES_HOME = os.path.normpath(HERMES_HOME)

LIVE = os.path.join(HERMES_HOME, "skills", "xrd-rietveld", "gsas-ii-rietveld-refinement",
                    "references", "pitfalls-observed.md")

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))      # <PACKAGE>
BACKUP_DIR = os.path.join(os.path.dirname(PKG), "_skill_backups_20261012")  # 包外
MARKER = "\n## 9. MCP wrapper layer"

if not os.path.isfile(LIVE):
    print("LIVE FILE NOT FOUND:", LIVE)
    sys.exit(1)

with io.open(LIVE, "r", encoding="utf-8", newline="") as fh:
    text = fh.read()

os.makedirs(BACKUP_DIR, exist_ok=True)
p_cur = os.path.join(BACKUP_DIR, "pitfalls-observed.md.current-20261012")
shutil.copy2(LIVE, p_cur)
print("local file untouched:", LIVE)
print("bytes now          :", len(text.encode("utf-8")))
print("backup (current)   :", os.path.basename(p_cur))

if MARKER in text:
    pre = text.split(MARKER)[0]
    p_pre = os.path.join(BACKUP_DIR, "pitfalls-observed.md.pre-section9-20261012")
    with io.open(p_pre, "w", encoding="utf-8", newline="") as fh:
        fh.write(pre)
    print("backup (pre §9)    :", os.path.basename(p_pre), "-", len(pre.encode("utf-8")), "bytes")
else:
    print("no section 9 found — pre-§9 backup skipped (already absent)")

assert not BACKUP_DIR.startswith(PKG), "backup dir must live OUTSIDE the package"
print("backup dir is OUTSIDE the package:", os.path.relpath(BACKUP_DIR, PKG))
