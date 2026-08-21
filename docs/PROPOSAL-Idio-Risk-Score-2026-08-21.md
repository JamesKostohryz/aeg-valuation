# PROPOSAL — the idiosyncratic risk score, 1–100, four legs, equal weighted

**2026-08-21, submitted against James's decision of the same date. This is a build proposal, not a
result. Nothing here has been implemented and no number below may be quoted for any company.**

---

## 0. THE ONE-PARAGRAPH ANSWER

**The framework is right and it solves the problem that has been eating this workstream.** A 1–100
cross-sectional score separates *where a company sits among its peers* from *how much the market
pays for risk overall* — the first comes from the score, the second from the market ERP that is
already built and dated back to 1929. That separation is why the last three weeks kept failing: we
were trying to make one construction carry both. **Three of the four legs already exist in this
project and two of them are already production code.** Coverage today: semi-deviation 99%, bond
spread 74%, put-option implied volatility 53%, industry rank 100%. **Only 221 of 503 names carry
all four**, which makes the missing-data rule the most consequential design choice in the build,
not an afterthought.

**Two things James should know before I build, because they cut against parts of the design:**

1. **Put-option IV was already tested in this project and failed out of sample.** On the second
   sample it beat a flat market ERP on 35 of 90 names, and a *random reshuffle of the same implied
   volatilities scored better than the real assignment* (p = 1.000).
2. **Put IV and semi-deviation rank-correlate at +0.778.** Equal weighting four legs therefore does
   not give four independent votes; it gives roughly two and a half, tilted toward volatility.

I will build exactly what was specified. But those two facts belong on the record now rather than
after the system is running.

---

## 1. WHAT THE FOUR LEGS ARE, WHAT WE HAVE, AND WHAT THE PRIOR EVIDENCE SAYS

| leg | source, today | coverage | prior evidence in this project |
|---|---|---|---|
| **1. Semi-deviation**, 1y/2y blend | `idio/semidev.py`, production, monthly refresh | **99%** (499/503) | The incumbent. Beat by bond spread head-to-head within sector. |
| **2. Corporate bond spread** | `outputs/issuer_widen_latest.csv`, `s1_pp` | **74%** (372/503; tier 1 = 165, tier 2 = 156, tier 3 = 51) | **The best-evidenced result in the whole workstream.** Beat semi-deviation as the within-sector ranking, n=99 tier-1, t = −7.28, replicated on a doubled universe, 0 of 500 permutation draws matched it. |
| **3. Put-option implied volatility** | `outputs/.svix_cache`, 3,350 cached chains | **53%** (265/503) — and only ~47% carry a clean 365-day tenor, ~80% at 180 days | **Failed out of sample.** 35 of 90 against a flat ERP; a random reshuffle did better. Rank correlation with leg 1: **+0.778**. |
| **4. Industry risk rank** | built this week: `panel_sector_semidev.csv` (2003–2026, actual S&P constituents) and `french_gics_sector_semidev.csv` (1928–2026) | **100%** | New. Sector ratios validate against an independent vendor for Utilities, Financials and Technology; poorly for the rest. |

**Leg 2 is the strongest leg and it is the one with the most upside.** Coverage went 174 → 372
issuers this month. Extending it further is ordinary work — more bond pulls — and it improves the
best-evidenced input rather than the weakest.

**Leg 3 is the weakest on both evidence and coverage, and it is also the most expensive** (each
refresh is roughly 11,500 API calls). I would still build it, because James specified it and
because a scoring system has a different job from the pricing test that rejected it — see §6.

---

## 2. THE ARCHITECTURE

```
tools/idio_score.py            builds the score
    leg_semidev(t)   -> raw    idio/semidev.py, imported, never reimplemented
    leg_spread(t)    -> raw    issuer_widen_latest.csv s1_pp
    leg_putiv(t)     -> raw    svix cache, 180-day tenor (80% coverage, same verdict as 365)
    leg_industry(t)  -> raw    the name's sector ratio from panel_sector_semidev.csv
    score(t)         -> 1..100 equal-weighted mean of the available legs' scaled values
    suggest_erp(t)   -> pp     the default idiosyncratic ERP, and the analyst override hook

outputs/idio_score_latest.csv  ticker, four raw values, four scaled values, n_legs,
                               score, suggested_erp, and the override if one is set
```

The score file is a **published artefact with every input visible on the row.** A score whose four
components cannot be read off the same line is a number nobody can argue with, which is how this
project has repeatedly ended up with figures nobody could check.

---

## 3. THE SCALING DECISION — the one thing I need James to rule on

Turning a raw metric into 1–100 can be done two ways, and they are not interchangeable.

**A. Percentile rank within the current universe.** Company at the 73rd percentile of
semi-deviation scores 73. Simple, robust to outliers, immediately comparable across the four legs
whose raw units are unrelated (a semi-deviation in per cent, a spread in basis points, an implied
vol, a sector ratio).
*Consequence:* the score is **purely relative**. If every company's risk doubles, every score is
unchanged. The level must come entirely from the market ERP — which is correct and is exactly the
separation §0 describes. **But a historical score needs the historical cross-section to rank
against**, which is the universe-history problem that consumed the last two days, and it returns.

