"""Probe: what does GSAS-IIscriptable expose after refine() in this version?

Real evidence only — loads the GPX that the e2e run left behind and inspects it
with the same import path the MCP server uses (GSAS2_MCP_PATH on sys.path,
`from GSASII import ...`).
"""
import json
import os
import sys

GSAS2 = os.environ.get("GSAS2_MCP_PATH", r"D:\app\xrd\GSAS2-MCP")
if GSAS2 not in sys.path:
    sys.path.insert(0, GSAS2)
os.environ.setdefault("GSASII_HEADLESS", "true")
os.environ.setdefault("MPLBACKEND", "Agg")

from GSASII import GSASIIpath  # noqa: E402

GSASIIpath.SetBinaryPath()
from GSASII import GSASIIscriptable as G2sc  # noqa: E402

gpx = sys.argv[1]
p = G2sc.G2Project(gpx)
hist = p.histograms()[0]
print("PROJECT:", gpx)
print("RESIDUALS:", json.dumps(dict(hist.residuals or {}), indent=1, default=str))
cd = p.data.get("Controls", {}).get("data", {})
of_interest = sorted(k for k in cd if any(s in k.lower() for s in ("shft", "shift", "cyc", "conv")))
print("CONTROLS_KEYS_OF_INTEREST:", of_interest)
for k in of_interest:
    print("   %-22s = %r" % (k, cd[k]))
print("HAS_PHASE_RESULTS:", [ph.name for ph in p.phases()])
