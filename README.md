# XRD Rietveld 精修 · Skill + MCP 宣传包

**版本**：2026-10-12　|　**打包人**：中国科学院大学
**内容**：4 个 GSAS-II Rietveld 精修 Skill + 1 个 GSAS-II MCP 服务器（19 工具）
**用途**：科研协作分享 / 公众号与组内宣传 / GitHub Release 素材

> **脱敏声明（2026-10-12）**：本包**不含任何本课题组未公开数据**。
> 样品来源与配比、样品编号、相名与结论、全部测量/精修数值、结构来源文献、项目目录名已全部移除或改写为方法描述；
> 验证所用的公开数据只来自 GSAS-II 官方 PbSO₄ 示例（可自由引用）；本包只随包**结果文件与复现脚本**，
> 运行日志与内部核查报告保留在作者本机、不随包发布。
> 逐项清单、核查命令与扫描结果见 **`docs/06_脱敏说明.md`**。

---

## 一句话

> 把 GSAS-II 的 Rietveld 精修交给 AI 代理：**Skill 管"怎么修"（流程、判据、口径），MCP 管"能动手"（19 个可调用工具）**，
> 精修 → 判定 → 画图严格分离，每一步都留下可复核的数字与哈希。

---

## 1. 这个包解决什么问题

粉末 XRD 精修的门槛不在"会不会点 GSAS-II"，而在**同类问题反复踩坑**：

| 常见翻车 | 本包的对应设计 |
|---|---|
| 第二相分数没释放，精修"收敛"了但第二相被冻结在初值 | Skill 强制 `set_HAP_refinements({'Scale': True})` 检查点 |
| 直方图标度与相分数同时放开 → SVD 丢参数 | 阶段 01 用直方图标度，阶段 02 起固定标度、释放相分数 |
| 放开 Zero 把宿主晶胞带跑（Zero 与晶胞互相替代） | 强制"零偏移分支"作为比较口径，Zero 场景单列 |
| wR 一直卡在 ~30% 下不来 | 记录 GSAS-II 的 U/V/W 是**方差**参数（FWHM = 2.3548·σ），按 FWHM² 灌入会宽 2.35 倍 |
| 幻影相"改善"拟合，实际是把邻峰吸走 | 线位缺失检验 + 晶胞自走检验 + Rf² 三条件判否 |
| 结果无法复现、多个后台进程互相覆盖输出 | 每样品独立输出树 + 阶段摘要写入代码版本特征 + `.lst` 回读校验 |

---

## 2. 包内容

```
XRD-Rietveld-Skill-MCP-2026-10-12/
├── README.md                       ← 本文件（宣传主页）
├── docs/
│   ├── 01_安装与配置.md             3 步接入 Hermes / Claude Code / Codex / OpenCode
│   ├── 02_工具速查表.md             4 Skill 路由表 + 19 个 MCP 工具参数速查
│   ├── 03_实测案例.md               匿名化方法案例 + MCP 端到端验证（全部为公开样例数据）
│   ├── 04_宣传文案.md               公众号 / 朋友圈 / GitHub 三版现成文案
│   ├── 05_修复记录_MCP_refine.md    打包自检发现的 MCP 缺陷：根因、修复、修前/修后对比
│   └── 06_脱敏说明.md               移除了什么、怎么核查、还剩什么（分享前必读）
├── skills/xrd-rietveld/            4 个 Skill（**脱敏副本**：与打包机本地安装不再逐字节一致，
│                                          本地版本仍保留完整案例数值供自用；差异见 docs/06）
│   ├── gsas-ii-rietveld-refinement/      单相 + 顺序/原位精修（主力，含实测坑库）
│   ├── gsas-ii-multiphase-refinement/    多相 QPA / 相分数（Beta）
│   ├── rietveld-plotting/                出版级精修图（只读 GPX，不回改参数）
│   └── gsas2-xrd-refinement/             GSAS-II 全自动单/多相脚本化流程
├── mcp/gsas2_mcp_server/           MCP 服务器（server.py + 入口 + 修复前原件备份）
├── mcp/examples/e2e_pbso4.py       端到端自检脚本（PbSO4 官方样例）
├── mcp/patches/                    refine 缺陷修复补丁（可直接 review 的 diff）
├── mcp/config/                     可直接粘贴的 MCP 注册片段
├── verify/                         复现脚本 + 公开样例结果（工具清单、结果 JSON、拟合图；
│                                          运行日志与核查报告按要求不随包发布，见 verify/README.md）
├── licences/                       上游许可证（MIT，Li KangYing）
└── 宣传卡.html                     一页式宣传图（浏览器打开，可直接截图）
```

