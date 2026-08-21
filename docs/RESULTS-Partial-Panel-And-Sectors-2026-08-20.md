# RESULTS — how far back the company leg really goes, and the sector route

**2026-08-20. Run against three pre-registrations, each committed before its test:
`PREREG-Partial-Panel-Denominator` (`7cc39f2`), its D3 amendment (`a3d1599`), and
`PREREG-Imputed-Denominator` (`edb9c16`). One of them fails its own criterion and that is reported
first. No threshold was moved.**

---

## 0. THE CORRECTION I OWE, RESTATED

I told James that no valuation before 2002 could carry a company-specific premium. **That was
wrong, and it was my error, not the data's.** It came from a gate I pre-registered as *count*
coverage — 80% of index members by number of names — which is the wrong measure for a
**cap-weighted** average. Missing three hundred small companies matters far less than missing
three large ones.

James's underlying point is right and worth stating flatly: **the company's own downside
semi-deviation was never the problem.** It needs only that company's own price history, it is
already the production statistic, and it uses no options data at all. The options dependence lives
entirely in the market leg, and that leg is already reconstructed monthly to October 1929 in
`outputs/market_coe_history.csv`. The gap is one scalar per date — the cap-weighted average the
company is measured against — and the real question is how badly a partial panel misestimates it.

---

## 1. THE THREE MODELS, AND WHAT EACH SAID

All measured the same way: at the 54 quarterly dates from 2013 to 2026 where the panel effectively
*is* the universe, hide names to reproduce a historical coverage profile, and see how far the
cap-weighted average moves. `e = capw_degraded / capw_full − 1`.

**D1/D2 — "keep the biggest until X% of cap".** Only X ≥ 85% passed; the falsifier fired.
Survivorship made almost no difference (D1 and D2 were identical to two decimals), which was
itself worth learning.

**But D1 was the wrong shape, and I could prove it rather than suspect it.** Measured against the
true CRSP roster with Compustat caps, the panel's miss rate by market-cap decile of the actual
index:

| date | in panel | d1 (largest) | d2 | d3 | d5 | d8 | d10 |
|---|---|---|---|---|---|---|---|
| 1985-06 | 136 / 442 | **41%** | 50% | 52% | 62% | 82% | 100% |
| 1995-06 | 177 / 433 | **28%** | 47% | 47% | 60% | 81% | 86% |
| 2000-06 | 249 / 422 | 21% | 40% | 38% | 30% | 38% | 74% |
| 2005-06 | 291 / 413 | 7% | 17% | 22% | 17% | 29% | 76% |
| 2010-06 | 378 / 413 | 2% | 2% | 5% | 2% | 7% | 36% |

**In 1995 the panel is missing more than a quarter of the largest decile of the S&P 500.** D1 never
drops a large name, so it could not model the thing that matters most.

**D3 — drop decile by decile at those observed rates, 200 draws.** The honest result:

| target profile | median \|e\| | p95 \|e\| | mean signed e | verdict vs 3% / 5% |
|---|---|---|---|---|
| 1985 | 4.50% | 15.10% | −0.05% | FAIL |
| 1995 | **3.41%** | 10.62% | +0.06% | FAIL |
| 2000 | 2.55% | 8.32% | +0.07% | FAIL |
| 2005 | 0.79% | 5.54% | −0.12% | FAIL (marginal) |
| 2010 | 0.18% | 2.74% | −0.06% | **PASS** |

Two things in that table matter more than the verdict column. **The estimator is unbiased** — the
mean signed error is within 0.1% at every profile. And **the crisis falsifier does not fire
anywhere**: the error on drawdown quarters is 0.93× to 1.14× the calm-quarter error. The
approximation does not fall apart in exactly the episodes a historical valuation is about. It is
noisy, not skewed, and not fragile.

---

## 2. A REAL MEASUREMENT THAT CAME OUT OF THIS AND SHOULD BE KEPT

D3 had to bracket one unknown: are the missing names more volatile than the ones we kept? They are
missing because they left the index, and departures mix calm acquisitions with volatile failures.
**So I measured it instead of assuming it.** Across 24 quarterly dates, 2013–2018, comparing names
that left the index within eight years against names that stayed, **within the same market-cap
decile so size is controlled for**:

| | n | semi-deviation relative to its own decile median |
|---|---|---|
| left within 8 years | 2,271 | **1.151** |
| stayed | 8,629 | **0.975** |
| **ratio** | | **1.181** |

**The date-by-date ratio runs 1.13 to 1.25 and never once falls below 1.12.** Departing S&P 500
companies are about 18% more volatile than their surviving size peers, and the finding is stable
across every date measured. That is a reusable parameter this project did not have, and it says
the true historical denominator is understated by roughly `0.18 × (missing share of cap)` — about
**6% at a 1995-shaped panel** — which biases every company premium *up* and every historical
valuation *down*. Conservative, but real, and it has to travel with the number.

---

## 3. THE IMPUTATION FAILED ITS OWN TEST, AND I AM NOT TUNING IT

Knowing the tilt, the obvious construction is to impute the missing names rather than ignore them:
their market caps are **known exactly** from Compustat, so only the semi-deviation needs imputing,
at `1.18 × the kept names' median in that name's own cap decile`.

I pre-registered that this must **beat D3 on both median and p95**, because machinery that does not
reduce error is worse than no machinery.

