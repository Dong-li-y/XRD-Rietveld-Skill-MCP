"""
GSAS2-MCP Server — MCP stdio server wrapping the GSAS-II scriptable API.

Provides AI agents with Rietveld refinement and crystallographic analysis
tools for powder XRD data. The server keeps a single in-process GSAS-II
project (G2Project) and exposes tools to create/load projects, import
powder data and phases, set refinement parameters, run refinements, and
extract results.

Environment variables:
    GSAS2_MCP_PATH  path to the GSAS-II source tree (default: D:\\app\\xrd\\GSAS2-MCP)
    GSASII_HEADLESS  set to "true" to suppress GUI (default: true)
    MPLBACKEND       matplotlib backend (default: Agg)
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import sys
import traceback
from pathlib import Path

# ── GSAS-II setup ──────────────────────────────────────────────────────
GSAS2_MCP_PATH = os.environ.get("GSAS2_MCP_PATH", r"D:\app\xrd\GSAS2-MCP")
if GSAS2_MCP_PATH not in sys.path:
    sys.path.insert(0, GSAS2_MCP_PATH)
os.environ.setdefault("GSASII_HEADLESS", "true")
os.environ.setdefault("MPLBACKEND", "Agg")

from GSASII import GSASIIpath  # noqa: E402

GSASIIpath.SetBinaryPath()
from GSASII import GSASIIscriptable as G2sc  # noqa: E402

# ── MCP server ──────────────────────────────────────────────────────────
from mcp.server import Server  # noqa: E402
from mcp.server.stdio import stdio_server  # noqa: E402
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool  # noqa: E402

# ── Global state ────────────────────────────────────────────────────────
_current_project = None  # type: ignore
_temp_dir: Path = Path(os.environ.get("TEMP", os.path.expanduser("~"))) / "gsas2_mcp_projects"
_temp_dir.mkdir(parents=True, exist_ok=True)


# ── Helpers ─────────────────────────────────────────────────────────────

def _out(data) -> CallToolResult:
    """Serialize a result (str or JSON-able object) into a CallToolResult."""
    if isinstance(data, str):
        text = data
    else:
        text = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    return CallToolResult(content=[TextContent(type="text", text=text)])


def _safe_run(func) -> CallToolResult:
    """Wrap a tool function, converting exceptions into error results."""
    try:
        return _out(func())
    except Exception as e:  # noqa: BLE001
        return CallToolResult(
            content=[TextContent(type="text", text=f"Error: {e}\n{traceback.format_exc()}")],
            isError=True,
        )


def _ensure_project():
    if _current_project is None:
        raise RuntimeError("No project loaded. Use create_project or load_project first.")


def _round(v, nd=6):
    try:
        f = float(v)
        return round(f, nd)
    except (TypeError, ValueError):
        return v


def _extract_xy(powderdata):
    """Extract (x, y) arrays from a GSAS-II reader powderdata structure.

    Handles both the flat layout (x, y, w, ...) used by some readers and
    the nested layout [(name, {keys}), ...] used by others.
    """
    import numpy as np

    if not powderdata:
        return None, None
    first = powderdata[0]
    if isinstance(first, (list, tuple)) and len(first) == 2 and isinstance(first[1], dict):
        d = first[1]
        x = d.get("x")
        y = d.get("yobs")
        if x is None and "data" in d:
            x = d["data"][0]
            y = d["data"][1]
        return (np.asarray(x) if x is not None else None,
                np.asarray(y) if y is not None else None)
    if isinstance(first, np.ndarray) and len(powderdata) >= 2:
        return np.asarray(first), np.asarray(powderdata[1])
    return None, None


def _hist_summary(hist) -> dict:
    """Compact summary of a powder histogram."""
    info = {
        "name": hist.name,
        "type": str(hist.InstrumentParameters.get("Type", "")),
        "limits": [_round(hist.Limits("lower")), _round(hist.Limits("upper"))],
    }
    try:
        info["wR"] = _round(hist.get_wR()) if hist.get_wR() is not None else None
    except Exception:
        info["wR"] = None
    try:
        info["n_reflections"] = len(hist.reflections())
    except Exception:
        info["n_reflections"] = 0
    return info


def _phase_summary(phase) -> dict:
    """Compact summary of a phase."""
    cell = phase.get_cell()
    try:
        space_group = phase.getPhaseEntryValue(["General", "SGData", "SpGrp"])
    except Exception:
        space_group = ""
    info = {
        "name": phase.name,
        "space_group": space_group,
        "cell": {k: _round(v) for k, v in cell.items()},
    }
    try:
        info["n_atoms"] = len(phase.atoms())
    except Exception:
        info["n_atoms"] = 0
    return info


# ── Tool implementations ────────────────────────────────────────────────

def create_project(name: str = "untitled") -> str:
    """Create a new GSAS-II project (.gpx file)."""
    global _current_project
    path = str(_temp_dir / f"{name}.gpx")
    _current_project = G2sc.G2Project(newgpx=path)
    return f"Project '{name}' created at {path}"


def load_project(path: str) -> str:
    """Load an existing GSAS-II project (.gpx file)."""
    global _current_project
    _current_project = G2sc.G2Project(gpxfile=path)
    return f"Loaded project from {path} ({len(_current_project.histograms())} histograms, {len(_current_project.phases())} phases)"


def save_project(path: str | None = None) -> str:
    """Save the current project to a .gpx file."""
    _ensure_project()
    _current_project.save(path)
    return f"Project saved to {path or _current_project.filename}"


def project_summary() -> dict:
    """Structured summary of the current project."""
    _ensure_project()
    gpx = _current_project
    return {
        "filename": gpx.filename,
        "histograms": [_hist_summary(h) for h in gpx.histograms()],
        "phases": [_phase_summary(p) for p in gpx.phases()],
        "vary_list": gpx.get_VaryList() or [],
    }


def inspect_data_file(datafile: str) -> dict:
    """Inspect a diffraction data file and report its contents (no project needed)."""
    import numpy as np

    p = Path(datafile)
    if not p.exists():
        raise FileNotFoundError(f"Data file not found: {datafile}")
    summary = {"file": str(p), "size_bytes": p.stat().st_size}
    # Try GSAS-II reader first
    try:
        from GSASII.GSASIIscriptable import LoadG2fil, Readers

        LoadG2fil()
        for rd in Readers["Pwdr"]:
            try:
                if not rd.ExtensionValidator(str(p)):
                    continue
                rd.ReInitialize()
                rd.errors = ""
                if not rd.ContentsValidator(str(p)):
                    continue
                rd.objname = p.name
                if rd.Reader(str(p), buffer={}, blocknum=1):
                    summary["format"] = rd.formatName
                    x, y = _extract_xy(rd.powderdata)
                    if x is not None:
                        summary["n_points"] = int(len(x))
                        summary["two_theta_range"] = [_round(x[0]), _round(x[-1])]
                        if y is not None:
                            summary["intensity_range"] = [_round(float(y.min())), _round(float(y.max()))]
                    return summary
            except Exception:
                continue
    except Exception:
        pass
    # Fallback: try simple 2-column numeric parse
    try:
        data = np.loadtxt(datafile)
        if data.ndim == 2 and data.shape[1] >= 2:
            summary["format"] = "xy (numeric)"
            summary["n_points"] = int(len(data))
            summary["two_theta_range"] = [_round(float(data[0, 0])), _round(float(data[-1, 0]))]
            summary["intensity_range"] = [_round(float(data[:, 1].min())), _round(float(data[:, 1].max()))]
            return summary
    except Exception:
        pass
    summary["format"] = "unknown"
    summary["note"] = "Could not auto-detect format; try add_powder_histogram with an instrument parameter file."
    return summary


def add_powder_histogram(datafile: str, iparams: str = "", fmthint: str = "") -> str:
    """Add powder diffraction data to the project.

    iparams: path to an instrument parameter file (.prm). Required for
    formats that do not embed instrument parameters (e.g. .xye, .fxye).
    fmthint: optional format hint, e.g. 'RAS', 'xye', 'fxye'.
    """
    _ensure_project()
    iparams_path = iparams if iparams else None
    fmthint_val = fmthint if fmthint else None
    hist = _current_project.add_powder_histogram(datafile, iparams=iparams_path, fmthint=fmthint_val)
    return f"Added histogram '{hist.name}' from {datafile}"


def add_phase(cif_file: str, phase_name: str = "", histograms: list[str] | None = None) -> str:
    """Add a crystallographic phase from a CIF file, linked to histograms."""
    _ensure_project()
    hist_names = histograms or [h.name for h in _current_project.histograms()]
    if not hist_names:
        return "Error: No histograms in project. Add powder data first."
    phase = _current_project.add_phase(cif_file, phasename=phase_name, histograms=hist_names)
    return f"Added phase '{phase.name}' from {cif_file}"


def list_histograms() -> dict:
    """List all powder histograms with their current state."""
    _ensure_project()
    return {"histograms": [_hist_summary(h) for h in _current_project.histograms()]}


def list_phases() -> dict:
    """List all phases with their current state."""
    _ensure_project()
    return {"phases": [_phase_summary(p) for p in _current_project.phases()]}


def set_refinement(params: str) -> dict:
    """Set refinement parameters using a GSAS-II refinement recipe.

    params is a JSON string with keys 'set', 'clear' and/or 'once'.
    Optional keys 'histograms' and 'phases' restrict the recipe to
    specific histograms/phases (by name or index).

    Example:
      {"set": {"Limits": [10.0, 130.0],
               "Background": {"no. coeffs": 3, "refine": True},
               "Sample Parameters": ["Scale"],
               "Instrument Parameters": ["U", "V", "W"]},
       "clear": {"Instrument Parameters": ["X", "Y"]}}
    """
    _ensure_project()
    try:
        param_dict = json.loads(params)
    except json.JSONDecodeError:
        raise ValueError(
            "Invalid JSON for params. Use format: "
            '{"set": {"Background": {"no. coeffs": 3, "refine": true}, "Sample Parameters": ["Scale"]}}'
        ) from None
    _current_project.set_refinement(param_dict)
    return {
        "applied": True,
        "note": "Refinement flags set. Run refine() then get_variables() to see the refined variable list.",
    }


def set_histogram_params(histogram: str = "", params: str = "") -> dict:
    """Set refinement flags on one histogram (or all if histogram is empty).

    params is a JSON object, e.g.
      {"Background": {"no. coeffs": 3, "refine": true},
       "Sample Parameters": ["Scale"],
       "Limits": [10.0, 130.0],
       "Instrument Parameters": ["U", "V", "W"]}
    """
    _ensure_project()
    try:
        param_dict = json.loads(params)
    except json.JSONDecodeError:
        raise ValueError("Invalid JSON for params.") from None
    targets = _current_project.histograms(histogram) if histogram else _current_project.histograms()
    for h in targets:
        h.set_refinements(param_dict)
    return {"applied": True, "histograms": [h.name for h in targets]}


def set_phase_params(phase: str = "", params: str = "") -> dict:
    """Set refinement flags on one phase (or all if phase is empty).

    params is a JSON object, e.g.
      {"Cell": true,
       "Atoms": {"Pb1": "XU", "S1": "XU", "O1": "XU"}}
    or for HAP parameters (scale, size, mustrain):
      {"Scale": true, "Size": {"type": "isotropic", "refine": true}}
    """
    _ensure_project()
    try:
        param_dict = json.loads(params)
    except json.JSONDecodeError:
        raise ValueError("Invalid JSON for params.") from None
    targets = _current_project.phases(phase) if phase else _current_project.phases()
    for p in targets:
        p.set_refinements(param_dict)
    return {"applied": True, "phases": [p.name for p in targets]}


def get_variables() -> dict:
    """List the variables currently set to refine."""
    _ensure_project()
    return {"vary_list": _current_project.get_VaryList() or []}


def hold_variable(var_name: str) -> str:
    """Hold (fix) a refinement variable."""
    _ensure_project()
    _current_project.set_refinement({"hold": var_name})
    return f"Held variable '{var_name}'"


def free_variable(var_name: str) -> str:
    """Free (release) a refinement variable."""
    _ensure_project()
    _current_project.set_refinement({"free": var_name})
    return f"Freed variable '{var_name}'"


_MAX_SHIFT_RE = re.compile(r"Maximum shift/esd = ([0-9.eE+-]+)")
_REFINE_FAIL_MARKERS = (
    "Refinement failed",
    "Refine aborted",
    "Least squares aborted",
)


def refine(max_cycles: int = 0) -> dict:
    """Run a Rietveld refinement on the current project.

    GSAS-II iterates internally until convergence or until
    Controls['max cyc'] is reached. Pass max_cycles > 0 to raise that limit for
    this call (GSAS-II's default of 3 frequently stops before convergence).

    Outcome detection: GSASIIscriptable.Project.refine() has no return value in
    this GSAS-II version, so success/failure is read from the refinement log
    itself, and the final "Maximum shift/esd" is reported back to the caller.
    """
    _ensure_project()
    if max_cycles and int(max_cycles) > 0:
        try:
            _current_project.data["Controls"]["data"]["max cyc"] = int(max_cycles)
        except Exception:  # pragma: no cover - defensive, Controls always present
            pass
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            _current_project.refine()
    except Exception as e:
        log = buf.getvalue().splitlines()[-15:]
        raise RuntimeError(
            "Refinement raised: %s\n--- GSAS-II log tail ---\n%s" % (e, "\n".join(log))
        ) from None
    log = buf.getvalue()
    for marker in _REFINE_FAIL_MARKERS:
        if marker in log:
            tail = "\n".join(
                ln for ln in log.splitlines() if ln.strip()
            )[-1200:]
            raise RuntimeError(
                "Refinement failed (%s). GSAS-II log tail:\n%s" % (marker, tail)
            )
    out = {"refinement": "completed", "residuals": _results_residuals()}
    if "Refinement successful" in log:
        out["gsas2_status"] = "Refinement successful"
    m = _MAX_SHIFT_RE.search(log)
    if m:
        try:
            shift = float(m.group(1))
        except ValueError:
            shift = None
        if shift is not None:
            out["max_shift_over_esd"] = _round(shift, 4)
            if shift > 1.0:
                out["convergence_warning"] = (
                    "Max shift/esd = %.3f > 1: GSAS-II stopped before convergence "
                    "(Controls['max cyc'] = %s). Re-run with refine(max_cycles=N) or "
                    "release fewer parameters before trusting these residuals."
                    % (shift, _current_project.data.get("Controls", {}).get("data", {}).get("max cyc"))
                )
    return out


def _results_residuals() -> dict:
    """Collect residual (R-factor) summary across histograms."""
    out = {}
    for hist in _current_project.histograms():
        res = dict(hist.residuals or {})
        entry = {
            "wR": _round(res.get("wR")),
            "R": _round(res.get("R")),
            "wRmin": _round(res.get("wRmin")),
        }
        if res.get("wR") and res.get("wRmin"):
            entry["GOF"] = _round(res["wR"] / res["wRmin"], 4)
        out[hist.name] = entry
    return out


def get_results() -> dict:
    """Get full refinement results: residuals, cell parameters, atoms."""
    _ensure_project()
    results = {"residuals": _results_residuals()}
    phases_out = {}
    for phase in _current_project.phases():
        cell, esd = phase.get_cell_and_esd()
        atoms = []
        for a in phase.atoms():
            atoms.append({
                "label": a.label,
                "element": a.element,
                "type": a.type,
                "coordinates": [_round(x, 5) for x in a.coordinates],
                "occupancy": _round(a.occupancy, 5),
                "uiso": _round(a.uiso, 5),
                "refinement_flags": a.refinement_flags,
            })
        phases_out[phase.name] = {
            "cell": {k: _round(v, 6) for k, v in cell.items()},
            "cell_esd": {k: _round(v, 6) for k, v in esd.items()},
            "atoms": atoms,
        }
    results["phases"] = phases_out
    return results


def export_results(path: str = "") -> str:
    """Export refinement results to a JSON file. Returns the file path."""
    _ensure_project()
    out_path = Path(path) if path else _temp_dir / "gsas2_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(get_results(), ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return f"Results exported to {out_path}"


def export_plot(path: str = "") -> str:
    """Export a Rietveld fit plot (observed, calculated, residual) as PNG.

    Uses the first powder histogram. Returns the image file path.
    """
    _ensure_project()
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    hists = _current_project.histograms()
    if not hists:
        raise RuntimeError("No histograms in project.")
    hist = hists[0]
    x = hist.getdata("x")
    yobs = hist.getdata("yobs")
    ycalc = hist.getdata("ycalc")
    resid = hist.getdata("residual")

    out_path = Path(path) if path else _temp_dir / "gsas2_plot.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(10, 7), sharex=True,
        gridspec_kw={"height_ratios": [3, 1]},
    )
    ax1.plot(x, yobs, "b.", markersize=2, label="Observed")
    if ycalc is not None:
        ax1.plot(x, ycalc, "r-", linewidth=1, label="Calculated")
    ax1.set_ylabel("Intensity")
    ax1.legend(loc="upper right", fontsize=8)
    ax1.set_title(hist.name)
    if resid is not None:
        ax2.plot(x, resid, "g-", linewidth=0.8)
        ax2.set_ylabel("Residual")
    ax2.set_xlabel("2θ (deg)")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return f"Plot exported to {out_path}"


# ── Tool definitions ────────────────────────────────────────────────────

def _tool(name, description, properties, required=()):
    return Tool(
        name=name,
        description=description,
        inputSchema={"type": "object", "properties": properties, "required": list(required)},
    )


TOOLS = [
    _tool(
        "create_project",
        "Create a new GSAS-II project (.gpx file) for Rietveld refinement",
        {"name": {"type": "string", "description": "Project name (without extension)", "default": "untitled"}},
    ),
    _tool(
        "load_project",
        "Load an existing GSAS-II project (.gpx file)",
        {"path": {"type": "string", "description": "Absolute path to the .gpx project file"}},
        required=["path"],
    ),
    _tool(
        "save_project",
        "Save the current GSAS-II project",
        {"path": {"type": "string", "description": "Optional save path"}},
    ),
    _tool(
        "project_summary",
        "Get a structured summary of the current project (histograms, phases, refineable variables)",
        {},
    ),
    _tool(
        "inspect_data_file",
        "Inspect a diffraction data file and report its contents (no project needed)",
        {"datafile": {"type": "string", "description": "Path to the diffraction data file"}},
        required=["datafile"],
    ),
    _tool(
        "add_powder_histogram",
        "Add powder diffraction data to the current project. Provide iparams (instrument parameter .prm file) for formats that do not embed them (e.g. .xye, .fxye).",
        {
            "datafile": {"type": "string", "description": "Path to the powder diffraction data file (e.g. .xye, .fxye, .gsas, .raw, .XRA)"},
            "iparams": {"type": "string", "description": "Path to instrument parameter file (.prm)", "default": ""},
            "fmthint": {"type": "string", "description": "Optional format hint, e.g. 'RAS', 'xye', 'fxye'", "default": ""},
        },
        required=["datafile"],
    ),
    _tool(
        "add_phase",
        "Add a crystallographic phase from a CIF file, linked to the project histograms",
        {
            "cif_file": {"type": "string", "description": "Path to the CIF file"},
            "phase_name": {"type": "string", "description": "Optional custom phase name", "default": ""},
            "histograms": {"type": "array", "items": {"type": "string"}, "description": "Histogram names to associate with this phase (default: all)"},
        },
        required=["cif_file"],
    ),
    _tool("list_histograms", "List all powder histograms with their current state (limits, wR, reflections)", {}),
    _tool("list_phases", "List all phases with their current state (space group, cell, atoms)", {}),
    _tool(
        "set_refinement",
        "Set Rietveld refinement parameters using a GSAS-II refinement recipe. JSON with keys 'set'/'clear'/'once' and optional 'histograms'/'phases'. Example: {\"set\":{\"Background\":{\"no. coeffs\":3,\"refine\":true},\"Sample Parameters\":[\"Scale\"],\"Cell\":true}}",
        {"params": {"type": "string", "description": "JSON refinement recipe string"}},
        required=["params"],
    ),
    _tool(
        "set_histogram_params",
        "Set refinement flags on one histogram (or all). JSON params, e.g. {\"Background\":{\"no. coeffs\":3,\"refine\":true},\"Sample Parameters\":[\"Scale\"],\"Limits\":[10,130],\"Instrument Parameters\":[\"U\",\"V\",\"W\"]}",
        {
            "histogram": {"type": "string", "description": "Histogram name or index (default: all)", "default": ""},
            "params": {"type": "string", "description": "JSON params object"},
        },
        required=["params"],
    ),
    _tool(
        "set_phase_params",
        "Set refinement flags on one phase (or all). JSON params, e.g. {\"Cell\":true,\"Atoms\":{\"Pb1\":\"XU\"}} or HAP params {\"Scale\":true,\"Size\":{\"type\":\"isotropic\",\"refine\":true}}",
        {
            "phase": {"type": "string", "description": "Phase name or index (default: all)", "default": ""},
            "params": {"type": "string", "description": "JSON params object"},
        },
        required=["params"],
    ),
    _tool("get_variables", "List the variables currently set to refine", {}),
    _tool(
        "hold_variable",
        "Hold (fix) a refinement variable",
        {"var_name": {"type": "string", "description": "Variable name to hold"}},
        required=["var_name"],
    ),
    _tool(
        "free_variable",
        "Free (release) a refinement variable",
        {"var_name": {"type": "string", "description": "Variable name to free"}},
        required=["var_name"],
    ),
    _tool(
        "refine",
        "Run a Rietveld refinement on the current project (GSAS-II iterates to "
        "convergence or until Controls['max cyc']). Returns residuals plus the "
        "final max shift/esd and a convergence warning when shift/esd > 1.",
        {"max_cycles": {"type": "integer",
                        "description": "Optional: raise Controls['max cyc'] for this call "
                                       "(GSAS-II default 3 often stops before convergence)",
                        "default": 0}},
    ),
    _tool("get_results", "Get full refinement results: residuals (wR, R, GOF), cell parameters with esd, atomic coordinates", {}),
    _tool(
        "export_results",
        "Export refinement results to a JSON file",
        {"path": {"type": "string", "description": "Optional output path (default: temp dir)"}},
    ),
    _tool(
        "export_plot",
        "Export a Rietveld fit plot (observed/calculated/residual) as PNG",
        {"path": {"type": "string", "description": "Optional output path (default: temp dir)"}},
    ),
]

TOOL_MAP = {
    "create_project": create_project,
    "load_project": load_project,
    "save_project": save_project,
    "project_summary": project_summary,
    "inspect_data_file": inspect_data_file,
    "add_powder_histogram": add_powder_histogram,
    "add_phase": add_phase,
    "list_histograms": list_histograms,
    "list_phases": list_phases,
    "set_refinement": set_refinement,
    "set_histogram_params": set_histogram_params,
    "set_phase_params": set_phase_params,
    "get_variables": get_variables,
    "hold_variable": hold_variable,
    "free_variable": free_variable,
    "refine": refine,
    "get_results": get_results,
    "export_results": export_results,
    "export_plot": export_plot,
}


# ── MCP Server (low-level API for mcp>=2.0) ────────────────────────────

async def _list_tools(ctx, params=None):
    return ListToolsResult(tools=TOOLS)


async def _call_tool(ctx, params):
    handler = TOOL_MAP.get(params.name)
    if handler is None:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Unknown tool: {params.name}")],
            isError=True,
        )
    return _safe_run(lambda: handler(**params.arguments))


server = Server(
    "gsas2-mcp",
    version="1.1.0",
    on_list_tools=_list_tools,
    on_call_tool=_call_tool,
)


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())