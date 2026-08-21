# RESULTS — the 49-industry to GICS mapping, built, guarded, and validated

**2026-08-20. Built as instructed. It works for most sectors and does not work for two, and the
two are named. I also found and fixed a defect in my own construction from an hour earlier, which
is reported before the results.**

---

## 1. A DEFECT IN MY OWN WORK, FOUND BY LOOKING AT AN EXTREME VALUE

The first run of the mapping published **Real Estate at a risk ratio of 6.46 in September 1941**.
That number is arithmetically perfect and externally absurd. The cause:

| French real estate industry, firm count | 1926 | 1935 | 1945 | 1955 | 1965 | 1975 | 2025 |
|---|---|---|---|---|---|---|---|
| | **2** | **3** | **3** | **2** | 31 | 62 | 29 |

**A sector of two companies is not a sector.** Its downside deviation is one company's
idiosyncratic risk wearing a sector's name. My construction never asked how many firms were in
the portfolio, and would have published a 98-year Real Estate series with a fabricated first
three decades — the standing suspicion in its purest form, in code I had just written.

**The fix is a firm-count guard**, `MIN_FIRMS = 20`, refusing the sector-month rather than
publishing it. For an N-name portfolio with average pairwise correlation ρ the surviving
single-name share of variance goes as `(1−ρ)/N` — about 5% at N=20, about 33% at N=3 — and cap
weighting makes the *effective* count lower than the nominal one, so 20 is a floor and not a
comfort. **The firm count is now written on every row** so a stricter filter can be applied later
without recomputing anything.

**1,146 of 12,936 sector-months are refused.** Real Estate's maximum fell from 6.46 to 2.55 and
its usable history now starts in 1963. The riskiest sector at the 1932 depression trough changed
from Real Estate (on four firms) to **Financials at 1.32**, which is the right answer.

---

## 2. THE MAPPING, AND THE ONE CORRECTION

Forty-nine French industries into eleven GICS sectors, cap-weighted by industry using French's own
`Number of Firms × Average Firm Size`, prior month-end weights held within the month. Equal
weighting would have made Gold and Coal count as much as Banks.

**Every judgment call is in the table in `tools/french_gics_map.py`, flagged `JUDGMENT` with its
reason**, so a reader can disagree with a specific line. The seven are Coal, Rubbr, BldMt, FabPr,
Whlsl, Hshld, PerSv, LabEq, and the two that depend on *which year's* GICS you mean — `Fun` and
`Books` (Entertainment and Media moved to Communication Services in the 2018 restructure) and
`RlEst` (Real Estate became a sector in 2016). Those three are assigned on the **current**
definition so historical and modern numbers are comparable.

**One correction, made for a reason that is a fact and not a preference.** I first put Business
Services in Industrials on the advertising-and-printing reading. GICS classified **Data Processing
& Outsourced Services under Information Technology (45102020) until the March 2023 restructure**,
so for almost the whole period this data covers, IT is the correct home for the bulk of that
industry. I found the error while running a mapping sensitivity test, and the correlation effect
is small — Industrials 0.392 → 0.405 — so **this is a correctness fix and not the thing that
fixes Industrials.** `Other`, French's own catch-all, is assigned to no sector at all.

---

## 3. THE RESULT — ELEVEN GICS SECTORS, 1,176 MONTHS, 1928 TO 2026

| GICS | sector | usable from | median ratio | %>1 | min | max | ERP @4.13pp |
|---|---|---|---|---|---|---|---|
| 10 | Energy | 1928-07 | 1.222 | 91% | 0.848 | 2.361 | 5.05pp |
| 15 | Materials | 1928-07 | 1.110 | 85% | 0.824 | 1.503 | 4.59pp |
| 20 | Industrials | 1928-07 | 1.182 | 94% | 0.911 | 1.609 | 4.88pp |
| 25 | Consumer Discretionary | 1928-07 | 1.137 | 88% | 0.881 | 1.566 | 4.70pp |
| 30 | Consumer Staples | 1928-07 | **0.846** | 32% | 0.574 | 1.411 | **3.49pp** |
| 35 | Health Care | 1958-07 | 1.167 | 78% | 0.711 | 2.118 | 4.82pp |
| 40 | Financials | 1930-07 | 1.074 | 73% | 0.802 | 1.778 | 4.44pp |
| 45 | Information Technology | 1934-07 | **1.300** | 85% | 0.768 | 2.317 | **5.37pp** |
| 50 | Communication Services | 1941-07 | 1.011 | 54% | 0.436 | 1.669 | 4.18pp |
| 55 | Utilities | 1928-07 | **0.838** | 33% | 0.510 | 1.911 | **3.46pp** |
| 60 | Real Estate | 1963-07 | 1.373 | 79% | 0.589 | 2.549 | 5.67pp |

**The crisis checks are all correct, and nothing was told about any crisis:**