| target | imputed median | imputed p95 | D3 median | D3 p95 | |
|---|---|---|---|---|---|
| 1985 | 3.48% | 14.58% | 4.50% | 15.10% | better on both, still over the limits |
| 1995 | **2.66%** | 11.57% | 3.41% | 10.62% | **median better, p95 worse** |
| 2000 | 1.98% | 9.89% | 2.55% | 8.32% | median better, p95 worse |
| 2005 | 0.74% | 5.64% | 0.79% | 5.54% | no material gain |
| 2010 | 0.19% | 2.46% | 0.18% | 2.74% | no material gain |

**It fails.** It sharpens the middle of the distribution and fattens the tail, because imputing a
very large missing company at its decile median adds cap weight at a wrong number. **TILT stays at
1.18 and is not re-fitted to rescue this**, per the stopping rule.

One honest caveat on that verdict, stated because it cuts against my own result: the neutral test
hides names *at random*, so the correct tilt in the simulation is 1.0 and applying 1.18 penalises
it by construction. Where reality actually sits — the departure-selected "high" bracket — the
imputation does help, moving 1995's error from −20.20% to −16.18%. The pre-registered criterion
still says fail, and fail is what I am reporting.

---

## 4. TWO PRE-REGISTERED CRITERIA DISAGREE, AND THAT IS THE DECISION

This is the part James has to rule on, and I am putting both numbers up rather than choosing.

The 3%/5% relative-error limits were written as a **proxy** for the displacement limits set in the
earlier pre-registration — G1, p95 ≤ 15bp and max ≤ 30bp on the **collapsed real cost of equity**,
which is the number that actually enters a valuation. **The proxy turned out to be tighter than the
thing it was proxying.** Converting D3's p95 error into displacement:

| semi-deviation decile | ratio | 1985 | 1995 | 2000 | 2005 | 2010 |
|---|---|---|---|---|---|---|
| d1 (calmest) | 0.674 | ≥11bp | **≥7bp** | ≥6bp | ≥4bp | ≥2bp |
| d5 (median) | 0.939 | ≥15bp | **≥10bp** | ≥8bp | ≥5bp | ≥3bp |
| d9 (most volatile) | 1.536 | ≥24bp | **≥17bp** | ≥13bp | ≥9bp | ≥4bp |

**On the relative-error gate, nothing before 2010 passes. On the displacement gate — the one tied
to the valuation — the 1995 profile passes for roughly the first eight deciles at 7 to 10 basis
points and breaches only for the most volatile decile at 17bp.** Both were pre-registered. They
disagree because I set the proxy too tight, and that is my specification error, not a result.

For orientation on materiality: at a 6.27% real cost of equity, 10bp is 1.6% of the discount rate
and moves a neutral value by about the same 1.6%.

---

## 5. THE SECTOR ROUTE, WHICH IS IN BETTER SHAPE THAN THE COMPANY ONE

James also asked for sector-level ERP and cost of equity, and the data for that is already here:
`outputs/gfd_sector_price_raw/extracted/` — eleven Global Financial Data S&P sector workbooks, 60
sector and sub-sector index series. Verified periodicity on the energy series (10,176
observations, September 1910 to November 2014):

| period | frequency | usable? |
|---|---|---|
| 1910 – 1925 | monthly | no — 12 observations a year cannot carry this statistic |
| 1926 – 1989 | **weekly** | needs a weekly-to-daily bridge |
| **1990 – 2014** | **daily** | **directly computable with `idio/semidev.py` as it stands** |
| 2014 – today | absent | needs joining to a modern sector series |

**A sector index has no missing-constituent problem at all** — Global Financial Data computed the
index; we are not reassembling it from names we happen to have. That removes the entire difficulty
this document is about.

Two gaps, both ordinary work rather than research. The 2014-to-today join, which the daily overlap
from 1998 makes testable against sector ETFs or a panel-built aggregate. And the weekly-to-daily
bridge for 1926–1989, **which is the same construction that already worked for the market leg** —
fit two parameters on the 1990–2014 daily overlap, pre-register the falsifiers first, and carry the
statistic back. The market bridge scored 0.80 out of sample doing exactly this.

**Sectors are the better first target and I did not expect that when the session started.**

---

## 6. WHAT I RECOMMEND

Three things, in order, and the first one needs a ruling from James rather than from me.

1. **Rule on the displacement question.** Is 7 to 17 basis points of denominator uncertainty
   acceptable on a valuation dated 1995? My view is yes for historical analysis — the questions
   history is asked are "was the market cheap", not "should I trade this" — and no for anything
   published as a live number. If James agrees, the company leg runs back to roughly **1985** on
   direct computation, with the error and the imputed cap share stated on every number's face.
2. **Build the sector leg on the daily 1990–2014 window first.** It needs no new method, no
   imputation, and no ruling. It is the shortest path to something publishable.
3. **Then pre-register the weekly-to-daily sector bridge** for 1926–1989, on the pattern that
   already worked.

**What I would not do** is spend more effort on the company denominator before 1985. Three models
have now been tried; the stopping rule says the answer is that the panel does not support it, not
that a fourth model is needed.

## ARTIFACTS

`outputs/2026-08-20-partial-panel/panel_detail.csv` — per-name semi-deviation and market cap at 54
quarterly dates, 2013–2026, 26,000 rows. `tools/partial_panel_degradation.py` (D1/D2 and the dump),
`tools/partial_panel_D3.py`, `tools/imputed_denominator.py`.

## WHAT IS NOT CLAIMED

Nothing here touches the market leg, the term structure past one year, Region 2, Region 3, or the
four-method tie. The departure-volatility tilt of 1.18 is measured on 2013–2018 and assumed
stationary before that, which is exactly the kind of assumption this project's standing suspicion
is about; it should be re-measured on any period where the data allows.
