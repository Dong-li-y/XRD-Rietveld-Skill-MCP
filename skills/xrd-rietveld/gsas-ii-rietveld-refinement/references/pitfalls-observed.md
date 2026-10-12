# Pitfalls actually hit in this environment (Windows, GSAS-II `D:\app\XRD\GSAS-II`)

These are not hypothetical: every item cost a failed run and was reproduced.

## 1. Interpreter / binary path

- `import GSASIIscriptable` succeeds with several interpreters but only some find the
  compiled kernels. Working combination here:
  `/d/app/xrd/python.exe` + `sys.path.insert(0, r"D:\app\XRD\GSAS-II\GSASII")`
  → `GSASIIpath.SetBinaryPath(True)` reports `GSASII-bin/win_64_p3.11_n1.26`.
- The source tree is a **package** layout (`GSAS-II/GSASII/*.py`). Put the *inner*
  `GSAS-II\GSASII` directory on `sys.path` and then `import GSASIIscriptable` as a
  top-level module (`from GSASII import GSASIIpath` still works for the helper).
  Putting the *outer* `GSAS-II` root on `sys.path` instead makes `GSASII` resolve to
  `GSASII.py` and the import dies with `ModuleNotFoundError: No module named 'GSASIIpath'`
  or `ImportError: cannot import name 'GSASIIscriptable' from 'GSASII'`.
- The Anaconda 3.13 interpreter imports `GSASII.GSASIIscriptable` but then prints
  `*** ERROR: Unable to find GSAS-II binaries ... pypowder is not available`
  → profile calculations are silently disabled: wR values become meaningless. It also
  cannot be used for post-processing a GPX (`NameError: name 'wx' is not defined`).
  Use the GSAS-II interpreter for anything that touches a GPX, including plotting
  arrays out of it.
- `GSASIIpath.BinaryPath` does **not** exist as an attribute; use
  `GSASIIpath.GetConfigValue('GSASII_bin')`.

## 1b. U/V/W units: GSAS-II stores the VARIANCE, not the FWHM

Reproduced with a controlled probe (one phase, `U=V=0`, `W=10000`, no variables free):

- `W = 10000` cdeg² produced a calculated FWHM of **2.380 deg**, i.e. `2.3548 * sqrt(W)/100`.
- Therefore `sigma^2(2theta) [centideg^2] = U tan^2(theta) + V tan(theta) + W` and
  `FWHM = 2.3548 * sigma` (= `sqrt(8 ln 2) * sigma`).
- Consequence: seed `W` with `FWHM_cdeg^2 / (8 ln 2)`, i.e. divide every FWHM² value
  measured from the data by **5.5452**. Seeding with the raw `FWHM_cdeg^2` makes every
  calculated peak 2.35x too broad, which cannot be fixed by scale or background and
  leaves `wR` stuck near 30 % with a large positive residual on the strongest line.
- Conversely, a *free* `W` (or `U`,`V`,`W`) stage drives the coefficients to large
  negative values, i.e. negative variance and needle-sharp calculated peaks. With an
  uncalibrated profile keep `U,V,W` locked or release `W` only.
- Do not solve for `U,V,W` by unconstrained least squares on the measured FWHM²: the
  solution is not physical outside the measured window (observed: large negative `W`,
  negative variance below ~25 deg 2-theta). Constrain
  `U >= 0` and `sigma^2 >= (0.1 deg / 2.3548)^2` over the whole scanned range.

## 2. CIF reader traps

- A hand-written or pymatgen-written **Fd-3m** symop block is rejected:
  `CIF symops do not agree with GSAS-II, calling Bilbao "CIF to Standard Setting"`
  and, offline, `No reader could read file`.
  Fix that works: take the symop loop **verbatim from a COD/ICSD CIF that GSAS-II
  already reads** (e.g. COD 1513301 magnetite) and pair it with plain
  `_symmetry_space_group_name_H-M 'F d -3 m'` + `_space_group_IT_number 227`.
