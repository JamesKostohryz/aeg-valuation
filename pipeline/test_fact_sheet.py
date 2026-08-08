#!/usr/bin/env python3
"""test_fact_sheet.py — tests for fact_sheet.py, which runs on every live build and emits
<TICKER>_fact_sheet.csv (trailing growth, return metrics, DuPont) for the cockpit's AI Fact
Sheet. Closes a gap flagged in AEG-Coverage-Map-2026-08-08.md.

Builds the golden AAPL engine and recalculates through real LibreOffice — no network access
needed.

Checks:
  1. `_cagr`, in isolation: exact compound-growth arithmetic; None (not a fabricated rate,
     per the module's own fail-soft docstring) across a sign change, across a non-positive
     base, and when the earlier year isn't in the series at all.
  2. `compute_fact_sheet`'s CAGR fields (rev/eps/oi, 5y and 10y) recompute exactly from the
     SAME reported Income Statement series read independently.
  3. `roic_reported` recomputes exactly from its own documented formula
     (NOPAT = OI x (1 - effective_tax_rate), IC = total_debt + equity), re-derived from
     the raw statement cells rather than from the function's own intermediate values.
  4. `roe_reported`, `rnoa_econ`, `roce_econ`, etc. are exactly the DuPont module's own
     latest-year values (fact_sheet explicitly reuses dupont_extract rather than
     re-implementing DuPont — this confirms the reuse is wired correctly, not silently
     dropped or shifted by a year).
  5. Fail-soft behavior at the boundary: a ticker/window combination with too little
     history (e.g. asking `_cagr` for a base year before the series starts) returns None
     rather than raising or fabricating a number, so one bad metric never aborts the whole
     fact sheet.

Usage: python3 test_fact_sheet.py
"""
import os
import shutil
import sys

_PIPE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_PIPE)
for p in (_ROOT, _PIPE):
    if p not in sys.path:
        sys.path.insert(0, p)
import aeg_engine as AE
import dupont_extract as DP
import fact_sheet as FS
from recalc_lo import recalc

GOLDEN = os.path.join(_ROOT, "tests", "golden", "AAPL")
TEMPLATE = os.path.join(_ROOT, "MODEL_TEMPLATE.xlsx")
WORK = os.path.join(_ROOT, "_factsheettest")
os.makedirs(WORK, exist_ok=True)

_p = _f = 0
def check(c, m):
    global _p, _f
    if c: _p += 1; print(f"  PASS  {m}")
    else: _f += 1; print(f"  FAIL  {m}")


print("== _cagr: exact arithmetic and fail-soft None cases ==")
series = {2020: 100.0, 2025: 200.0, 2015: 50.0, 2018: -10.0, 2019: 5.0}
want = (200.0 / 100.0) ** (1.0 / 5) - 1.0
check(abs(FS._cagr(series, 2025, 5) - want) < 1e-12, f"5y CAGR from 100->200 = 2^(1/5)-1 exactly (got {FS._cagr(series, 2025, 5)})")
check(FS._cagr(series, 2019, 1) is None, "CAGR across a sign change (negative base year) returns None, not a fabricated rate")
check(FS._cagr(series, 2025, 30) is None, "CAGR with the base year absent from the series (2025-30=1995) returns None")
check(FS._cagr({}, None, 5) is None, "CAGR with no latest year at all returns None")
check(FS._cagr({2020: -5.0, 2025: 10.0}, 2025, 5) is None, "CAGR with a negative BASE year value returns None even if the latest year is positive")

print("== compute_fact_sheet on the golden AAPL engine ==")
files = {"is_csv": f"{GOLDEN}/REAL_IS.csv", "bs_csv": f"{GOLDEN}/REAL_BS.csv",
          "cf_csv": f"{GOLDEN}/REAL_CF.csv", "prices": f"{GOLDEN}/REAL_prices.csv",
          "dividends": f"{GOLDEN}/REAL_div.csv", "splits": f"{GOLDEN}/REAL_splits.csv"}
