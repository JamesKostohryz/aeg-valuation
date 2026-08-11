#!/usr/bin/env python3
"""test_run_scenarios.py — S5. `pipeline/run_scenarios.py` had no automated coverage.

The module's contract is fail-closed: if ANY scenario fails its gates or its four-method
tie, the whole run raises and no CSV is written, so continuous integration goes red
rather than committing a green file with a broken scenario quietly inside it. That is the
property worth testing, because the failure mode it guards against — a plausible-looking
scenarios CSV that the cockpit then displays — is exactly the kind this project keeps
getting bitten by.
"""
import csv
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
for _p in (_ROOT, os.path.join(_ROOT, "pipeline")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import aeg_engine as AE                                      # noqa: E402
import run_scenarios as RS                                   # noqa: E402
from recalc_lo import recalc                                 # noqa: E402

GOLDEN = os.path.join(_ROOT, "tests", "golden", "AAPL")
TEMPLATE = os.path.join(_ROOT, "MODEL_TEMPLATE.xlsx")
WORK = os.environ.get("AAPL_ENG_WORK") or "/tmp/_run_scenarios_work"
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


def expect_error(fn, needle, msg):
    global _p, _f
    try:
        fn()
        _f += 1
        print("  FAIL", msg, "(no error)")
    except RS.ScenariosError as e:
        if needle.lower() in str(e).lower():
            _p += 1
            print("  PASS", msg)
        else:
            _f += 1
            print("  FAIL", msg, f"(wrong error: {e})")


print("== scenario-list validation is fail-loud ==")
GOOD = {"name": "base", "probability": 0.5, "mode": "Equity", "N": 4}
expect_error(lambda: RS._validate_scenarios([]), "non-empty", "an empty list aborts")
expect_error(lambda: RS._validate_scenarios("bull"), "non-empty", "a non-list aborts")
expect_error(lambda: RS._validate_scenarios([{"probability": 0.5}]), "name",
             "a nameless scenario aborts")
expect_error(lambda: RS._validate_scenarios([{"name": "  ", "probability": 0.5}]), "name",
             "a blank name aborts")
expect_error(lambda: RS._validate_scenarios([{"name": "x", "probability": "half"}]),
             "probability", "a non-numeric probability aborts")
expect_error(lambda: RS._validate_scenarios([{"name": "x", "probability": True}]),
             "probability", "a boolean probability aborts (bool is a Python int)")
_names, _total = RS._validate_scenarios([GOOD, {**GOOD, "name": "bull", "probability": 0.5}])
ok(_names == ["base", "bull"] and abs(_total - 1.0) < 1e-12,
   "a valid pair returns its names and the probability total")

print("== payload reshaping ==")
_single = RS._as_single_payload("AAPL", {**GOOD, "drivers": {"tax_rate": [0.2] * 4},
                                         "singles": {"target_flev": 0.3}})
ok(_single["ticker"] == "AAPL" and _single["mode"] == "Equity" and _single["N"] == 4,
   "the scenario's ticker/mode/N reach the payload")
ok(_single["drivers"] == {"tax_rate": [0.2] * 4} and _single["singles"] == {"target_flev": 0.3},
   "drivers and singles pass through unchanged")
ok("name" not in _single and "probability" not in _single,
   "scenario bookkeeping fields are not smuggled into the payload apply_payload validates")
_bare = RS._as_single_payload("AAPL", GOOD)
ok(_bare["drivers"] == {} and _bare["singles"] == {},
   "a scenario with no drivers reshapes to empty rather than None (absent = hold at anchor)")

print("== build the base engine ==")
CFG = {"company": "Apple Inc.", "ticker": "AAPL", "price": 315.0, "fy_end_month": 9,
       "forecast_horizon_N": 4,
       "files": {"is_csv": f"{GOLDEN}/REAL_IS.csv", "bs_csv": f"{GOLDEN}/REAL_BS.csv",
                 "cf_csv": f"{GOLDEN}/REAL_CF.csv", "prices": f"{GOLDEN}/REAL_prices.csv",
                 "dividends": f"{GOLDEN}/REAL_div.csv", "splits": f"{GOLDEN}/REAL_splits.csv"},
       "judgments": {"minority_include": False, "finlease": 0.0, "oi_adj_override": None,
                     "rd_capitalize": True, "rd_life": 5.0, "dps_override": None},
       "cost_of_debt": {"single_ytw": 0.05}}
BASE = os.path.join(WORK, "scn_base.xlsx")
AE.build_model(CFG, TEMPLATE, BASE)
recalc(BASE)
ok(os.path.exists(BASE), "base engine built and recalculated")

print("== two real scenarios: value, tie, and the expected-value row ==")
# CONTRACT CHANGE 2026-08-10: the payout seed is rejected under the canonical operating
# closure (distributions are implied there), so scenarios differentiate on a live driver.
# The tax rate is used because its direction is unambiguous: a lower rate leaves more
# after-tax operating income, so it must value higher.
SCEN = [{"name": "base", "probability": 0.6, "mode": "Enterprise", "N": 4,
         "drivers": {"tax_rate": [0.15] * 4}},
        {"name": "bear", "probability": 0.4, "mode": "Enterprise", "N": 4,
         "drivers": {"tax_rate": [0.30] * 4}}]
rep = RS.run_scenarios(BASE, SCEN, ticker="AAPL", price=315.0, out_dir=OUT,
                       recalc=recalc, work_dir=WORK, run_timestamp="2026-08-08T00:00:00Z")
ok(rep["rows"] == 2 and rep["scenarios"] == ["base", "bear"], "both scenarios valued")
_csv_path = os.path.join(OUT, "AAPL_scenarios.csv")
ok(os.path.exists(_csv_path), "the scenarios CSV was written")
with open(_csv_path, newline="") as fh:
    ROWS = list(csv.DictReader(fh))
ok(len(ROWS) == 3, f"one row per scenario plus an expected-value summary row (got {len(ROWS)})")
_num = {r["scenario"]: float(r["intrinsic_value_per_share_real"]) for r in ROWS
        if r.get("intrinsic_value_per_share_real")}
ok("base" in _num and "bear" in _num, f"both scenario values present in the CSV ({sorted(_num)})")
ok(_num["base"] > _num["bear"],
   f"the 15% tax scenario values above the 30% one "
   f"({_num['base']:.6f} vs {_num['bear']:.6f}) — a lower tax rate leaves more after-tax "
   f"operating income at every forecast date")
# the expected-value row must be the probability-weighted combination, recomputed here
_want = 0.6 * _num["base"] + 0.4 * _num["bear"]
ok(abs(_num["expected_value"] - _want) < 1e-9,
   f"the expected-value row is the probability-weighted mean (recomputed {_want:.9f})")
# every scenario row must carry its own tie residual, and each must be at machine precision
_ties = [float(r["tie_residual"]) for r in ROWS if r.get("tie_residual")]
ok(len(_ties) == 2 and max(_ties) < 1e-9,
   f"each scenario row carries its own tie residual, all at machine precision ({_ties})")
# the real price is anchor-based and must therefore be identical across scenarios
_prices = {r["current_real_price_per_share"] for r in ROWS}
ok(len(_prices) == 1, f"the real price is identical across scenarios ({_prices})")

print("== fail-closed: a bad scenario aborts and writes nothing ==")
_stamp = os.path.getmtime(_csv_path)
try:
    RS.run_scenarios(BASE, [{"name": "broken", "probability": 1.0, "mode": "Equity",
                             "N": 4, "drivers": {"tax_rate": [9.0, 9.0, 9.0, 9.0]}}],
                     ticker="AAPL", price=315.0, out_dir=OUT, recalc=recalc,
                     work_dir=WORK, run_timestamp="2026-08-08T00:00:00Z")
    ok(False, "an out-of-range driver aborts the whole run")
except (RS.ScenariosError, Exception) as e:
    ok("out of range" in str(e).lower() or "payload" in str(e).lower(),
       f"an out-of-range driver aborts the whole run ({type(e).__name__})")
ok(os.path.getmtime(_csv_path) == _stamp,
   "the previous good CSV was left untouched — no half-written or misleading green file")

print(f"\n{_p} passed, {_f} failed")
raise SystemExit(1 if _f else 0)
