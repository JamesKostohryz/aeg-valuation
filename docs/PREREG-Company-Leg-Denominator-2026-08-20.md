# PRE-REGISTRATION — the company leg's denominator going backwards, and whether the universe's history is needed at all

**Written 2026-08-20, BEFORE the ratio has been measured at any date other than today.
Sections 3 to 8 are fixed now and may not be changed after a result is seen. If one has to
change, that is a new document with a new date and the reason written down, and this result is
reported alongside it.**

---

## 1. THE QUESTION, AS JAMES ASKED IT

> "We do have this historical data going back to 1960 and even further back, but I wonder if all
> of that is necessary."

It is the right question and it has a cheap answer. Every company's premium is priced off one
ratio:

```
ERP_i(front) = market_ERP(front) x semidev_i / capw_avg_semidev
```

The **numerator** — that company's own blended residual semi-deviation — needs only that
company's own price history, which exists for any company worth valuing. It was never the
problem.

The **denominator** — `capw_avg_semidev`, the cap-weighted average across the S&P 500 — is the
piece that appears to need the whole index's price history *and* its point-in-time membership at
every historical date. That is the expensive thing, and it is charged to every name at every
tenor: get it wrong and every premium is wrong together, quietly, with the four-method tie green
throughout.

**Tier A asks whether the denominator can be had for free.** `capw_avg_semidev` is a market-level
aggregate. The market's *own* semi-deviation has already been reconstructed daily to 1929-09-14
(`outputs/market_semidev_history.csv`, 25,350 days). If

```
k(t) = capw_avg_semidev(t) / market_semidev(t)
```

is stable, then `capw_avg_semidev(t) ≈ k̄ x market_semidev(t)` back to 1929 and **no universe
history is needed at all** — not to 1960, not to 1990. If k is not stable, we know by how much
and in which direction, and the decision moves to tier B (a fixed panel of long-lived large caps)
or to not doing it.

---

## 2. WHAT HAS ALREADY BEEN SEEN, DECLARED HONESTLY

**Seen, and unavoidable — it is in documents this session had to read:**

- `capw_avg_semidev` **19.6820** at `px_asof` 2026-08-18, recomputed here from
  `outputs/idio_universe_latest.csv` (499 names, all with market caps). Cross-section: min 10.73,
  median 19.24, max 60.73.
- `market_semidev` **10.5244** at 2026-08-12, the last row of `outputs/market_semidev_history.csv`.
- Therefore **one point of k, today: 1.870.** That is the whole of what I know about its level.
- Microsoft's published Region 1 inputs: semi-deviation 15.82 against the 19.68 denominator,
  ratio 0.804x, front premium **−0.8104pp**, implying `market_ERP(front) ≈ 4.13pp`. Used below
  only to calibrate a sensitivity analytically.

**Not seen, and this document exists to fix the rules before it is:**

- k at any date other than 2026-08.
- Any time series, trend, crisis behaviour or dispersion of k.
- Any historical `capw_avg_semidev` at any date.
- The coverage of the price panel against point-in-time membership at any historical date.

The *form* of the proposal — one scalar k̄, applied multiplicatively — is inherited from the
handoff and is not a finding of mine. The thresholds below are mine, and section 5 says why two
of them differ from the ones the handoff proposed.

---

## 3. MY PRIOR, WRITTEN DOWN BEFORE MEASURING: I EXPECT THIS TO FAIL

A pre-registration that does not say what its author expects is theatre. **I expect k to be
unstable, for two independent and separately documented reasons.** If the measurement comes back
clean on both, the correct first response is to suspect the measurement, not to celebrate.

**Channel one — correlation asymmetry in crashes.** The numerator is the average *idiosyncratic*
(market-model residual) downside deviation; the denominator is the *index's* downside deviation.
In a crash, cross-sectional correlation rises toward one: the index's own volatility rises more
than the average residual's, because the residual is by construction what is left after the
common factor is stripped out. So **k should fall sharply in 2008 and 2020, and again in 1987 and
1929 if it could be measured there.** This asymmetry is not speculative — it is the standing
result of Longin and Solnik (2001) and Ang and Chen (2002), that correlations rise in down markets
specifically.

