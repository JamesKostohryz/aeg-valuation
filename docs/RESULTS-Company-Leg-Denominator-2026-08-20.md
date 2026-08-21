# RESULTS — tier A is dead, and the historical universe is not unnecessary, it is unavailable

**2026-08-20. Run against `PREREG-Company-Leg-Denominator-2026-08-20.md`, committed as
`aeg-valuation a6ff42f` before k was measured at any date but today. Four of the five gates fail.
They are reported first, and no threshold was moved.**

---

## THE VERDICT

| | gate | limit | measured, primary window | |
|---|---|---|---|---|
| **G1** | displacement in the collapsed real cost of equity | p95 ≤ 15bp, max ≤ 30bp | **≥ 41bp to ≥ 98bp** depending on the name | **FAIL** |
| **G2** | secular drift | ≤ 10% | 7.5% on 2011–2026; **30.9% on 1995–2026** | pass / **FAIL** |
| **G3** | crisis conditioning | ≤ 10% | **23.0%** | **FAIL** |
| **G4** | dispersion, sd/mean | ≤ 8% | **24.2%** | **FAIL** |
| **G5** | panel validity, count coverage ≥ 80% | per date | passes only from **2011-06-30** | **FAIL before 2011** |

**k is not approximately constant. It ranges from 0.63 to 2.18 on the clean window alone — a
factor of 3.5 — and from 0.63 to 2.87 over the full period measured.** There is no k̄ that can
stand in for the measured denominator, and the pre-registered decision rule is unambiguous: *"G3
fails alone → tier A is dead and is not repaired. Fitting a crisis-conditional correction is
fitting a second parameter to the failure that falsified the first, on the same data."*

**I predicted this failure in section 3 of the pre-registration, before measuring, and named both
channels. Both fired.**

---

## WHAT k ACTUALLY IS, AND WHY IT COULD NEVER HAVE BEEN CONSTANT

This is the part worth keeping after the gates are forgotten.

The numerator is the average *idiosyncratic* downside deviation; the denominator is the *index's*
downside deviation. In a one-factor market with average pairwise correlation ρ̄, index variance is
ρ̄σ² and residual variance is (1−ρ̄)σ², so

```
k = sqrt( (1 − ρ̄) / ρ̄ )        and equivalently        ρ̄ = 1 / (1 + k²)
```

**k is average pairwise correlation wearing a different hat.** Asking whether it is stable is
asking whether the correlation of everything with everything else is stable, which it is not, and
which is one of the most heavily documented facts in market microstructure.

Inverting the measured series is the external check this project's standing suspicion demands —
a number that is internally consistent and externally wrong is the failure mode, so here is the
external comparison:

| date | k | implied ρ̄ | what that market was |
|---|---|---|---|
| 1995-06 | 2.85 | **0.11** | calm, high dispersion *(32% coverage — exploratory)* |
| 1999-12 | 1.94 | 0.21 | late bubble *(43% coverage)* |
| 2002-09 | 1.43 | 0.33 | post-bubble bear |
| 2008-12 | 0.82 | **0.60** | global financial crisis |
| 2011-09 | 0.90 | 0.55 | the euro crisis, the risk-on/risk-off market |
| 2018-12 | 1.12 | 0.44 | the Q4 drawdown |
| **2020-04** | **0.63** | **0.72** | **COVID — everything moved together** |
| 2022-06 | 1.00 | 0.50 | the rate shock |
| 2024-08 | 1.67 | 0.26 | narrow leadership, wide dispersion |
| **2026-08** | **1.87** | **0.22** | **today** |

Those correlations are right. They are not a rescaled copy of the input — they land on the values
and, more tellingly, the *ordering* that CBOE's implied-correlation series has printed through the
same episodes: 0.5–0.6 in the financial crisis, a spike above 0.7 in March–April 2020, the low
0.2s in the dispersed post-2023 market. **The measurement is real. It is the hypothesis that was
wrong.**

And this reframes the whole exercise. Region 1 charges a company for its risk *relative to the
average*, so the denominator is a diversification measure. **Substituting a constant k̄ would have
asserted that the diversification benefit of holding the S&P 500 was the same in April 2020 as in
August 2026.** It was not; it was less than a third as large. A valuation built on that assumption
would have been internally perfect and externally absurd — with the four-method tie green
throughout, because the tie cannot see a discount rate that is merely wrong.

---

## THE LAG ROBUSTNESS CHECK — the verdict does not depend on a convention

Section 4.3 pre-registered that k be computed twice, at production lags (numerator 60, denominator
0) and with both legs at lag 60, and that **disagreement between them is itself a FAIL**.

