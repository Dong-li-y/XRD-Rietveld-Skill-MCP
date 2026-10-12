"""Post-fix verification: drive the MCP `refine` tool to real convergence.

Mirrors examples/e2e_pbso4.py but calls refine(max_cycles=12) repeatedly until
the reported max shift/esd <= 1, and records wR per pass. Uses the GSAS-II
PbSO4 tutorial data (ships with GSAS-II; no private data).

Run (same env as the MCP server):
  PYTHONPATH=<gsas2-mcp> GSAS2_MCP_PATH=<GSAS-II tree> MPLBACKEND=Agg \
  D:\\app\\xrd\\python.exe verify/rerun_converged_max_cycles.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.dirname(HERE)
MCP_DIR = os.path.join(PKG_ROOT, "mcp")
sys.path.insert(0, MCP_DIR)
os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("GSASII_HEADLESS", "true")

from gsas2_mcp_server import server as S  # noqa: E402

DATA = os.path.join(os.environ["GSAS2_MCP_PATH"], "tests", "testinp")
OUT = os.path.join(HERE, "e2e_out_converged")
S._temp_dir = __import__("pathlib").Path(OUT) / "gsas2_mcp_projects"
S._temp_dir.mkdir(parents=True, exist_ok=True)
os.makedirs(OUT, exist_ok=True)


def call(tool, *a, **kw):
    out = S.TOOL_MAP[tool](*a, **kw)
    if not isinstance(out, str):
        out = json.dumps(out, ensure_ascii=False, indent=2)
    print("\n[%s]\n%s" % (tool, out[:1500]))
    return out


print("=== setup ===")
call("create_project", name="pbso4_convergence")
call("add_powder_histogram",
     datafile=os.path.join(DATA, "PBSO4.XRA"),
     iparams=os.path.join(DATA, "INST_XRY.PRM"))
call("add_phase", cif_file=os.path.join(DATA, "PbSO4-Wyckoff.cif"))
call("set_refinement", params=json.dumps({
    "set": {
        "Limits": [10.0, 130.0],
        "Background": {"no. coeffs": 3, "refine": True},
        "Sample Parameters": ["Scale"],
        "Cell": True,
    }
}))

print("\n=== stage 1: background + scale + cell ===")


def drive(label, passes=6):
    """Call refine(max_cycles=12) until max shift/esd <= 1; return last result."""
    last = None
    for i in range(1, passes + 1):
        res = json.loads(call("refine", max_cycles=12))
        r = list(res.get("residuals", {}).values())[0]
        last = res
        print("%s pass %d: wR=%.4f%% GOF=%.4f shift/esd=%s" % (
            label, i, r["wR"], r.get("GOF", float("nan")), res.get("max_shift_over_esd")))
        if res.get("max_shift_over_esd", 99) <= 1.0:
            print("%s CONVERGED at pass %d (wR=%.4f%%)" % (label, i, r["wR"]))
            return last, r
    print("%s NOT converged after %d passes" % (label, passes))
    return last, list(last.get("residuals", {}).values())[0]


_, r1 = drive("S1")

print("\n=== stage 2: + Zero, instrument U/V/W/X/Y/SH-L, sample shift ===")
call("set_refinement", params=json.dumps({
    "set": {
        "Instrument Parameters": ["U", "V", "W", "X", "Y", "SH/L"],
        "Sample Parameters": ["Shift"],
    }
}))
_, r2 = drive("S2")

print("\n=== wR summary: %.4f%% (3 background coeffs + scale + cell) -> %.4f%% (stage 2) ==="
      % (r1["wR"], r2["wR"]))

print("\n=== outputs ===")
call("export_results", path=os.path.join(OUT, "pbso4_results_converged.json"))
call("export_plot", path=os.path.join(OUT, "pbso4_plot_converged.png"))
call("save_project", path=os.path.join(OUT, "pbso4_converged.gpx"))
print("\nDONE ->", OUT)
