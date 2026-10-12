---
name: gsas2-xrd-refinement
description: Perform GSAS-II based Rietveld refinement for powder XRD data using one or more CIF phases. Use when the task is to script GSAS-II, convert XY/XYE style patterns, refine single-phase or multiphase models, iterate toward target Rwp and chi2 values, and report final lattice, phase-fraction, profile, and atomic parameters from the GPX result.
---

# GSAS-II XRD Refinement

Use this skill when the user wants powder XRD Rietveld refinement in GSAS-II, especially when they provide an experimental pattern plus one or more CIF files and expect an automated refinement loop with reported `a/b/c`, phase fractions, fit metrics, and optional atomic outputs.

## Inputs

- Experimental pattern in `.dat`, `.xy`, `.xye`, or similar plain-text numeric format.
- One or more phase CIF files.
- Optional `.instprm` file. If absent, the bundled script can generate a conservative single-wavelength Bragg-Brentano instrument file and record that assumption.

If candidate phases are still unknown, use `mat-xrd-phase-analysis` first and come back here once the phase list is narrowed down.

## Workflow

1. Inspect the folder and identify the pattern file plus candidate CIFs.
2. Prefer an existing local GSAS-II source tree or install. The script accepts `--gsasii-root` or `GSASII_ROOT`.
3. If no local GSAS-II source tree is found, the script can automatically install GSAS-II with the official `gitstrap.py` installer into `~/.codex/tools/GSAS-II-src` or a user-specified directory.
4. Run `scripts/refine_gsas2.py` with the pattern and CIF list.
5. Read `final_summary.json`, `final_phase_parameters.csv`, and `final_atomic_parameters.csv`.
6. If the requested target is not met, rerun with a better `instprm`, tighter `--limits`, or a different phase list before forcing unstable late-stage refinements.

## Refinement Strategy

The bundled script uses a guarded staged strategy:

1. Refine one parameter group at a time.
2. Then run the requested joint `background + zero + cell + U/V/W` combinations in increasing complexity.
3. Then try preferred orientation.
4. Then try atomic parameters.
5. If a stage produces non-finite values or clearly worsens the fit, automatically revert to the last stable project state.

This keeps the requested refinement order, but avoids letting one unstable stage poison the final result.

### Single phase

The default order is:

1. Scale plus Chebyshev background
2. `Zero`
3. `Cell`
4. `U`
5. `V`
6. `W`
7. `X`
8. `Y`
9. `SH/L`
10. Optional isotropic size
11. Optional isotropic microstrain
12. `background + zero + cell + U`
13. `background + zero + cell + V`
14. `background + zero + cell + W`
15. `background + zero + cell + U + V`
16. `background + zero + cell + U + W`
17. `background + zero + cell + V + W`
18. `background + zero + cell + U + V + W`
19. Optional preferred orientation
20. Optional atomic coordinates `X`
21. Optional atomic displacement `U`
22. Optional atomic occupancy `F`
23. Optional combined atomic `FXU`
24. Optional higher-order background reruns with the best accepted late-stage model

Notes:

- Preferred orientation refinement is enabled by default. Disable with `--disable-preferred-orientation`.
- Atomic refinement is enabled by default. Disable with `--disable-atomic-refinement`.
- Size and microstrain can be skipped with `--disable-size-microstrain`.
- Atomic stages are attempted only when the phase actually has atoms that GSAS-II exposes scriptably.

### Multiphase

Multiphase jobs are refined phase-by-phase in strict order before a final global pass:

1. Initial all-phase scale plus background
2. Refine **phase 1** with the complete single-phase sequence above
3. Refine **phase 2** with the same complete sequence
4. Refine **phase 3** with the same complete sequence
5. Continue similarly for additional phases
6. Finish with a global late refinement where all phases are active together
7. Optionally expand the background and rerun the global late refinement

This means the script does not open all phases for every stage from the start. It first lets phase 1 settle, then phase 2, then phase 3, and only then does the final global cleanup.

It treats scaling differently for single-phase and multiphase fits:

- **Single phase:** refine histogram scale and keep phase HAP scale fixed.
- **Multiphase:** fix histogram scale and refine phase HAP scales as phase fractions. During the per-phase passes, only the current phase scale is opened.