**B. Fixed scale on absolute thresholds**, calibrated once — e.g. semi-deviation 8% → 10 points,
40% → 90 points, fixed forever.
*Consequence:* scores move with the overall level of risk, so a 2008 score is high for everyone.
Historical scoring needs **no universe at all** — only the company's own metrics. But the fixed
thresholds are a parameter set that will drift out of date, and the score then double-counts the
market's risk level, which the market ERP is already carrying.

**My recommendation: A for the live system, B for history, with the mapping between them measured
rather than assumed.** Concretely: build the percentile scale on the live universe; then measure,
over 2003–2026 where both are computable, the fixed absolute thresholds that best reproduce the
percentile scores; publish those thresholds; use them before 2003 with the error stated. That
keeps the live system clean and makes the historical extension an explicit, measured
approximation instead of a silent one.

**This is the decision that determines whether the system works historically. Everything else in
this proposal is implementation.**

---

## 4. THE SCORE → ERP MAPPING, AND HOW TO CALIBRATE IT WITHOUT INVENTING A NUMBER

```
idio_ERP_i  =  market_ERP  ×  ( f(score_i) − 1 )
```

with `f(50) = 1` exactly, so **the median-scored company earns the market premium and no more**,
and the cap-weighted average premium stays close to zero, preserving the property the current
construction has.

The only free parameter is the **spread**, how far a score of 90 sits from a score of 10. **Do not
choose it.** Calibrate it so the score-based cross-section reproduces today's published
semi-deviation-based premiums as closely as possible in the least-squares sense. That has three
virtues: the transition moves no published valuation on day one, the parameter is fitted to
existing production behaviour rather than invented, and the fit residual is itself a diagnostic —
if the score cannot reproduce the incumbent cross-section at all, that is a finding.

`f` should be linear in the score unless there is evidence for curvature, and I would test one
alternative — linear in the *rank-implied normal quantile* — and report both rather than pick
silently.

---

## 5. MISSING DATA — the most consequential rule, because 56% of names lack a leg

Only **221 of 503** names carry all four legs today. The rule must be explicit:

- **Score on the available legs, equal weighted among them.** This is what James specified,
  applied honestly to a subset.
- **Publish `n_legs` on every row.** A score built on two legs and one built on four are not the
  same number and must not look alike.
- **Refuse below two legs.** One leg is not a blend; it is that leg wearing a blend's name.
- **Never impute a missing leg from the others.** Leg 3 correlates 0.778 with leg 1, so imputing
  put IV from semi-deviation would manufacture agreement and then count it twice.
- **Report the coverage matrix every run** — how many names at four legs, three, two, refused.

**A warning from this project's own history:** the equal-weighted mean of available legs is
*biased* when coverage is not random, and it is not random here. Bond spreads exist for large,
indebted, investment-grade issuers; put-IV chains exist for large, liquid, heavily optioned names.
A small company will systematically be scored on semi-deviation and industry alone. **That bias
should be measured on the 221 names that have all four** — score them on all four, then re-score
them on the two legs a small company would have, and report the difference. That measurement
belongs in the first build, not later.

---

## 6. ON PUT-OPTION IV, FAIRLY

The prior test asked whether re-ordering names by a semi-deviation/put-IV blend improved *pricing
errors against market prices*. It did not. **But that is a test of whether the blend beats the
market, and a default scoring system has a different job**: to be transparent, stable, defensible
and overridable. A leg can fail to beat the market and still be a reasonable input to a suggested
default — implied volatility is genuinely forward-looking, which the other three legs are not.

So I would build it, at the **180-day tenor** (80% coverage against 47%, same verdict on the prior
test, no incremental API cost since those slices are already fitted), and I would **report its
marginal contribution explicitly**: the score with and without leg 3, and the rank correlation
between them. If leg 3 moves nothing, that is worth knowing and cheap to see.

---

## 7. BUILD PLAN

| # | step | effort | needs |
|---|---|---|---|
| 1 | `tools/idio_score.py` with legs 1, 2 and 4 — the three that exist and are cheap | 1 day | §3 decision |
| 2 | Leg 3 at the 180-day tenor from the existing cache; measure marginal contribution | 0.5 day | |
| 3 | Calibrate `f` against the published semi-deviation cross-section; report the fit residual | 0.5 day | |
| 4 | Coverage-bias measurement on the 221 four-leg names | 0.5 day | |
| 5 | Wire the override: payload field, recorded in the manifest, delta from default printed | 0.5 day | GATED — it moves valuations |
| 6 | Historical extension per the §3 ruling | 1–2 days | §3 decision |

**About three days to a working live system, plus the historical extension.**

---

## 8. WHAT I NEED FROM JAMES

**One decision: §3, percentile or absolute scaling.** My recommendation is percentile for live and
a measured absolute mapping for history.

Everything else I can build and bring back with the diagnostics attached. Two things I will report
whether or not they are welcome: the marginal contribution of put-option IV, and the coverage bias
on names that carry only two legs.
