# verify/ — 复现与核查（本目录只放可复现的东西）

本目录**不含运行日志、不含内部核查报告**（按作者要求：日志不对外）。只保留：

| 文件 | 用途 |
|---|---|
| `mcp_tools_live.txt` | MCP 工具清单（19 个工具名，活体导出） |
| `rerun_converged_max_cycles.py` | 复现"两阶段收敛到 wR 12.87 %"：直接用 MCP 工具函数驱动 GSAS-II 官方 PbSO₄ 样例 |
| `probe_gpx_state.py` | 读回任意 `.gpx`，打印残差与 `Controls` 关键项（含 `max cyc`） |
| `e2e_out_after_fix/`、`e2e_out_converged/` | 上述运行留下的**结果文件**（`pbso4_results*.json` + 拟合图 PNG），公开样例数据 |
| `sanitize_paths.py` | 把包内文本里的本机绝对路径替换为占位符（用户名用 `expanduser` 推导，脚本内无真实路径） |
| `backup_local_skill.py` | 把本机 skill 的"改动前原件"备份到**包外**（`../_skill_backups_<日期>/`） |
| `diff_local_vs_package.sh` | 核对"本机全量"与"包内脱敏版"的哈希差异，确认本机未被改动 |
| `leak_scan.sh` | 按**包外**关键词表逐组扫描包内文本，确认无课题组数据/测量值/项目名/用户名路径 |
| `move_logs_outside.sh` | 把运行日志与核查报告移出包外（保持本包"只有可复现内容"） |
| `run_all_checks.sh` | 一条命令串起：备份 → 本机/包内比对 → 脱敏核查 → 密钥样式检查 → 重建清单与 zip → 交付校验 |
| `finalize_package.sh` / `verify_zip.sh` / `make_patch.sh` | 重建 sha256 清单与 zip / 解压回比校验 / 重新生成 MCP 修复补丁 |

## 日志与报告放在哪

运行日志、脱敏核查报告、本机/包内差异报告都写在**包外**：

```
<WORKSPACE>/
├── XRD-Rietveld-Skill-MCP-2026-10-12/     ← 本包（对外）
├── _evidence_20261012/                    ← 运行日志 + 核查报告（本机留存，不发布）
│   ├── mcp_e2e_pbso4_run.log              修前失败原文
│   ├── mcp_e2e_pbso4_AFTER_FIX.log        修后 12/12 步
│   ├── mcp_e2e_converged.log              两阶段收敛过程
│   ├── probe_gpx_state.log                读回 .gpx 的客观状态
│   ├── leak_scan_after_sanitize.txt       脱敏核查结果
│   └── local_vs_package_diff.txt          本机 vs 包内 逐文件哈希
├── _sanitize_keywords.txt                 ← 脱敏核查关键词表（刻意不入包）
└── _skill_backups_20261012/               ← 本机 skill 的改动前原件
```

想重新生成上面任何一项：直接跑对应脚本（`leak_scan.sh`、`diff_local_vs_package.sh`、`backup_local_skill.py`、`rerun_converged_max_cycles.py`）。
脚本里没有任何真实路径，路径由脚本自身位置与 `~` 推导。

## 一次性全查

```bash
bash verify/run_all_checks.sh
```