- A CIF that GSAS-II reads as **P1** makes `phase.set_refinements({'Cell': True})
  refine six cell parameters**. Verify the variable count that GSAS-II prints
  (`Hessian Levenberg-Marquardt SVD refinement on N variables`): a cubic phase must
  add exactly **1** variable per phase. When a P1 phase is present the extra
  parameters drift and the refinement dies with
  `invalid value encountered in arccos`.  Two working remedies, in order of
  preference:
  1. **Re-express the structure in its own space group** and prove the rewrite is
     the same structure: expand both CIFs to explicit atoms (fold coords into
     [0,1)) and match element-by-element with a tolerance. Build the symop block
     from `pymatgen.symmetry.groups.SpaceGroup(symbol).symmetry_ops` +
     `_space_group_symop_operation_xyz` (this IS accepted by GSAS-II for C 2/m
     and P m n m; only a *setting mismatch* gets rejected). Do NOT trust
     `get_symmetrized_structure()` coordinates against a freshly generated symop
     list without that check - doing so produced a file with doubled atoms that
     looked fine in a viewer. Beware also `StructureMatcher` on partially
     occupied sites: it reported "not equivalent" for a file that was in fact
     atom-for-atom identical. Compare atoms, not Structures.
  2. **Hold the cell** (`--hold-cell NAME` in the drivers here: skip
     `set_refinements({'Cell': True})` for that phase) and say so in the report.
     Also keep an audit that flags any cell ANGLE drifting >0.5 deg from the angle
     in the phase CIF - that is the cheap smoke detector for a P1 phase silently
     becoming a different structure.

- **Charged `_atom_site_type_symbol` values are parsed as WRONG elements, without
  any error.** A user CIF with `_atom_site_type_symbol` = `Li+ / Fe3+ / Cl- / O2-`
  was read by GSAS-II as elements **`C`, `H`, `Fe+3`, `O-2`** - lithium vanished
  completely and chlorine was split into C+H. The refinement then runs happily and
  silently against the wrong scattering factors. Always print, for every phase,
  what GSAS-II built (`phase.data['Atoms']` -> element set + count + cell) and
  compare it with the CIF's declared composition BEFORE refining. Fix: rewrite the
  type-symbol column with plain element symbols (leave the numbers alone) and drop
  the charged `_atom_type_symbol/_atom_type_oxidation_number` loop.

## 2b. Building a reference pattern with pymatgen (for line-presence tests)

- `CifParser(cif).parse_structures(primitive=False)[0]` is the right entry point, but
  `Structure.to_conventional()` raises `SymmetryUndeterminedError` on a distorted
  monoclinic cell and mangles a 3-atom cubic spinel input into a hexagonal cell.
- Do **not** expand with `pymatgen.symmetry.groups.SpaceGroup('<symbol>').symmetry_ops`:
  for `Fd-3m` those operations map (1/8,1/8,1/8) onto **16** points and (1/2,1/2,1/2)
  onto **8**, i.e. backwards for the spinel setting, which silently swaps the 8a and 16d
  occupants and inverts the (111)/(220) intensities. Always check the element counts of
  the expanded cell against the expected Wyckoff multiplicities before trusting a
  pattern.
- The robust recipe is: parse the phase CIF once with `CifParser` (it applies the CIF's
  own symop block, the same thing GSAS-II uses), keep `[site.species for site in base]`
  and `[site.frac_coords for site in base]`, and for each refined cell rebuild
  `Structure(Lattice.from_parameters(...), species, coords)`. Keeping `site.species`
  rather than plain element strings preserves partial occupancies, so a rock-salt
  (Li0.525Mn0.425Ti0.05) site keeps its correct scattering power.
- `XRDCalculator.get_pattern(..., two_theta_range=(lo,hi))` raises
  `ValueError: max() iterable argument is empty` when no reflection falls in the window
  (e.g. a collapsed cell). Catch it and report, do not let it kill a whole audit run.

## 3. Two-phase least squares

- **A second phase whose phase fraction is never released is silently frozen at its
  seed.** `add_phase(..., histograms=...)` creates `phase.data['Histograms'][hn]['Scale']`
  = `[seed, refine_flag]`; nothing turns the refine flag on. Symptom: the extra phase's
  reflections stay unexplained no matter what is released, the host's strongest line
  keeps a large positive residual, and `wR` stalls around 25-30 % with `GOF ~ 3`.
  Fix: with more than one phase linked to the histogram, call
  `ph.set_HAP_refinements({'Scale': True}, histograms='all')` for every phase (the
  `'Scale'` key is the phase fraction). In practice this alone shifts `wR` by several
  percentage points (both at the cell-only stage and in the final fit) and turns a host
  phase with no `RF`/`RF2` output into one with finite R-factors.
- `set_HAP_refinements({'Size': True})` raises `TypeError: argument of type 'bool' is
  not iterable`. The HAP values must be dicts, e.g.
  `{'Size': {'type': 'isotropic', 'refine': True, 'value': 0.05}}` (size in um).
- Forcing every phase scale to 1.0 (`hap['Scale'][0] = max(..., 1.0)`) makes the
  first cycle explode (`chi^2 ~ 1e23`, `Maximum shift/esd = 253`). Seed the second
  phase's scale *small* (e.g. 0.02-0.05) or leave the GSAS-II default.
- A phase that is genuinely absent collapses its scale to ~1e-12 and then the SVD
  becomes singular; the run ends at `wR = 100.0000 %`. Treat that pattern as
  **"the phase has no support in these data"**, not as a fit failure — but confirm
  with a second criterion (Rf² near 100 % for that phase).
- Seed both cells near their peak-implied values before releasing Cell, otherwise the
  phases trade intensity against each other and the cells do not move at all
  (wR identical to 6 decimals between stages = the stage did nothing).
- GSAS-II's own `Controls` default stops after very few cycles. A stage that reports
  `Maximum shift/esd` in the tens or hundreds has not converged; set
  `proj.data['Controls']['data']['max cyc'] = 12` before calling `refine()`.
- `G2PwdrData.getdata('ycalc')` returns zeros until a refinement has actually been run
  in that project; a freshly built GPX cannot be inspected this way.
- `phase.data['SGData']` does not exist at the top level: the space group lives at
  `phase.data['General']['SGData']['SpGrp']`. Verify a newly built phase through
  `phase.data['Atoms']` (`label, element, '', x, y, z, occ, ...`) and print the element
  set, because a wrong/charged type symbol is otherwise invisible.

## 4. Parameter blocks: inconsistent shapes

- Instrument: `hist.data['Instrument Parameters'][0][key] = [initial, current, refine]`.
- HAP: `Size`/`Mustrain` = `[type, [values], [refine flags], ...]` but
  `Pref.Ori.` = `[type, value, refine_flag, ...]`. Indexing `entry[2][0]`
  therefore works for the first two and raises `'bool' object is not subscriptable`
  for the third. Use a shape-tolerant helper.
- There is **no parameter-limit mechanism** (`ip[1]` is empty, no `ParmLimits`).
  Non-physical values can only be caught by an explicit post-refinement audit and a
  revert — implement that audit yourself.

## 5. Undocumented UI

- `.lst` files are snapshots written **at save time**; the post-refine values live in
  the `.gpx` (GSAS-II re-saves the same project name after `refine`). Read final
  numbers from the project, not from `Unit cell:` in the `.lst`.
- Covariance-derived cell esd: `G2Phase.get_cell_and_esd()` returns dicts keyed
  `length_a/angle_alpha/...`, not `a/alpha`.

## 5b. Excluding a phase the user insists on (the "but it should be X" case)

When a user overrides your phase assignment, never argue from authority and never
quietly keep your own labelling. Re-run **their** model, report the numbers, then
apply these three checks (they are what actually decides such a case):

1. **Missing-line test.** A phase that is present must show its *two strongest*
   reflections. Compute the candidate's reference pattern (pymatgen `XRDCalculator`
   on the full symmetric cell) and look for its top lines in the raw pattern using a
   local background estimate. If both strongest lines are pure background in every
   sample -> the phase is excluded, regardless of any wR improvement.
2. **Cannot-be-textured-away test.** Texture can suppress one family (e.g. 00l of
   flat-lying platelets) but not two mutually perpendicular ones. If both missing
   strong lines lie in different families, preferred orientation is not an excuse.
3. **Cell-runaway test.** Give the candidate a free cell. A real phase keeps its
   cell near the reference (a few %); a phantom absorbs neighbouring intensity and
   the cell drifts wildly -- an unambiguous "not present". Combine with Rf2: a
   well-constrained phase gives a modest Rf2, an unsupported one a large one.

Extra rule for **layered** candidates: if the strongest unexplained observed line
sits at `d`, and indexing it as a low-angle interlayer reflection would require an
interlayer repeat smaller than the slab thickness `t` of that structure type, the cell
is physically impossible (slabs would interpenetrate). Use this before spending
refinement time.

When a user-named phase is excluded, offer the **structural family** the positions do
support instead (typically a cubic close-packed type or a layered type reproduces the
residual lines while a slab-type cell cannot), and ask for their CIF to settle it.

*Concrete sample identities, compositions, peak positions and refined values from the
cases above are not recorded here (unpublished data).*

## 6. Reproducibility and process hygiene

- **A stale `.pyc` can silently feed a helper module to the GSAS-II interpreter.**
  `importlib.util.spec_from_file_location(...)` + `exec_module` uses the normal
  `__pycache__` bytecode cache, whose validity check is source mtime+size. A helper that
  was edited inside the same mtime tick as its cached `.pyc` keeps serving the OLD code.
  Reproduced here: the profile-seeding module returned one seed under the 3.11 GSAS-II
  interpreter and a different one under a 3.13 interpreter. Fix: `exec(compile(open(p)
  .read(), p, 'exec'), ns)` and read the functions out of `ns` via `SimpleNamespace`
  (a `type("X", (), ns)` wrapper would bind them as methods and shift every argument).
- **An under-determined fit is not reproducible across numpy/scipy builds.** With only
  two accepted observations and three parameters the Caglioti solve has an exact-fit
  curve; different builds returned visibly different parameters for **identical** input.
  Add a tiny Tikhonov term (`+ 1e-9 * sum(p**2)`) so the minimum-norm
  interpolant is selected, and require at least three accepted lines (relax the S/N gate
  until three pass). Verify by running the helper under both interpreters and comparing.
- **A failed refinement can leave numpy in a raising error state for the rest of the
  process.** After one project died with `divide by zero encountered`, every later project
  in the same process reported `Error message: underflow encountered in multiply` and
  `ouch #0 unable to evaluate initial objective function`. Reset with
  `numpy.seterr(all='warn')` immediately before every `refine()` call. Symptom signature:
  a batch where the first few refinements are fine and everything after one hard failure
  is dead.
