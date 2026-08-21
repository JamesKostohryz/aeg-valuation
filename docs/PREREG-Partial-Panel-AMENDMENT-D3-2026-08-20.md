# PRE-REGISTRATION, AMENDMENT — a degradation model that matches what is actually missing

**Written 2026-08-20, after the D1/D2 result and BEFORE D3 is run. The D1/D2 result stands and is
reported beside this, exactly as the stopping rule requires. Nothing below relaxes a threshold —
the acceptance limits are unchanged at median |e| ≤ 3%, p95 |e| ≤ 5%.**

---

## 1. WHY THE FIRST MODEL WAS THE WRONG SHAPE, AND HOW I KNOW

D1 kept names from the largest downward until cumulative market cap reached X%. It therefore
never drops a large company and always drops every small one. **The real panel does neither.**

Measured, against the true CRSP roster with Compustat market caps — the miss rate by market-cap
decile of the actual index, decile 1 being the largest:

| date | true members | in panel | d1 | d2 | d3 | d4 | d5 | d6 | d7 | d8 | d9 | d10 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1985-06 | 442 | 136 | **41%** | 50% | 52% | 66% | 62% | 70% | 82% | 82% | 86% | 100% |
| 1995-06 | 433 | 177 | **28%** | 47% | 47% | 45% | 60% | 51% | 66% | 81% | 79% | 86% |
| 2000-06 | 422 | 249 | 21% | 40% | 38% | 26% | 30% | 33% | 50% | 38% | 57% | 74% |
| 2005-06 | 413 | 291 | 7% | 17% | 22% | 14% | 17% | 34% | 33% | 29% | 44% | 76% |
| 2010-06 | 413 | 378 | 2% | 2% | 5% | 7% | 2% | 10% | 0% | 7% | 12% | 36% |

**In 1995 the panel is missing more than a quarter of the largest decile of the S&P 500.** D1
never models that, and it is the part that matters most for a cap-weighted mean. D1 was harsher
than reality on small names and blind to reality on large ones, so its answer is not
interpretable as either an upper or a lower bound. That is why it needs replacing rather than
reweighting.

## 2. D3, FIXED NOW

At each of the 54 quarterly test dates where the panel effectively is the universe (2013–2026),
rank the names by market cap, cut into ten equal-count deciles, and drop a subset of each decile
at **that decile's observed historical miss rate** for a target year
**Y ∈ {1985, 1995, 2000, 2005, 2010}** from the table above. **200 independent draws per date per
target year.** Report the distribution of

```
e = capw_degraded / capw_full − 1
```

pooled over dates and draws.

## 3. THE BRACKET, BECAUSE WITHIN-DECILE SELECTION IS NOT RANDOM EITHER

A name is missing from the panel because it left the index and a modern vendor stopped tracking
it. Departures are a mix of acquisitions, which skew calm, and failures, which skew volatile. We
cannot observe which, so the honest output is a range and not a point. Three selection rules,
all at the same decile miss rates:

- **D3-neutral** — drop at random within the decile.
- **D3-high** — drop the highest semi-deviation names within the decile first. Models "we lost the
  failures", and biases the surviving average **down**.
- **D3-low** — drop the lowest semi-deviation names first. Models "we lost the sleepy acquirees",
  and biases the surviving average **up**.

D3-high and D3-low are deterministic and need one draw each.

## 4. ACCEPTANCE, UNCHANGED

A target year Y is **usable** if, across all dates and draws, **median |e| ≤ 3% and p95 |e| ≤ 5%
under D3-neutral, and the D3-high to D3-low bracket at that year is reported in full alongside**.
Passing on D3-neutral while the bracket is wide is a qualified pass and must be stated as one.

The crisis falsifier carries over unchanged: if median |e| on drawdown quarters exceeds twice the
median on calm quarters, the year fails regardless of its unconditional error.

## 5. THE FALSIFIER, AND WHAT EACH OUTCOME MEANS

- **1985 passes** — the denominator is computable directly from the panel back to roughly 1985,
  and the company leg's limit becomes price history rather than universe coverage.
- **1995 or 2000 passes but 1985 does not** — the company leg starts there, and everything earlier
  is sector-level or market-level.
- **Nothing before 2005 passes** — the D1 answer was right for the wrong reason, the company leg
  starts in the mid-2000s, and I will say so rather than search for a fourth model.

## 6. STOPPING RULE

Run once. This is the second and final degradation model; if it fails, the answer is that the
panel does not support the period, not that a third model is needed.