---

## 3. 四个 Skill 分别是什么

| Skill | 定位 | 关键机制 | 本次打包时的真实使用统计 |
|---|---|---|---|
| `gsas-ii-rietveld-refinement` | 单相精修 + 顺序/原位序列 | 强制请求分类 → 分阶段释放 → 结构化审查 → 原子归档（含**实测坑库**，脱敏版） | 被加载 **9 次**，最近一次 **2026-10-12**，被修订 15 版 |
| `gsas2-xrd-refinement` | 全自动脚本流：一条命令跑完单相/多相 | 参数组逐级释放 + 联合递增加参 + 阶段失败自动回退 + 产物 CSV/JSON 齐全 | 被加载 1 次（2026-09-22） |
| `gsas-ii-multiphase-refinement` | 多相精修与定量相分析 QPA（**Beta**） | 12 条强制 QPA 规则：相集状态声明、协方差质量分数、简并规避、可重复性重跑 | 本地尚未加载过（Beta，未用于产出） |
| `rietveld-plotting` | 只读画图：出版级单相/多相/变温/原位图 | GPX 哈希进出一致、Bragg 行按物相分色、wt% 只取 GSAS-II 协方差质量分数 | 本地尚未加载过 |

> 统计来自 Hermes 本地 `skills/.usage.json`，不是估计值。**未使用过的两个 Skill 已如实标注**——它们随包分享，但不作为"已产出成果"宣传。

---

## 4. MCP：19 个工具，AI 代理真正能动手

`python -m gsas2_mcp_server`，纯标准输入输出，无 GUI（`GSASII_HEADLESS=true` + `MPLBACKEND=Agg`）。
本地实测 **TOOL_COUNT = 19**（`verify/mcp_tools_live.txt`）。

| 分组 | 工具 |
|---|---|
| 项目管理 | `create_project` `load_project` `save_project` `project_summary` |
| 数据与结构 | `inspect_data_file` `add_powder_histogram` `add_phase` `list_histograms` `list_phases` |
| 参数设置 | `set_refinement` `set_histogram_params` `set_phase_params` `get_variables` `hold_variable` `free_variable` |
| 精修与结果 | `refine` `get_results` `export_results` `export_plot` |

设计要点：精修配方用 **JSON 字符串**传入（模型不会漏参数）、变量可逐个 `hold/free`（收敛可控）、结果与图像分别导出（数字和图上都留证据）。

---

## 5. 实测战绩（可复核）

### 案例 A：匿名化实战流程（数据未公开，只保留方法）

**问题类型**：一张粉末 XRD 图 + 已定宿主结构，另有 1–2 个候选第二相结构模型，需要判断"候选相是否真的存在"，
而不是"哪个模型 wR 更低"。做法是把判据拆成三条**互相独立、任一条即可否证**的检验：

1. **线位缺失检验**：扣掉宿主能解释的反射后，候选相**必须**出现它自己的两条最强反射；最强线落在本底上 → 否证。
   两条强线若属不同晶面族，"取向择优"不能当借口（取向能压一族，压不了两族）。
2. **晶胞自走检验**：给候选相一个自由晶胞。真结构收敛在参考值附近；**幻影相**会被邻峰吸走 —— 晶胞严重偏离
   参考值、esd 失去约束，比 wR 更早暴露问题。