- Do not hold the shell's working directory inside a run folder on Windows: `rm -rf` of
  that folder then fails with `Device or resource busy`, and a chained `&&` silently
  aborts the rest of the command.

- **Never let two refinement processes write into the same run tree.** While diagnosing a
  profile-seed bug, three background matrices were live over one `02_runs/` tree at once; the
  last one to exit rewrote the `stage_summary.json` files. The output looked plausible either
  way. Cheap inoculation, in order of value: (1) give each sweep its own output directory and
  pass it in, rather than defaulting to the same paths; (2) record something in every summary
  that identifies the *code version* that produced it (a fitted profile seed is enough to tell
  two runs apart); (3) add a cheap cross-check that compares a value re-read from
  the saved `.lst` against the value recorded in memory at save time:

  ```python
  # stage_summary.json stores script_metrics.script_wR_percent = wR * 100 (naming slip!)
  assert abs(v["wR"] - v["script_metrics"]["script_wR_percent"] / 100.0) < 0.05
  ```

  A full sweep of converged stages agreeing to a few 1e-3 percentage points proves the numbers and
  the `.gpx`/`.lst` on disk came from the same refinement. Run it any time a sweep overlapped another.

## 7. Reading numbers back out of a `.lst`

- Every line in a GSAS-II `.lst` carries leading spaces. Parsing with `re.match` without
  `line.strip()` silently drops the per-phase `Final refinement RF, RF^2 = ...`,
  `Phase fraction ... Weight fraction ...` and `Unit cell: ...` lines — the metrics look
  missing rather than wrong, which is easy to miss.
