# RESULTS — the semi-deviation bridge, against the rules fixed before it was run

**2026-08-20. Run against `PREREG-Semidev-ERP-Bridge-2026-08-20.md`, written before the
out-of-sample test. One falsifier fired. It is reported first.**

---

## THE FALSIFIER THAT FIRED — F2, in one direction

```
fit 2017-2026 -> test 2007-2016
   drawdown-conditional error sd is 2.64x the calm-day sd  (pre-registered limit 2.0x)
```

The other direction does not fire (1.49×). **The asymmetry is the finding, and it is
interpretable rather than mysterious.** 2017–2026 contains COVID and 2022 but no 2008-scale
event, so a bridge calibrated on it has too narrow a spread to reach the global financial crisis.
Calibrated the other way round — on a window that *does* contain 2008 — it generalizes to
2017–2026 without firing.

**What it means operationally: the bridge is only as good as the worst episode in its calibration
window.** The production parameters must therefore be fitted on the **full 2007–2026 overlap**,
which contains both the GFC and COVID, and the calibration window must never be narrowed to a
period without a severe crisis. That is a constraint the split test discovered and I would not
have thought to impose.

**And the conditional error is biased in a consistent direction.** Near drawdowns the mean error
is **+1.05** and **+2.69** VIX points in the two splits — always positive. The reconstruction
**overstates** risk around crashes, which is the semi-deviation overstay effect appearing exactly
where the pre-registration predicted it. For valuation that biases historical intrinsic values
**low** around crises. Conservative, but real, and it must be recorded on any 2008-era or
1930s-era number this system produces.

---

## THE FOUR THAT DID NOT FIRE

| | test | result | limit |
|---|---|---|---|
| **F1** | out-of-sample correlation, both directions | **0.797** and **0.808** | ≥ 0.60 |
| **F3** | fitted slope positive | **+1.084**, **+1.139** | > 0 |
| **F4** | splice step at 2007-01-03, before blending | **+1.60 VIX points** | ≤ 5.0 |
| **F5** | impossible levels | **0 of 25,350 days** | within [5, 100] |

F1 is the one that decides whether the bridge is real at all, and it passes decisively — 0.80 out
of sample against 0.806 in sample means the relationship is not an artefact of the fitting
window. F4 at 1.60 points means the blend is smoothing a genuinely small step rather than
concealing a cliff.

---

## THE BRIDGE

```
VIX_equivalent = 8.9374 + 1.1053 x market_semideviation        lag 0, two-moment match
```

Fitted on all 4,927 overlapping days, 2007-01-03 to 2026-08-12. In-sample correlation **0.8061**.
Two parameters and no more.

**It targets the risk INPUT, not the premium.** Whatever supersedes the current ERP methodology
consumes this reconstructed VIX-equivalent exactly as it consumes VIX1Y today. Recalibrating
later is two numbers, not a rebuilt history.

**The idiosyncratic leg was never bridged, because it never needed to be.** `idio/semidev.py` is
already the production statistic and `idio/erp.py` already prices Region 1 off it against the
cap-weighted average. Going backwards changes only the market proxy and each company's own price
history.

---

## THE RECONSTRUCTION — 25,350 days, 1929-09-14 to 2026-08-12

| | semi-dev | VIX-equiv | market ERP | source |
|---|---|---|---|---|
| 1932-06 depression | 25.93 | 37.59 | **14.13%** | bridge |
| 1937-10 recession | 14.66 | 25.14 | 6.32% | bridge |
| 1974-10 bear trough | 12.73 | 23.01 | 5.29% | bridge |
| 1987-12 post-crash | 24.84 | 36.39 | **13.24%** | bridge |
| 2000-03 bubble peak | 13.93 | 24.33 | 5.92% | bridge |
| 2009-03 GFC trough | 27.29 | 41.14 | **16.93%** | blend |
| 2020-06 post-COVID | 21.98 | 29.43 | 8.66% | live |
| 2026-08 today | 10.52 | 22.62 | 5.12% | live |

Required returns rising to 13–17% at troughs is the behaviour a historical premium should show —
it is what makes a historical valuation say equities were cheap then.

---

## THE SUSPICION I RECORDED IN ADVANCE, AND WAS WRONG ABOUT

The pre-registration flagged the 1974 reading as probably a data artefact: *"a market
semi-deviation of 12.73 at the October 1974 trough is implausibly calm for that bear market."*

**It is not an artefact and the data is sound.**

| period | annualized vol | zero-return days | peak-to-trough |
|---|---|---|---|
| 1973–74 | **19.01%** | 0.4% | −48.2% |
| 1987 | 33.69% | 0.0% | −33.5% |
| 2008 | 41.00% | 0.4% | −48.0% |

1973–74 realized volatility of 19% against a 48% drawdown is the historical record, and
semi-deviation runs about **0.70× total volatility in every era** (1987: 24.84 on 33.69; 2008:
27.29 on 41.00). The statistic is internally consistent across a century.

**But the reading exposes a real property of the method, and it applies to the LIVE method too.**
A variance-based premium measures **volatility, not cheapness**. October 1974 was arguably the
cheapest the post-war market ever got, and this construction gives it 5.29% — barely above
today's 5.12% — because 1974 fell a very long way on ordinary volatility. Slow bear markets get
understated; violent shallow ones get overstated.

That is not a defect of the bridge. It is the Martin variance bound doing what it says, and the
live method shares it exactly. Worth knowing before any 1970s valuation is quoted.

---

## WHAT LANDED

- `idio/market_semidev_bridge.py` — imports `idio/semidev.py`; there is no second implementation
  of the statistic and there must never be one.
- `data/market_history/sp500_daily_1927_2026.json` — 25,855 daily closes.
- `data/market_history/vix1y_2007_2026.csv` — the frozen calibration fixture, 4,933 days.
- `outputs/market_semidev_history.csv` — the reconstruction, with the source of every day marked
  `bridge`, `blend` or `live`.
- `tests/test_market_semidev_bridge.py` — 11 assertions. Notably: that the statistic is imported
  rather than copied, that the market lag is 0 while the company lag stays 60, that a negative
  lag can never be introduced, that zero lag still beats the production lag on the data, and that
  **the pre-registered thresholds have not been relaxed** — F2 fired, and a threshold quietly
  widened to make it pass would be worse than no threshold.

117 tests green.

---

## STILL OPEN

1. **The 0.52pp splice break in the EXISTING historical series.** Unrelated to this work and
   larger than anything here: `history/FINAL_decomposition_v4_1877_2026.csv` reads `eff_erp`
   **3.887** for June 2026 where the live `ERP_effective_latest.csv` reads **3.37**. Nothing
   builds that file and nothing reconciles them. Fix before any historical valuation publishes.
2. **The term structure.** This bridges the one-year point. Tenors 2–10 need the shape mapping;
   beyond 10 the live construction is a preset constant and needs no historical input at all.
3. **The company side going back** needs each name's own price history and a pre-1993 market
   proxy, since SPY does not exist before then.
