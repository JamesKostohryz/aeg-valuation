# RESULTS — James's constant-denominator proposal, tested

**2026-08-20. Judged on G1, the displacement criterion fixed in
`PREREG-Company-Leg-Denominator-2026-08-20.md` on the same day, before any of this work: p95 ≤
15bp and max ≤ 30bp on the collapsed real cost of equity. No new criterion was invented for this
test and none was moved.**

---

## THE PROPOSAL, AND WHY IT IS NOT TIER A

> *"We don't need data for every year we are going to apply an idiosyncratic premium… We simply
> see how it works on a sample of the last 20 years or so and then we apply the same model going
> backwards. The stock's downside deviation over a 1 and 2 year period can be compared to a
> long-term weighted average or median. As long as that weighted average or median has been
> stationary over long periods of time, then it should be fine."*

**This is a different proposal from the one that failed this morning, and the distinction
matters.** Tier A scaled the denominator off the *market's* semi-deviation at each date; it failed
because that scaling factor turns out to be average pairwise correlation and moves by a factor of
three. James's proposal uses no market series at all. The denominator is **one number**, the
long-run central value of the cross-sectional average, held fixed at every historical date.

**The premise is empirical and testable, and the first half of it is correct.**

---

## 1. IS THE DENOMINATOR MEAN-REVERTING? YES — BUT FAR TOO SLOWLY TO HELP

Monthly, 1995-06 to 2026-08, 375 observations of `capw_avg_semidev`:

| | |
|---|---|
| AR(1) coefficient, on logs | **0.9907** |
| implied half-life | **6.2 years** |
| mean / median | 18.25 / 17.35 |
| standard deviation | 4.71, **25.8% of the mean** |
| range | 12.27 to 33.64, a factor of **2.74** |
| successive five-year means | 19.8, 24.5, 18.9, 15.3, 13.5, 17.3 |

**It reverts, and it has no trend — James's stationarity premise is satisfied.** It is also the
slowest possible way for that to be true. A half-life of six years means a deviation opened in
2000 is still half-present in 2006. The five-year means run from 13.5 to 24.5, a spread of 81%,
and those are *averages of sixty months each*, not spikes.

**Stationary over a century and close to its mean on any given date are different properties, and
the premium needs the second one.**

---

## 2. WHAT THE CONSTANT COSTS

The error passes **one for one** into every company's premium, because the premium is linear in
one over the denominator:

| constant used | median \|e\| | p95 \|e\| | max \|e\| | range |
|---|---|---|---|---|
| long-run mean, 18.25 | 15.3% | 59.3% | 84.3% | −33% to +84% |
| long-run median, 17.35 | **12.5%** | **67.6%** | 93.9% | −29% to +94% |

Converted to the pre-registered criterion — displacement in the **collapsed real cost of equity**:

| | ratio | at the p95 error | at the maximum |
|---|---|---|---|
| calmest decile | 0.674 | ≥ **47bp** | ≥ 65bp |
| median decile | 0.939 | ≥ **66bp** | ≥ 91bp |
| most volatile decile | 1.536 | ≥ **107bp** | ≥ 149bp |

**Against limits of 15bp and 30bp.** For comparison, computing the denominator directly from the
partial panel we already have costs **7 to 17bp** at a 1995-shaped panel. **The constant is six to
ten times worse than the option already on the table.**

And it fails the crisis test the direct method passes: the error on drawdown months is **1.87×**
the error on calm months, where the partial panel ran 0.93× to 1.14×.

---

## 3. WHY IT FAILS — AND IT IS NOT A DATA PROBLEM, IT IS A DOUBLE COUNT

The construction is `ERP_i(t) = market_ERP(t) × semidev_i(t) / denominator(t)`. In a crisis
**both** the company's own semi-deviation and the cross-sectional average rise together. Dividing
by the contemporaneous average cancels that common movement, which is the whole point: what
survives is the company's *relative* risk. Holding the denominator fixed removes the cancellation,
so the company's premium rises with market-wide volatility — **at the same time as
`market_ERP(t)` is already rising for the same reason.** The crisis gets paid for twice.

**Microsoft makes it concrete.** Its premium multiplier, `semidev / denominator`:

| date | MSFT semidev | contemporaneous capw | vs capw(t) | vs constant 17.35 |
|---|---|---|---|---|
| 2002-09, post-bubble | 21.41 | 23.24 | **0.922** | 1.234 |
| 2008-12, financial crisis | 17.38 | 21.35 | **0.814** | 1.002 |
| **2009-06, the trough** | 22.02 | 26.17 | **0.841** | **1.269** |
| 2020-04, COVID | 8.05 | 13.64 | **0.590** | 0.464 |
| 2026-06, today | 14.95 | 20.04 | **0.746** | 0.862 |

Against the contemporaneous average, Microsoft is *less* risky than the typical company at every
one of those dates — 0.59 to 0.92 — which is true and is what its premium should say. Against a
constant, Microsoft becomes **27% riskier than average at the bottom of the financial crisis**.
Nothing about Microsoft changed. The market's volatility did, and the constant attributed it to
Microsoft.

**The general form of that, measured.** For each name, the variability over time of its own
relative-risk ratio — lower is better, because a company's relative riskiness ought to be a
reasonably stable characteristic rather than noise:

| | vs capw(t) | vs constant |
|---|---|---|
| MSFT | **19.7%** | 37.0% |
| KO | **19.0%** | 38.4% |
| WMT | **19.1%** | 33.5% |
| PEP | **22.8%** | 39.5% |
| JNJ | **23.4%** | 35.8% |
| INTC | **25.4%** | 38.4% |
| XOM | **26.6%** | 32.4% |
| GE | 46.0% | **45.4%** |

**Seven of eight.** The contemporaneous denominator very nearly halves the noise in the thing the
premium is supposed to measure. GE is the exception and is the one company in the list that
genuinely changed character over the period.

---

## 4. WHERE JAMES IS RIGHT, AND IT IS THE PART THAT MATTERS

**"We don't need data for every year" is correct, and it is already established.** What is not
needed is the *complete* universe. What is needed is a *contemporaneous* denominator, and the
partial panel supplies one — at a cost of 7 to 10 basis points for ordinary names back to 1995,
and 11 to 15 back to 1985, measured today under a decile-matched degradation model.

The distinction is between **completeness**, which we do not have and do not need, and
**contemporaneity**, which we do have and cannot do without. The constant sacrifices the second to
buy relief from the first, and the first was not the binding constraint.

---

## 5. WHAT IS NOT CLAIMED

The AR(1) is fitted on 1995–2026, where panel coverage rises from 32% to 99%. The decile-matched
model says that bias is near zero on average (mean signed error +0.06%), but it is noisy, so the
half-life of 6.2 years should be read as an order of magnitude and not to one decimal. It does not
change the verdict: the standard deviation would have to fall below about 3% of the mean for a
constant to pass, and it is 25.8%.

`outputs/2026-08-20-constant-denominator/capw_series.csv`, `tools/constant_denominator_test.py`.