**Channel two — secular drift in idiosyncratic volatility.** Campbell, Lettau, Malkiel and Xu
(2001) document a rising trend in firm-level volatility *relative to* market volatility over
1962–1997 — which is exactly the numerator of k rising against its denominator over three and a
half decades. Bekaert, Hodrick and Zhang (2012) and Brandt, Brav, Graham and Kumar (2010) find
that trend reversed after 2000. Either finding on its own is fatal to a single constant k spanning
1929–2026; together they say the ratio has a hump, not a level.

**What this means for the reading of a pass.** If k passes on 2000–2026 alone, that window sits
entirely inside the post-2000 reversal and tells us nothing about 1929–2000. Section 6 therefore
pre-registers that **a pass on the modern window alone does not license extension to 1929**, and
what would.

---

## 4. WHAT WILL BE COMPUTED, FIXED IN ADVANCE

### 4.1 The numerator

At each month-end date `d` in the window, for each ticker in the **point-in-time** S&P 500
membership at `d`:

```
semidev_i(d) = idio/semidev.py :: blended_semidev(stock, market, asof=d)
```

**The production function, imported, not reimplemented.** Lag 60 trading days, 0.5/0.5 blend of
the one- and two-year residual semi-deviations, `clean_series` truncation at the last adjustment
discontinuity, `None` returned rather than a one-year figure wearing the two-year name. There is
one implementation of this statistic in the repository and there must never be a second.

Cap weight: `shares_annual` for the fiscal year covering `d`, times the unadjusted close on `d`.
A name with a semi-deviation but no share count still exists; it simply does not vote on the
weight. That is `idio/universe.py`'s own convention and it is kept.

```
capw_avg_semidev(d) = Σ cap_i(d) x semidev_i(d) / Σ cap_i(d)      over names with both
```

**Membership source, fixed now:** CRSP point-in-time windows for `d ≤ 2012-12-31`
(`outputs/crsp_store/parsed_windows.json`, 1,788 windows over 1,678 PERMNOs), EODHD's
`universe()['historical']` after — the splice `tools/crsp_membership.py` already establishes and
justifies. Not today's 499 names carried backwards.

**Price panel:** `outputs/eodhd_store/prices_adj_close_v2/*.parquet`, 816 tickers, 6.20M rows,
1962-01-02 to 2026-08-18, of which **163 stopped trading before 2026** — so the panel is not
purely survivors, but it is not the full historical roster either. Section 7's coverage gate is
what decides which dates this panel is allowed to speak about.

**Market proxy:** SPY (`outputs/.px_cache/SPY_US_1950-01-01.json`, 8,443 rows, first 1993-01-29),
which is what production uses and why. Before 1993-01-29 there is no SPY, and the only available
proxy is the ^GSPC price index. See 4.4.

### 4.2 The denominator

Read from `outputs/market_semidev_history.csv`, the published reconstruction. **Not recomputed.**
Recomputing it here would create the second implementation the bridge's own header forbids.

### 4.3 The lag asymmetry, and what it costs

The numerator's window ends **60 trading days** before `d`; the denominator's ends at `d` — the
bridge's pre-registered `MARKET_LAG = 0`. These are different windows and k is therefore a ratio
of two statistics measured three months apart. That is deliberate in production, it is defensible
(the reflexivity argument applies to a single name and not to the aggregate), and **it will not be
"fixed" here.**

But it can manufacture instability at exactly the dates the test cares about, because a
three-month offset straddling a crash puts a calm numerator over a violent denominator. So,
pre-registered: **k is computed twice, once at production lags (60/0) and once with both legs at
lag 60.** If the two versions disagree on the verdict, **the verdict is FAIL** — a conclusion that
depends on a lag convention is not a conclusion.

### 4.4 The pre-1993 proxy, and its own gate