| | riskiest | | calmest | |
|---|---|---|---|---|
| 1932-06 depression | Financials | 1.32 | Consumer Staples | 0.82 |
| 1974-10 | Real Estate | 1.36 | Utilities | 0.72 |
| 2000-03 bubble peak | Information Technology | 1.62 | Utilities | 0.70 |
| **2002-09 dot-com bust** | **Information Technology** | **1.94** | Consumer Staples | 0.70 |
| **2008-12 financial crisis** | **Financials** | **1.67** | Consumer Staples | 0.67 |
| **2020-04 COVID** | **Energy** | **1.46** | Utilities | 0.79 |
| 2026-06 today | Real Estate | 1.71 | Consumer Staples | 0.79 |

**A third independent agreement on the level.** The equal-weighted average sector ratio:

| construction | universe | period | result |
|---|---|---|---|
| GFD, 5 S&P sectors | S&P 500, price indices | 1991–2014 | **1.109** |
| French, 12 SIC industries | CRSP, total returns | 1928–2026 | **1.110** |
| French → GICS, 11 sectors | CRSP, total returns | 1928–2026 | **1.109** |

---

## 4. WHERE THE MAPPING FAILS, AND TWO EXPLANATIONS I TESTED AND THREW AWAY

Validated against the GFD S&P sector indices over 1991–2014, now GICS against GICS:

| GICS | sector | correlation |
|---|---|---|
| 30 | Consumer Staples | **0.971** |
| 55 | Utilities | 0.943 |
| 40 | Financials | 0.861 |
| 25 | Consumer Discretionary | 0.844 |
| **20** | **Industrials** | **0.392** |

**Explanation one, tested and rejected: the mapping.** A sensitivity test moving the two contested
industries — `BusSv` to Information Technology, `Whlsl` to Consumer Discretionary — lifts the
Industrials correlation only from 0.392 to 0.520. **The mapping is not what is wrong**, and
chasing it further would be fitting to the validation set.

**Explanation two, tested and rejected: concentration.** I guessed the S&P sector index was a
few-name portfolio and French's a many-name one. Measured today, **Industrials is the *least*
concentrated S&P 500 sector** — top name 8.9%, top five 29.5%, against Communication Services at
37.3% and 90.6%. The hypothesis fails on its own test.

**Explanation three, which the data supports.** Split at the introduction of GICS in August 1999:

| sector | 1991–1999 | 2000–2014 |
|---|---|---|
| Utilities | 0.992 | 0.918 |
| Consumer Staples | 0.966 | 0.963 |
| Financials | 0.729 | 0.886 |
| Consumer Discretionary | **0.988** | **0.655** |
| **Industrials** | **0.948** | **0.267** |

**Industrials correlates at 0.948 before GICS existed and 0.267 after** — the opposite of what I
expected, and it identifies the cause. French's SIC groupings track the *legacy* broad S&P
"Industrials", which is what GFD's backfill contains, and they cannot reproduce the much narrower
sector GICS defined in 1999. Consumer Discretionary shows the same break, 0.988 to 0.655. The
three sectors whose boundaries GICS did not substantially redraw — Staples, Utilities, Financials
— are unaffected.

**So the honest statement of what this delivers:** a defensible 98-year history for sectors with
stable definitions, and a known weakness for Industrials and Consumer Discretionary in the GICS
era, where a SIC-based grouping is reproducing a taxonomy built on different principles. That
weakness should be disclosed on any number those two sectors produce; it should not be tuned away.

---

## 5. WHAT I RECOMMEND NEXT, AND A HANDOFF

1. **Do not tune the mapping further.** Two explanations have been tested and rejected and the
   third is structural. More adjustment is fitting to the validation set.
2. **For Industrials and Consumer Discretionary in the modern era, prefer a panel-built sector
   index** — the daily panel plus EODHD's own GICS-style labels gives the actual S&P sector, and
   the French series is then the pre-1990 history with a disclosed join. That join has a measured
   level offset of about 4% (French runs below GFD by a median 0.958 across the five sectors) and
   it must be stated, not smoothed.
3. **The market ERP is the missing multiplier.** Every premium quoted here applies today's 4.13pp
   for readability. A real historical sector cost of equity multiplies each month's ratio by that
   month's `market_erp_1y_pct` from `outputs/market_coe_history.csv` and adds
   `real_rf`. That is assembly, not research, and it is the next thing to build.

**This session is long and the sector work has reached a natural boundary.** Everything is
committed. A fresh session should start from this document, `RESULTS-French-Sector-ERP-1928-2026`
and the doctrine, and build item 3.

## ARTIFACTS

`outputs/2026-08-20-sectors/french_gics_sector_semidev.csv` — 1,176 months, eleven GICS sectors,
total semi-deviation, ratio to market, and **firm count** per sector-month.
`tools/french_gics_map.py` — the mapping table, the guard, and the build.
`outputs/famafrench_raw/` — eight daily French files, 202606 CRSP vintage.

## WHAT IS NOT CLAIMED

Front-tenor level only; nothing about the sector term structure, `D(t)`, Region 2 or Region 3.
French reconstructs his whole history at every monthly update, so these numbers are reproducible
only against the **202606** vintage. The pre-1962 CRSP universe is NYSE-only, so "the market"
before 1962 is a narrower object than it is after.
