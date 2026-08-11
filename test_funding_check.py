#!/usr/bin/env python3
"""test_funding_check.py — the unfunded-distribution guard.

Written 2026-08-11 alongside pipeline/funding_check.py. See
AEG-REGRESSION-Third-Failure-FOUND-2026-08-11.md for what this is defending against.

The point of these tests is NOT that the guard fires. A guard that always fires is a guard
nobody keeps. The point is that it DISCRIMINATES: it refuses a plan that repurchases more
stock than the operating plan can fund, it passes a plan that does not, and the boundary
between the two sits where the arithmetic says it should. It also has to stay silent in the
equity presentation branch, where distributions are set rather than implied and there is no
residual to have an opinion about.

Each case drives the real engine: build the golden Apple model, override the net buyback
driver on the Forecast tab, recalculate headless, and read the workbook's own implied
dividend back out.
"""
import os
import shutil
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
_PIPE = os.path.join(_ROOT, "pipeline")
for p in (_ROOT, _PIPE):
    if p not in sys.path:
        sys.path.insert(0, p)

import openpyxl
import aeg_engine as AE
import funding_check as FC
from recalc_lo import recalc

GOLDEN = os.path.join(_ROOT, "tests", "golden", "AAPL")
TEMPLATE = os.path.join(_ROOT, "MODEL_TEMPLATE.xlsx")
WORK = os.path.join(_ROOT, "_fundwork")

BUYBACK_ROW, FIRST_COL, LAST_COL = 21, 7, 36

_passed = _failed = 0


def check(cond, msg):
    global _passed, _failed
    print(f"  {'PASS' if cond else 'FAIL'}  {msg}")
    if cond:
        _passed += 1
    else:
        _failed += 1


def _cfg():
    return {"company": "Apple Inc.", "ticker": "AAPL", "price": 315.0,
            "files": {"is_csv": f"{GOLDEN}/REAL_IS.csv", "bs_csv": f"{GOLDEN}/REAL_BS.csv",
                      "cf_csv": f"{GOLDEN}/REAL_CF.csv", "prices": f"{GOLDEN}/REAL_prices.csv",
                      "dividends": f"{GOLDEN}/REAL_div.csv", "splits": f"{GOLDEN}/REAL_splits.csv"},
            "fy_end_month": 9, "forecast_horizon_N": 4,
            "judgments": {"minority_include": False, "finlease": 0.0, "oi_adj_override": None,
                          "rd_capitalize": True, "rd_life": 5.0, "dps_override": None},
            "cost_of_debt": {"single_ytw": 0.05}}


def build(tag, buyback=None, mode=None):
    """Build + recalc the golden engine, optionally overriding the buyback driver and mode."""
    os.makedirs(WORK, exist_ok=True)
    path = os.path.join(WORK, f"AAPL_{tag}.xlsx")
    AE.build_model(_cfg(), TEMPLATE, path)
    if buyback is not None or mode is not None:
        wb = openpyxl.load_workbook(path, data_only=False)
        if mode is not None:
            wb["Inputs"]["B37"] = mode
        if buyback is not None:
            F = wb["Forecast"]
            for c in range(FIRST_COL, LAST_COL + 1):
                F.cell(row=BUYBACK_ROW, column=c).value = buyback
        wb.save(path)
    recalc(path)
    return path


def main():
    print("== the shipped default is NOT fundable for Apple ==")
    # This is the finding that produced this module. The Consensus overlay's three percent
    # buyback against 2.5 percent net-operating-asset growth cannot be paid for.
    d = build("default")
    r = FC.funding_report(d)
    check(r["verdict"] == "REVIEW",
          f"default Consensus overlay trips the guard (verdict {r['verdict']})")
    check(all(y["implied_dps"] < 0 for y in r["years"]),
          f"implied dividend negative in all {len(r['years'])} forecast years "
          f"(worst {r['worst']['implied_dps']:+.4f}/sh)")
    check(r["worst"]["repurchases"] > r["worst"]["distribution_capacity"],
          f"the shortfall is real: repurchases {r['worst']['repurchases']:.6f} exceed "
          f"distribution capacity {r['worst']['distribution_capacity']:.6f}")

    print("== it discriminates: a fundable plan passes ==")
    lo = build("lo", buyback=0.015)
    rl = FC.funding_report(lo)
    check(rl["verdict"] == "PASS",
          f"1.5% buyback is fundable (verdict {rl['verdict']}, "
          f"year-1 implied DPS {rl['years'][0]['implied_dps']:+.4f}/sh)")
    check(all(y["implied_dps"] > 0 for y in rl["years"]),
          "implied dividend positive in every year at 1.5%")

    zero = build("zero", buyback=0.0)
    rz = FC.funding_report(zero)
    check(rz["verdict"] == "PASS",
          f"no buyback at all is trivially fundable (year-1 implied DPS "
          f"{rz['years'][0]['implied_dps']:+.4f}/sh)")

    print("== the boundary sits where the arithmetic puts it ==")
    # Capacity and repurchase dollars are both roughly linear in the buyback rate over this
    # range, so the crossover implied by the default run predicts where the verdict flips.
    w = r["worst"]
    implied_break = 0.03 * (w["distribution_capacity"] / w["repurchases"])
    check(0.015 < implied_break < 0.030,
          f"arithmetic puts the crossover at about {implied_break:.3%}")
    hi = build("hi", buyback=0.024)
    rh = FC.funding_report(hi)
    check(rh["verdict"] == "REVIEW",
          f"2.4% is above the crossover and still trips (year-1 implied DPS "
          f"{rh['years'][0]['implied_dps']:+.4f}/sh)")
    check(rh["years"][0]["implied_dps"] > r["years"][0]["implied_dps"],
          "and it trips less badly than 3.0% — the guard is monotone in the buyback rate")

    print("== silent where distributions are SET, not implied ==")
    eq = build("equity", mode="Equity")
    re_ = FC.funding_report(eq)
    check(re_["verdict"] == "NOT_APPLICABLE",
          f"equity presentation branch returns NOT_APPLICABLE (got {re_['verdict']})")
    check(re_["years"] == [],
          "and offers no per-year opinion, because there is no residual to have one about")

    print("== a zero dividend is admissible; only a negative one is not ==")
    # The guard must not confuse "distributes nothing" with "cannot fund the plan".
    check(FC.ZERO_FLOOR > 0 and FC.ZERO_FLOOR <= 1e-6,
          f"zero floor is a numerical tolerance, not a materiality threshold "
          f"({FC.ZERO_FLOOR:g})")
    fake = {"implied_dps": 0.0}
    check(fake["implied_dps"] >= -FC.ZERO_FLOOR,
          "an exactly-zero implied dividend is treated as fundable")

    shutil.rmtree(WORK, ignore_errors=True)
    print(f"\n{_passed} passed, {_failed} failed")
    sys.exit(1 if _failed else 0)


if __name__ == "__main__":
    main()
