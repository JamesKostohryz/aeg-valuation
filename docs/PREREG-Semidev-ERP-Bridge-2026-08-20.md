# PRE-REGISTRATION — reconstructing the market equity risk premium before options existed

**Written 2026-08-20, BEFORE the out-of-sample test is run. Everything in sections 3 to 6 is
fixed now and may not be changed after a result is seen. If it has to change, that is a new
document with a new date and the reason written down.**

---

## 1. WHAT HAS ALREADY BEEN SEEN, DECLARED HONESTLY

A pre-registration that hides what its author already knows is worthless, so:

**Already measured, on the FULL 2007–2026 overlap, and reported to James before this document
existed:**

- market semi-deviation, engine convention, mean 13.22, sd 5.22, range 5.86 to 29.11
- VIX1Y, mean 23.60, sd 5.73, range 13.31 to 53.53
- correlation at the production 60-day lag: **0.622**; at lag 0: **0.806**; at lag −63: 0.802
- the full-sample two-moment bridge: **VIX_equiv = 8.9374 + 1.1053 × semidev**
- full-sample Martin-ERP error: mean 0.000 pp by construction, sd 2.184, p95 |err| 4.883
- reconstructed levels at nine historic dates (1932 14.13%, 1987 13.24%, 2009 15.29%, today 4.23%)

**NOT yet seen, and this document exists to fix the rules before it is:**

- any split-sample fit or its out-of-sample error
- any error conditioned on drawdown proximity
- the size of the splice step at the 2007 boundary
- anything about tenors other than the 1-year point
- the reconstruction before 2007 other than the nine spot dates above

The choice of *form* (two-moment match, lag 0) was made on the full sample and is therefore
**in-sample**. That is exactly why the test below is a split-sample test and why its acceptance
criteria are written down now.

---

## 2. THE PROBLEM, AND WHY ONLY ONE LEG OF IT IS ACTUALLY A PROBLEM

Historical abnormal-earnings-growth valuation needs a historical cost of equity, which needs a
historical market equity risk premium and a historical idiosyncratic premium. The live method
takes both from options. Options do not exist historically: **CBOE VIX1Y begins 2007-01-03**
(verified by direct download: 4,933 rows, first row 03/01/2007), and single-name implied vol
term structures are a live scrape with no history at all.

**The idiosyncratic leg needs no substitute, because the production method is ALREADY a
semi-deviation method.** `idio/semidev.py` computes

```
semidev_i = 0.5 × resid_semidev(i, 1y) + 0.5 × resid_semidev(i, 2y)
```

— the downside semi-deviation, about its own mean, of the residual from a market-model
regression of daily log returns — and `idio/erp.py` prices Region 1 off that name's statistic
against the cap-weighted universe average. Going backwards changes only the market proxy (SPY
begins 1993; the spliced index is used before) and each company's own price history. **Nothing
about the idiosyncratic construction is being replaced, and nothing needs harmonizing.**

**Only the market leg needs a bridge.** That is the whole of the exercise below.

---

## 3. THE BRIDGE, FIXED IN ADVANCE

**3.1 What is bridged.** `semidev_market(t) → VIX1Y_equivalent(t)`. **The bridge targets the RISK
INPUT, not the equity risk premium.**

This is the central design decision and it is deliberate. James has said the current ERP
methodology is going to be superseded. A bridge fitted to today's *ERP output* would have to be
rebuilt when the methodology changes; a bridge fitted to the *vol input* would not — whatever
model replaces the current one consumes the reconstructed VIX-equivalent exactly as it consumes
VIX1Y today. **Recalibrating later is two numbers, not a rebuilt history.**

**3.2 The statistic.** The market's own downside semi-deviation, computed with
`idio/semidev.py`'s primitives — the same `_semidev_about`, the same 0.5/0.5 blend of one- and
two-year trailing windows, the same annualization and the same per-cent scaling. **It is
imported, never reimplemented**, so there is no second version of the statistic. The market has
no market-model residual, so the raw index log return is used in place of the residual; that is
the only difference and it is a definition, not a choice.

**3.3 The lag is ZERO, and this is a departure from production.** `idio/semidev.py` ends its
window `LAG_TRADING_DAYS = 60` before the as-of date, so that a company is not charged for its
own last three months of price action. **That rationale is about idiosyncratic reflexivity and
does not apply to the market aggregate**, and it costs 18 points of correlation (0.622 vs 0.806).
The market bridge therefore uses lag 0. The company statistic keeps its 60-day lag, unchanged.