cfg = {"company": "Apple Inc.", "ticker": "AAPL", "price": 315.0, "files": files,
       "fy_end_month": 9,
       "judgments": {"minority_include": False, "finlease": 0.0, "oi_adj_override": None,
                     "rd_capitalize": True, "rd_life": 5.0, "dps_override": None},
       "cost_of_debt": {"single_ytw": 0.05}}
eng = os.path.join(WORK, "AAPL_fs.xlsx")
AE.build_model(cfg, TEMPLATE, eng)
recalc(eng)

d = dict(FS.compute_fact_sheet(eng, "AAPL"))

import openpyxl
wb = openpyxl.load_workbook(eng, data_only=True)
IS, BS = wb["Income Statement"], wb["Balance Sheet"]
rev = DP._year_series(IS, DP.IS_HDR, "Total Revenue")
eps = DP._year_series(IS, DP.IS_HDR, "Diluted EPS")
oi = DP._year_series(IS, DP.IS_HDR, "Operating Income")
ebt = DP._year_series(IS, DP.IS_HDR, "Pretax Income")
tax = DP._year_series(IS, DP.IS_HDR, "Tax Provision")
equity = DP._year_series(BS, DP.BS_HDR, "Common Stock Equity")
debt = DP._year_series(BS, DP.BS_HDR, "Total Debt")
y = d["fiscal_year"]

for label, series_, window in [("rev_cagr_5y", rev, 5), ("rev_cagr_10y", rev, 10),
                                ("eps_cagr_5y", eps, 5), ("eps_cagr_10y", eps, 10),
                                ("oi_cagr_5y", oi, 5), ("oi_cagr_10y", oi, 10)]:
    want_v = FS._cagr(series_, y, window)
    got_v = d[label]
    same = (want_v is None and got_v is None) or (want_v is not None and got_v is not None and abs(want_v - got_v) < 1e-9)
    check(same, f"{label} = {got_v} matches independently recomputed CAGR = {want_v}")

print("== roic_reported recomputes exactly from its own documented formula ==")
eff_tax = tax[y] / ebt[y]
nopat = oi[y] * (1.0 - eff_tax)
ic = (debt.get(y) or 0.0) + (equity.get(y) or 0.0)
want_roic = nopat / ic
check(abs(d["roic_reported"] - want_roic) < 1e-9,
      f"roic_reported = NOPAT/(debt+equity) exactly (NOPAT = OI x (1 - tax/ebt)); got {d['roic_reported']}, want {want_roic}")

print("== DuPont fields are exactly dupont_extract's own latest-year values (correct reuse, no drift) ==")
dd = DP.compute_dupont(eng, "AAPL")
cl, rf = dd["classic"], dd["reformulated"]
check(abs(d["roe_reported"] - cl["roe_3step"][-1]) < 1e-12, "roe_reported == dupont_extract classic roe_3step[-1] exactly")
check(abs(d["rnoa_econ"] - rf["rnoa"][-1]) < 1e-12, "rnoa_econ == dupont_extract reformulated rnoa[-1] exactly")
check(abs(d["roce_econ"] - rf["roce"][-1]) < 1e-12, "roce_econ == dupont_extract reformulated roce[-1] exactly")
check(abs(d["net_profit_margin"] - cl["net_profit_margin"][-1]) < 1e-12, "net_profit_margin == dupont_extract classic value exactly")
check(abs(d["asset_turnover"] - cl["asset_turnover"][-1]) < 1e-12, "asset_turnover == dupont_extract classic value exactly")
check(abs(d["flev_econ"] - rf["flev"][-1]) < 1e-12, "flev_econ == dupont_extract reformulated value exactly")

print("== write_fact_sheet: field,value CSV round-trips ==")
fn = FS.write_fact_sheet(eng, "AAPL", WORK)
import csv
with open(os.path.join(WORK, fn)) as fh:
    csv_d = {r["field"]: r["value"] for r in csv.DictReader(fh)}
check(csv_d["ticker"] == "AAPL", "CSV round-trips the ticker field")
check(abs(float(csv_d["roic_reported"]) - d["roic_reported"]) < 1e-9, "CSV round-trips roic_reported to the same precision")

shutil.rmtree(WORK, ignore_errors=True)
print(f"\n{_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
