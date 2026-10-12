# 05 修复记录：MCP `refine` 工具恒报失败（2026-10-12 定位并修复）

打包时按"先跑自检再说能用"的原则执行了 MCP 自带端到端自检 `mcp/examples/e2e_pbso4.py`，
**第 8 步 `refine` 直接抛错**。下面是根因、修复与修前/修后实测对比。原始文件已备份，改动可回退。

---

## 1. 现象

```
=== 8. refine ===
Cycle 0: 0.61s, Chi**2: 1.7726e+06 ...
Cycle 2: 0.62s, Chi**2: 8.5298e+05 ...
Maximum shift/esd = 55.127 for all cycles
 ***** Refinement successful *****
[FAIL] refine: Refinement failed (GSAS-II returned no result).
RuntimeError: Refinement failed (GSAS-II returned no result). ...
```

注意关键矛盾：**GSAS-II 自己打印了 `***** Refinement successful *****`，包装层却报失败。**

## 2. 根因（两层，互相独立）

### 缺陷 A：包装层把"成功"当"失败"——`refine` 工具在任何情况下都不可用

`gsas2_mcp_server/server.py`（修复前 356-374 行）：

```python
result = _current_project.refine()
if result is None:
    raise RuntimeError("Refinement failed (GSAS-II returned no result)...")
```

而本机 GSAS-II（`D:\app\xrd\GSAS2-MCP`）的 `GSASIIscriptable.py:1610-1634`：

```python
def refine(self, newfile=None, printFile=None, makeBack=False):
    ...
    G2strMain.Refine(self.filename, makeBack=makeBack)
    self.reload()
    # ← 没有 return 语句，恒返回 None
```

**结论：`Project.refine()` 在本版本中恒返回 `None`，"返回 None"不是失败信号。**
因此 `refine` 工具在**任何**情况下都会抛 `RuntimeError`，无论精修成功与否。

### 缺陷 B：迭代次数默认 3 轮，静默不收敛

实测把精修后的 `.gpx` 读回来（用 `verify/probe_gpx_state.py` 可复现；该脚本与日志不随包发布）：

```
RESIDUALS: {"R": 55.43, "wR": 63.80, "wRmin": 4.79, "0:0:Rf": 42.13, "0:0:Rf^2": 77.37}
CONTROLS_KEYS_OF_INTEREST: ['max cyc', 'shift factor']
   max cyc = 3          ← GSAS-II 默认值
```

自检脚本第 6 步只放了 7 个变量（3 本底 + 标度 + 晶胞），3 轮后 `Maximum shift/esd = 55.1`（远超 1 = 未收敛），
但 GSAS-II 仍按"跑完了"处理并打印成功。**包装层既不上调轮数、也不把 shift/esd 回报给调用方**，
代理会拿着 wR=63.8% 的未收敛结果当"精修完成"。

## 3. 修复（最小改动，向后兼容）

`mcp/gsas2_mcp_server/server.py`（本包内为修复后版本）：

1. **不再依赖返回值判断成败**：改为捕获精修日志，只有出现
   `Refinement failed` / `Refine aborted` / `Least squares aborted` / 异常时才抛错。
2. **回报收敛信号**：从日志解析 `Maximum shift/esd = X`，作为 `max_shift_over_esd` 返回；
   `X > 1` 时附加 `convergence_warning`（明确写出"GSAS-II 在收敛前停止，请用 `refine(max_cycles=N)` 重跑"）。
3. **新增可选参数 `max_cycles`**：>0 时上调 `Controls['max cyc']` 再精修。
4. 工具描述同步更新（工具总数仍为 **19**，仅参数增加）。

修复补丁：`mcp/patches/refine-return-value-fix.patch`
原始文件备份：`mcp/gsas2_mcp_server/server.py.orig-2026-08-14.bak`（打包机上的实时副本为
`<USER_HOME>\iPolloWork\gsas2-mcp\gsas2_mcp_server\server.py.bak-before-refine-fix-20261012`）

## 4. 修前 / 修后实测对比

| 项 | 修前 | 修后 |
|---|---|---|
| 自检 `e2e_pbso4.py` 12 步 | 第 8 步 `refine` 抛 `RuntimeError`，中断 | **12/12 步全部 `[OK]`，exit=0** |
| `refine` 返回内容 | 无（异常） | `residuals` + `gsas2_status` + `max_shift_over_esd` + `convergence_warning` |
| 未收敛是否可见 | 不可见（甚至报"失败"） | `"max_shift_over_esd": 55.127` + 显式警告 |
| 能否主动提高迭代轮数 | 不能（固定 3 轮） | `refine(max_cycles=12)` |
| 产出文件 | 无（中途中断） | `.gpx` / `*_results.json` / `*_plot.png` 全部生成 |

修复后 `refine` 的真实返回（跑一遍 `mcp/examples/e2e_pbso4.py`，第 8 步可见同样内容）：

```json
{
  "refinement": "completed",
  "residuals": {"PWDR PBSO4.XRA Bank 1": {"wR": 63.802889, "R": 55.42854, "wRmin": 4.78675, "GOF": 13.3291}},
  "gsas2_status": "Refinement successful",
  "max_shift_over_esd": 55.127,
  "convergence_warning": "Max shift/esd = 55.127 > 1: GSAS-II stopped before convergence (Controls['max cyc'] = 3). ..."
}
```

## 5. 修复后的收敛实测（`verify/rerun_converged_max_cycles.py`）

GSAS-II 官方 PbSO₄ 样例，全程只用 MCP 工具函数，逐阶段 `refine(max_cycles=12)` 直到 shift/esd ≤ 1：

| 阶段 | 释放参数 | 收敛时 wR | GOF | 末轮 shift/esd |
|---|---|---|---|---|
| S1 | 3 项本底 + 标度 + 晶胞 | 31.6808 % | 6.6184 | 0.759 |
| S2 | + Zero + 仪器 U/V/W/X/Y/SH-L + 样品位移 | **12.8650 %** | **2.6876** | 0.486 |

最终晶胞（协方差 esd）：a = 8.481861(138)、b = 5.399835(90)、c = 6.961628(116) Å，V = 318.847(106) Å³
（与 PbSO₄ 文献值 a≈8.48 / b≈5.398 / c≈6.958 一致）；拟合图 `verify/e2e_out_converged/pbso4_plot_converged.png`。

> 对照：默认 3 轮时 wR = 63.80 %。**同一份数据、同一套工具，只是把"我以为跑完了"换成"确认 shift/esd ≤ 1"，wR 63.80 % → 12.87 %。**

## 6. 顺带发现（未改，如实记录）

- `export_plot` 输出的图**不裁剪到精修区间**：本例 Limits = 10–130°，图上却画到 160°，130° 之后是未参与拟合的平坦计算线。它输出的是通用 matplotlib 图（`Observed/Calculated` + 残差子图），**不是出版级图** —— 这正是 `rietveld-plotting` 存在的理由：精修与画图分离。
- `refine` 的日志会刷到服务端 stdout（stdio 通道）；本修复把日志捕获到内存并在失败时才回传尾部，避免污染 MCP 通道。
- **坑库同步更新**：本次实测已追加为 skill `gsas-ii-rietveld-refinement` 的 `references/pitfalls-observed.md` 第 9 节
  （MCP 包装层），改动前原件备份在 `verify/pitfalls-observed.md.before-2026-10-12-mcp-section.bak`。
  包内 `skills/` 因此**不是纯原文**：除该节外与本地安装逐字节一致。
