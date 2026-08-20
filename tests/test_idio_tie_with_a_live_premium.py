#!/usr/bin/env python3
"""
tests/test_idio_tie_with_a_live_premium.py — the tie holds with a REAL premium in the row.

WHY THIS IS SEPARATE FROM EVERY OTHER TIE TEST. The hook `install_idio_hook` writes thirty
zeros into `finrate_idio` and every existing tie check runs against those zeros. Zero is flat,
zero is tie-neutral, and zero told us nothing for the entire period the feature was dormant --
which is exactly how the `cfg_coe_mode="Single"` defect stayed invisible: row 26 added a
PER-TENOR premium onto a FLAT base in Single mode, and it could not show while the row carried
nothing but zeros.

So this file installs the premium the production fleet would actually use -- built by
`idio/company_curve.build()` from the committed universe and the committed issuer credit
curves -- and asserts BOTH halves:

  THE TIE STILL HOLDS.   AEG = ReOI = FCFE = FCFF at machine precision, in all four
                         configurations. A premium that broke the tie would be caught anywhere.
  THE VALUE ACTUALLY MOVED. A premium that ties and moves nothing is inert, and an inert
                         premium puts every company silently back on the market rate with a
                         perfect tie. That is the state this whole feature exists to end, and
                         it is the half no identity check can see.

Run: AAPL_ENG_WORK=/tmp/idiotie python3 tests/test_idio_tie_with_a_live_premium.py
"""
import csv
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "pipeline"), os.path.join(_ROOT, "idio")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import aeg_engine as AE                 # noqa: E402
import company_curve as CC              # noqa: E402
import repoint_rates as RP              # noqa: E402
from recalc_lo import recalc            # noqa: E402
import openpyxl                         # noqa: E402

TEMPLATE = os.path.join(_ROOT, "MODEL_TEMPLATE.xlsx")
GOLDEN = os.path.join(_ROOT, "tests", "golden", "AAPL")
WORK = os.environ.get("AAPL_ENG_WORK") or "/tmp/_idio_tie_work"
os.makedirs(WORK, exist_ok=True)

_p = _f = 0


def ok(cond, msg):
    global _p, _f
    if cond:
        _p += 1
        print("  PASS %s" % msg)
    else:
        _f += 1
        print("  FAIL %s" % msg)


def market_erp():
    rows = sorted(csv.DictReader(open(os.path.join(_ROOT, "rate_fixtures",
                                                   "erp_market_latest_annual.csv"))),
                  key=lambda r: float(r["tenor"]))
    return [float(r["market_erp"]) for r in rows]


def main():
    print("== the premium the fleet would use, from the COMMITTED curves ==")
    built = CC.build("AAPL", market_erp(), outdir=os.path.join(_ROOT, "outputs"),
                     asof="2026-08-20", log=None)
    series = built["series"]
    prov = built["provenance"]
    print("  AAPL premium: %+.4f pp at 1y, %+.4f at 30y, %+.4f collapsed  (region 2 %s)"
          % (series[0] * 100, series[29] * 100, prov.get("premium_collapsed_pp"),
             prov.get("region2_tier")))
    ok(len(series) == 30, "the series is thirty annual decimals")
    ok(any(abs(v) > 1e-9 for v in series),
       "THE SERIES IS NOT INERT -- a zero series would tie perfectly and mean nothing")
    ok(max(abs(v) for v in series) < 0.25,
       "the series is in DECIMALS, not percentage points (a hundredfold slip would tie too)")
    ok(prov.get("region3_visible_on_this_grid") is False,
       "obsolescence is still declared absent rather than quietly zero")

    BUILD = {"company": "Premium Tie Fixture", "ticker": "AAPL", "price": 315.0,
             "fy_end_month": 9, "forecast_horizon_N": 4,
             "files": {"is_csv": "%s/REAL_IS.csv" % GOLDEN, "bs_csv": "%s/REAL_BS.csv" % GOLDEN,
                       "cf_csv": "%s/REAL_CF.csv" % GOLDEN,
                       "prices": "%s/REAL_prices.csv" % GOLDEN,
                       "dividends": "%s/REAL_div.csv" % GOLDEN,
                       "splits": "%s/REAL_splits.csv" % GOLDEN},
             "judgments": {"minority_include": False, "finlease": 0.0, "oi_adj_override": None,
                           "rd_capitalize": True, "rd_life": 5.0, "dps_override": None},
             "cost_of_debt": {"single_ytw": 0.05}}
    results = []
    for valread in ("Equity path", "Enterprise path"):
        for coe in ("Single", "Term"):
            vals = {}
            for label, s in (("zero", [0.0] * 30), ("premium", series)):
                eng = os.path.join(WORK, "eng_%s_%s_%s.xlsx" % (valread[:4], coe, label))
                AE.build_model(BUILD, TEMPLATE, eng)
                wb = openpyxl.load_workbook(eng)
                wb["Inputs"]["B34"] = valread
                wb["Inputs"]["B29"] = coe
                RP.install_idio_hook(wb)
                RP.set_idio(wb, s)
                wb.save(eng)
                recalc(eng)
                wb = openpyxl.load_workbook(eng, data_only=True)
                vals[label] = (float(wb["Valuation"]["B54"].value),
                               float(wb["Audit"]["B5"].value))
            (v0, t0), (v1, t1) = vals["zero"], vals["premium"]
            results.append((valread, coe, v0, t0, v1, t1))
            print("  %-16s %-6s  tie(zero) %.2e  tie(premium) %.2e   value %.4f -> %.4f  (%+.2f%%)"
                  % (valread, coe, abs(t0), abs(t1), v0, v1, 100 * (v1 / v0 - 1)))

    for valread, coe, v0, t0, v1, t1 in results:
        ok(abs(t1) < 1e-9,
           "%s/%s: the four-method tie holds WITH the premium (%.2e)" % (valread, coe, abs(t1)))
    moves = [abs(v1 / v0 - 1) for _, _, v0, _, v1, _ in results]
    ok(min(moves) > 1e-4,
       "the premium MOVES the value in every configuration (min %.2f%%, max %.2f%%) -- a change "
       "that ties and moves nothing is inert" % (100 * min(moves), 100 * max(moves)))

    # The defect the dormancy hid: row 26 reads $AE$ in Single mode, so a per-tenor premium
    # appended without the same switch made "Single" not single. It could not show at zero.
    sing = [r for r in results if r[1] == "Single"]
    term = [r for r in results if r[1] == "Term"]
    ok(all(abs(a[4] / a[2] - 1) != abs(b[4] / b[2] - 1) for a, b in zip(sing, term)),
       "Single and Term move by DIFFERENT amounts -- the two modes are genuinely distinct")

    print("\n%d passed, %d failed" % (_p, _f))
    return 1 if _f else 0


def test_the_tie_holds_with_a_live_non_zero_premium():
    """Collected by the regression harness. The body is `main()` so the same file is also a
    diagnostic somebody can run by hand and read the four-config table off."""
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