Before 1993-01-29 the residual regression must use the ^GSPC price index
(`outputs/.px_cache/GSPC_INDX_1950-01-01.json`). `idio/semidev.py`'s header says plainly why this
is not equivalent: a price index against total-return stock series puts a dividend yield into
every residual. Pre-registered gate: **k computed on GSPC and k computed on SPY, both over
1995–2005, must agree to within 3% in mean.** If they do not, every date before 1993-01-29 is
reported **UNMEASURED** and takes no part in any verdict.

---

## 5. THE ACCEPTANCE CRITERIA, AND WHY TWO OF THEM ARE NOT THE HANDOFF'S

The handoff proposed two thresholds: that k's standard deviation be under **15% of its mean**, and
that using a fixed k̄ move no reconstructed company premium by more than **25bp** at any date.

**Those two are not compatible with each other, and the arithmetic is one line.** Substituting
k̄·market_semidev for the measured denominator displaces the front premium by

```
Δ idio_i(front) = ERP_i(front) x e,        e = capw_true / capw_hat − 1
```

With Microsoft's published inputs — `market_ERP(front) ≈ 4.13pp`, ratio 0.804x — a relative error
`e` of 15% displaces Microsoft's front premium by **50bp**, twice the stated limit, and for the
highest-risk name in the current cross-section (60.73 over 19.68, a ratio of 3.09x) by **191bp**.
A 15% dispersion criterion therefore *guarantees* the 25bp criterion is violated. To hit 25bp for
Microsoft, `e` must stay under about **7.6%**; for the top of the cross-section, under **2.4%**.

I am resolving the inconsistency **in favour of the displacement criterion**, tightening the
dispersion threshold to match it rather than loosening the displacement threshold to match the
dispersion one. Nothing below is weaker than what was handed down.

I am also **changing the quantity the displacement is measured on**, and this makes the test
stricter in substance while looking looser in units. The front premium is not what enters a
valuation. `D(t)` decays the front differential toward `LAM_ADOPTED = 0.25`, and the curve is then
collapsed to a single rate. The number that reaches the model is the **collapsed real cost of
equity**, so that is what will be measured, by running the production `idio/erp.py` and
`idio/company_curve.py` with the substituted denominator rather than by estimating the
pass-through.

### The five gates

| | gate | limit, fixed now |
|---|---|---|
| **G1** | **Displacement in the collapsed real cost of equity**, per test company per date, from using k̄·market_semidev in place of the measured denominator | **p95 ≤ 15bp and max ≤ 30bp** |
| **G2** | **Secular drift.** \|mean k over the first decade of the window − mean k over the last decade\| / mean k | **≤ 10%** |
| **G3** | **Crisis conditioning.** \|mean k on drawdown days − mean k on calm days\| / mean k, using the drawdown definition **already pre-registered** in the semi-deviation bridge (any day more than 20% below the trailing 252-day maximum, plus the following 252 trading days) — reused verbatim, not reinvented | **≤ 10%** |
| **G4** | **Dispersion.** sd(k) / mean(k) | **≤ 8%** |
| **G5** | **Panel validity.** Share of the point-in-time membership, by count, that the price panel resolves with a computable `blended_semidev` at each date | **≥ 80%, else the date is UNMEASURED** |

**Why 15bp on G1.** At Microsoft's published real cost of equity of 6.2728%, 15bp is 2.4% of the
discount rate and moves a neutral value by roughly the same 2.4% — about **$6.60 a share on a
$276.30 valuation**. 30bp is roughly 4.8%, about $13. That is the outer edge of what can honestly
be called "free". Anything looser and the denominator shortcut is not a saving, it is a second
opinion.

**Test companies for G1, named now, not after seeing the answer:** MSFT and PEP (the two published
valuations); and the names at the **10th, 50th and 90th percentiles of the current
cross-section of `semidev_i`**, selected from `outputs/idio_universe_latest.csv` before k is
computed and listed in the results document. The extremes of the ratio are where the displacement
is largest, and picking the test set after seeing the ratio would be choosing the answer.