| window | version | mean | min | max | G4 | G3 | G2 |
|---|---|---|---|---|---|---|---|
| 2011–2026 | lag 60/0 | 1.373 | 0.629 | 2.185 | **24.2% F** | **23.0% F** | 7.5% P |
| 2011–2026 | lag 60/60 | 1.362 | 0.733 | 2.109 | **22.3% F** | **17.2% F** | 7.2% P |
| 1995–2026 | lag 60/0 | 1.552 | 0.629 | 2.865 | **29.2% F** | **22.1% F** | **30.9% F** |
| 1995–2026 | lag 60/60 | 1.558 | 0.733 | 2.911 | **29.6% F** | **20.1% F** | **32.6% F** |

**They agree on every gate.** The three-month offset does inflate the crisis effect — matched
windows move April 2020's k from 0.63 to 1.33, because at production lags the numerator's window
ends just *before* the crash while the denominator's includes it — but the compression is real
and merely arrives later: June and July 2020 read 0.74 under **both** conventions. The conclusion
is not an artefact of a lag choice.

---

## THE PRE-REGISTERED TIE-BREAKER, AND IT CLEARS THE PANEL

G5 warned that a thin panel biases the numerator **down**, most in crises, which is the same
direction as the correlation channel — so a G3 failure could have been either. The
pre-registration fixed the tie-breaker in advance: report drawdown-day coverage alongside G3.

**On the primary window, coverage on drawdown months averages 99.0% against 95.2% on calm
months.** Coverage is *higher* exactly where G3 fails. The panel cannot be the explanation, and
the failure is the economics.

The same tie-breaker cuts the other way on G2 and strengthens it. Panel coverage rises from 32% in
1995 to 99% today, and the pre-registered bias direction says early k is biased **low** — yet
early k is the **high** end of the range (1.85 in the first decade against 1.37 in the last). The
true drift is therefore **larger** than the 30.9% measured, not smaller.

---

## AND THE ANSWER TO THE QUESTION YOU ACTUALLY ASKED

> *"We do have this historical data going back to 1960 and even further back, but I wonder if all
> of that is necessary."*

**It is not unnecessary. It is not there.** That is the finding of the day, and it is worth more
than the gate table.

The membership roster is fine: CRSP gives point-in-time S&P 500 membership from 1925, 1,788
windows over 1,678 securities, and it is already parsed in
`outputs/crsp_store/parsed_windows.json`. What does not exist in this project is **daily prices
for those securities**, and the semi-deviation statistic is a daily statistic. Measured against
the true roster:

| date | true members | in the daily-price panel | by count | **by market cap** |
|---|---|---|---|---|
| 1975-06 | 500 | 90 | 20% | 54% |
| 1985-06 | 500 | 136 | 31% | 52% |
| 1995-06 | 500 | 177 | 41% | 62% |
| 2000-06 | 500 | 249 | 59% | 77% |
| 2005-06 | 500 | 291 | 70% | 87% |
| 2010-06 | 500 | 378 | 92% | 95% |
| 2012-12 | 500 | 399 | 95% | 96% |

*(cap coverage computed from Compustat quarterly `mkvaltq`/`cshoq × prccq` on CRSP PERMNOs — the
whole roster, not just the panel, so this is coverage of the true index and not of itself.)*

**The reason is mechanical, and it is the same defect class this project keeps finding.** The
daily panel — `outputs/eodhd_store/prices_adj_close_v2`, 816 tickers, 6.20M rows, 1962–2026 — was
built from EODHD's own historical membership list, and EODHD's index-membership tracking is
reliable only from about 2012 (`sector_aggregates.RELIABLE_MEMBERSHIP_FLOOR` says so in its own
docstring). So the panel is not a sample of the historical index. It is *today's* index plus the
163 names EODHD happened to keep after they left, projected backwards. It looks like a historical
universe and it is not one, and every gate on it would have stayed green.

**Compustat does not fix it.** `outputs/compustat_raw/all_data.csv` has 1,483 PERMNOs with
quarterly prices and share counts from 1970 — enough to measure the *coverage* above, which is
what it was used for here, and not enough to compute a daily statistic. There is no CRSP daily
stock file anywhere in this project; I looked at every file over 50MB.

---

## WHAT WAS VERIFIED, NOT ASSERTED

- **The statistic is imported, never reimplemented.** `idio/semidev.py::blended_semidev`, lag 60,
  0.5/0.5 blend. The 700-day slicing shortcut was proved equal to the full-series call: **worst
  absolute difference 0.000e+00 over 40 calls** spanning the window, and the run refuses to
  continue above 1e-9.
