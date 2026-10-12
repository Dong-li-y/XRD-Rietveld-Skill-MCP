# GSAS-II CLI Notes

## Single-phase example

```powershell
.\.venv-gsas2\Scripts\python.exe `
  ~/.codex/skills/gsas2-xrd-refinement\scripts\refine_gsas2.py `
  --pattern E:\data\sample\scan.dat `
  --cifs E:\data\sample\phase.cif `
  --output-dir E:\data\sample\gsas2_refinement `
  --limits 15 110 `
  --esd-factor 2.4
```

## Multiphase example

```powershell
.\.venv-gsas2\Scripts\python.exe `
  ~/.codex/skills/gsas2-xrd-refinement\scripts\refine_gsas2.py `
  --pattern E:\data\mixture\scan.xy `
  --cifs E:\data\mixture\a.cif E:\data\mixture\b.cif E:\data\mixture\c.cif `
  --phase-names A B C `
  --output-dir E:\data\mixture\gsas2_refinement `
  --instprm E:\data\mixture\instrument.instprm `
  --target-rwp 12 `
  --target-chi2 6
```

## Tuning reminders

- Start with the smallest believable phase list.
- A real `instprm` is usually worth more than adding more refinement flags.
- If the file already has explicit sigma or esd in column three, the script keeps it.
- If the script stops above target, try better limits or a different phase list before preferred orientation.