- `Unit cell:` lines are printed in the phase-structure section, i.e. BEFORE the first
  `Phase: <name> in histogram: <hist>` header, and the whole per-phase block appears
  twice (parameter echo + final results). Map the i-th distinct phase name to the i-th
  `Unit cell:` value and assign only on the first occurrence, otherwise the second block
  overwrites every phase with the last cell and all phases appear to share one lattice.
- Metrics can be rebuilt from existing `.lst` files without re-running GSAS-II: import the
  driver module, call its `lst_metrics()` on each saved `.lst`, and merge into
  `stage_summary.json`. That kept a large-sweep bookkeeping bug from costing a full
  re-refinement.

## 8. STOE WinXPOW ASCII `.asc`

> **⚠ 更改提示 —— 本节仪器参数是打包机的默认示例，请按自己的仪器改写。**
> `STOE WinXPOW` 格式、Cu Kα（λ₁/λ₂ 与 `I(L2)/I(L1) = 0.5`）、扫描栅格 `10/90/0.01°`、
> `I_MONOCHRO = Manual` / `FILTER = None` 等，都是**某一台仪器、某一次实验的默认取值**，在这里只用于说明
> 解析与轮廓处理的坑。换仪器 / 换实验室 / 换扫描参数时请逐项替换为自己数据文件里的值，不要照搬。
> 这些默认值**不影响下面任何一条经验结论**（解析正则、`*DATE`/`*COMMENT` 被吞、无峰形参数即未标定、
> Kα₂ 必须保留等）的适用性。

