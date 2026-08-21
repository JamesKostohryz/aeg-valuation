# PRE-REGISTRATION — how wrong is the denominator on the panel we actually have?

**Written 2026-08-20, BEFORE the degradation test is run. Sections 3 to 6 are fixed now.
Supersedes nothing; it follows `PREREG-Company-Leg-Denominator-2026-08-20.md`, whose tier A
result stands.**

---

## 1. A CORRECTION I OWE FIRST

I told James that "no valuation before 2002 may carry a company-specific premium." **That was
too strong, and the error was mine.**

It followed from G5, which I pre-registered as *count* coverage — at least 80% of the index
membership by number of names. For a **cap-weighted** average that is the wrong measure, and I
said so in the results document while still quoting the conclusion it produced. The cap-weighted
average semi-deviation is dominated by the largest names. Whether the panel is missing 300 small
companies matters far less than whether it is missing three large ones.

**James's underlying point is correct and it needs restating clearly.** The company's own
downside semi-deviation — the *numerator* — was never in question. It needs only that company's
own price history, it is already the production statistic, it uses no options at all, and it is
available for any name we would want to value at any date it traded. The options dependence in
this system lives entirely in the **market** leg, and that leg is already reconstructed monthly
to October 1929 in `outputs/market_coe_history.csv`.

So the gap is narrower than I made it sound. It is one scalar per date: the cap-weighted average
across the index, which the company's own figure is measured against. And the question is not
"do we have the universe" — we do not, and will not soon — but **"how badly does a partial,
large-cap-weighted panel misestimate a cap-weighted average?"** That is an approximation
question, it is measurable today, and this document fixes the rules before it is measured.

---

## 2. WHAT HAS ALREADY BEEN SEEN

Declared, because it motivated the test:

- On the **current** universe, the cap-weighted average semi-deviation computed on the largest
  names only reproduces the full 499-name figure closely: top 100 names (76.7% of cap) errs
  **−1.79%**, top 150 (83.4%) **−1.29%**, top 200 (88.3%) **−1.09%**, top 50 (65.4%) **−2.27%**,
  top 25 (54.5%) **−4.43%**. Measured before the tier A run and reported in that document.
- Panel cap coverage of the true index: 54% in 1975, 52% in 1985, 62% in 1995, 77% in 2000,
  87% in 2005, 95% from 2010.

**Not seen:** anything about how that error behaves at other dates, in crises, or once
survivorship is modelled. One date is not a result.

---

## 3. THE TEST, FIXED IN ADVANCE

Ground truth is the panel's own `capw_avg_semidev` at dates where panel cap coverage of the true
index is at least 95% — **2013-01 through 2026-08, quarterly**. At those dates the panel is
effectively the universe, so degrading it deliberately and comparing is a clean experiment.

Two degradation models, both run at every coverage level
**X ∈ {50, 55, 60, 65, 70, 75, 80, 85, 90}%**:

- **D1, "the big names survive."** Rank by market cap, keep names from the top down until
  cumulative cap reaches X% of the panel's total. This is the optimistic model: it assumes what
  a vendor kept is what was large.
- **D2, "the leavers are the missing ones."** D1, and then additionally drop every kept name that
  **left the index within the following eight years**, read from EODHD's historical membership
  windows. This models the actual mechanism: our panel is thin historically because it is built
  from names a modern vendor still tracks, and names that left are exactly the ones it lost. It
  is the pessimistic model and it is the one that matters.

The error reported is relative, on the quantity that is actually used:

```
e = capw_degraded / capw_full − 1
```

**Its sign will be reported, not just its size.** If large caps are the calmer names, degraded
capw sits below the truth, the historical denominator is biased **low**, every company premium is
biased **high**, and every historical valuation is biased **low** — conservative, but real, and it
must travel with the number.

---

## 4. ACCEPTANCE, FIXED NOW

A coverage level X is **usable** if, across all test dates and under **both** D1 and D2:

| | limit |
|---|---|
| median \|e\| | **≤ 3%** |
| 95th percentile \|e\| | **≤ 5%** |

**Why those numbers.** The pass-through to the valuation is the same arithmetic as G1 in the
previous pre-registration: a relative error `e` in the denominator displaces a company's front
premium by `ERP_i(front) × e`, and the collapsed cost of equity by at least `0.25 ×` that, since
`D(t)` decays only to `LAM_ADOPTED = 0.25`. At `market_ERP(front) ≈ 4.13pp`:

- a typical name (ratio ≈ 1.0): e = 3% → **12bp** front, ≥3bp collapsed; e = 5% → 21bp front.
- Microsoft (ratio 0.804): e = 3% → 10bp front.
- the top of the cross-section (ratio 3.09): e = 3% → **38bp** front, ≥10bp collapsed.

So 3% sits inside the previously pre-registered 15bp/30bp displacement limits for ordinary names
and **outside them for the most volatile decile**. That is a real limitation, not a rounding
detail, and it is pre-registered to be **reported separately by semi-deviation decile rather than
averaged away**.

## 5. THE FALSIFIER

**If |e| passes the 5% p95 limit before X falls to 60%, the panel cannot support pre-2000 dates**
and the honest answer to James is that the company leg stops somewhere around 2000 and the
historical route is sector-level. I will say that rather than soften the threshold.

**A second falsifier, on crisis behaviour.** If the median |e| on drawdown quarters is more than
twice the median on calm quarters — same drawdown definition as the bridge, reused verbatim —
then the approximation fails exactly where historical valuation is most interesting, and no
coverage level passes regardless of its unconditional error.

## 6. WHAT A PASS LICENSES, AND WHAT IT DOES NOT

A pass at level X licenses **direct computation** of `capw_avg_semidev` from point-in-time
membership at every historical date whose cap coverage exceeds X — no ratio, no calibration, no
constant — with the measured error attached to the number. It licenses nothing about the market
leg, the term structure, sectors, or any date whose coverage falls below X.

**It also does not license silence about survivorship.** D2 is a model of the missing names, not
a measurement of them. The names we cannot see are unobservable by definition; D2 is the best
available proxy and its result is an estimate of a bias, not a correction for it.

## 7. STOPPING RULE

Run once. No threshold, window, degradation model or coverage grid changes after a result is
seen. If one must, it is a new document with the old result reported beside it.
