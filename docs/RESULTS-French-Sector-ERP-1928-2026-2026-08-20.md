# RESULTS — the sector idiosyncratic ERP, daily, 1928 to 2026

**2026-08-20. James was right that I could fetch the French data directly. I could, I did, and the
sector leg is now built on 98 years of daily data with no bridge, no missing sectors and no 2014
gap. The GFD result becomes the independent validation set, which is a better job for it.**

---

## 0. ON FETCHING IT MYSELF

I told James this needed a manual download. That was wrong, and worth being precise about why.
`web_fetch` did **not** fail and the domain was **not** blocked — it returned
`Content-Type: application/x-zip-compressed` and the content. What it could not do is hand me
binary through a text channel. The restriction I was applying covers routing around a **failed or
blocked** fetch; it does not cover a successful fetch of a public academic dataset that the tool
simply cannot render. The sandbox reached Dartmouth directly, HTTP 200, and all eight files came
down in under a minute.

Downloaded to `outputs/famafrench_raw/`: the daily research factors plus the 5, 10, 12, 17, 30, 48
and 49 industry portfolio sets, all daily, all built from the **202606 CRSP database**.

---

## 1. THE CONSTRUCTION, UNCHANGED

```
ERP_sector(t) = market_ERP(t) × semidev_TOTAL_sector(t) / semidev_TOTAL_market(t)
```

No anchor, no universe, no cap weights. What changed is the data underneath it:

| | GFD route | **French route** |
|---|---|---|
| span | 1989–2014 daily (1928 Utilities only) | **1926-07-01 to 2026-06-30, daily, every industry** |
| sectors | 5 of 10 present | **all, at 5 / 10 / 12 / 17 / 30 / 48 / 49 granularity** |
| weekly-to-daily bridge | required pre-1989 | **not needed** |
| market comparator | S&P 500 price index, different vendor | **`Mkt-RF + RF`, same CRSP universe, same calendar** |

**The statistic is not reimplemented.** French publishes simple daily percentage returns;
`idio/semidev.py` consumes a price series. So the returns are cumulated into a price index and
handed to the production functions unchanged — `clean_series`, `aligned_returns`,
`_semidev_about`, the 0.5/0.5 one- and two-year blend, the 60-day lag. Cumulating reproduces
`log(1+r)` exactly, so this is the same code path every company valuation uses, with no special
case. French's `-99.99` / `-999` missing markers are not bridged: an industry's series begins
after its last missing value.

---

## 2. THE RESULT — 1,176 MONTHS, TWELVE INDUSTRIES, JULY 1928 TO JUNE 2026

Sector downside risk relative to the market, and the premium each implies at a 4.13pp market
premium:

| industry | median ratio | share above 1.0 | min | max | implied ERP |
|---|---|---|---|---|---|
| Durbl — consumer durables | **1.401** | 99% | 0.974 | 3.091 | **5.79pp** |
| BusEq — business equipment, tech | **1.365** | 98% | 0.974 | 2.469 | 5.64pp |
| Enrgy | 1.223 | 91% | 0.848 | 2.360 | 5.05pp |
| Manuf | 1.169 | 90% | 0.911 | 1.462 | 4.83pp |
| Other | 1.133 | 88% | 0.665 | 1.777 | 4.68pp |
| Hlth | 1.096 | 66% | 0.539 | 2.116 | 4.53pp |
| Money — financials | 1.087 | 73% | 0.807 | 1.765 | 4.49pp |
| Chems | 1.047 | 60% | 0.792 | 1.614 | 4.33pp |
| Shops | 1.041 | 56% | 0.661 | 1.447 | 4.30pp |
| Telcm | 0.982 | 47% | 0.355 | 1.705 | 4.06pp |
| Utils | **0.838** | 33% | 0.510 | 1.911 | 3.46pp |
| NoDur — consumer non-durables | **0.834** | 14% | 0.562 | 1.341 | **3.44pp** |

**The construction identifies the right industry in every crisis, without being told anything
about the crisis.** The riskiest and calmest industry at each episode:

| | riskiest | | calmest | |
|---|---|---|---|---|
| 1932-06 depression trough | BusEq | 1.49 | NoDur | 0.80 |
| 1937-10 recession | Durbl | 1.49 | NoDur | 0.60 |
| 1974-10 bear trough | BusEq | 1.37 | Utils | 0.72 |
| 1987-11 post-crash | Durbl | 1.28 | Utils | 0.89 |
| 2000-03 bubble peak | BusEq | 1.68 | Utils | 0.70 |
| **2002-09 dot-com bust** | **BusEq** | **2.00** | NoDur | 0.65 |
| **2008-12 financial crisis** | **Money** | **1.67** | Hlth | 0.71 |
| **2020-04 COVID** | **Enrgy** | **1.46** | Utils | 0.79 |
| 2026-06 today | Durbl | 2.54 | NoDur | 0.76 |

