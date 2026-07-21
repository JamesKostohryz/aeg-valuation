# Earnings Normalization Engine (v2)

**Owner:** SP500 (S&P 500 Valuation) · **Gate:** COCKPIT (AEG Consolidation) · **Committed by:** EXEC

One numpy-only module, **two regimes x three modes**, that turns a noisy realized-earnings
series into NORMAL (mid-cycle) earning power. It is the shared primitive that supplies `eps1`
to the AEG valuation and the earnings anchor to RIV, and it works for BOTH an index (long
history + present forecast) and a single stock (mainly present forecast).

This module is standalone: it imports nothing from the sealed valuation engine, and the engine
imports nothing from it. It touches no loader, no formula, no guard, no tolerance.

---

## 1. Concept (one engine, not many)

Mid-cycle "normal" earnings lie on a NORMAL LINE growing at a constant real rate
`g = b_norm * rho` (retention x normalized RORE; set `rho = COE` for the value-neutral
default, per Miller-Modigliani). One on-trend anchor pins today's normal point; the engine
builds it from anchors on one or both sides and reconciles.

Same primitive both directions: an anchor at month-offset `k` from target `t` is walked to `t`
by `E_anchor * exp(C[t] - C[anchor])`, where `C` is cumulative log normal-growth. Past anchors
(`k<0`) are GROWN forward; future anchors (`k>0`) are DISCOUNTED back — automatically, by the
sign of the cumulative-growth difference.

## 2. Two regimes x three modes

**Regimes** (differ only in what supplies the future anchor):

- **#1 BACK-CAST (time series), REAL-TIME MODE.** Stand at a past month as an investor then
  would. Walk-back / two-sided are admissible ONLY where contemporaneous forecast data existed
  (`forecast_available[t] == True`); elsewhere the engine FALLS BACK to forward-only — because
  that is all a real investor there could have used. (Pure-hindsight back-cast is available by
  setting the mask all-True, but that is NOT the default use.)
- **#2 FORECAST (single 1-yr-forward point).** Stand at the present: past anchors are realized
  EPS; the future anchor is analyst CONSENSUS (a far year, tested for normality). Produces the
  forward normalized `eps1`.

**Modes** (identical in both regimes):

