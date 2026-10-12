#!/usr/bin/env python3
"""
Automated GSAS-II Rietveld refinement for single-phase and multiphase XRD jobs.
"""

from __future__ import annotations

import argparse
import csv
import importlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.request import urlretrieve

import numpy as np


INSTRUMENT_GROUPS = {
    "zero": ["Zero"],
    "uvw": ["U", "V", "W"],
    "xy": ["X", "Y"],
    "shl": ["SH/L"],
}
SINGLE_PARAMETER_INSTRUMENT_STAGES = [
    ("zero", "Zero", ["Zero"]),
    ("u", "U", ["U"]),
    ("v", "V", ["V"]),
    ("w", "W", ["W"]),
    ("x", "X", ["X"]),
    ("y", "Y", ["Y"]),
    ("shl", "SH/L", ["SH/L"]),
]
PROGRESSIVE_UVW_JOINT_STAGES = [
    ("joint_abc_u", "background + zero + cell + U", ["Zero", "U"]),
    ("joint_abc_v", "background + zero + cell + V", ["Zero", "V"]),
    ("joint_abc_w", "background + zero + cell + W", ["Zero", "W"]),
    ("joint_abc_uv", "background + zero + cell + U + V", ["Zero", "U", "V"]),
    ("joint_abc_uw", "background + zero + cell + U + W", ["Zero", "U", "W"]),
    ("joint_abc_vw", "background + zero + cell + V + W", ["Zero", "V", "W"]),
    ("joint_abc_uvw", "background + zero + cell + U + V + W", ["Zero", "U", "V", "W"]),
]
ATOMIC_REFINEMENT_STAGES = [
    ("atoms_x", "atomic coordinate refinement", "X"),
    ("atoms_u", "atomic displacement refinement", "U"),
    ("atoms_occ", "atomic occupancy refinement", "F"),
    ("atoms_fxu", "combined atomic refinement", "FXU"),
]
LATE_STAGE_INSTRUMENT_KEYS = INSTRUMENT_GROUPS["zero"] + INSTRUMENT_GROUPS["uvw"]
OFFICIAL_GITSTRAP_URL = (
    "https://raw.githubusercontent.com/AdvancedPhotonSource/GSAS-II-buildtools/main/install/gitstrap.py"
)
AUTO_INSTALLER_PYTHON_PACKAGES = {
    "git": "GitPython",
    "requests": "requests",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run GSAS-II Rietveld refinement for one or more CIF phases."
    )
    parser.add_argument("--pattern", required=True, help="Path to the experimental XRD pattern.")
    parser.add_argument(
        "--cifs",
        nargs="*",
        default=None,
        help="One or more CIF files. If omitted, .cif files are auto-discovered beside the pattern or in a cifs subfolder.",
    )
    parser.add_argument(
        "--phase-names",
        nargs="*",
        default=None,
        help="Optional phase names, one for each CIF.",
    )
    parser.add_argument("--output-dir", default=None, help="Output directory for GPX and reports.")
    parser.add_argument("--gsasii-root", default=None, help="GSAS-II source root containing the GSASII package.")
    parser.add_argument(
        "--gsasii-install-dir",
        default=None,
        help="Install GSAS-II here if it is not found locally. Defaults to ~/.codex/tools/GSAS-II-src.",
    )
    parser.add_argument(
        "--no-auto-install-gsasii",
        action="store_true",
        help="Do not auto-install GSAS-II when no local source tree is found.",
    )
    parser.add_argument("--instprm", default=None, help="Instrument parameter file.")
    parser.add_argument(
        "--limits",
        nargs=2,
        type=float,
        metavar=("LOW", "HIGH"),
        default=None,
        help="2theta refinement limits.",
    )
    parser.add_argument(
        "--wavelength",
        type=float,
        default=1.54056,
        help="Single-wavelength value used only when generating a default instprm.",
    )
    parser.add_argument(
        "--esd-factor",
        type=float,
        default=2.4,
        help="When the pattern lacks sigma/esd, write esd = factor * sqrt(I).",
    )
    parser.add_argument(
        "--target-rwp",
        type=float,
        default=10.0,
        help="Target Rwp for success.",
    )
    parser.add_argument(
        "--target-chi2",
        type=float,
        default=5.0,
        help="Target reduced chi2 for success.",
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=6,
        help="Refinement cycles for ordinary stages.",
    )
    parser.add_argument(
        "--final-cycles",
        type=int,
        default=8,
        help="Refinement cycles for late background stages.",
    )
    parser.add_argument(
        "--background-sequence",
        default="8,16",
        help="Comma-separated Chebyshev coefficient counts used across stages.",
    )
    parser.add_argument(
        "--disable-size-microstrain",
        action="store_true",
        help="Skip isotropic size and microstrain refinement.",
    )
    parser.add_argument(
        "--refine-preferred-orientation",
        dest="refine_preferred_orientation",
        action="store_true",
        help="Enable preferred-orientation refinement stages. Enabled by default.",
    )
    parser.add_argument(
        "--disable-preferred-orientation",
        dest="refine_preferred_orientation",
        action="store_false",
        help="Skip preferred-orientation refinement stages.",
    )
    parser.add_argument(
        "--refine-atomic-parameters",
        dest="refine_atomic_parameters",
        action="store_true",
        help="Enable atomic occupancy/coordinate/U refinement stages. Enabled by default.",
    )
    parser.add_argument(
        "--disable-atomic-refinement",
        dest="refine_atomic_parameters",
        action="store_false",
        help="Skip atomic refinement stages.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Reduce console output.",
    )
    parser.set_defaults(
        refine_preferred_orientation=True,
        refine_atomic_parameters=True,
    )
    return parser.parse_args()


def log(message: str, quiet: bool = False) -> None:
    if not quiet:
        print(message)


def is_gsasii_root(path: Path) -> bool:
    return (path / "GSASII" / "GSASIIscriptable.py").exists()


def default_gsasii_install_dir() -> Path:
    return (Path.home() / ".codex" / "tools" / "GSAS-II-src").resolve()


def detect_gsasii_root(args_root: str | None, pattern_path: Path) -> Path:
    candidates = []
    if args_root:
        candidates.append(Path(args_root))
    env_root = os.environ.get("GSASII_ROOT")
    if env_root:
        candidates.append(Path(env_root))

    probes = [Path.cwd(), pattern_path.parent, Path(__file__).resolve().parent]
    for base in list(probes):
        probes.extend(base.parents)

    for base in probes:
        candidates.append(base)
        candidates.append(base / "GSAS-II-src")

    seen = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate
        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        if is_gsasii_root(resolved):
            return resolved

    raise FileNotFoundError(
        "Could not locate GSAS-II. Pass --gsasii-root or set GSASII_ROOT."
    )


