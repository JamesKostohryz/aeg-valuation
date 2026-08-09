#!/usr/bin/env python3
"""test_kit_feeds.py — S5. `pipeline/kit_feeds.py` had no automated coverage.

Covers the parts that run without a network call: the Ohlson-Juettner abnormal-earnings-
growth history, its fail-closed gate on the cost-of-equity history file, and the fail-soft
arithmetic helpers. The two functions that require an EODHD key (`write_growth_trend`'s
trailing-twelve-month leg and `write_analyst_estimates`) are not exercised here; that is a
stated limit of this suite, not an omission to be read as coverage.

The abnormal-earnings-growth numbers are re-derived here from the Ohlson-Juettner
definition against the engine's own reported statements, rather than compared to the
module's own arithmetic.
"""
import csv
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
for _p in (_ROOT, os.path.join(_ROOT, "pipeline")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import aeg_engine as AE                                      # noqa: E402
import kit_feeds as KF                                       # noqa: E402
from recalc_lo import recalc                                 # noqa: E402

GOLDEN = os.path.join(_ROOT, "tests", "golden", "AAPL")
TEMPLATE = os.path.join(_ROOT, "MODEL_TEMPLATE.xlsx")
WORK = os.environ.get("AAPL_ENG_WORK") or "/tmp/_kit_feeds_work"
OUT = os.path.join(WORK, "out")
os.makedirs(OUT, exist_ok=True)

_p = _f = 0


def ok(cond, msg):
    global _p, _f
    if cond:
        _p += 1
        print("  PASS", msg)
    else:
        _f += 1
        print("  FAIL", msg)


print("== fail-soft arithmetic (never fabricate a rate) ==")
ok(KF._safe(4.0, 2.0) == 2.0, "_safe divides")
ok(KF._safe(1.0, 0) is None, "_safe returns None on a zero denominator, not an exception")
ok(KF._safe(None, 2.0) is None and KF._safe(1.0, None) is None, "_safe returns None on missing input")
_s = {2020: 100.0, 2021: 110.0, 2025: 200.0, 2024: -5.0}
ok(abs(KF._cagr(_s, 2025, 5) - ((200.0 / 100.0) ** 0.2 - 1)) < 1e-12, "_cagr computes")
ok(KF._cagr(_s, 2025, 1) is None, "_cagr is undefined across a negative base, not fabricated")
ok(KF._cagr(_s, 2025, 99) is None, "_cagr is None when the base year is missing")
ok(KF._cagr(_s, None, 5) is None, "_cagr is None with no latest year")
ok(KF._mean([1.0, 2.0, None, 3.0]) == 2.0, "_mean skips missing values")
ok(KF._mean([None]) is None and KF._mean([]) is None, "_mean of nothing is None, not zero")
ok(KF._window({2023: 1, 2024: 2, 2025: 3}, [2023, 2024, 2025], 2) == [2, 3],
   "_window takes the last n years off the sorted axis")

print("== build the engine ==")
CFG = {"company": "Apple Inc.", "ticker": "AAPL", "price": 315.0, "fy_end_month": 9,
       "forecast_horizon_N": 4,
       "files": {"is_csv": f"{GOLDEN}/REAL_IS.csv", "bs_csv": f"{GOLDEN}/REAL_BS.csv",
                 "cf_csv": f"{GOLDEN}/REAL_CF.csv", "prices": f"{GOLDEN}/REAL_prices.csv",
                 "dividends": f"{GOLDEN}/REAL_div.csv", "splits": f"{GOLDEN}/REAL_splits.csv"},
       "judgments": {"minority_include": False, "finlease": 0.0, "oi_adj_override": None,
                     "rd_capitalize": True, "rd_life": 5.0, "dps_override": None},
       "cost_of_debt": {"single_ytw": 0.05}}
ENG = os.path.join(WORK, "kit_base.xlsx")
AE.build_model(CFG, TEMPLATE, ENG)
recalc(ENG)
ok(os.path.exists(ENG), "engine built and recalculated")

print("== the cost-of-equity history gate is fail-CLOSED ==")
_hist = os.path.join(OUT, "coe_history_AAPL_annual.csv")
if os.path.exists(_hist):
    os.remove(_hist)
try:
    KF.compute_aeg_momentum(ENG, "AAPL", OUT)
    ok(False, "a missing cost-of-equity history raises rather than returning an empty series")
except FileNotFoundError as e:
    ok("coe_history" in str(e) and "AAPL" in str(e),
       "a missing cost-of-equity history raises and names the file it needs")

print("== abnormal-earnings-growth history, re-derived independently ==")
ST = KF._load_statements(ENG)
E, D = ST["net_income"], ST["dividends"]
_years = sorted(y for y in E if (y - 1) in E)
# synthesise a history with a DIFFERENT rate each year, so a hard-coded or last-value-only
# implementation cannot pass. Stored in percent points, as the reader expects.
_rates = {y: 6.0 + (i % 7) * 0.5 for i, y in enumerate(_years)}
with open(_hist, "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["yr", "coe_nom_dec"])
    for y in _years:
        w.writerow([y, _rates[y]])
_read = KF._read_coe_history(OUT, "AAPL")
ok(all(abs(_read[y] - _rates[y] / 100.0) < 1e-15 for y in _years),
   "the reader converts percent points to decimals")

ROWS = KF.compute_aeg_momentum(ENG, "AAPL", OUT)
ok(len(ROWS) == len(_years), f"one row per year with a prior year and a rate ({len(ROWS)})")
_bad = []
for r in ROWS:
    y = r["period"]
    e_t, e_p = E[y], E[y - 1]
    d_p = D.get(y - 1, 0.0) or 0.0
    rate = _rates[y] / 100.0
    # Ohlson-Juettner: abnormal earnings growth is earnings plus the return earned on the
    # prior year's distribution, less the prior year's earnings grown at the required rate.
    want_aeg = (e_t + rate * d_p) - (1 + rate) * e_p
    want_rore = ((e_t - e_p) / (e_p - d_p)) if (e_p - d_p) else None
    if abs(r["aeg"] - want_aeg) > 1e-9:
        _bad.append((y, "aeg", r["aeg"], want_aeg))
    if want_rore is not None and abs(r["rore"] - want_rore) > 1e-12:
        _bad.append((y, "rore", r["rore"], want_rore))
    if want_rore is not None and abs(r["rore_minus_r"] - (want_rore - rate)) > 1e-12:
        _bad.append((y, "rore_minus_r", r["rore_minus_r"], want_rore - rate))
    if abs(r["r_nom"] - rate) > 1e-15:
        _bad.append((y, "r_nom", r["r_nom"], rate))
ok(not _bad, f"every year re-derives exactly from the Ohlson-Juettner definition "
             f"(first mismatches: {_bad[:3]})")

# the internal consistency that makes the series meaningful: a company earns abnormal
# growth in a year if and only if its return on retained earnings beat the required rate
_sign = [(r["period"], r["aeg"], r["rore_minus_r"]) for r in ROWS
         if r["rore_minus_r"] is not None and abs(r["aeg"]) > 1e-9
         and (r["aeg"] > 0) != (r["rore_minus_r"] > 0)]
ok(not _sign, f"the sign of abnormal growth always agrees with return-on-retention minus "
              f"the required return (disagreements: {_sign[:3]})")

print("== the momentum CSV ==")
KF.write_aeg_momentum(ENG, "AAPL", OUT, data_as_of="2026-08-08")
_path = os.path.join(OUT, "AAPL_aeg_momentum.csv")
ok(os.path.exists(_path), "AAPL_aeg_momentum.csv written")
with open(_path, newline="") as fh:
    OUT_ROWS = list(csv.DictReader(fh))
    fh.seek(0)
    _hdr = next(csv.reader(fh))
ok(_hdr == KF._AEG_COLS, "the CSV header matches the module's declared column contract")
_tables = {r["table"] for r in OUT_ROWS}
ok("single_year" in _tables, f"per-year rows present ({sorted(_tables)})")
ok({"trailing_5y", "trailing_10y"} & _tables,
   f"trailing-window summary rows present ({sorted(_tables)})")
_sy = [r for r in OUT_ROWS if r["table"] == "single_year"]
ok(len(_sy) == len(ROWS), "one single-year CSV row per computed year")
ok(all(r["data_as_of"] == "2026-08-08" for r in OUT_ROWS),
   "every row carries the data-as-of stamp")

print(f"\n{_p} passed, {_f} failed")
raise SystemExit(1 if _f else 0)
