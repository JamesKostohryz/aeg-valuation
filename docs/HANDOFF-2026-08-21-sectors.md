# HANDOFF — 2026-08-21, the historical ERP and cost of equity

**`aeg-valuation` main at `30c1d49`. Use Opus: what remains is one reconciliation, one assembly
job, and two decisions that only James can make.**

---

## READ FIRST, IN THIS ORDER

1. **`docs/DOCTRINE-How-This-Model-Thinks-2026-08-20.md`** — two conceptual errors made by an
   assistant that had read everything. Skip it and you will make them again.
2. `docs/RESULTS-French-GICS-Mapping-2026-08-20.md` — the sector leg as built, its validation, and
   the two sectors where it does not work.
3. `docs/RESULTS-Company-Leg-Denominator-2026-08-20.md` and
   `docs/RESULTS-Partial-Panel-And-Sectors-2026-08-20.md` — the company leg, and why three
   shortcuts failed.
4. `docs/RESULTS-Constant-Denominator-2026-08-20.md` — read before proposing any constant.

---

## STATE OF PLAY

**The market leg is finished.** `outputs/market_coe_history.csv` — monthly real cost of equity
1929-10 to 2026-06 from current components only, `real_rf + market_erp`.

**The sector leg is built and cross-checked three ways.**
`outputs/2026-08-20-sectors/french_gics_sector_semidev.csv` — eleven GICS sectors, 1,176 months,
July 1928 to June 2026, from Kenneth French's daily 49-industry portfolios cap-weighted into GICS
sectors, with a firm-count guard. The equal-weighted average sector risk ratio is **1.109**, and
two independent constructions on a different vendor and universe agree: GFD's five S&P sectors
1991–2014 give **1.109**, French's twelve SIC industries give **1.110**.

**The company leg's numerator was never a problem** — a company's own semi-deviation needs only
its own price history. The denominator is measurable directly from the existing daily panel back
to about **1985** at a cost of **7 to 17 basis points** of cost of equity, measured under a
decile-matched degradation model. Three shortcuts were tried and all three failed, each
pre-registered before it ran: the market-scaled ratio (tier A), the partial-panel imputation, and
a constant denominator.

**Four companies of fleet state unchanged:** MSFT and PEP valued; KO one line from valuing;
fourteen awaiting forecast, which is rule D1 working.

---

## THE FIRST JOB, AND IT BLOCKS EVERYTHING ELSE

**There are at least three different published numbers called "the market equity risk premium",
and every sector and company premium is a multiple of one of them.**

| source | value | what it is |
|---|---|---|
| `outputs/market_coe_history.csv`, 2026-06 | **5.304%** | Martin bound at the 1-year tenor from the reconstruction |
| the engine's `fwd_erp` at tenor 30 (MSFT run) | **2.037%** | what the valuation actually discounted with |
| implied by MSFT's published Region 1 arithmetic | **≈4.13pp** | back-solved from `−0.8104pp` at a ratio of `0.804` |

These are not obviously the same object at different tenors — 5.30% at one year against 2.04% at
thirty years is a very steep term structure, and the middle number is the one a valuation used.
**Reconcile these three before multiplying any ratio by any of them.** This is the standing
suspicion in its classic form: several internally consistent numbers wearing one name, and nothing
that compares them.

Everything below is blocked on this, because a sector cost of equity is
`real_rf(t) + ratio(t) × market_erp(t)` and the answer changes by a factor of two depending on
which `market_erp` is meant.

---

## THEN, IN ORDER

### 1. Build the historical sector cost-of-equity series — assembly, not research

For each month, `sector_COE(t) = real_rf(t) + ratio_sector(t) × market_erp(t)`, joining
`french_gics_sector_semidev.csv` to `market_coe_history.csv` on the month. Both files exist and
both are monthly. **Do not apply a single current market premium to historical ratios** — that is
what the results documents do for readability and they say so; it is not a historical series.