**Looking forward is REJECTED, and the measurement is why.** Shifting the window forward a
quarter gives 0.802 — *worse* than lag 0. There is no case for accepting look-ahead bias for a
fit it does not improve, so the reconstruction uses only information available at the time.

**3.4 The functional form: a two-moment match.**

```
VIX_equiv(t) = a + b × semidev_market(t)
      b = sd(VIX1Y) / sd(semidev)          a = mean(VIX1Y) − b × mean(semidev)
```

**Two parameters, no more.** A two-moment match rather than ordinary least squares because the
reconstruction must reproduce the *spread* of the premium, not only its conditional mean:
least squares would shrink the historical range toward the average and flatten every crisis. The
cost is that it is not the minimum-error estimator, and that cost is reported.

**3.5 Which tenors are bridged.** Tenors **1 to 10 only**. Beyond that the live construction is
dominated by the plateau preset — measured 2026-08-20, holding the vol-scale flat changes the
30-year premium by **exactly 0.000 pp** and the duration-collapsed effective by 7bp median. The
long end needs no historical input because it does not depend on one.

**3.6 The splice.** Live method from 2007-01-03. Bridge before. A **linear blend over the five
years 2007-01-03 to 2012-01-03**, weight on the bridge running 1 → 0. **The step size at the
boundary is measured and reported BEFORE the blend is applied**, because a blend that hides a
large step is a cosmetic device.

---

## 4. THE TEST, FIXED IN ADVANCE

**4.1 Split-sample, both directions.** Fit the two parameters on 2007-01-03 → 2016-12-31, test on
2017-01-01 → 2026-08-20. Then fit on the second half and test on the first. **Both are reported
whichever way they come out.**

**4.2 The conditional test, which is the one that matters.** A realized-volatility proxy fails by
lagging: it stays high after a crash and is low going into one. A pooled error statistic hides
this, because most days are calm. So error is reported **separately for days within 12 months of
a drawdown** — defined here, in advance, as any day on which the S&P 500 is more than 20% below
its trailing 252-day maximum, plus the 252 trading days following the last such day.

**4.3 Reported metrics**, on the VIX-equivalent and on the Martin premium (`VIX²/100`):
mean error, standard deviation of error, p95 absolute error, maximum absolute error, and
correlation — each computed overall, and again on the drawdown-conditional subset.

---

## 5. THE FALSIFIERS

Written now, and if one fires it goes to James rather than into the engine.

**F1 — the bridge does not survive out of sample.** Out-of-sample correlation below **0.60** in
either split direction. *(In-sample full-period is 0.806. If it falls below the production 60-day
lag's own in-sample 0.622, the relationship is an artefact of the fitting window.)*

**F2 — it fails where it matters.** Standard deviation of the VIX-equivalent error on the
drawdown-conditional subset more than **twice** the unconditional standard deviation. *(This is
the specific failure mode of realized-vol proxies and the reason for section 4.2.)*

**F3 — the sign of the lag reverses.** If the fitted relationship on either split has **b ≤ 0**,
the statistic is not measuring what it is supposed to measure.

**F4 — the splice is a cliff.** A step at 2007-01-03 exceeding **5 VIX points** before blending.
*(A blend can smooth a small step honestly; smoothing a large one is concealment.)*

**F5 — the reconstruction produces impossible levels.** Any reconstructed VIX-equivalent below
**5** or above **100**, or any reconstructed market premium below **0**.

---

## 6. WHAT IS NOT CLAIMED

- **This is not an ERP model.** It is a reconstruction of a vol input, so that an ERP model can
  be run historically. Errors in the ERP model are not corrected by it and not measured here.
- **It cannot see a repricing that has not reached realized returns.** October 1987 is the test
  case: implied volatility exploded within hours and semi-deviation takes weeks at lag 0. The
  reconstruction will be late to every shock, by construction, and how late is what section 4.2
  measures.
- **The pre-1962 data is a different object.** Daily index closes before the CRSP era are a
  splice (Global Financial Data to GSPC). **The 1974 reconstruction already looks wrong** — a
  market semi-deviation of 12.73 at the October 1974 trough is implausibly calm for that bear
  market, and the 1970s splice must be checked before any 1970s valuation is quoted. Recorded
  here as a known suspicion, in advance.
- **Nothing here touches the idiosyncratic leg**, which is already this statistic.
- **The reconstruction reaches 1930**, not 1928: the two-year window needs two years of returns
  and the series begins 1927-12-31.

---

Written 2026-08-20. Sections 3 to 6 may not be revised after the first out-of-sample number is
produced.
