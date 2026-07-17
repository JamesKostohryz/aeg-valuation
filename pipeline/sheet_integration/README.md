# Sheet integration — wiring the committed CSVs into the Google Sheet + locking cells

Two jobs: (1) pull the pipeline's committed outputs into the Sheet with native
`IMPORTDATA` (no auth, no script, auto-refresh), and (2) lock every cell except the blue
inputs with one Apps Script. Together these close the loop: GitHub Actions runs the gated
pipeline → commits CSVs → the Sheet imports them → the Work Area drives the forecast → and
nothing but the blue cells can be touched.

Replace `<USER>/<REPO>` below with your repo (same public raw base as the rate feed), and
`<TICKER>` with the company (e.g. `T`).

## 1. Data pull (IMPORTDATA — paste these formulas)

Base: `https://raw.githubusercontent.com/<USER>/<REPO>/main/outputs/`

**`_Actuals` tab (A2)** — the reformulated real historicals that feed the Work Area's
historical columns:
```
=IMPORTDATA("https://raw.githubusercontent.com/<USER>/<REPO>/main/outputs/<TICKER>_restated_real.csv")
```

**`_Rates` tab (A2)** — the real cost of debt ρD by tenor, single-sourced from the rate
infrastructure (their file, so the Sheet and the engine use the same bytes):
```
=IMPORTDATA("https://raw.githubusercontent.com/JamesKostohryz/real-yields/main/outputs/cod_<TICKER>_annual.csv")
```

**A `_Valuation` helper tab (A2)** — the headline numbers + the tie-check verdict + the
Option-A disclosure bridge:
```
=IMPORTDATA("https://raw.githubusercontent.com/<USER>/<REPO>/main/outputs/<TICKER>_valuation.csv")
```

**Same tab (D2)** — the restated anchors (shares, real NOA/NFO/CSE, real price):
```
=IMPORTDATA("https://raw.githubusercontent.com/<USER>/<REPO>/main/outputs/<TICKER>_anchors.csv")
```

`IMPORTDATA` returns `field,value` rows; reference any field with a `VLOOKUP`, e.g. the
intrinsic equity value on your summary/Control tab:
```
=VLOOKUP("equity_value", _Valuation!$A:$B, 2, FALSE)
=VLOOKUP("adjusted_equity_ps", _Valuation!$A:$B, 2, FALSE)   // market-debt + idio disclosed
```

## 2. Health badge (formula + conditional format — no script)

Put the standing tie-check verdict somewhere prominent on the Control tab:
```
=VLOOKUP("tie_check", _Valuation!$A:$B, 2, FALSE)     // "PASS" or "FAIL"
```
Then Format → Conditional formatting on that cell: green fill if text is exactly `PASS`,
red fill if `FAIL`. That surfaces the four-method reconciliation status on every refresh —
if the pipeline ever shipped a broken tie (it won't; the job fails first), you'd see red.

## 3. Lock the cells (one Apps Script run)

The blue driver/control cells are the only editable surface; everything else is machinery.

1. Extensions → Apps Script, paste `protect_workarea.gs`.
2. Run `protectAll()` once and authorize. It protects the Work Area with the 15 blue input
   ranges as the only exceptions, and fully locks the `_Actuals` / `_Rates` data tabs.
3. Re-run after any Work Area layout change. If the blue-input layout itself changes,
   regenerate the range list with `extract_blue_ranges.py` and paste the new
   `EDITABLE_RANGES` into the script.

The editable ranges (from `blue_ranges.json`): the mode/financing/payout/target controls
(`C2, E2, C3, E3, C4`), the real-price anchor (`F30`), and the nine driver rows
(`G7/G10/G12/G14/G17/G24/G36/G45/G50 : AJ`).

## Refresh cadence

`IMPORTDATA` re-pulls roughly hourly, and whenever the Sheet is opened/edited. The pipeline
commits fresh CSVs whenever a company config changes or on its schedule, so the Sheet tracks
the latest gated run automatically — no manual copy step, and the tie-check badge confirms
each pull reconciles.