3. **逐阶段胜负检验**：同图、同峰形参数下跑同一套阶段（推荐 9 阶段，见 `docs/02`），比较"零偏移分支"的胜负，
   并按**参数更少优先**取舍。

**必须写进报告的边界**：粉末 XRD 对散射因子接近的原子不可分辨（只能支持"该结构族存在"，给不出确切化学计量）；
无法归属的残余峰单列为未识别杂相；被否方案连同否证理由留档，避免重复试。

> 这套流程的价值不是"跑出漂亮数字"，而是**允许被数据否证**。案例 A 的样品来源、配比、相名、全部测量值
> 与结构来源文献属未公开课题数据，**已从本包移除**（移除清单与核查方法见 `docs/06_脱敏说明.md`）。

### 案例 B：MCP 服务器端到端自检（打包时实跑，并据此修复了一个缺陷）

按"先跑自检再说能用"的原则执行 `mcp/examples/e2e_pbso4.py`，**第一次运行在第 8 步 `refine` 直接失败**：

```
***** Refinement successful *****        ← GSAS-II 自己说成功
[FAIL] refine: RuntimeError: Refinement failed (GSAS-II returned no result).   ← 包装层判成失败
```

根因两条，都已在 `docs/05` 写清：本版本 `GSASIIscriptable.Project.refine()` **没有 return 语句、恒返回 `None`**，
包装层却把 `None` 当失败信号（→ 该工具在任何情况下都抛错）；同时 GSAS-II 默认只迭代 **3 轮**，
精修实际停在 wR 63.80 %、shift/esd 55.1 却毫无提示。

修复后（改动可 review：`mcp/patches/refine-return-value-fix.patch`，原件已备份）：

| 项 | 修前 | 修后 |
|---|---|---|
| 自检 12 步 | 第 8 步中断 | **12/12 `[OK]`，exit = 0** |
| `refine` 返回 | 异常 | residuals + `max_shift_over_esd` + 未收敛警告 |
| 迭代控制 | 固定 3 轮 | `refine(max_cycles=12)` |
| 收敛 wR（PbSO₄ 样例） | 63.80 %（未收敛） | **12.865 %**（GOF 2.6876，shift/esd 0.486） |

收敛后的晶胞：a = 8.481861(138)、b = 5.399835(90)、c = 6.961628(116) Å（与 PbSO₄ 文献值一致），
拟合图 `verify/e2e_out_converged/pbso4_plot_converged.png`。

**验证怎么做**（全部使用 GSAS-II 自带 PbSO₄ 样例，不含私有数据；**运行日志不随包发布**，本机留存于 `_evidence_20261012/`）：
`verify/mcp_tools_live.txt`（19 工具清单）、`verify/rerun_converged_max_cycles.py` + `verify/probe_gpx_state.py`（一键复现收敛过程与 GPX 状态）、
`verify/e2e_out_converged/pbso4_results_converged.json` + `pbso4_plot_converged.png`（公开样例的最终结果与拟合图）、
`verify/run_all_checks.sh`（串起备份、本机/包内比对、脱敏核查、密钥检查、重建与交付校验）。

---

## 6. 快速开始

```bash
# 1) 放置 Skill（Hermes：放进 skills/ 目录；Claude Code / Codex：放进各自 skills 目录）
cp -r skills/xrd-rietveld "$HERMES_HOME/skills/"

# 2) 注册 MCP：把 mcp/config/hermes-mcp-config-snippet.yaml 里的 gsas2 段并入 config.yaml
#    （其他客户端：统一用 command / args / env 三段，见 docs/01）

# 3) 新开会话，让 MCP 工具加载，然后直接下任务
#    "导入 sample.xye 和 phase.cif，按标准阶段跑 Rietveld，报告 Rwp/晶胞/相分数，并做残差峰审计"
```

详细步骤、环境要求、排错表见 **`docs/01_安装与配置.md`**。

---

## 7. 设计原则（也是分享时最值得说的部分）

