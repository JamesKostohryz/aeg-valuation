# RESULTS — the sector idiosyncratic ERP, built and measured

**2026-08-20. The construction works, produces economically sensible numbers, and needs no anchor
parameter. One claim I made to James yesterday is falsified by the measurement and is reported
first. Nothing here touches any company valuation; this is new capability, not a change to the
pricing core.**

---

## THE CONSTRUCTION

```
ERP_sector(front) = market_ERP(front) × semidev_TOTAL_sector / semidev_TOTAL_market
```

Same statistic as production — `idio/semidev.py`'s primitives, 0.5/0.5 blend of the one- and
two-year downside semi-deviations, 60-trading-day lag — computed on raw sector index returns
rather than market-model residuals, against the S&P 500 **price** index so that both sides are on
the same basis as the GFD sector series.

**No anchor parameter, no universe, no membership, no cap weights.** Two price series per sector.
The market's own ratio is exactly 1.0, so the market carries no premium against itself, which is
right: `market_ERP` already is the market's premium.

---

## 1. THE CLAIM I MADE, AND WHY IT IS WRONG

I told James that under this construction *"every sector comes out above 1.0 automatically,
because a sector is a less diversified portfolio than the index it sits inside."*

**Measured over 286 months, 1991–2014, that is false.**

| GICS | sector | n | min | median | max | share above 1.0 |
|---|---|---|---|---|---|---|
| 40 | Financials | 286 | 1.067 | **1.373** | 2.172 | **100%** |
| 25 | Consumer Discretionary | 280 | 0.904 | 1.157 | 1.429 | 95% |
| 20 | Industrials | 280 | 0.969 | 1.098 | 1.354 | 94% |
| 55 | Utilities | 286 | 0.564 | **0.959** | 1.469 | **48%** |
| 30 | Consumer Staples | 280 | 0.601 | **0.877** | 1.425 | **35%** |

**Consumer Staples sits below the market about two thirds of the time and Utilities about half.**
The reasoning was right about diversification and wrong about what dominates: a sector is indeed
less diversified than the index, but it is also *a different bet*, and for defensive sectors the
low-volatility character of the businesses swamps the concentration effect.

**The half of James's intuition that survives is the important half.** The equal-weighted average
sector ratio has a median of **1.109** across dates, and pooled across 1,412 sector-months
**74.4% sit above 1.0 with a median of 1.118**. The average sector *does* land above the market,
by a measured amount rather than a chosen one — which is exactly the property he was reaching for
with the 75% anchor, obtained without the anchor.

**And a defensive sector reading below the market is not a defect to be normalized away.**
Consumer Staples genuinely is less risky than the S&P 500. Its cost of equity should be lower. A
construction that forced every sector above the market would be imposing an answer.

---

## 2. WHAT IT PRODUCES

At today's front-tenor market premium of 4.13pp, using each sector's median ratio over 1991–2014:

| sector | ratio | sector ERP | vs the market |
|---|---|---|---|
| Consumer Staples | 0.877 | **3.62pp** | −0.51pp |
| Utilities | 0.959 | 3.96pp | −0.17pp |
| Industrials | 1.098 | 4.53pp | +0.40pp |
| Consumer Discretionary | 1.157 | 4.78pp | +0.65pp |
| Financials | 1.373 | **5.67pp** | +1.54pp |

That ordering and that spread are what a practitioner would expect, and nobody chose them.

**The crisis behaviour is the real test, and it passes.** Ratio to market:

| | 2000-03 | 2002-09 | 2008-09 | **2008-12** | 2009-03 | 2011-09 |
|---|---|---|---|---|---|---|
| Financials | 1.39 | 1.27 | 1.56 | **1.85** | 1.72 | 1.44 |
| Consumer Staples | 0.89 | 0.73 | 0.68 | **0.62** | 0.65 | 0.67 |
| Utilities | 0.76 | 1.22 | 1.07 | 0.93 | 0.89 | 0.81 |

In December 2008 Financials carried a **7.6pp** premium against Consumer Staples at **2.6pp** —
a three-fold spread, at exactly the moment that was true. The peak reading, 2.11 in September
2010, is the two-year window still holding the crisis. Utilities in 2002 rising above the market
is the post-Enron merchant-power collapse, which is also correct.

---

## 3. TOTAL OR RESIDUAL — and why sectors must use total

The company leg uses the market-model **residual**. For sectors that option is not available
without reintroducing the anchor, because **the market's own residual against itself is zero**, so
there is no denominator to normalize against. Total semi-deviation is what makes the anchor
unnecessary.

It is also the like-for-like comparison: `market_ERP` is built from the Martin variance bound on
the market's **total** risk, so dividing a sector's total downside deviation by the market's total
downside deviation compares two portfolios on the basis the numerator was measured on.

The two readings differ a great deal, and by sector, which is worth knowing:

| sector | median total | median residual | residual / total |
|---|---|---|---|
| Industrials | 12.59 | 4.43 | **0.352** |
| Consumer Discretionary | 12.39 | 4.95 | 0.400 |
| Financials | 15.37 | 6.66 | 0.434 |
| Consumer Staples | 9.54 | 5.25 | 0.550 |
| Utilities | 9.60 | 7.26 | **0.757** |

Only 35% of Industrials' downside deviation is idiosyncratic; 76% of Utilities' is. Utilities move
on their own account, industrials move with the market.

---

## 4. THE DATA, HONESTLY — half the sectors were never downloaded

Each GFD workbook's "Index" sheet is their **catalogue of what exists in their database**, not a
list of what is in the file. Ten top-level S&P 500 GICS sector indices are catalogued; **five have
a data sheet.** Both zips were checked and both are fully extracted, so this is a partial
download, not a missing file. Reading the catalogue as the contents would have produced a
confident, complete-looking, half-empty answer.

**Present, with the top-level sector index:**

| symbol | GICS | sector | daily from | earlier |
|---|---|---|---|---|
| `_SPLRCU` | 55 | Utilities | **1928-01** | monthly 1871 |
| `_SPLRCF` | 40 | Financials | **1976-07** | weekly 1970 |
| `_SPLRCI` | 20 | Industrials | 1989-09 | weekly **1925-12** |
| `_SPLRCD` | 25 | Consumer Discretionary | 1989-09 | weekly **1925-12** |
| `_SPLRCS` | 30 | Consumer Staples | 1989-09 | weekly **1925-12** |

**The shopping list — five series to pull from GFD, by exact symbol:**

| symbol | GICS | sector | coverage | what is in the file instead — NOT a substitute |
|---|---|---|---|---|
| `_SPLRCE` | 10 | Energy | weekly 1986, daily Sep 1989 | `_SPLRCOIG` Oil, Gas & Consumable Fuels |
| `_SPLRCM` | 15 | Materials | daily Sep 1989 | `_SPLRCPM` Chemicals |
| `_SPLRCA` | 35 | Health Care | weekly 1987, daily Sep 1989 | `_SPLRCCARG` Pharmaceuticals |
| `_SPLRCT` | 45 | Information Technology | weekly 1986, daily Sep 1989 | `_SPLRCSOFW` Software |
| `_SPLRCL` | 50 | Telecommunication Services | daily Sep 1989 | `_SPLRCTELP` Integrated Telecom |

A sub-industry is more volatile than its parent sector, so substituting one would overstate that
sector's premium. The proxies are recorded so the gap stays visible, not so it can be papered
over. Real Estate (60) is absent everywhere: it became a GICS sector in 2016 and this data stops
in 2014.

**Reach achieved today, on daily data, with no new method:**

- **Utilities, 1930 to 2014 — 1,018 continuous monthly observations.** Median ratio 0.771 over
  1930–1990, so utilities' cost of equity ran about 23% below the market's through most of the
  twentieth century.
- **Financials, 1978 to 2014.** Median ratio 1.105 over 1978–1990.
- **Industrials, Consumer Discretionary, Consumer Staples, 1991 to 2014.**

---

## 5. THE TWO REMAINING GAPS, BOTH ORDINARY WORK

**2014 to today.** GFD stops in November 2014. Sector labels for the current index are already in
the EODHD payload — eleven of them, mappable to GICS — so a cap-weighted sector index can be built
from the daily panel. **The 1991–2014 overlap is a free validation**: build the panel version over
the overlap and check it against GFD before trusting it forward. That check must happen before
anything is published, not after.

**Pre-1989 for the three 1925-era sectors.** Weekly data, so it needs a weekly-to-daily bridge —
the same two-parameter construction that already worked for the market leg at 0.80 out of sample.
Pre-register the falsifiers before fitting, as that one did.

---

## 6. WHAT I RECOMMEND

Build the sector leg now on what is here. It needs no ruling, no anchor, no company universe, and
it already reaches 1930 for Utilities and 1978 for Financials. Do the panel-versus-GFD overlap
validation first, because it is cheap and it is the only thing standing between this and a
publishable series. Then pull the five missing symbols, which turns five sectors into ten. The
weekly bridge is last: it buys 1925–1989 for three sectors and it is the only part that is
research rather than assembly.

## ARTIFACTS

`outputs/2026-08-20-sectors/gfd_sector_daily.csv` (63,091 rows, five sectors, 1871–2014),
`sector_semidev_1991_2014.csv`, `sector_semidev_1930_1991.csv`.
`tools/gfd_sector_extract.py`, `tools/sector_semidev.py`.

## WHAT IS NOT CLAIMED

This is the front-tenor level only — nothing here says anything about the sector term structure,
and the decay `D(t)`, Region 2 and Region 3 have not been considered for sectors at all. The
market ERP used for the illustrative premiums is today's 4.13pp applied to historical ratios,
which is a scaling for readability and **not** a historical sector cost of equity; a real one
takes `market_ERP(t)` from `outputs/market_coe_history.csv` at each date. The pre-1957 market
series is the S&P 90, not the S&P 500.