- **A forward** — median of X past-anchor walks. Backward-looking; only mode valid in true real-time.
- **B backward** — median of X future-anchor walks. Forward-looking (future = realized in #1,
  consensus in #2).
- **C two_sided** — combine both sides. Two flavors:
  - `pooled` — one median over all past+future walks (robust, centered).
  - `reconcile` — forward & backward medians computed separately; take the GAP; DIAGNOSE it
    (capital drawdown `gap/rho_cap` vs slope error via anchor-to-anchor growth vs `g`); then
    select the backward walk when a future anchor exists. Carries the explicit capital charge.

**Orthogonal options** (apply within any cell): `retention_normalize` (replace actual `b` by a
trailing X-anchor median `b_norm` in the growth factor — book-free, designed to reconcile
EXACTLY with RIV's book-based normalization); explicit capital charge `rho_cap * D` in the
reconcile/forecast routes.

## 3. API

```python
# regime #1 — back-cast time series
normalize_series(E, b, r, X=4, mode="forward",
                 forecast_available=None,   # bool mask; False => forced forward (REAL-TIME)
                 join_flavor="pooled",      # "pooled" | "reconcile"
                 retention_normalize=False, X_retention=4,
                 rho_cap=None, min_anchors=None)
    -> {"normalized": array, "gap": array, "implied_drawdown": array}

# regime #2 — present forecast (single forward-normalized eps1)
normalize_forecast(past_anchors,    # [(years_before, E_real_on_trend), ...]
                   future_anchors,  # [(years_after,  E_real_consensus), ...]
                   g, target_years_forward=1.0,
                   mode="two_sided", join_flavor="reconcile",
                   rho_cap=None, capital_drawdown=0.0)
    -> {"normEPS", "normEPS_fwd", "normEPS_back", "gap", "implied_drawdown", "slope_gap_vs_g"}

# backward-compat
walk_forward_normalized(E, b, r, X=4)   # == normalize_series(mode="forward")["normalized"]
```

Inputs monthly, real, aligned. `E` = real TTM EPS; `b = 1 - D/E` (may be `<0` or `>1`);
`r` = real COE (annual). **Real-base consistency is the caller's responsibility.**

## 4. Integration contract

- **AEG valuation:** `eps1 = normalize_forecast(...)` (forward normalized 1-yr EPS) ->
  `price / eps1` -> AEG solve for implied growth / ERP. The back-cast series
  (`normalize_series`) feeds the HISTORICAL implied-expectations series.
- **RIV:** the same normalized series is the earnings anchor; the retention-normalized variant
  is designed to reconcile EXACTLY with RIV's book-based normalization (the AEG identity
  `dE = COE * retained` is the earnings-space image of clean surplus; the book anchor cancels).
  **This equivalence is a design goal to VERIFY once RIV is built** — not yet proven.
- **Cyclical wedge** `actual/normal - 1` is a standalone "earnings stretch" indicator.
- **Canonical setting for the index history:** `mode="forward"`, `X=4` (median-of-4). This is
  what the production S&P workbook uses and what the golden CSV encodes.

## 5. Validation

1. `python normalization/normalization_engine.py` -> prints max rel err ~1e-15 for all
   three modes and an exact forecast round-trip. **Wired into CI** (`test_regression.py` Stage 1).
2. **Regression (pending fixture):** `normalize_series(E_real, retention_b, COE_r, X=4,
   mode="forward")["normalized"]` must reproduce the `normalized_X4` column of the golden fixture
   to the penny (NaN before month 48). Requires `tests/normalized_reference_series.csv`.

Verified at commit: byte-identical to SP500's raw artifact (10,588 bytes, 232 lines); non-ASCII
limited to 4 em-dashes in comments/docstrings, **zero in executable code**; self-test observed at
forward 1.30e-15, backward 1.22e-15, two_sided 8.80e-16, forecast round-trip exact.

## 6. Known data gaps (resolve on the consolidation side)

- **Real-time two-sided BACK-CAST needs historical consensus VINTAGES** (what analysts actually
  forecast in 1985, 1995, …). We do NOT have these. Without them the real-time-valid index
  back-cast is FORWARD-ONLY across all history. (Backward/two-sided on realized future EPS is
  HINDSIGHT — illustrative only.)
- **Present FORECAST (#2) backward route needs a FAR-DATED consensus anchor** (3-5 yr out, tested
  for normality). The S&P currently has only NTM (~1 yr) consensus loaded — wrong horizon to
  discount back from. Supply a long-dated consensus or an LTG estimate and the full two-sided
  reconciliation (with gap/slope diagnosis) runs.
- **COE inputs:** the engine takes `r` (real COE) as given. In the S&P model
  `COE = ex-ante ERP + real risk-free`. The historical monthly EX-ANTE ERP series is still
  outstanding (James producing it). The options-implied "variance v2" market ERP is a CURRENT
  TERM STRUCTURE ONLY (no history; cannot predate listed options ~1990). Decide how COE history
  is sourced before running the engine at scale.

## 7. Settled conventions (do not relitigate)

Real terms, common CPI base ("today's dollars"). Normal growth `g = b*r` (retention x COE);
`rho = COE` value-neutral default. Index canonical = forward, median-of-4; `X` exposed for
3/4/5 sensitivities. Capital destruction captured natively via negative retention in the growth
factor (index) or the explicit `rho_cap * D` charge (single-stock reconcile). `eps1` for
valuation is the FORWARD normalized (1-yr), not TTM.

## 8. Golden regression fixture (`tests/normalized_reference_series.csv`)

S&P, 1868 monthly rows. Columns: `date, E_real, retention_b, COE_r, normalized_X4,
cyclical_wedge`. Regenerable exactly by running Mode A (X=4, forward) on the S&P
`E_real` / `retention_b` / `COE_r` columns. Format:

```
date,E_real,retention_b,COE_r,normalized_X4,cyclical_wedge
1871.01,10.8055,0.35,0.09966,,
...
2026.06,273.9283,0.7037,0.05705,233.8148,0.17156
2026.07,277.4264,,0.05704,235.7734,0.17667
```

**Status: NOT YET COMMITTED.** SP500 is posting the static 1868-row CSV; the §5(2) regression
test is wired only once it lands.

---

## Provenance

- Engine spec + artifact: `20260720-2157 · TO-COCKPIT · FROM-SP500 · earnings-normalization-model-v2`
  and `… · normalization_engine-py-raw-artifact` (Drive id `1RcNWfX1_uoZXCrRw1t0k0PUa18EkvKQG`).
- Gate approval: `20260720-2213 · TO-EXEC · FROM-COCKPIT · COMMIT-normalization-engine-v2`.