- Header `*BEGIN` … `*END`; the data block is **comma-separated intensities in rows
  of four**, no 2-theta column. Grid: `*START`/`*STOP`/`*STEP` (e.g. 10/90/0.01 →
  8001 points). Always assert `len(parsed) == round((stop-start)/step)+1` before use.
- Parsing the header with `^\*([A-Z_()/0-9]+)\s*=\s*(.*)$` is wrong: `\s` also matches
  the newline, so any header line with an EMPTY value swallows the following key
  (`*SAMPLE\t\t=  ` ate `*COMMENT`, `*FNAME` ate `*DATE`). Use
  `^\*([A-Z_()/0-9]+)[ \t]*=[ \t]*([^\r\n]*)$`. This bites exactly on the fields you
  need (DATE, COMMENT, FNAME) and silently drops them.
- Header carries `*DATE`, `*KV`/`*MA`, slit specs, counter name and the two
  wavelengths, but **no peak-shape parameters** ⇒ uncalibrated profile.
- Cu Kα2 is present (`I_MONOCHRO = Manual`, `FILTER = None`): keep
  `I(L2)/I(L1) = 0.5`; the residual shape changes visibly if it is dropped.

## 9. MCP wrapper layer (`gsas2_mcp_server`) — `refine` reported failure on every run

Reproduced 2026-10-12 on the GSAS-II PbSO4 example (`tests/testinp`, no private data).

- `GSASIIscriptable.Project.refine()` in this tree (`GSASIIscriptable.py:1610-1634`) has **no return
  statement**, so it always returns `None`. The MCP wrapper treated `None` as failure and raised
  `RuntimeError("Refinement failed (GSAS-II returned no result)")` **even when GSAS-II had just printed
  `***** Refinement successful *****`**. Signature: `.gpx`/`.lst` are written and valid, the refinement log
  ends with the success banner, yet the tool errors out. Never write `if result is None: raise` around this
  API — read the log instead.
- `Controls['data']['max cyc']` defaults to **3** in a fresh project and the wrapper never raised it. A stage
  that stops after 3 cycles still prints `***** Refinement successful *****`; the only visible symptoms are
  `Maximum shift/esd = 55.127` in the stdout log and wR stuck at 63.80 %. **Read `Maximum shift/esd` and
  require ≤ 1 before calling a stage converged** (the `.gpx` does not persist this value — `Controls` keeps
  only `max cyc` and `shift factor`).
- Fix applied 2026-10-12 (patch + before/after logs shipped in the `XRD-Rietveld-Skill-MCP-2026-10-12`
  package): take success/failure from the captured refinement log (`Refinement failed` / `Refine aborted` /
  `Least squares aborted`), return the parsed `Maximum shift/esd`, and add `refine(max_cycles=N)` which raises
  `Controls['max cyc']`. Same PbSO4 data: wR 63.80 % (3 cycles) → **12.865 %**, GOF 2.6876, shift/esd 0.486,
  cell a = 8.481861(138) / b = 5.399835(90) / c = 6.961628(116) A.
- `export_plot` does not clip to the histogram `Limits` (a 10-130 deg fit is drawn to 160 deg) and emits a
  generic matplotlib figure, not a publication one — that hand-off belongs to `rietveld-plotting`.