- **The denominator is read, not recomputed.** `outputs/market_semidev_history.csv`, spot-checked
  against the published file at six dates across thirty-one years — exact match at every one. The
  lag-60 variant calls `idio/market_semidev_bridge.py::market_semidev` directly, so there is still
  no second implementation of either statistic.
- **It reproduces production.** My capw at 2026-08-12 is **19.6509** against the published
  **19.6820** at 2026-08-18 — 0.16% apart on six days and a different price source. The end-to-end
  path is the production path.
- **The membership is point-in-time, not frozen.** NVIDIA absent in 1999 and present from 2005;
  Activision absent at 2015-06-30 and present from its true 2015-08-31 addition; `n_true` varies
  478–505 across the window. A frozen list was the failure mode and it is not present.
- **No threshold was moved.** The five constants at the top of `tools/tierA_gates.py` are the five
  in the pre-registration, and the file is meant to be diffed against it in one glance.
- **One honest deviation.** The G1 test companies were to be "selected before k is computed". The
  *rule* was fixed in advance and is mechanical — the 10th, 50th and 90th percentiles of the
  current cross-section, plus MSFT and PEP — but the names were extracted after the run. They are
  AAPL, HAS and ARE, and the rule left no choice in them.
- **One known imperfection, disclosed.** After 2012 the roster comes from EODHD, which returns
  478–505 names where the true index is 500. Where it undercounts it *inflates* count coverage,
  which flatters G5. It does not affect any date's k.

---

## WHAT I RECOMMEND, AND IT IS ONE DECISION

**Do not build tier B.** A fixed panel of long-lived large caps does not address what failed.
Nothing failed because the panel was the wrong panel; k failed because the quantity it stands for
moves by a factor of three. A fixed panel would inherit that and add survivorship on top.

**The direct computation already works, and it is bounded by data, not by method.** Everything in
this document was produced by computing `capw_avg_semidev` directly from point-in-time membership.
It clears the 80%-by-count gate from **June 2011**, and clears 80% *by market cap* — the
economically relevant measure for a cap-weighted mean, and the one I should have pre-registered —
from **July 2002**. A company premium for any date after that needs no k and no calibration. It
needs the panel it already has.

**Before 2002 there is nothing to compute it from, and the fix is a download, not a design.** The
CRSP Daily Stock File on WRDS — the same subscription the Compustat pull came from — carries
`PERMNO`, `DATE`, `PRC`, `RET` and `SHROUT` daily from 1925. That single file supplies the
numerator, the denominator *and* the cap weights for the entire roster CRSP has already given us
the membership for, on total returns rather than adjusted closes, which matches the SPY convention
better than what we use today.

**So the one question: shall I write the pre-registration for a direct, point-in-time company leg
back to 2002 on the data in hand — and separately give you the exact WRDS query for the CRSP Daily
Stock File that would extend it to 1925?** I recommend yes to both, in that order, because the
first is an afternoon and publishes something, and the second is a download whose cost is your
time rather than mine.

**Until one of those lands, no historical valuation before 2002 may carry a company-specific
premium.** The honest interim treatments, both pre-authorized in section 7 of the
pre-registration, are to publish market-level only, or to hold the premium at its live value and
say so on the face of the number. Neither may be adopted silently.

---

## ARTIFACTS

- `outputs/2026-08-20-tierA-denominator/tierA_k_full.csv` — 375 monthly observations, 1995-06-30
  to 2026-08-12, with both lag conventions, coverage by count and by cap, the drawdown flag and
  the implied average correlation.
- `outputs/2026-08-20-tierA-denominator/market_semidev_lag60.csv` — the denominator at the company
  lag, 25,290 days, 1929–2026, from the bridge's own function.
- `tools/tierA_denominator_ratio.py` — the measurement, resumable, with the slicing-equivalence
  proof built in as a refusal.
- `tools/tierA_market_semidev_lag60.py`, `tools/tierA_gates.py` — the robustness leg and the gates.

## WHAT IS NOT CLAIMED

This tested the **denominator of Region 1** and nothing else. It says nothing about the ERP term
structure past one year, nothing about `COMMON(t)` historically, nothing about Region 3, and
nothing about whether historical valuation is a good idea. It also inherits, unchanged, the
semi-deviation bridge's own measured defect: the market reconstruction **overstates** risk near
drawdowns by 1.05 to 2.69 VIX points, so any historical premium built on it carries that term too.
