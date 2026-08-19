#!/usr/bin/env python3
"""Tests for the Option A disclosure layer.

S1 note. This suite existed but was run by nothing — it was absent from the regression
harness and from every workflow. The reason it could not be run is that it depended on a
scratch artifact, `ENGINE_A.xlsx`, that has never been in the repository: invoked
standalone it died in `recalc` with "file not found" before reaching its first assertion.
It also still reconciled the bridge with three terms, having never been updated for the
depreciation-anchor penalty that Increment 1 added as a fourth.

It now builds the golden Apple engine itself and re-points rates from the committed
fixtures, exactly as regression Stage 4 does, so it is self-sufficient and can be wired
into the harness.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
for _p_ in (_ROOT, os.path.join(_ROOT, "pipeline")):
    if _p_ not in sys.path:
        sys.path.insert(0, _p_)

import openpyxl                                              # noqa: E402
import aeg_engine as AE                                      # noqa: E402
import rate_feed as RF                                       # noqa: E402
import repoint_rates as RP                                   # noqa: E402
import disclose as D                                         # noqa: E402
from recalc_lo import recalc                                 # noqa: E402

GOLDEN = os.path.join(_ROOT, "tests", "golden", "AAPL")
TEMPLATE = os.path.join(_ROOT, "MODEL_TEMPLATE.xlsx")
FIXTURES = os.path.join(_ROOT, "rate_fixtures")
WORK = os.environ.get("AAPL_ENG_WORK") or "/tmp/_disclose_work"
os.makedirs(WORK, exist_ok=True)

_p = _f = 0


def ok(c, m):
    global _p, _f
    if c:
        _p += 1
        print("  PASS", m)
    else:
        _f += 1
        print("  FAIL", m)


print("== build the golden engine and re-point rates from the fixtures ==")
CFG = {"company": "Apple Inc.", "ticker": "AAPL", "price": 315.0, "fy_end_month": 9,
       "forecast_horizon_N": 4,
       "files": {"is_csv": f"{GOLDEN}/REAL_IS.csv", "bs_csv": f"{GOLDEN}/REAL_BS.csv",
                 "cf_csv": f"{GOLDEN}/REAL_CF.csv", "prices": f"{GOLDEN}/REAL_prices.csv",
                 "dividends": f"{GOLDEN}/REAL_div.csv", "splits": f"{GOLDEN}/REAL_splits.csv"},
       "judgments": {"minority_include": False, "finlease": 0.0, "oi_adj_override": None,
                     "rd_capitalize": True, "rd_life": 5.0, "dps_override": None},
       "cost_of_debt": {"single_ytw": 0.05}}
ENG = os.path.join(WORK, "disclose_engine.xlsx")
AE.build_model(CFG, TEMPLATE, ENG)
recalc(ENG)
feed = RF.load_all("AAPL", cash=0, sti=0, local_dir=FIXTURES)
wb = openpyxl.load_workbook(ENG)
RP.repoint(wb, feed)
wb.save(ENG)
ok(os.path.exists(ENG), "engine built and re-pointed")

d = D.disclose(ENG, feed, price=315.0, recalc=recalc,
               sens_path=os.path.join(WORK, "disclose_sens.xlsx"))

print("== disclosure bridge integrity ==")
ok("PASS" in d["base_audit"], f"base audit passes ({d['base_audit']!r})")
ok(d["base_tie"] < 1e-9, f"base tie at machine precision ({d['base_tie']:.1e})")
# The sensitivity tie and the idiosyncratic-drag assertion were deleted 2026-08-19 with the
# term itself. There is no second recalculation left to tie.
ok("idiosyncratic_haircut_ps" not in d,
   "the deleted idiosyncratic haircut is GONE from the disclosure, not merely zeroed")
ok(0.3 <= d["market_debt_engine"] / d["book_debt"] <= 1.3,
   f"market/book debt inside the plausibility band "
   f"({d['market_debt_engine'] / d['book_debt']:.4f})")

print("== the bridge sums, with all THREE remaining terms ==")
# Increment 1 added the depreciation-anchor penalty. A two-term reconciliation would silently
# pass on a name where that term happens to be zero, so it is asserted present and then included.
ok("depreciation_anchor_penalty_ps" in d,
   "the Increment 1 depreciation-anchor penalty is present in the bridge")
_dep = d.get("depreciation_anchor_penalty_ps") or 0.0
recon = d["base_equity_ps"] + d["debt_capital_gain_ps"] - _dep
ok(abs(recon - d["adjusted_equity_ps"]) < 1e-9,
   f"bridge sums exactly to adjusted equity (residual {abs(recon - d['adjusted_equity_ps']):.2e})")
# each term must actually be doing something, or the sum proves nothing
ok(abs(d["debt_capital_gain_ps"]) > 1e-9, "the debt capital-gain term is non-trivial")

print("== what the bridge does NOT prove ==")
# Stated as a test so it is not forgotten: the sum being right says nothing about whether any
# single term is the right number. debt_capital_gain_ps is checked only by the plausibility
# band above. The one term that had NO cross-check anywhere in this repository was the
# idiosyncratic haircut, and it is now deleted rather than trusted.

print("== fail-loud unit gate ==")
try:
    D.disclose(ENG, feed, price=315.0, recalc=recalc, debt_scale=1.0,
               sens_path=os.path.join(WORK, "disclose_sens2.xlsx"))
    ok(False, "an unscaled debt figure should abort")
except ValueError as e:
    ok("implausible" in str(e).lower(), "an unscaled debt figure aborts loudly")

print(D.format_bridge(d))
print(f"\n{_p} passed, {_f} failed")
raise SystemExit(1 if _f else 0)