def ensure_python_packages(package_map: dict[str, str], quiet: bool) -> tuple[list[str], list[str]]:
    installed = []
    log_lines = []
    for module_name, package_name in package_map.items():
        try:
            importlib.import_module(module_name)
            continue
        except ImportError:
            pass

        log(f"Installing missing Python package {package_name} for GSAS-II bootstrap", quiet)
        command = [sys.executable, "-m", "pip", "install", package_name]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        log_lines.append(f"Dependency install command: {' '.join(command)}")
        log_lines.append("STDOUT:")
        log_lines.append(result.stdout)
        log_lines.append("STDERR:")
        log_lines.append(result.stderr)
        log_lines.append("")
        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to install required Python package {package_name} for GSAS-II bootstrap."
            )
        importlib.invalidate_caches()
        importlib.import_module(module_name)
        installed.append(package_name)
    return installed, log_lines


def install_gsasii_with_gitstrap(install_dir: Path, quiet: bool) -> dict:
    install_dir = install_dir.expanduser().resolve()
    install_dir.parent.mkdir(parents=True, exist_ok=True)
    log_path = install_dir.parent / "gitstrap_install.log"
    installed_packages, bootstrap_log_lines = ensure_python_packages(
        AUTO_INSTALLER_PYTHON_PACKAGES,
        quiet,
    )

    with tempfile.TemporaryDirectory(prefix="gsas2_gitstrap_") as temp_dir:
        gitstrap_path = Path(temp_dir) / "gitstrap.py"
        urlretrieve(OFFICIAL_GITSTRAP_URL, gitstrap_path)
        command = [
            sys.executable,
            str(gitstrap_path),
            f"--loc={install_dir}",
            "--nocheck",
            "--noshortcut",
        ]
        log(
            f"GSAS-II not found. Installing with official gitstrap.py into {install_dir}",
            quiet,
        )
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

    log_text = []
    log_text.extend(bootstrap_log_lines)
    log_text.append("Command:")
    log_text.append(" ".join(command))
    log_text.append("")
    log_text.append("STDOUT:")
    log_text.append(result.stdout)
    log_text.append("")
    log_text.append("STDERR:")
    log_text.append(result.stderr)
    log_path.write_text("\n".join(log_text), encoding="utf-8")

    if result.returncode != 0:
        raise RuntimeError(
            "Official GSAS-II installer failed. "
            f"See install log: {log_path}"
        )
    if not is_gsasii_root(install_dir):
        raise RuntimeError(
            "Official GSAS-II installer completed but no valid GSAS-II root was created. "
            f"See install log: {log_path}"
        )

    return {
        "performed": True,
        "root": str(install_dir),
        "gitstrap_url": OFFICIAL_GITSTRAP_URL,
        "log": str(log_path),
        "bootstrap_python_packages": installed_packages,
    }


def resolve_gsasii_root(
    args_root: str | None,
    pattern_path: Path,
    install_dir_arg: str | None,
    no_auto_install: bool,
    quiet: bool,
) -> tuple[Path, dict | None]:
    try:
        return detect_gsasii_root(args_root, pattern_path), None
    except FileNotFoundError:
        if no_auto_install:
            raise

    if args_root:
        install_dir = Path(args_root)
    elif install_dir_arg:
        install_dir = Path(install_dir_arg)
    else:
        install_dir = default_gsasii_install_dir()

    install_info = install_gsasii_with_gitstrap(install_dir, quiet)
    return install_dir.resolve(), install_info


def bootstrap_gsas2(gsasii_root: Path):
    if str(gsasii_root) not in sys.path:
        sys.path.insert(0, str(gsasii_root))
    from GSASII import GSASIIpath

    GSASIIpath.SetBinaryPath(True)
    import GSASII.GSASIIscriptable as G2sc

    return G2sc


def parse_background_sequence(raw: str) -> list[int]:
    values = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        values.append(int(item))
    if not values:
        raise ValueError("background-sequence must contain at least one integer")
    return values


def discover_cifs(pattern_path: Path) -> list[Path]:
    discovered = []
    for folder in (pattern_path.parent / "cifs", pattern_path.parent):
        if not folder.exists():
            continue
        discovered.extend(sorted(folder.glob("*.cif")))
    discovered.extend(sorted(pattern_path.parent.glob("*/*.cif")))
    unique = []
    seen = set()
    for path in discovered:
        key = str(path.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(path.resolve())
    return unique


def resolve_cifs(pattern_path: Path, raw_cifs: list[str] | None) -> list[Path]:
    if raw_cifs:
        cifs = [Path(item).resolve() for item in raw_cifs]
    else:
        cifs = discover_cifs(pattern_path)
    if not cifs:
        raise FileNotFoundError("No CIF files were provided or auto-discovered.")
    for cif in cifs:
        if not cif.exists():
            raise FileNotFoundError(f"CIF not found: {cif}")
    return cifs


def resolve_phase_names(cifs: list[Path], raw_names: list[str] | None) -> list[str]:
    if raw_names:
        if len(raw_names) != len(cifs):
            raise ValueError("--phase-names must match the number of CIF files.")
        return raw_names
    return [cif.stem for cif in cifs]


def extract_numeric_values(line: str) -> list[float]:
    values = []
    for token in line.replace(",", " ").split():
        try:
            values.append(float(token))
        except ValueError:
            continue
    return values


def looks_like_scan_metadata(first_row: list[float], second_row: list[float]) -> bool:
    if len(first_row) < 3 or len(second_row) < 2:
        return False
    start = first_row[0]
    step = first_row[1]
    if step <= 0 or abs(step) >= 5:
        return False
    tol = max(abs(step) * 0.25, 1e-4)
    second_x = second_row[0]
    near_start = abs(second_x - start) <= tol
    near_next = abs(second_x - (start + step)) <= tol
    intensity_mismatch = abs(second_row[1]) > max(abs(step) * 5, 1.0)
    return intensity_mismatch and (near_start or near_next)


def parse_pattern_rows(pattern_path: Path) -> tuple[list[list[float]], bool]:
    rows = []
    for line in pattern_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "%", ";", "!", "//")):
            continue
        values = extract_numeric_values(stripped)
        if len(values) >= 2:
            rows.append(values)
    if len(rows) < 2:
        raise RuntimeError(f"Could not parse enough numeric rows from {pattern_path}")
    skipped_metadata = False
    if looks_like_scan_metadata(rows[0], rows[1]):
        rows = rows[1:]
        skipped_metadata = True
    return rows, skipped_metadata


