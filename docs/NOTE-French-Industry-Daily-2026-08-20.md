# NOTE — Kenneth French's industry portfolios beat the GFD route, and here is exactly what to download

**2026-08-20. James: *"don't forget that we also have the Kenneth French data."* He is right, and
it changes the recommendation I made an hour ago. This supersedes section 6 of
`RESULTS-Sector-Idiosyncratic-ERP-2026-08-20.md`; the measured results in that document stand.**

---

## 1. YES, ENERGY WAS MISSING

To answer the question directly. Of the ten top-level S&P 500 GICS sector indices catalogued in
the Global Financial Data workbooks, **five have data and five do not**, and Energy (`_SPLRCE`) is
one of the five that do not. The Energy workbook contains only two sub-industries — Oil, Gas &
Consumable Fuels, and Oil & Gas Equipment & Services. Also missing: Materials, Health Care,
Information Technology, Telecommunication Services.

**James re-uploaded four of the workbooks, including Energy, on the reasonable assumption that the
sector was there. It is not, and the reason is worth spelling out because it is easy to miss.**
The four uploads are byte-identical to the copies already in `outputs/gfd_sector_price_raw/`
— checked by md5, all four match. Inside the Energy workbook:

```
sheets: ['Index', 'Available', '_SPLRCOIG', '_SPLRCOILW']
Index tab: 83 series catalogued        data sheets present: 2
```

The **Index** tab lists 83 Energy-related series, including the top-level `_SPLRCE`, and that tab
is what makes the file look complete. It is GFD's **catalogue of their database**, not a table of
contents. The workbook itself carries two data sheets: `_SPLRCOIG` (Oil, Gas & Consumable Fuels)
and `_SPLRCOILW` (Oil & Gas Equipment & Services). Both are sub-industries of Energy; neither is
Energy.

**French makes that gap irrelevant.**

---

## 2. WHY FRENCH IS THE BETTER SOURCE, ON EVERY AXIS

| | GFD sector workbooks | **Kenneth French industry portfolios** |
|---|---|---|
| frequency | daily from 1989 (1928 Utilities, 1976 Financials); weekly before | **daily from 1926-07-01** |
| coverage now | **stops November 2014** | **current — the file on disk is built from the 202606 CRSP database** |
| sectors present | 5 of 10 | **all of them, 5 / 10 / 12 / 17 / 30 / 38 / 48 / 49 groupings** |
| weighting | S&P index weights | **value-weighted, and equal-weighted as a cross-check** |
| the market comparator | S&P 500 price index, different vendor and calendar | **the same CRSP universe, same calendar, same return definition** |
| cost | already bought | free |
| weekly-to-daily bridge | needed for 1925–1989 | **not needed at all** |

The last row is the big one. The bridge was the only part of the sector plan that was research
rather than assembly, and French removes it. So do the 2014 gap and the five missing sectors.

**And the market leg gets cleaner too.** French publishes `Mkt-RF` and `RF` daily from 1926 in the
research factors file. Using `Mkt-RF + RF` as the market comparator means numerator and
denominator come from one universe, one calendar and one return definition — better than
measuring a GFD price index against an S&P 500 price index from a different vendor.

---

## 3. WHAT IS ON DISK IS MONTHLY, AND MONTHLY WILL NOT DO

`outputs/famafrench_raw/` holds `10_Industry_Portfolios.csv` and `49_Industry_Portfolios.csv`.
Both are **monthly**, value- and equal-weighted, 1926-07 through **2026-06**, plus annual blocks,
firm counts and average firm size.

**The semi-deviation statistic is a daily statistic.** `idio/semidev.py` blends the one- and
two-year downside semi-deviations of *daily* log returns on a sixty-trading-day lag. Computing it
on monthly returns produces a different number wearing the same name — which is the exact failure
mode this codebase forbids in `blended_semidev`'s own docstring, and the reason there is only one
implementation of the statistic in the repository.