**G5's bias has a known sign and it is recorded now.** A panel missing part of the historical
roster is missing, disproportionately, the names that stopped trading — and names that stop
trading are more volatile than names that do not. So a `capw_avg_semidev` measured on an
incomplete panel is **biased low**, k is **biased low**, and the bias is **largest in the periods
with the most attrition**, which are the crises. That is the same direction as channel one in
section 3, which means a G3 failure could be either the economics or the panel. Pre-registered
tie-breaker: if G3 fails, report the drawdown-day coverage from G5 alongside it, and do not
attribute the failure to either cause without it.

---

## 6. WHAT A PASS LICENSES, AND WHAT IT DOES NOT

**Pre-registered, so it cannot be argued afterwards:**

1. A pass on **2000–2026 alone licenses nothing before 2000.** That window lies entirely inside
   the post-2000 reversal documented in section 3. The primary window is therefore the **longest
   window on which G5 holds** — expected to begin around 1995, since SPY starts 1993 and the
   statistic needs two and a quarter years plus the lag — and 2000–2026 is reported as a
   secondary, comparable-to-the-handoff figure only.
2. Any window before 1993-01-29 is **exploratory** whatever it shows, because of the proxy change
   in 4.4 and because G5 will almost certainly fail there: CRSP carries 1,678 historical PERMNOs
   and this project's price store carries 816 tickers. It may not pass or fail anything.
3. Even a full pass licenses the denominator only as far back as **the market reconstruction
   itself is trustworthy**, and that reconstruction has a known, measured defect: falsifier F2 of
   the semi-deviation bridge fired, and the reconstruction **overstates** risk near drawdowns by
   +1.05 to +2.69 VIX points. Tier A inherits that error and multiplies it. Any historical premium
   built this way carries both terms and must say so on its face.

---

## 7. THE DECISION RULE, FIXED IN ADVANCE

| outcome | what happens next |
|---|---|
| **All five gates pass on the primary window** | The denominator is free back to 1929. Only the company being valued needs its own price history. No universe history is built — not tier B, not tier C. |
| **G3 fails alone** | **Tier A is dead and is not repaired.** Fitting a crisis-conditional correction is fitting a second parameter to the failure that falsified the first, on the same data. Go to tier B. |
| **G2 fails alone** | Tier A is dead, and **tier B is unlikely to save it**: a fixed panel of long-lived large caps has the same secular-drift problem and adds survivorship on top. Report that, and go to section 7's last row rather than building tier B on hope. |
| **G1 fails while G2–G4 pass** | The ratio is stable and the model is simply more sensitive than the ratio is steady. Report the required precision; the honest conclusion is that the shortcut does not exist at the tolerance the engine needs. |
| **G5 fails over most of the window** | The question is not answered. Say so. Do not report the measured part as though it were the answer. |
| **Anything fails and no tier is affordable** | **This is a pre-authorized outcome, not a failure of the session.** The honest result is then: historical company premiums cannot be built from the data on hand; historical valuations are published either market-level only, or with the company premium held at its live value and that substitution disclosed on the face of the number. |

---

## 8. STOPPING RULE

k is computed once. The gates are applied once. **After the result is seen, none of the window,
the statistic, the weighting, the membership source, the lag conventions, the test companies or
the thresholds may be changed.** If any of them must change, the changed version is a new
pre-registration with a new date, and this result is reported next to it — because a threshold
quietly widened to make a falsifier pass is worse than having no threshold, which is the finding
the semi-deviation bridge's own test suite already asserts.

**And the standing suspicion, in its form for this exercise:** the failure mode here is not a
crash. It is a k that comes back beautifully stable because the panel silently collapsed to fifty
survivors, or because `blended_semidev` returned `None` for two thirds of the roster and the
average was taken over what was left. G5 exists for that. It is the only gate that can see it, and
it must be reported at every date, not summarized.

---

## 9. WHAT IS NOT CLAIMED

This tests the **denominator** of Region 1 and nothing else. It says nothing about the ERP term
structure beyond one year, nothing about Region 2's `COMMON(t)` historically, nothing about
Region 3, and nothing about whether a historical valuation is a good idea. It is one input, and
the question asked of it is narrow: **is the universe's history necessary, or is it not.**
