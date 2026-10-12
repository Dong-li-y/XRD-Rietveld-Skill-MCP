# GSAS2-MCP

用于粉末 X 射线衍射（XRD）数据 Rietveld 精修的 MCP（Model Context Protocol）服务器。
封装 GSAS-II 的脚本化 API（`GSASIIscriptable`），让 AI 代理可以直接创建项目、导入
衍射数据与结构模型、设置精修参数、执行 Rietveld 精修并提取结果。

## 环境要求

| 组件 | 说明 |
| --- | --- |
| Python | 建议 3.10–3.12（GSAS-II 官方支持的版本） |
| GSAS-II | 源码目录（本机位于 `D:\app\xrd\GSAS2-MCP`，git 检出） |
| MCP SDK | `pip install mcp`（本机 `D:\app\xrd` 环境已装 2.0.0） |

服务器通过环境变量 `GSAS2_MCP_PATH` 定位 GSAS-II 源码树（默认
`D:\app\xrd\GSAS2-MCP`），并在导入前调用 `GSASIIpath.SetBinaryPath()` 配置二进制
路径；`GSASII_HEADLESS=true` 与 `MPLBACKEND=Agg` 保证无 GUI 运行。

## 配置（iPolloWork / OpenCode）

已在工作区 `opencode.jsonc` 中注册：

```jsonc
{
  "mcp": {
    "gsas2": {
      "type": "local",
      "command": ["D:\\app\\xrd\\python.exe", "-m", "gsas2_mcp_server"],
      "cwd": "<USER_HOME>\\iPolloWork\\gsas2-mcp",
      "environment": {
        "GSAS2_MCP_PATH": "D:\\app\\xrd\\GSAS2-MCP",
        "GSASII_HEADLESS": "true",
        "MPLBACKEND": "Agg"
      },
      "enabled": true
    }
  }
}
```

重启会话后 `gsas2` 服务器的工具即作为 MCP 工具可用。

## 工具清单（19 个）

**项目管理**
- `create_project(name)` — 新建 GSAS-II 项目（.gpx）
- `load_project(path)` — 加载已有项目
- `save_project(path?)` — 保存项目
- `project_summary()` — 项目概览（直方图、相、可精修变量）

**数据导入**
- `inspect_data_file(datafile)` — 解析数据文件并报告格式、点数、2θ 范围（无需项目）
- `add_powder_histogram(datafile, iparams?, fmthint?)` — 添加粉末衍射数据（无内嵌仪器参数的格式需提供 `.prm`）
- `add_phase(cif_file, phase_name?, histograms?)` — 从 CIF 添加相并关联直方图
- `list_histograms()` / `list_phases()` — 查看当前状态

**参数设置**
- `set_refinement(params_json)` — 通用精修配方（`set`/`clear`/`once` + 可选 `histograms`/`phases`）
- `set_histogram_params(histogram?, params_json)` — 直方图级：背景、限制、仪器 U/V/W、样品参数
- `set_phase_params(phase?, params_json)` — 相级：Cell、Atoms、HAP（Scale/Size/Mustrain）
- `get_variables()` / `hold_variable(var)` / `free_variable(var)` — 查看与固定/释放变量

**精修与结果**
- `refine()` — 执行 Rietveld 精修（GSAS-II 内部迭代至收敛）
- `get_results()` — 残差（wR/R/GOF）、晶胞参数（含 esd）、原子坐标与 Uiso
- `export_results(path?)` — 导出 JSON 结果
- `export_plot(path?)` — 导出拟合图 PNG（观察/计算/残差）

## 使用示例（提示词）

```
1. 用 gsas2 的 create_project 创建项目 demo
2. 用 add_powder_histogram 导入 sample.xye，iparams 用 my_lab.prm
3. 用 add_phase 导入结构 CIF
4. 用 set_refinement 设置 {"set": {"Background": {"no. coeffs": 3, "refine": true},
   "Sample Parameters": ["Scale"], "Cell": true}}
5. 用 refine 精修，然后用 get_results 查看 Rwp 和晶胞参数
```

## 分层精修建议（Rietveld 常规顺序）

1. 精修背景（多项式系数）+ 比例因子
2. 加入仪器峰形参数 U/V/W、样品位移
3. 加入晶胞参数
4. 加入原子坐标（X/Y/Z）与各向同性温度因子（Uiso），必要时加约束
5. 检查 `get_results` 的 GOF 与 Rwp 趋势，使用 `hold_variable`/`free_variable` 控制收敛

## 测试

```powershell
# 端到端 Rietveld 精修（使用 GSAS-II 自带的 PbSO4 示例数据）
D:\app\xrd\python.exe examples\e2e_pbso4.py
```

输出：`.gpx` 项目、`pbso4_results.json`（残差/晶胞/原子）、`pbso4_plot.png`（拟合图）。

## 目录结构

```
gsas2-mcp/
├── gsas2_mcp_server/     # MCP 服务器包
│   ├── __init__.py
│   ├── __main__.py       # python -m gsas2_mcp_server 入口
│   └── server.py         # 服务器实现（19 个工具）
├── examples/
│   └── e2e_pbso4.py      # 端到端测试脚本
└── README.md
```