1. **精修 / 判定 / 画图三权分立**：画图 Skill 只读 `.gpx` 且校验哈希进出一致，永不回改参数。
2. **每个数字有出处**：报告数字从磁盘 JSON 读入，晶胞带 GPX 协方差 esd，文件带 sha256。
3. **口径先声明**：仪器轮廓是否标定、Zero 分支、相集状态（verified / provisional / unknown）都必须先写清，再谈结论。
4. **允许被数据否证**：模型失败、相分数塌缩、被否方案与理由全部保留记录，不静默改写。
5. **停规则优于硬修**：出现未解释的强残差峰、相关度 ≥95%、SVD 失败、方向敏感性未解时，停在"待科学复核"，不给出漂亮但假的结论。

---

## 8. 局限与免责

- 局部安装实测环境：Windows 11 + GSAS-II（`D:\app\xrd\GSAS-II`）+ 专用解释器 `D:\app\xrd\python.exe`。换环境需重跑自检。
- **仪器参数为默认示例**：包内 Skill 的仪器示例（STOE WinXPOW `.asc`、Cu Kα 波长与 `I(L2)/I(L1)`、扫描栅格、
  `I_MONOCHRO`/`FILTER`）刻意保留为**打包机的默认条件**，用于说明解析与轮廓坑；换仪器请按自己文件头改写
  （见 `pitfalls-observed.md` §8 的"更改提示"）。
- **本包范围为 XRD 精修本身**：不含材料数据库 / Materials Project / matDB 等材料侧内容（按要求暂不纳入）。
- **本包不含运行日志与内部核查报告**（按作者要求不对外）：包内 `verify/` 只放复现脚本与公开样例的结果文件；
  日志、脱敏核查报告、本机/包内差异报告都在作者本机的 `_evidence_20261012/`，可随时用脚本重新生成（见 `verify/README.md`）。
- `skills/` 为**脱敏副本**，与打包机上的本地安装不再一致（本地版保留完整案例数值自用）；如需同步见 `docs/06`。
- `gsas-ii-multiphase-refinement` 为 **Beta**：适合已声明相集的科研流程，不替代专家相鉴定与独立验证。
- 包内部分 Skill 文档引用的辅助脚本（如 `scripts/run_multiphase_qpa.py`、`scripts/make_rietveld_plot.py`）**不在本机安装中**，属上游发行包内容；见 `docs/01` 的"已知缺口"。
- 精修结果的可信度取决于原始数据、仪器标定与相模型；本包不改变这一点。

---

## 9. 来源与致谢 / 许可

- `gsas2-xrd-refinement`：来自 GitHub 仓库 `kk154/XRD_Rietveld_skills`，**MIT License, Copyright (c) 2026 Li KangYing**，许可证原文随包（`licences/`）。
- `gsas-ii-rietveld-refinement`、`gsas-ii-multiphase-refinement`、`rietveld-plotting`：本地安装版本，**上游出处与许可证待确认** — `[AUTHOR TODO]`：分享前请补齐来源与许可（工作区 `_refs_gsas_skill/README.md` 中提及过 R3ze959 相关仓库，本地未找到对应 LICENSE）。
- GSAS-II 本体：Toby & Von Dreele, *J. Appl. Cryst.* **46**, 544 (2013)，许可与引用请遵循其官方说明。

---

## 10. [AUTHOR TODO] 分享前请确认

1. 三个 Skill 的上游出处与许可证（见第 9 节）。
2. 署名：已改为机构（`中国科学院大学`），包内无个人姓名与原机构名。
3. 日志处理：已按你的要求**不对外** —— 运行日志与内部核查报告已移出包外（`_evidence_20261012/`），包内只留复现脚本与结果文件。
4. MCP 的 `GSAS2_MCP_PATH` / 解释器路径、以及 Skill 里的仪器示例（STOE/Cu Kα/栅格）在他人机器上需替换为本地值。
5. 若要发布到 GitHub：用本目录为仓库根即可（已无运行产物与本地路径；`docs/06` 附脱敏核查命令，可在 CI 里跑一遍）。
