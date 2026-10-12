"""
End-to-end test of the GSAS2-MCP server tool functions using the PbSO4
example data shipped with GSAS-II.

Run with the GSAS-II Python environment:
    D:\\app\\xrd\\python.exe examples\\e2e_pbso4.py

This exercises the full Rietveld workflow:
create project -> add powder data -> add phase -> set parameters -> refine -> results.
"""

import json
import os
import sys
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MPLBACKEND", "Agg")

from gsas2_mcp_server import server as S

DATA = r"D:\app\xrd\GSAS2-MCP\tests\testinp"
OUT = os.path.join(os.environ.get("TEMP", "."), "gsas2_mcp_e2e")


def run(tool_name, *args, **kwargs):
    try:
        fn = S.TOOL_MAP[tool_name]
        out = fn(*args, **kwargs)
        if not isinstance(out, str):
            out = json.dumps(out, ensure_ascii=False, indent=2)
        print(f"[OK] {tool_name}: {out[:800]}")
        return out
    except Exception as e:
        print(f"[FAIL] {tool_name}: {e}")
        traceback.print_exc()
        raise


def main():
    os.makedirs(OUT, exist_ok=True)
    print("=== 1. create_project ===")
    run("create_project", name="pbso4_demo")

    print("=== 2. inspect_data_file ===")
    run("inspect_data_file", datafile=os.path.join(DATA, "PBSO4.XRA"))

    print("=== 3. add_powder_histogram (with instrument params) ===")
    run("add_powder_histogram",
        datafile=os.path.join(DATA, "PBSO4.XRA"),
        iparams=os.path.join(DATA, "INST_XRY.PRM"))

    print("=== 4. add_phase ===")
    run("add_phase", cif_file=os.path.join(DATA, "PbSO4-Wyckoff.cif"))

    print("=== 5. project_summary ===")
    run("project_summary")

    print("=== 6. set_refinement (background + scale + cell) ===")
    run("set_refinement", params=json.dumps({
        "set": {
            "Limits": [10.0, 130.0],
            "Background": {"no. coeffs": 3, "refine": True},
            "Sample Parameters": ["Scale"],
            "Cell": True,
        }
    }))

    print("=== 7. get_variables ===")
    run("get_variables")

    print("=== 8. refine ===")
    run("refine")

    print("=== 9. get_results ===")
    run("get_results")

    print("=== 10. export_results ===")
    run("export_results", path=os.path.join(OUT, "pbso4_results.json"))

    print("=== 11. export_plot ===")
    run("export_plot", path=os.path.join(OUT, "pbso4_plot.png"))

    print("=== 12. save_project ===")
    run("save_project", path=os.path.join(OUT, "pbso4_demo.gpx"))

    print("\nAll steps completed. Outputs in:", OUT)


if __name__ == "__main__":
    main()