**Disclose the Industrials and Consumer Discretionary weakness on the face of those two sectors.**
Validated against the S&P sector indices, correlations are 0.97 Consumer Staples, 0.94 Utilities,
0.86 Financials — and 0.39 Industrials. Split at the August 1999 introduction of GICS, Industrials
runs **0.948 before and 0.267 after**. French's SIC groupings track the legacy broad "S&P
Industrials" and cannot reproduce the narrower sector GICS defined in 1999. Two other explanations
were tested and rejected: the mapping (a sensitivity test moves it only to 0.520) and
concentration (Industrials is the *least* concentrated S&P sector, top name 8.9%).

### 2. Decide the company construction — GATED, and it decides whether step 3 exists

Two constructions, and they are not a technical preference. They answer different questions about
*whose* cost of equity this is.

- **Today's**: residual semi-deviation over the cap-weighted universe average. Prices
  idiosyncratic risk only cross-sectionally — the average company's is not priced at all, since
  the cap-weighted mean premium is zero by construction. It values for an index holder.
- **The alternative**: total semi-deviation over the market's total semi-deviation. Prices
  idiosyncratic risk fully. It values for someone holding that one position. **It needs no
  universe, no denominator and no panel at any historical date**, which dissolves the entire
  company-leg problem.

Measured at 2026-08-12: Microsoft 1.77× the market against 0.805× today, so its front premium
roughly doubles and its real cost of equity moves from 6.27% toward 10%. **That would cut the
published $276.30 substantially.** Textbook portfolio theory favours the first; a method built for
concentrated value investors arguably wants the second. `docs/NOTE-Sector-Anchor-And-Total-
Semidev-2026-08-20.md` has the full table.

**Decide this before step 3, because if the answer is "total", step 3 never needs doing.**

### 3. Only if the answer is "keep today's construction": build the company denominator back to 1985

Direct point-in-time computation from the daily panel — no ratio, no constant, no imputation.
`tools/tierA_denominator_ratio.py` already does the computation; what is needed is to run it
monthly back to 1985 and attach the measured error. Cost is 7–10bp for ordinary names and 17bp for
the most volatile decile at a 1995-shaped panel. **James has not yet ruled on whether that is
acceptable** — my view is yes for historical analysis and no for a live published number.

### 4. Smaller, real, and still open from the previous handoff

- The refusal message names the scenario but never the ticker — it let Coca-Cola's failure be read
  as PepsiCo's twice.
- Size-weighting the issuer curve fit. GATED.
- Financials: the restatement double-subtracts a bank's interest expense (JPMorgan's economic net
  income comes out **−$14.5bn against a reported +$55.7bn**) and `synthetic_rating.py` rates all
  nine banks CCC off an interest-coverage ratio meaningless for a bank. Rewrite Rule 5's
  justification; do not delete the check.
- Objective 4, behind `PREREG-Terminal-Grid-And-Region3-2026-08-20.md`. Do not build it.

---

## PRACTICAL, AND TWO CORRECTIONS TO WHAT YOU MAY HAVE BEEN TOLD

**A cloud session CAN build and recalculate the engine.** Clone
`github.com/JamesKostohryz/market-data`, set `MARKET_DATA_DIR`, and
`pipeline/run_company.py --rate-feed-live` runs in forty seconds and reproduces CI to the last
digit.

**The sandbox CAN download public data directly.** `web_fetch` returns binary as unusable text,
but that is a rendering limit, not a block — the restriction covers routing around a *failed or
blocked* fetch. All eight French daily files came down over plain HTTPS in under a minute. A
previous session wrongly told James this needed a manual download.

**`git fetch` before dispatching anything solved locally.** A parallel session once landed a
commit mid-solve and a driver set that passed locally came back refused.

Never print the token (`Documents\GitHub\.claude-github-token`); pipe git through `sed`. A commit
message mentioning the CI-skip marker skips CI.

---

## THE STANDING SUSPICION — one more instance, from this session, in code written this session

A number silently wrong while every gate reports success. On 2026-08-20 the first run of the GICS
mapping published **Real Estate at a risk ratio of 6.46 in September 1941**, because French's real
estate industry held **two to three firms** before 1960 and my construction never asked how many
firms were in the portfolio. It would have shipped a 98-year series with a fabricated first three
decades. The fix is `MIN_FIRMS = 20` and writing the firm count on every row.

**An identity check cannot see influence, a frozen list cannot see itself, a test nobody runs is
not a test, and a portfolio statistic that never asks its own sample size will invent one.**