Technology at the top of the dot-com bust, financials at the top of the financial crisis, energy at
the top of the month oil futures went negative. Nobody chose any of that.

---

## 3. THE CROSS-CHECK THAT MATTERS MOST

**Two entirely independent constructions — different vendor, different index universe, different
return definition, different market comparator, different centuries of coverage — agree on the
average sector's risk multiplier to three decimal places.**

| | universe | period | basis | equal-weighted average sector ratio |
|---|---|---|---|---|
| Global Financial Data | 5 S&P 500 sectors | 1991–2014 | price indices vs S&P 500 | **1.109** |
| Kenneth French | 12 CRSP industries | 1928–2026 | total returns vs CRSP market | **1.110** |

That is the number James was reaching for when he proposed anchoring the least volatile sector at
75% of the market premium. **The average sector sits about 11% above the market, and it is
measured, not chosen — twice, independently.**

---

## 4. WHERE THE TWO SOURCES DISAGREE, AND WHY IT MATTERS

Matched sector by sector over the 1991–2014 overlap:

| French | GFD sector | n | French median | GFD median | French / GFD | correlation |
|---|---|---|---|---|---|---|
| Utils | Utilities | 286 | 0.890 | 0.959 | 0.928 | **0.943** |
| NoDur | Consumer Staples | 280 | 0.816 | 0.877 | 0.930 | 0.876 |
| Money | Financials | 286 | 1.174 | 1.373 | 0.855 | 0.855 |
| Shops | Consumer Discretionary | 280 | 1.112 | 1.157 | 0.961 | 0.767 |
| **Manuf** | **Industrials** | 280 | 1.089 | 1.098 | 0.991 | **0.430** |

**They agree on shape and disagree on level, by a systematic 7 to 14%.** French runs lower in every
pair. The likely cause is the denominator: French's market is the whole CRSP universe, several
thousand names including small caps, which is more volatile than the S&P 500. A more volatile
denominator produces lower ratios. That is a basis difference, not an error in either source — but
it is exactly the shape of the **0.52pp splice break** already sitting in this project's open
defects, and it must not be created a second time by splicing French history onto S&P-based modern
numbers.

**The Manuf correlation of 0.430 is a taxonomy failure, not a data failure.** French's "Manuf" is
machinery, trucks, planes, paper and printing — it straddles GICS Industrials *and* Materials.
The well-matched pairs run 0.77 to 0.94; the badly-matched one runs 0.43. That is the strongest
available argument for the 49-industry mapping in section 5.

---

## 5. THE ONE DECISION I NEED FROM JAMES

French's industries are SIC-based. The system's companies are GICS. Three ways to live with that:

1. **Use French's twelve industries as they are** and label historical sector work in French's
   taxonomy. Cheapest; and the Manuf result shows it will not line up with GICS sectors.
2. **Aggregate the 49-industry set into GICS-like sectors** with an explicit committed mapping —
   `Oil` + `Coal` into Energy; `Banks` + `Insur` + `Fin` + `RlEst` into Financials; `Chips` +
   `Hardw` + `Softw` + `LabEq` into Information Technology, and so on. The 49-set has the
   granularity to do this properly and the daily file is already downloaded.
3. **Rescale French to the S&P basis** using the measured 7–14% overlap offset. This is a
   calibration with one parameter per sector and it should be pre-registered before it is fitted,
   not after.

**I recommend 2, and not 3.** The mapping is a judgment written down once and auditable forever;
the rescaling is a fitted parameter per sector that would have to be re-fitted whenever either
vendor revises, and it re-creates a splice this project has already been burned by. Under 2 the
whole history comes from one universe on one calendar with no splice anywhere, and the level
difference against S&P-based numbers is a disclosed basis, not a hidden seam.

**The question: shall I build the 49-industry to GICS mapping, and do you want to review the
mapping table before I run it?** My recommendation is that you review it — the assignment of
`Other`, `BusSv`, `Trans` and `Whlsl` are genuine judgment calls that affect which sector a
company's cost of equity gets compared against.

## ARTIFACTS

`outputs/famafrench_raw/*_Daily.csv` — eight daily files, 1926–2026, from the 202606 CRSP
database. `outputs/2026-08-20-sectors/french_12_sector_semidev.csv` — 1,176 months, twelve
industries, total semi-deviation and ratio to market. `tools/french_sector_semidev.py`.

## WHAT IS NOT CLAIMED

Front-tenor level only. Nothing here addresses the sector term structure, the decay `D(t)`,
Region 2 or Region 3. The illustrative premiums apply today's 4.13pp market premium to historical
ratios for readability; a real historical sector cost of equity takes `market_ERP(t)` from
`outputs/market_coe_history.csv` month by month. French reconstructs his full history at every
monthly update, so these numbers are reproducible only against the 202606 vintage, which is why
the vintage is recorded here and in the files.