So the daily files are needed. They exist, they are free, and I confirmed the download links are
live.

---

## 4. WHAT TO DOWNLOAD — four files, five minutes

Paste each link into a browser; each downloads a zip containing one CSV. Unzip all of them into

```
C:\Users\james\AEG-Project\outputs\famafrench_raw\
```

**Essential:**

1. **The market leg, daily** — `Mkt-RF` and `RF` from 1926-07-01
   `https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_daily_CSV.zip`

2. **10 industry portfolios, daily** — the closest thing to a sector view
   `https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/10_Industry_Portfolios_daily_CSV.zip`

3. **49 industry portfolios, daily** — matches the monthly file already on disk, and carries Oil,
   Util, Telcm, Banks, Insur, RlEst and Fin as separate industries
   `https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/49_Industry_Portfolios_daily_CSV.zip`

**Worth having:**

4. **12 industry portfolios, daily** — twelve groups is the closest French gets to the eleven GICS
   sectors, and it splits Money (finance) out of the catch-all
   `https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/12_Industry_Portfolios_daily_CSV.zip`

**What success looks like:** four new `.csv` files in `outputs/famafrench_raw/`, each beginning
with a header block that says which CRSP database built it, then a date column in `YYYYMMDD` form
starting at `19260701`, then one column per industry. The 10-industry columns will read
`NoDur, Durbl, Manuf, Enrgy, HiTec, Telcm, Shops, Hlth, Utils, Other`.

**I could not fetch these myself.** My web tool returns the zip as raw binary and cannot unpack it,
and I am not permitted to route around that with a shell download. That is the only reason this is
a manual step.

---

## 5. TWO THINGS THAT ARE NOT FREE, AND SHOULD BE DECIDED BEFORE BUILDING

**French's industries are SIC-based, not GICS.** The 10-industry set is `NoDur, Durbl, Manuf,
Enrgy, HiTec, Telcm, Shops, Hlth, Utils, Other`, and `Other` is a real catch-all — finance, real
estate, mining, construction, transport and hotels all land in it. That is not the eleven GICS
sectors the live system uses, and pretending it is would be a silent mismatch of exactly the kind
this project keeps finding.

Two honest options. Use French's taxonomy for historical work and say so on the face of the
numbers. Or aggregate the **49-industry** set into GICS-like groupings with an explicit, committed
mapping — `Oil` and `Coal` into Energy, `Banks`, `Insur`, `Fin` and `RlEst` into Financials, and so
on — which preserves comparability with the modern system at the cost of a mapping that has to be
written down and defended. **I lean to the second**, because the whole point is to compare a
historical sector cost of equity with a current one, and a taxonomy that changes at the join makes
that comparison meaningless.

**French's industry returns include dividends; the GFD series are price indices.** For a downside
semi-deviation the difference is second order but not zero. French publishes
`..._Wout_Div_CSV.zip` variants if a price-basis comparison is ever wanted, but since the market
comparator (`Mkt-RF + RF`) is also a total return, the total-return basis is internally consistent
and is what I would use.

---

## 6. THE REVISED PLAN

1. **Download the four files above.**
2. Compute the sector semi-deviation ratio on French daily data, 1926–2026, using
   `idio/semidev.py`'s primitives and `Mkt-RF + RF` as the market. This replaces the GFD path
   entirely and needs no bridge, no missing-sector shopping list and no 2014 join.
3. **Validate against what is already measured.** The GFD result stands as an independent check:
   over 1991–2014 the two sources should agree on the ordering and roughly on the level for
   Utilities, Financials, Consumer Staples, Industrials and Consumer Discretionary. If they
   disagree materially, one of them is wrong and that has to be resolved before anything
   publishes. **Do not skip this — it is the only external check available, and it is free.**
4. Then decide the taxonomy question in section 5.

**The GFD work is not wasted.** It is now the validation set rather than the production source,
which is a better job for it: an independently constructed second opinion from a different vendor
on a different index universe.