### Stage rollback

Late stages such as preferred orientation, occupancy, or combined atomic refinement can easily destabilize a lab XRD fit. The script therefore saves a stable checkpoint before each trial stage.

If a trial stage:

- produces `NaN` or other non-finite metrics, or
- gives a clearly worse `Rwp` or `chi2`

then that stage is marked as attempted but reverted in `final_summary.json`, and the project is restored to the previous stable state before moving on.

This is especially important for multiphase jobs, where a bad late-stage change in one phase can otherwise damage later phases and the global pass.

If the pattern has only two columns, the script writes a derived `.xye` file with
`esd = esd_factor * sqrt(I)` and records that assumption in the summary.

If the user has a measured instrument parameter file, prefer passing `--instprm path\to\instrument.instprm` over the generated default.

If no local GSAS-II source tree is available, automatic installation is supported:

```powershell
.\.venv-gsas2\Scripts\python.exe `
  ~/.codex/skills/gsas2-xrd-refinement\scripts\refine_gsas2.py `
  --pattern E:\work\sample\scan.dat `
  --cifs E:\work\sample\phase.cif `
  --gsasii-install-dir E:\tools\GSAS-II-src `
  --output-dir E:\work\sample\gsas2_refinement
```

Disable this behavior with `--no-auto-install-gsasii` if you want the run to fail instead of installing GSAS-II.

## Quick Commands

Single phase:

```powershell
.\.venv-gsas2\Scripts\python.exe `
  ~/.codex/skills/gsas2-xrd-refinement\scripts\refine_gsas2.py `
  --pattern E:\work\sample\scan.dat `
  --cifs E:\work\sample\phase.cif `
  --output-dir E:\work\sample\gsas2_refinement
```

Multiphase:

```powershell
.\.venv-gsas2\Scripts\python.exe `
  ~/.codex/skills/gsas2-xrd-refinement\scripts\refine_gsas2.py `
  --pattern E:\work\mix\scan.xy `
  --cifs E:\work\mix\phase_a.cif E:\work\mix\phase_b.cif `
  --phase-names phase_a phase_b `
  --output-dir E:\work\mix\gsas2_refinement `
  --target-rwp 10 `
  --target-chi2 5
```

## Outputs

The script writes:

- `final_refinement.gpx`
- `final_fit.png`
- `final_curve.csv`
- `final_summary.json`
- `final_phase_parameters.csv`
- `final_atomic_parameters.csv`
- `prepared_pattern.xye`
- per-stage `.gpx/.lst/.csv/.png` snapshots
- optional GSAS-II install metadata and installer log path when auto-install is used

`final_summary.json` is the main artifact for reporting:

- `Rwp`, `Rexp`, `chi2`, `GOF`
- instrument parameters
- per-phase cell constants and scale terms
- atomic-stage enable flags
- assumptions such as generated `esd`
- per-stage `history`, including `reverted` and `revert_reason` for failed trial stages
- `gsasii_install` metadata when automatic installation was triggered

`final_phase_parameters.csv` reports refined phase-level terms such as:

- `a`, `b`, `c`
- `alpha`, `beta`, `gamma`
- `volume`
- `scale`
- `size_value`
- `mustrain_value`
- `preferred_orientation`
- `atom_count`

`final_atomic_parameters.csv` reports per-atom values such as:

- label and element
- `x`, `y`, `z`
- occupancy
- `Uiso` or `Uij`
- final atom refinement flags

## When to Adjust the Run

- Provide a real `.instprm` when available.
- Use `--limits low high` to exclude obvious garbage range.
- Use only physically plausible phases in multiphase fits.
- If size or microstrain destabilizes the fit, rerun with `--disable-size-microstrain`.
- If texture should not be considered, rerun with `--disable-preferred-orientation`.
- If atomic refinement is chemically unsafe for the data quality or model quality, rerun with `--disable-atomic-refinement`.
- Use `--no-auto-install-gsasii` if you want the script to fail instead of installing GSAS-II automatically.

## Resources

- `scripts/refine_gsas2.py`: automated GSAS-II refinement for single-phase and multiphase jobs.
- `references/cli-examples.md`: command examples and tuning notes.
