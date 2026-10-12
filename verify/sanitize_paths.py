#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""脱敏：把包内文本文件里的本机绝对路径替换为占位符。

只替换路径前缀，不改任何数值、消息与行序；被改动的 .log 首行插入脱敏标注。
用户名/家目录通过 expanduser 获取，脚本本身不含任何真实路径字符串。

用法： python sanitize_paths.py <package_root>
"""
import io
import os
import sys

ROOT = os.path.abspath(sys.argv[1]).replace("\\", "/")
assert os.path.isfile(os.path.join(ROOT, "README.md")), "package root not recognised"
PKG_NAME = os.path.basename(ROOT.rstrip("/"))

HOME = os.path.expanduser("~").replace("\\", "/")
HOME_WIN = HOME.replace("/", "\\")
WORKSPACE = os.path.dirname(ROOT)
MCP_SRC = os.path.join(os.path.dirname(HOME), "iPolloWork", "gsas2-mcp").replace("\\", "/")
HERMES_HOME_MARK = "AppData/Local/Hermes Agent CN Desktop/data/hermes-home"


def variants(path):
    """同一路径的三种写法：正斜杠、原生反斜杠、JSON 双反斜杠。"""
    fwd = path.replace("\\", "/")
    win = fwd.replace("/", "\\")
    return [win.replace("\\", "\\\\"), win, fwd]


TARGETS = [
    (ROOT, "<PACKAGE>"),
    (WORKSPACE, "<WORKSPACE>"),
    (MCP_SRC, "<GSAS2_MCP>"),
    (os.path.join(HOME, HERMES_HOME_MARK), "<HERMES_HOME>"),
    (HOME, "<USER_HOME>"),
]

REPLACEMENTS = []
for path, label in TARGETS:                       # 长路径优先，避免被短前缀截断
    for variant in variants(path):
        REPLACEMENTS.append((variant, label))
REPLACEMENTS.sort(key=lambda kv: len(kv[0]), reverse=True)

TEXT_EXT = {".log", ".txt", ".md", ".sh", ".py", ".json", ".yaml", ".yml", ".html",
            ".patch", ".csv", ".toml", ".cfg", ".ini"}
SKIP_FILES = {"sanitize_paths.py"}                 # 本脚本自身含占位符与通用词，跳过

HEADER = ("# [脱敏] 本文件中的本机绝对路径已替换为占位符"
          "（<PACKAGE>/<WORKSPACE>/<GSAS2_MCP>/<HERMES_HOME>/<USER_HOME>）；"
          "数值、消息与行序未做任何修改。\n")

changed = []
for dirpath, dirnames, filenames in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if d != "__pycache__"]
    for fn in filenames:
        if fn in SKIP_FILES or os.path.splitext(fn)[1].lower() not in TEXT_EXT:
            continue
        p = os.path.join(dirpath, fn)
        try:
            with io.open(p, "r", encoding="utf-8", newline="") as fh:
                text = fh.read()
        except (UnicodeDecodeError, OSError):
            continue
        orig = text
        for old, new in REPLACEMENTS:
            if old in text:
                text = text.replace(old, new)
        if text != orig:
            if fn.lower().endswith(".log") and not text.startswith("# [脱敏]"):
                text = HEADER + text
            with io.open(p, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
            changed.append(os.path.relpath(p, ROOT).replace("\\", "/"))

print("sanitized %d file(s):" % len(changed))
for c in sorted(changed):
    print("  -", c)
