# AEG valuation pipeline (GitHub statement-adjustment job)

This is the deterministic, version-controlled home for the **financial-statement
adjustment + valuation** step. It replaces the old manual/notebook load — the surface
that once shipped a corrupted model — with a gated CI job. The engine and the economic
restatement stay in the sealed Excel; this pipeline orchestrates and *gates* them.

## What it does, per run

1. **Load + validate** `companies/<TICKER>.yaml` — every judgment (fiscal-year end,
   minority interest, finance leases, R&D capitalization/life, operating-income
   adjustment, spinoff factors, cost-of-debt source, price source) is committed config.
2. **Stage raw statements** — EODHD pull in production (`EODHD_API_KEY` secret), or a
   cached directory for local/testing.
3. **Build** the model from config (`aeg_engine.build_model`) — the statement adjustment.
4. **Recalc** headless with LibreOffice.
5. **Re-point rates** from the live rate-infra feed (if available) — real rf, market-ERP
   term structure, real COD, idiosyncratic hook. Non-blocking if the feed isn't published.
6. **Gates** — completeness + provenance (`aeg_engine.read_results`), then the standing
   **tie check** (`checks.tie_check`: in-sheet audit PASS + residual backstop +
   equity=enterprise agreement). **Any failure exits non-zero**, fails the CI job, blocks the
   merge. The tie check is separate on purpose: the data gates verify the data went in, not
   that the model reconciles — a broken tie with clean data still aborts here.
7. **Disclose** (bonded + live feed) — the Option-A bridge: base equity + debt capital
   gain − idiosyncratic haircut.
8. **Extract** restated anchors / valuation / real statement series + a run manifest to
   `outputs/`, which the Google Sheet `IMPORTDATA`s.

## Why the judgments-as-config matters

"What settings produced this valuation?" now has a versioned answer. Change a judgment in
a PR and the restated statements change deterministically, with a reviewable diff. The
`config_hash` in each manifest identifies the *decisions* (it excludes volatile price/rates).

## Repo layout

```
companies/<TICKER>.yaml         committed per-company judgments
pipeline/run_company.py         the job entry point (Actions calls this)
pipeline/config.py              config load + fail-loud validation
pipeline/extract.py             restated outputs + manifest -> outputs/
outputs/<TICKER>_*.csv          committed; the Sheet pulls these
.github/workflows/valuation.yml the CI job (gates = required checks)
```
Plus the engine modules (`aeg_engine.py`, `loader_core.py`, `market_data.py`,
`company_setup.py`, `validate_load.py`, `rate_feed.py`, `repoint_rates.py`, `disclose.py`,
`recalc_lo.py`) and `MODEL_TEMPLATE.xlsx`.

## Run locally (cached mode)

```bash
python pipeline/run_company.py companies/AAPL.yaml \
  --cached /path/to/raw_csvs \
  --rate-feed-dir /path/to/rate_fixtures \   # or --rate-feed-live for the real repo
  --price 315 --vintage 2025Q3-test
```
Exit 0 = gates passed, outputs written. Exit non-zero = something failed loud; nothing ships.

## Tests

- `pipeline/test_config.py` — config fail-loud validation (10 checks).
- `pipeline/test_checks.py` — standing tie-check logic (6 checks).
- `test_rate_feed.py`, `test_disclose.py` — rate reader + disclosure (repo root).
- `test_regression.py` — the CI regression harness: unit suites + golden-AAPL build/tie +
  config grid + disclosure round-trip. `--quick` (4 configs) / default (8) / `--full` (24).
  Run by `.github/workflows/regression.yml` on every engine/pipeline/template change.

## Secrets / setup for GitHub

- `EODHD_API_KEY` — repo secret for the statement pull.
- The rate-infra repo (`real-yields`) must publish the per-company CSVs (bonds committed →
  company job run) for step 5/7 to activate; until then the job runs with build-time rates
  and skips the disclosure bridge, non-blocking.
