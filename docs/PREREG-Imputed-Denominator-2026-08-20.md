# PRE-REGISTRATION — imputing the missing names instead of ignoring them

**Written 2026-08-20, BEFORE the imputation test is run. The D1/D2 and D3 results stand and are
reported beside this. The acceptance limits are unchanged: median |e| ≤ 3%, p95 |e| ≤ 5%.**

---

## 1. WHAT D3 ACTUALLY SHOWED, AND THE THING IT ASSUMED AWAY

D3 dropped names and computed the average over what was left. Its verdict: only the 2010 coverage
profile passes; 1995 fails on the 95th percentile at 10.6%, though its **median error is 3.4% and
its mean signed error is +0.06%** — the estimator is unbiased and noisy, not skewed.

**But D3 treats the missing names as unknown in every respect, and they are not.** For a name that
was in the S&P 500 in 1995 and is absent from our daily price panel we still know, from Compustat
via its CRSP PERMNO, **its market capitalisation on that date, exactly.** The only unknown is its
semi-deviation. Throwing away a known cap weight because the volatility is unknown is what makes
D3's tail fat: with 28% of the top decile missing in 1995, whether a single very large company is
in or out swings a cap-weighted mean.

**And the unknown is no longer entirely unknown.** Measured today across 24 quarterly dates,
2013–2018, comparing names that left the index within eight years against names that stayed,
**within the same market-cap decile so size is controlled for**:

| | n | median semi-deviation, relative to its decile median |
|---|---|---|
| left within 8 years | 2,271 | **1.151** |
| stayed | 8,629 | **0.975** |
| **ratio** | | **1.181** |

The date-by-date ratio runs **1.13 to 1.25 and never once falls below 1.12**. Departing companies
are about 18% more volatile than their surviving size peers. That is a stable, sizeable, and
previously unmeasured fact, and it is exactly the parameter D3 had to bracket at ±20%.

## 2. THE CONSTRUCTION, FIXED NOW

```
                Σ_kept c_i·s_i  +  Σ_missing c_j·ŝ_j
capw_imputed = ────────────────────────────────────────
                    Σ_kept c_i  +  Σ_missing c_j
```

- `c_i`, `c_j` — market capitalisations. For kept names, EODHD shares × price, as production does.
  For missing names, **Compustat `mkvaltq`, or `cshoq × prccq`, on the CRSP PERMNO**, refused if
  the mark is more than 400 days stale. These are known, not modelled.
- `ŝ_j` — **`TILT × (median semi-deviation of the KEPT names in j's market-cap decile)`**, with
  **`TILT = 1.18`**, the pooled ratio measured above. Fixed now and not re-fitted per date.

Deciles are of the **true** roster by cap, so a missing name is imputed from the kept names of its
own size, not from the universe average.

## 3. THE TEST, FIXED NOW

Identical in shape to D3, so the two are directly comparable. At each of the 54 quarterly dates
where the panel effectively is the universe (2013–2026), hide names decile-by-decile at the
observed historical miss rates for **Y ∈ {1985, 1995, 2000, 2005, 2010}**, 200 draws each — then
**impute the hidden names back** using their true caps (which the test knows and the estimator is
allowed to use, because historically we genuinely have them) and the tilted decile median.

```
e = capw_imputed / capw_full − 1
```

**Three variants of the hidden set's within-decile selection, as before**: neutral (random),
high (the most volatile hidden first), low (the calmest hidden first). Under `high` the true
tilt is far above 1.18 and the imputation should under-correct; under `low` it should
over-correct. **The bracket is the test of whether a single fixed TILT is good enough**, and it
is reported in full.

## 4. ACCEPTANCE, UNCHANGED, PLUS ONE ADDITION

Median |e| ≤ 3% and p95 |e| ≤ 5% under the neutral variant, crisis ratio ≤ 2.0x, **and** — new,
because it is the point of the exercise — **the imputation must beat D3 at the same target year
on both median and p95.** An imputation that adds machinery without reducing error is worse than
no imputation, and I would rather find that out here than ship it.

## 5. FALSIFIERS

- **If imputation does not beat D3**, the tilt is not carrying information and the construction is
  abandoned. I will not tune TILT to rescue it — that is fitting to the test.
- **If the high/low bracket is wider than ±8% at the earliest passing year**, a single fixed tilt
  is inadequate and the result is reported as a range rather than a number.
- **If nothing before 2005 passes**, the answer to James is that the company leg begins in the
  mid-2000s and everything earlier is sector- or market-level. I will say that plainly.

## 6. WHAT A PASS LICENSES

Direct, imputed computation of `capw_avg_semidev` at any historical date where CRSP membership
and Compustat caps both resolve — which is roughly **1975 to 2014** — with the measured error
attached. It licenses nothing about the market leg, the term structure, or sectors.

**It does not license hiding the imputation.** Any company premium built on an imputed denominator
must carry the imputed share of cap on its face, because a denominator that is 38% imputed and one
that is 2% imputed are not the same number even when they are equally defensible.

## 7. STOPPING RULE

Run once. TILT is 1.18 and is not adjusted after seeing a result. If the construction fails, it
fails.