def prepare_xye(pattern_path: Path, output_path: Path, esd_factor: float) -> dict:
    raw_rows, skipped_metadata = parse_pattern_rows(pattern_path)
    explicit_esd = all(len(row) >= 3 for row in raw_rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    prepared_rows = []
    with output_path.open("w", encoding="ascii", newline="\n") as handle:
        handle.write(f"# source: {pattern_path.name}\n")
        if skipped_metadata:
            handle.write("# skipped metadata row detected at file start\n")
        if explicit_esd:
            handle.write("# explicit sigma/esd column preserved from input\n")
        else:
            handle.write(f"# explicit esd = {esd_factor:.3f} * sqrt(I)\n")

        for row in raw_rows:
            x = float(row[0])
            y = float(row[1])
            if explicit_esd:
                esd = max(abs(float(row[2])), 1e-6)
            else:
                esd = max(math.sqrt(max(y, 1.0)) * esd_factor, 1.0)
            prepared_rows.append((x, y, esd))
            handle.write(f"{x:.6f} {y:.6f} {esd:.6f}\n")

    assumption = None
    if not explicit_esd:
        assumption = f"Generated esd as {esd_factor:.3f} * sqrt(I) because the input pattern lacked a third sigma/esd column."

    return {
        "rows": prepared_rows,
        "explicit_esd": explicit_esd,
        "skipped_metadata": skipped_metadata,
        "assumption": assumption,
    }


def write_default_instprm(path: Path, wavelength: float) -> None:
    lines = [
        "#GSAS-II instrument parameter file; do not add/delete items!",
        "Type:PXC;Bank:1",
        f"Lam:{wavelength:.6f}",
        "Zero:0.0;Polariz.:0.7",
        "U:2.0;V:-2.0;W:5.0;X:0.1;Y:0.0;Z:0.0;SH/L:0.015",
        "Azimuth:0.0;InstrName:Generated_single_wavelength",
        "Diff-type:Bragg-Brentano;Gonio.radius:200.0",
        "",
    ]
    path.write_text("\n".join(lines), encoding="ascii")


def residuals(hist) -> dict:
    raw = dict(hist.residuals)
    rwp = float(raw.get("wR", raw.get("Rwp", np.nan)))
    rexp = float(raw.get("wRmin", np.nan))
    if np.isfinite(rwp) and np.isfinite(rexp) and rexp > 0:
        gof = rwp / rexp
        chi2 = gof * gof
    else:
        gof = float(raw.get("GOF", np.nan))
        chi2 = float(raw.get("reduced_chi2", np.nan))
    clean_raw = {}
    for key, value in raw.items():
        if isinstance(value, (int, float, np.floating)):
            clean_raw[key] = float(value)
        else:
            clean_raw[key] = value
    return {"Rwp": rwp, "Rexp": rexp, "chi2": chi2, "GOF": gof, "raw": clean_raw}


def curve_data(hist) -> np.ndarray:
    cols = [
        np.asarray(hist.getdata(key), dtype=float)
        for key in ("x", "yobs", "ycalc", "background", "residual")
    ]
    return np.vstack(cols).T


def save_curve(hist, path: Path) -> None:
    data = curve_data(hist)
    np.savetxt(
        path,
        data,
        delimiter=",",
        header="two_theta,y_obs,y_calc,background,y_obs_minus_y_calc",
        comments="",
    )


def compact_space_group_label(space_group: str | None) -> str:
    if not space_group:
        return ""
    return str(space_group).replace(" ", "")


def phase_plot_label(phase) -> str:
    return str(phase.name)


def phase_reflection_positions(hist, phase_name: str) -> np.ndarray:
    try:
        reflection_info = hist.reflections().get(phase_name, {})
    except Exception:
        return np.array([], dtype=float)

    ref_list = reflection_info.get("RefList")
    if ref_list is None:
        return np.array([], dtype=float)

    array = np.asarray(ref_list, dtype=float)
    if array.ndim != 2 or array.shape[1] < 6:
        return np.array([], dtype=float)

    two_theta = array[:, 5]
    two_theta = two_theta[np.isfinite(two_theta)]
    if not len(two_theta):
        return np.array([], dtype=float)
    return np.unique(np.round(two_theta, 6))


def save_plot(hist, path: Path, title: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.ticker import MultipleLocator

    data = curve_data(hist)
    x, yobs, ycalc, background, diff = data.T

    _ = title
    finite_y = np.isfinite(yobs) & np.isfinite(ycalc)
    if not np.any(finite_y):
        finite_y = np.isfinite(yobs)
    if not np.any(finite_y):
        finite_y = np.isfinite(ycalc)

    yobs_finite = yobs[finite_y]
    ycalc_finite = ycalc[finite_y]
    main_min = float(np.nanmin(np.concatenate([yobs_finite, ycalc_finite])))
    main_max = float(np.nanmax(np.concatenate([yobs_finite, ycalc_finite])))
    main_range = max(main_max - main_min, 1.0)

    plt.rcParams.update(
        {
            "font.family": "STIXGeneral",
            "mathtext.fontset": "stix",
            "axes.unicode_minus": False,
        }
    )

    phase_palette = ["#19b85c", "#f59e0b", "#7c3aed", "#14b8a6", "#e11d48"]
    phase_tick_handles = []
    phase_tick_rows = []
    phase_row_gap = 0.032 * main_range
    tick_height = 0.024 * main_range
    tick_top = main_min - 0.11 * main_range

    if hasattr(hist, "proj"):
        for phase_index, phase in enumerate(hist.proj.phases()):
            positions = phase_reflection_positions(hist, phase.name)
            positions = positions[(positions >= np.nanmin(x)) & (positions <= np.nanmax(x))]
            if not len(positions):
                continue
            color = phase_palette[phase_index % len(phase_palette)]
            row_y = tick_top - len(phase_tick_rows) * phase_row_gap
            phase_tick_rows.append((positions, row_y, color))
            phase_tick_handles.append(
                Line2D(
                    [],
                    [],
                    color=color,
                    marker="|",
                    linestyle="None",
                    markersize=16,
                    markeredgewidth=1.2,
                    label=phase_plot_label(phase),
                )
            )

    tick_bottom = tick_top - max(len(phase_tick_rows) - 1, 0) * phase_row_gap
    diff_offset = tick_bottom - 0.13 * main_range
    diff_min = float(np.nanmin(diff[np.isfinite(diff)])) if np.any(np.isfinite(diff)) else 0.0
    diff_max = float(np.nanmax(diff[np.isfinite(diff)])) if np.any(np.isfinite(diff)) else 0.0
    y_bottom = min(diff_offset + diff_min, tick_bottom - 0.07 * main_range) - 0.03 * main_range
    y_top = main_max + 0.08 * main_range

    fig, axis = plt.subplots(figsize=(12.6, 9.6), dpi=180)
    axis.scatter(
        x,
        yobs,
        s=18,
        color="#5a5a5a",
        edgecolors="none",
        zorder=3,
    )
    axis.plot(x, ycalc, color="#ff3b30", lw=1.8, zorder=4)
    axis.plot(x, diff + diff_offset, color="#1565ff", lw=0.9, zorder=2)

    for positions, row_y, color in phase_tick_rows:
        axis.vlines(positions, row_y, row_y + tick_height, color=color, lw=0.9, zorder=1)

    axis.set_xlabel(r"$2\ \theta\ \mathrm{(degree)}$", fontsize=30, labelpad=22)
    axis.set_ylabel("Intensity (a.u.)", fontsize=32, labelpad=20)
    axis.set_xlim(float(np.nanmin(x)), float(np.nanmax(x)))
    axis.set_ylim(y_bottom, y_top)
    axis.set_yticks([])
    axis.xaxis.set_major_locator(MultipleLocator(10))
    axis.xaxis.set_minor_locator(MultipleLocator(5))
    axis.tick_params(axis="x", which="major", direction="out", length=10, width=2.2, labelsize=22, pad=8)
    axis.tick_params(axis="x", which="minor", direction="out", length=6, width=1.8)
    axis.tick_params(axis="y", which="both", length=0)
    for spine in axis.spines.values():
        spine.set_linewidth(2.0)

    legend_handles = [
        Line2D(
            [],
            [],
            linestyle="None",
            marker="o",
            color="#5a5a5a",
            markersize=7,
            label=r"$Y_{\mathrm{obs}}$",
        ),
        Line2D([], [], color="#ff3b30", lw=1.8, label=r"$Y_{\mathrm{calc}}$"),
        Line2D([], [], color="#1565ff", lw=0.9, label=r"$Y_{\mathrm{obs}}-Y_{\mathrm{calc}}$"),
    ]
    legend_handles.extend(phase_tick_handles)
    axis.legend(
        handles=legend_handles,
        loc="upper right",
        frameon=True,
        fancybox=False,
        framealpha=1.0,
        facecolor="white",
        edgecolor="black",
        fontsize=20,
        handlelength=2.2,
        handletextpad=0.4,
        borderpad=0.4,
        labelspacing=0.4,
    )
    axis.margins(x=0)
    fig.tight_layout()
    fig.savefig(path, facecolor="white", bbox_inches="tight")
    plt.close(fig)


def phase_hist_entry(phase) -> dict:
    return next(iter(phase.data["Histograms"].values()))


def set_scale_strategy(hist, phases: list) -> str:
    if len(phases) == 1:
        hist.data["Sample Parameters"]["Scale"] = [1.0, True]
        for phase in phases:
            entry = phase_hist_entry(phase)
            entry["Scale"][0] = max(entry["Scale"][0], 1.0)
            phase.set_HAP_refinements({"Scale": False})
        return "single_phase_histogram_scale"

    hist.data["Sample Parameters"]["Scale"] = [1.0, False]
    for phase in phases:
        entry = phase_hist_entry(phase)
        entry["Scale"][0] = max(entry["Scale"][0], 1.0)
        phase.set_HAP_refinements({"Scale": True})
    return "multiphase_phase_fraction_scales"


def activate_scale_refinement(hist, phases: list, active_phase_indexes: list[int] | None) -> None:
    if len(phases) == 1:
        hist.data["Sample Parameters"]["Scale"][1] = True
        for phase in phases:
            phase_hist_entry(phase)["Scale"][1] = False
        return

    hist.data["Sample Parameters"]["Scale"][1] = False
    if active_phase_indexes is None:
        active_phase_indexes = list(range(len(phases)))
    active = set(active_phase_indexes)
    for index, phase in enumerate(phases):
        phase_hist_entry(phase)["Scale"][1] = index in active


def clear_all_refinement_flags(hist, phases: list) -> None:
    hist.clear_refinements(
        {
            "Sample Parameters": ["Scale"],
            "Instrument Parameters": [
                "Zero",
                "U",
                "V",
                "W",
                "X",
                "Y",
                "SH/L",
            ],
        }
    )
    hist.clear_refinements({"Background": True})
    for phase in phases:
        phase.clear_refinements({"Cell": True})
        clear_atom_refinement_flags(phase)
        phase.clear_HAP_refinements(
            {
                "Scale": True,
                "Size": True,
                "Mustrain": True,
                "Pref.Ori.": True,
                "HStrain": True,
            }
        )


def current_block_value(block, default: float) -> float:
    if len(block) > 1 and isinstance(block[1], (list, tuple)) and block[1]:
        value = float(block[1][0])
        if np.isfinite(value) and value > 0:
            return value
    return float(default)


def enable_size_refinement(phase) -> None:
    entry = phase_hist_entry(phase)
    size_value = current_block_value(entry.get("Size", []), 1.0)
    phase.set_HAP_refinements(
        {"Size": {"type": "isotropic", "value": size_value, "refine": True}}
    )


def enable_mustrain_refinement(phase) -> None:
    phase.set_HAP_refinements({"Mustrain": {"type": "isotropic", "refine": True}})


def normalize_atom_flags(flags: str) -> str:
    order = "FXU"
    normalized = []
    for token in order:
        if token in flags and token not in normalized:
            normalized.append(token)
    return "".join(normalized)


def clear_atom_refinement_flags(phase) -> None:
    for atom in phase.atoms():
        atom.refinement_flags = " "


def phase_has_atoms(phase) -> bool:
    return any(True for _ in phase.atoms())


def atom_phase_flag_map(phases: list, phase_indexes: list[int], flags: str) -> dict[int, str] | None:
    normalized = normalize_atom_flags(flags)
    if not normalized:
        return None
    mapping = {}
    for phase_index in phase_indexes:
        if phase_has_atoms(phases[phase_index]):
            mapping[phase_index] = normalized
    return mapping or None


def safe_token(text: str) -> str:
    token = "".join(ch if ch.isalnum() else "_" for ch in text)
    token = token.strip("_").lower()
    return token or "phase"


def working_project_path(output_dir: Path) -> Path:
    return (output_dir / "final_refinement.gpx").resolve()


def copy_snapshot(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    if source.resolve() == destination.resolve():
        return
    shutil.copyfile(source, destination)


def run_configured_stage(
    gpx,
    hist,
    phases: list,
    output_dir: Path,
    history: list[dict],
    stage_number: int,
    label: str,
    notes: str,
    cycles: int,
    quiet: bool,
    background_coeffs: int,
    active_scale_phase_indexes: list[int] | None,
    instrument_keys: list[str] | None = None,
    cell_phase_indexes: list[int] | None = None,
    size_phase_indexes: list[int] | None = None,
    mustrain_phase_indexes: list[int] | None = None,
    pref_phase_indexes: list[int] | None = None,
    atom_phase_flags: dict[int, str] | None = None,
) -> dict:
    clear_all_refinement_flags(hist, phases)
    set_background(hist, background_coeffs)
    activate_scale_refinement(hist, phases, active_scale_phase_indexes)

    if instrument_keys:
        hist.set_refinements({"Instrument Parameters": list(dict.fromkeys(instrument_keys))})
    for phase_index in cell_phase_indexes or []:
        phases[phase_index].set_refinements({"Cell": True})
    for phase_index in size_phase_indexes or []:
        enable_size_refinement(phases[phase_index])
    for phase_index in mustrain_phase_indexes or []:
        enable_mustrain_refinement(phases[phase_index])
    for phase_index in pref_phase_indexes or []:
        phases[phase_index].set_HAP_refinements({"Pref.Ori.": True})
    for phase_index, atom_flags in (atom_phase_flags or {}).items():
        normalized = normalize_atom_flags(atom_flags)
        if normalized:
            phases[phase_index].set_refinements({"Atoms": {"all": normalized}})

    return run_stage(
        gpx,
        hist,
        output_dir,
        history,
        f"{stage_number:02d}_{label}",
        notes,
        cycles,
        quiet,
    )


def metrics_are_finite(result: dict) -> bool:
    return all(np.isfinite(result[key]) for key in ("Rwp", "chi2", "GOF"))


def trial_stage_is_acceptable(candidate: dict, baseline: dict | None) -> tuple[bool, str]:
    if not metrics_are_finite(candidate):
        return False, "non-finite residuals"
    if baseline is None or not metrics_are_finite(baseline):
        return True, "accepted"

    rwp_limit = min(baseline["Rwp"] + 0.02, baseline["Rwp"] * 1.002)
    chi2_limit = min(baseline["chi2"] + 0.05, baseline["chi2"] * 1.01)
    if candidate["Rwp"] <= rwp_limit and candidate["chi2"] <= chi2_limit:
        return True, "accepted"

    return (
        False,
        f"worse fit (Rwp {candidate['Rwp']:.4f} vs {baseline['Rwp']:.4f}, "
        f"chi2 {candidate['chi2']:.4f} vs {baseline['chi2']:.4f})",
    )


def reload_project_state(
    gpx,
    checkpoint_path: Path,
    hist_name: str,
    phase_names: list[str],
    active_project_path: Path,
):
    restored = gpx.__class__(str(checkpoint_path), newgpx=str(active_project_path))
    hist = restored.histogram(hist_name)
    phases = [restored.phase(name) for name in phase_names]
    return restored, hist, phases


def mark_reverted_trial_stage(
    history: list[dict],
    history_length_before: int,
    stage_name: str,
    notes: str,
    reason: str,
    fallback_result: dict | None,
    exception: bool = False,
) -> None:
    if len(history) > history_length_before and history[-1].get("stage") == stage_name:
        record = history[-1]
    else:
        record = {
            "stage": stage_name,
            "notes": notes,
            "Rwp": float("nan"),
            "Rexp": float("nan"),
            "chi2": float("nan"),
            "GOF": float("nan"),
        }
        if fallback_result:
            for key in ("Rwp", "Rexp", "chi2", "GOF"):
                if key in fallback_result:
                    record[key] = fallback_result[key]
        history.append(record)

    record["reverted"] = True
    record["revert_reason"] = reason
    revert_tag = "[reverted on exception]" if exception else "[reverted]"
    if revert_tag not in record["notes"]:
        record["notes"] = f"{record['notes']} {revert_tag}".strip()


def run_trial_configured_stage(
    gpx,
    hist,
    phases: list,
    output_dir: Path,
    history: list[dict],
    stage_number: int,
    label: str,
    notes: str,
    cycles: int,
    quiet: bool,
    background_coeffs: int,
    active_scale_phase_indexes: list[int] | None,
    baseline_result: dict | None,
    instrument_keys: list[str] | None = None,
    cell_phase_indexes: list[int] | None = None,
    size_phase_indexes: list[int] | None = None,
    mustrain_phase_indexes: list[int] | None = None,
    pref_phase_indexes: list[int] | None = None,
    atom_phase_flags: dict[int, str] | None = None,
) -> tuple[object, object, list, dict]:
    checkpoint_path = output_dir / "_stable_trial_checkpoint.gpx"
    active_project_path = working_project_path(output_dir)
    gpx.save(str(active_project_path))
    copy_snapshot(active_project_path, checkpoint_path)
    hist_name = hist.name
    phase_names = [phase.name for phase in phases]
    stage_name = f"{stage_number:02d}_{label}"
    history_length_before = len(history)
    try:
        candidate = run_configured_stage(
            gpx,
            hist,
            phases,
            output_dir,
            history,
            stage_number,
            label,
            notes,
            cycles,
            quiet,
            background_coeffs,
            active_scale_phase_indexes,
            instrument_keys=instrument_keys,
            cell_phase_indexes=cell_phase_indexes,
            size_phase_indexes=size_phase_indexes,
            mustrain_phase_indexes=mustrain_phase_indexes,
            pref_phase_indexes=pref_phase_indexes,
            atom_phase_flags=atom_phase_flags,
        )
    except Exception as exc:
        log(f"Reverting trial stage {label} after exception: {exc}", quiet)
        mark_reverted_trial_stage(
            history,
            history_length_before,
            stage_name,
            notes,
            f"exception: {exc}",
            baseline_result,
            exception=True,
        )
        gpx, hist, phases = reload_project_state(
            gpx,
            checkpoint_path,
            hist_name,
            phase_names,
            active_project_path,
        )
        return gpx, hist, phases, baseline_result
    accepted, reason = trial_stage_is_acceptable(candidate, baseline_result)
    if accepted:
        return gpx, hist, phases, candidate

    mark_reverted_trial_stage(
        history,
        history_length_before,
        stage_name,
        notes,
        reason,
        baseline_result,
    )
    log(f"Reverting {history[-1]['stage']}: {reason}", quiet)
    gpx, hist, phases = reload_project_state(
        gpx,
        checkpoint_path,
        hist_name,
        phase_names,
        active_project_path,
    )
    return gpx, hist, phases, baseline_result


def run_phase_refinement_sequence(
    gpx,
    hist,
    phases: list,
    output_dir: Path,
    history: list[dict],
    stage_number: int,
    phase_index: int,
    latest: dict | None,
    stage_prefix: str,
    notes_prefix: str,
    background_coeffs: int,
    cycles: int,
    final_cycles: int,
    quiet: bool,
    refine_preferred_orientation: bool,
    disable_size_microstrain: bool,
    refine_atomic_parameters: bool,
) -> tuple[object, object, list, dict, int]:
    active_scale_phase_indexes = [phase_index]

    gpx, hist, phases, latest = run_trial_configured_stage(
        gpx,
        hist,
        phases,
        output_dir,
        history,
        stage_number,
        f"{stage_prefix}_zero",
        f"{notes_prefix} single-parameter refinement: Zero",
        cycles,
        quiet,
        background_coeffs,
        active_scale_phase_indexes,
        latest,
        instrument_keys=["Zero"],
    )
    stage_number += 1

    gpx, hist, phases, latest = run_trial_configured_stage(
        gpx,
        hist,
        phases,
        output_dir,
        history,
        stage_number,
        f"{stage_prefix}_cell",
        f"{notes_prefix} single-parameter refinement: Cell",
        cycles,
        quiet,
        background_coeffs,
        active_scale_phase_indexes,
        latest,
        cell_phase_indexes=[phase_index],
    )
    stage_number += 1

    for label, display_name, instrument_keys in SINGLE_PARAMETER_INSTRUMENT_STAGES:
        if label == "zero":
            continue
        gpx, hist, phases, latest = run_trial_configured_stage(
            gpx,
            hist,
            phases,
            output_dir,
            history,
            stage_number,
            f"{stage_prefix}_{label}",
            f"{notes_prefix} single-parameter refinement: {display_name}",
            cycles,
            quiet,
            background_coeffs,
            active_scale_phase_indexes,
            latest,
            instrument_keys=instrument_keys,
        )
        stage_number += 1

    if not disable_size_microstrain:
        gpx, hist, phases, latest = run_trial_configured_stage(
            gpx,
            hist,
            phases,
            output_dir,
            history,
            stage_number,
            f"{stage_prefix}_size",
            f"{notes_prefix} single-parameter refinement: Isotropic size",
            cycles,
            quiet,
            background_coeffs,
            active_scale_phase_indexes,
            latest,
            size_phase_indexes=[phase_index],
        )
        stage_number += 1
        gpx, hist, phases, latest = run_trial_configured_stage(
            gpx,
            hist,
            phases,
            output_dir,
            history,
            stage_number,
            f"{stage_prefix}_mustrain",
            f"{notes_prefix} single-parameter refinement: Isotropic microstrain",
            cycles,
            quiet,
            background_coeffs,
            active_scale_phase_indexes,
            latest,
            mustrain_phase_indexes=[phase_index],
        )
        stage_number += 1

    for label, display_name, instrument_keys in PROGRESSIVE_UVW_JOINT_STAGES:
        gpx, hist, phases, latest = run_trial_configured_stage(
            gpx,
            hist,
            phases,
            output_dir,
            history,
            stage_number,
            f"{stage_prefix}_{label}",
            f"{notes_prefix} progressive joint refinement: {display_name}",
            final_cycles,
            quiet,
            background_coeffs,
            active_scale_phase_indexes,
            latest,
            instrument_keys=instrument_keys,
            cell_phase_indexes=[phase_index],
        )
        stage_number += 1

    if refine_preferred_orientation:
        gpx, hist, phases, latest = run_trial_configured_stage(
            gpx,
            hist,
            phases,
            output_dir,
            history,
            stage_number,
            f"{stage_prefix}_pref_ori",
            f"{notes_prefix} preferred-orientation refinement",
            final_cycles,
            quiet,
            background_coeffs,
            active_scale_phase_indexes,
            latest,
            instrument_keys=LATE_STAGE_INSTRUMENT_KEYS,
            cell_phase_indexes=[phase_index],
            pref_phase_indexes=[phase_index],
        )
        stage_number += 1

    if refine_atomic_parameters and phase_has_atoms(phases[phase_index]):
        for label, display_name, atom_flags in ATOMIC_REFINEMENT_STAGES:
            gpx, hist, phases, latest = run_trial_configured_stage(
                gpx,
                hist,
                phases,
                output_dir,
                history,
                stage_number,
                f"{stage_prefix}_{label}",
                f"{notes_prefix} {display_name}",
                final_cycles,
                quiet,
                background_coeffs,
                active_scale_phase_indexes,
                latest,
                instrument_keys=LATE_STAGE_INSTRUMENT_KEYS,
                cell_phase_indexes=[phase_index],
                pref_phase_indexes=[phase_index] if refine_preferred_orientation else None,
                atom_phase_flags={phase_index: atom_flags},
            )
            stage_number += 1

    return gpx, hist, phases, latest, stage_number


def run_single_phase_strategy(
    gpx,
    hist,
    phases: list,
    output_dir: Path,
    history: list[dict],
    background_sequence: list[int],
    cycles: int,
    final_cycles: int,
    quiet: bool,
    refine_preferred_orientation: bool,
    disable_size_microstrain: bool,
    refine_atomic_parameters: bool,
) -> tuple[object, object, list, dict]:
    phase = phases[0]
    phase_token = safe_token(phase.name)
    stage_number = 1

    latest = run_configured_stage(
        gpx,
        hist,
        phases,
        output_dir,
        history,
        stage_number,
        f"{phase_token}_scale_bkg{background_sequence[0]}",
        "initial background plus scale",
        cycles,
        quiet,
        background_sequence[0],
        [0],
    )
    stage_number += 1

    gpx, hist, phases, latest, stage_number = run_phase_refinement_sequence(
        gpx,
        hist,
        phases,
        output_dir,
        history,
        stage_number,
        0,
        latest,
        phase_token,
        f"phase {phase.name}",
        background_sequence[0],
        cycles,
        final_cycles,
        quiet,
        refine_preferred_orientation,
        disable_size_microstrain,
        refine_atomic_parameters,
    )

    late_atom_flags = atom_phase_flag_map(phases, [0], "FXU") if refine_atomic_parameters else None
    for coeffs in background_sequence[1:]:
        gpx, hist, phases, latest = run_trial_configured_stage(
            gpx,
            hist,
            phases,
            output_dir,
            history,
            stage_number,
            f"{phase_token}_late_bkg{coeffs}",
            f"phase {phase.name} final background-expanded refinement ({coeffs} coeffs)",
            final_cycles,
            quiet,
            coeffs,
            [0],
            latest,
            instrument_keys=LATE_STAGE_INSTRUMENT_KEYS,
            cell_phase_indexes=[0],
            pref_phase_indexes=[0] if refine_preferred_orientation else None,
            atom_phase_flags=late_atom_flags,
        )
        stage_number += 1

    return gpx, hist, phases, latest


def run_multiphase_strategy(
    gpx,
    hist,
    phases: list,
    output_dir: Path,
    history: list[dict],
    background_sequence: list[int],
    cycles: int,
    final_cycles: int,
    quiet: bool,
    refine_preferred_orientation: bool,
    disable_size_microstrain: bool,
    refine_atomic_parameters: bool,
) -> tuple[object, object, list, dict]:
    stage_number = 1
    all_phase_indexes = list(range(len(phases)))

    latest = run_configured_stage(
        gpx,
        hist,
        phases,
        output_dir,
        history,
        stage_number,
        f"multiphase_scale_bkg{background_sequence[0]}",
        "initial all-phase scale plus background",
        cycles,
        quiet,
        background_sequence[0],
        None,
    )
    stage_number += 1

    for phase_index in range(len(phases)):
        phase = phases[phase_index]
        phase_name = phase.name
        phase_tag = f"phase{phase_index + 1:02d}_{safe_token(phase.name)}"

        gpx, hist, phases, latest = run_trial_configured_stage(
            gpx,
            hist,
            phases,
            output_dir,
            history,
            stage_number,
            f"{phase_tag}_scale",
            f"phase {phase.name} scale rebalance",
            cycles,
            quiet,
            background_sequence[0],
            [phase_index],
            latest,
        )
        stage_number += 1

        phase = phases[phase_index]
        gpx, hist, phases, latest, stage_number = run_phase_refinement_sequence(
            gpx,
            hist,
            phases,
            output_dir,
            history,
            stage_number,
            phase_index,
            latest,
            phase_tag,
            f"phase {phase_name}",
            background_sequence[0],
            cycles,
            final_cycles,
            quiet,
            refine_preferred_orientation,
            disable_size_microstrain,
            refine_atomic_parameters,
        )

    all_phase_indexes = list(range(len(phases)))
    global_atom_flags = atom_phase_flag_map(phases, all_phase_indexes, "FXU") if refine_atomic_parameters else None
    gpx, hist, phases, latest = run_trial_configured_stage(
        gpx,
        hist,
        phases,
        output_dir,
        history,
        stage_number,
        "multiphase_global_late",
        "global refinement with all phases active after phasewise progressive, preferred-orientation, and atomic passes",
        final_cycles,
        quiet,
        background_sequence[0],
        None,
        latest,
        instrument_keys=LATE_STAGE_INSTRUMENT_KEYS,
        cell_phase_indexes=all_phase_indexes,
        pref_phase_indexes=all_phase_indexes if refine_preferred_orientation else None,
        atom_phase_flags=global_atom_flags,
    )
    stage_number += 1

    for coeffs in background_sequence[1:]:
        gpx, hist, phases, latest = run_trial_configured_stage(
            gpx,
            hist,
            phases,
            output_dir,
            history,
            stage_number,
            f"multiphase_global_late_bkg{coeffs}",
            f"global final background-expanded refinement ({coeffs} coeffs)",
            final_cycles,
            quiet,
            coeffs,
            None,
            latest,
            instrument_keys=LATE_STAGE_INSTRUMENT_KEYS,
            cell_phase_indexes=all_phase_indexes,
            pref_phase_indexes=all_phase_indexes if refine_preferred_orientation else None,
            atom_phase_flags=global_atom_flags,
        )
        stage_number += 1

    return gpx, hist, phases, latest


def target_met(result: dict, target_rwp: float, target_chi2: float) -> bool:
    return result["Rwp"] < target_rwp and result["chi2"] < target_chi2


def run_stage(
    gpx,
    hist,
    output_dir: Path,
    history: list[dict],
    name: str,
    notes: str,
    cycles: int,
    quiet: bool,
) -> dict:
    active_project_path = working_project_path(output_dir)
    gpx.save(str(active_project_path))
    gpx.set_Controls("cycles", int(cycles))
    gpx.refine(makeBack=True)
    result = {"stage": name, "notes": notes, **residuals(hist)}
    history.append(result)
    log(
        f"{name}: Rwp={result['Rwp']:.4f}, chi2={result['chi2']:.4f}, GOF={result['GOF']:.4f}",
        quiet,
    )
    gpx.save(str(active_project_path))
    copy_snapshot(active_project_path, output_dir / f"{name}.gpx")
    copy_snapshot(active_project_path.with_suffix(".lst"), output_dir / f"{name}.lst")
    save_curve(hist, output_dir / f"{name}_curve.csv")
    save_plot(
        hist,
        output_dir / f"{name}_fit.png",
        f"{name}: Rwp={result['Rwp']:.3f}, chi2={result['chi2']:.3f}",
    )
    return result


def set_background(hist, coeffs: int) -> None:
    hist.set_refinements(
        {"Background": {"type": "chebyschev-1", "no. coeffs": int(coeffs), "refine": True}}
    )


def instrument_value(inst: dict, key: str):
    if key not in inst:
        return None
    value = inst[key]
    if isinstance(value, (list, tuple)):
        for item in value[1:]:
            if isinstance(item, (int, float, np.floating)):
                return float(item)
        for item in value:
            if isinstance(item, (int, float, np.floating)):
                return float(item)
    if isinstance(value, (int, float, np.floating)):
        return float(value)
    return value


def summarize_phase(phase, cif_path: Path) -> dict:
    cell = phase.data["General"]["Cell"]
    entry = phase_hist_entry(phase)
    size_block = entry.get("Size", [])
    mustrain_block = entry.get("Mustrain", [])
    pref_block = entry.get("Pref.Ori.", [])

    size_value = None
    if len(size_block) > 1 and isinstance(size_block[1], (list, tuple)) and size_block[1]:
        size_value = float(size_block[1][0])

    mustrain_value = None
    if len(mustrain_block) > 1 and isinstance(mustrain_block[1], (list, tuple)) and mustrain_block[1]:
        mustrain_value = float(mustrain_block[1][0])

    pref_value = None
    if len(pref_block) > 1 and isinstance(pref_block[1], (int, float, np.floating)):
        pref_value = float(pref_block[1])

    return {
        "phase_name": phase.name,
        "cif": str(cif_path),
        "atom_count": sum(1 for _ in phase.atoms()),
        "cell": {
            "a": float(cell[1]),
            "b": float(cell[2]),
            "c": float(cell[3]),
            "alpha": float(cell[4]),
            "beta": float(cell[5]),
            "gamma": float(cell[6]),
            "volume": float(cell[7]),
        },
        "scale": float(entry["Scale"][0]),
        "scale_refined": bool(entry["Scale"][1]),
        "size_model": size_block[0] if size_block else None,
        "size_value": size_value,
        "mustrain_model": mustrain_block[0] if mustrain_block else None,
        "mustrain_value": mustrain_value,
        "preferred_orientation": pref_value,
    }


def write_phase_csv(path: Path, phases: list[dict]) -> None:
    fieldnames = [
        "phase_name",
        "cif",
        "atom_count",
        "a",
        "b",
        "c",
        "alpha",
        "beta",
        "gamma",
        "volume",
        "scale",
        "scale_refined",
        "size_model",
        "size_value",
        "mustrain_model",
        "mustrain_value",
        "preferred_orientation",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for phase in phases:
            row = {
                "phase_name": phase["phase_name"],
                "cif": phase["cif"],
                "atom_count": phase["atom_count"],
                "a": phase["cell"]["a"],
                "b": phase["cell"]["b"],
                "c": phase["cell"]["c"],
                "alpha": phase["cell"]["alpha"],
                "beta": phase["cell"]["beta"],
                "gamma": phase["cell"]["gamma"],
                "volume": phase["cell"]["volume"],
                "scale": phase["scale"],
                "scale_refined": phase["scale_refined"],
                "size_model": phase["size_model"],
                "size_value": phase["size_value"],
                "mustrain_model": phase["mustrain_model"],
                "mustrain_value": phase["mustrain_value"],
                "preferred_orientation": phase["preferred_orientation"],
            }
            writer.writerow(row)


def summarize_atoms(phase) -> list[dict]:
    atoms = []
    for atom in phase.atoms():
        x, y, z = atom.coordinates
        adp_flag = atom.adp_flag
        uiso = None
        uij = [None, None, None, None, None, None]
        if adp_flag == "I":
            uiso = float(atom.ADP)
        else:
            values = [float(value) for value in atom.ADP]
            uij[: len(values)] = values
        atoms.append(
            {
                "phase_name": phase.name,
                "label": atom.label,
                "type": atom.type,
                "element": atom.element,
                "x": float(x),
                "y": float(y),
                "z": float(z),
                "occupancy": float(atom.occupancy),
                "adp_flag": adp_flag,
                "uiso": uiso,
                "u11": uij[0],
                "u22": uij[1],
                "u33": uij[2],
                "u12": uij[3],
                "u13": uij[4],
                "u23": uij[5],
                "refinement_flags": atom.refinement_flags.strip(),
            }
        )
    return atoms


def write_atom_csv(path: Path, atoms: list[dict]) -> None:
    fieldnames = [
        "phase_name",
        "label",
        "type",
        "element",
        "x",
        "y",
        "z",
        "occupancy",
        "adp_flag",
        "uiso",
        "u11",
        "u22",
        "u33",
        "u12",
        "u13",
        "u23",
        "refinement_flags",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for atom in atoms:
            writer.writerow(atom)


def main() -> None:
    args = parse_args()
    pattern_path = Path(args.pattern).resolve()
    if not pattern_path.exists():
        raise FileNotFoundError(f"Pattern not found: {pattern_path}")

    cifs = resolve_cifs(pattern_path, args.cifs)
    phase_names = resolve_phase_names(cifs, args.phase_names)
    background_sequence = parse_background_sequence(args.background_sequence)

    output_dir = (
        Path(args.output_dir).resolve()
        if args.output_dir
        else (pattern_path.parent / "gsas2_refinement" / pattern_path.stem).resolve()
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    prepared_xye = output_dir / "prepared_pattern.xye"
    prepared = prepare_xye(pattern_path, prepared_xye, args.esd_factor)

    instprm_path = Path(args.instprm).resolve() if args.instprm else output_dir / "generated.instprm"
    if args.instprm:
        if not instprm_path.exists():
            raise FileNotFoundError(f"instprm not found: {instprm_path}")
        instprm_generated = False
    else:
        write_default_instprm(instprm_path, args.wavelength)
        instprm_generated = True

    gsasii_root, gsasii_install = resolve_gsasii_root(
        args.gsasii_root,
        pattern_path,
        args.gsasii_install_dir,
        args.no_auto_install_gsasii,
        args.quiet,
    )
    log(f"Using GSAS-II root: {gsasii_root}", args.quiet)
    G2sc = bootstrap_gsas2(gsasii_root)

    gpx_path = output_dir / "final_refinement.gpx"
    if gpx_path.exists():
        gpx_path.unlink()

    gpx = G2sc.G2Project(newgpx=str(gpx_path))
    hist = gpx.add_powder_histogram(str(prepared_xye), str(instprm_path), fmthint="xye")
    phases = []
    for cif_path, phase_name in zip(cifs, phase_names):
        phases.append(gpx.add_phase(str(cif_path), phasename=phase_name, histograms=[hist]))

    x_values = [row[0] for row in prepared["rows"]]
    if args.limits:
        low, high = args.limits
    else:
        low, high = min(x_values), max(x_values)
    hist.set_refinements({"Limits": [float(low), float(high)]})

    scale_strategy = set_scale_strategy(hist, phases)
    history = []
    if len(phases) == 1:
        gpx, hist, phases, latest = run_single_phase_strategy(
            gpx,
            hist,
            phases,
            output_dir,
            history,
            background_sequence,
            args.cycles,
            args.final_cycles,
            args.quiet,
            args.refine_preferred_orientation,
            args.disable_size_microstrain,
            args.refine_atomic_parameters,
        )
    else:
        gpx, hist, phases, latest = run_multiphase_strategy(
            gpx,
            hist,
            phases,
            output_dir,
            history,
            background_sequence,
            args.cycles,
            args.final_cycles,
            args.quiet,
            args.refine_preferred_orientation,
            args.disable_size_microstrain,
            args.refine_atomic_parameters,
        )

    gpx.save(str(gpx_path))
    save_curve(hist, output_dir / "final_curve.csv")
    save_plot(
        hist,
        output_dir / "final_fit.png",
        f"Final: Rwp={latest['Rwp']:.3f}, chi2={latest['chi2']:.3f}",
    )

    phase_summaries = [
        summarize_phase(phase, cif_path) for phase, cif_path in zip(phases, cifs)
    ]
    write_phase_csv(output_dir / "final_phase_parameters.csv", phase_summaries)
    atomic_summaries = []
    for phase in phases:
        atomic_summaries.extend(summarize_atoms(phase))
    write_atom_csv(output_dir / "final_atomic_parameters.csv", atomic_summaries)

    inst = hist.data["Instrument Parameters"][0]
    instrument_summary = {}
    for key in ("Lam", "Lam1", "Lam2", "I(L2)/I(L1)", "Zero", "U", "V", "W", "X", "Y", "Z", "SH/L"):
        value = instrument_value(inst, key)
        if value is not None:
            instrument_summary[key] = value

    assumptions = []
    if prepared["assumption"]:
        assumptions.append(prepared["assumption"])
    if instprm_generated:
        assumptions.append(
            f"Generated a default Bragg-Brentano instprm with single wavelength {args.wavelength:.6f}."
        )
    if gsasii_install:
        assumptions.append(
            f"GSAS-II was not found locally and was installed automatically into {gsasii_install['root']} using the official gitstrap.py installer."
        )

    summary = {
        "target_met": target_met(latest, args.target_rwp, args.target_chi2),
        "mode": "single-phase" if len(phases) == 1 else "multiphase",
        "scale_strategy": scale_strategy,
        "assumptions": assumptions,
        "inputs": {
            "pattern": str(pattern_path),
            "cifs": [str(path) for path in cifs],
            "phase_names": phase_names,
            "limits": [float(low), float(high)],
            "target_rwp": args.target_rwp,
            "target_chi2": args.target_chi2,
            "background_sequence": background_sequence,
            "refine_preferred_orientation": args.refine_preferred_orientation,
            "refine_atomic_parameters": args.refine_atomic_parameters,
            "disable_size_microstrain": args.disable_size_microstrain,
        },
        "gsasii_root": str(gsasii_root),
        "gsasii_install": gsasii_install,
        "instrument": instrument_summary,
        "final_metrics": latest,
        "phases": phase_summaries,
        "atomic_parameter_count": len(atomic_summaries),
        "history": history,
        "points": len(prepared["rows"]),
        "files": {
            "gpx": str(gpx_path),
            "plot": str(output_dir / "final_fit.png"),
            "curve": str(output_dir / "final_curve.csv"),
            "summary": str(output_dir / "final_summary.json"),
            "phase_csv": str(output_dir / "final_phase_parameters.csv"),
            "atomic_csv": str(output_dir / "final_atomic_parameters.csv"),
            "xye": str(prepared_xye),
            "instprm": str(instprm_path),
        },
    }
    (output_dir / "final_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    if not summary["target_met"]:
        raise SystemExit("Refinement finished, but the requested target was not reached.")


if __name__ == "__main__":
    main()
