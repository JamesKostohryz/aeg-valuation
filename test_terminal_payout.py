#!/usr/bin/env python3
"""test_terminal_payout.py — the terminal (continuing-period) distribution-policy gate.

Written 2026-08-12 alongside pipeline/terminal_payout.py, discovered while extending the
funding gate to cover the continuing period at James's request.

TWO THINGS THIS PINS.

1. terminal_payout_report() discriminates correctly: MISSING when no ratio was ever set (no
   escape hatch -- run_company.py refuses this unconditionally), REVIEW when the normalized
   EPS benchmark is not a coherent base for a payout assertion (zero, negative, absent), and
   PASS with the right arithmetic otherwise. Pure-function tests, no engine needed.

2. THE PROPERTY THAT MATTERS MOST: this gate cannot move the published value, whatever ratio
   is chosen. It is disclosure and a boundary check, not a valuation input. Proven by driving
   the real engine once and computing the report at ratio 0.0, 0.5 and 1.0 off the SAME
   recalculated workbook -- normalized_eps_N does not change (it is read off Valuation-tab
   rows this module never touches), so nothing here can feed back into row 24's cfg_N-gated
   contribution sum. This is the same property test_horizon_gating.py proved for the raw
   Forecast-tab driver cells past cfg_N; this test proves it for the new gate specifically,
   because a future change that accidentally wired the ratio into the workbook would be
   exactly the silent-and-green failure this project keeps finding.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
_PIPE = os.path.join(_ROOT, "pipeline")
for p in (_ROOT, _PIPE):
    if p not in sys.path:
        sys.path.insert(0, p)

import terminal_payout as TP

_passed = _failed = 0


def check(cond, msg):
    global _passed, _failed
    print(f"  {'PASS' if cond else 'FAIL'}  {msg}")
    if cond:
        _passed += 1
    else:
        _failed += 1


def main():
    print("== terminal_payout_report: discriminates on the ratio ==")
    r = TP.terminal_payout_report(None, 7.87)
    check(r["verdict"] == "MISSING", f"no ratio set -> MISSING (got {r['verdict']})")
    check(r["implied_dps"] is None, "MISSING carries no implied DPS")

    for bad_norm in (None, 0.0, -1.25, "n/a"):
        r = TP.terminal_payout_report(0.5, bad_norm)
        check(r["verdict"] == "REVIEW",
              f"ratio set but normalized EPS is {bad_norm!r} -> REVIEW (got {r['verdict']})")
        check(r["implied_dps"] is None, f"REVIEW ({bad_norm!r}) carries no implied DPS")

    r = TP.terminal_payout_report(0.55, 7.8729)
    check(r["verdict"] == "PASS", f"valid ratio + positive normalized EPS -> PASS "
                                  f"(got {r['verdict']})")
    check(abs(r["implied_dps"] - 0.55 * 7.8729) < 1e-9,
          f"implied terminal DPS = ratio x normalized EPS "
          f"({r['implied_dps']:.6f} vs {0.55 * 7.8729:.6f})")
    check(abs(r["implied_retained_ps"] - (7.8729 - r["implied_dps"])) < 1e-9,
          "implied retention = normalized EPS - implied DPS")
    check(abs(r["implied_dps"] + r["implied_retained_ps"] - 7.8729) < 1e-9,
          "dividend + retention reconciles exactly to normalized EPS (no third destination)")

    print("== boundary ratios ==")
    r0 = TP.terminal_payout_report(0.0, 10.0)
    check(r0["verdict"] == "PASS" and abs(r0["implied_dps"]) < 1e-12,
          "ratio 0.0 -> zero terminal dividend, full retention")
    check(abs(r0["implied_retained_ps"] - 10.0) < 1e-9, "ratio 0.0 retains all of normalized EPS")
    r1 = TP.terminal_payout_report(1.0, 10.0)
    check(r1["verdict"] == "PASS" and abs(r1["implied_dps"] - 10.0) < 1e-9,
          "ratio 1.0 -> the full normalized EPS is distributed")
    check(abs(r1["implied_retained_ps"]) < 1e-12, "ratio 1.0 retains nothing")
    print("  (bounded to [0,1] at the config seam -- see pipeline/test_config.py -- so a "
          "negative implied dividend is not reachable through this gate at all)")

    print("== the published value cannot depend on the ratio: engine-level pin ==")
    try:
        import aeg_engine as AE
        import convergence as CV
        from recalc_lo import recalc
    except Exception as e:
        print(f"  SKIP (engine deps unavailable: {e})")
    else:
        GOLDEN = os.path.join(_ROOT, "tests", "golden", "AAPL")
        TEMPLATE = os.path.join(_ROOT, "MODEL_TEMPLATE.xlsx")
        WORK = os.path.join(_ROOT, "_termwork")
        os.makedirs(WORK, exist_ok=True)
        cfg = {"company": "Apple Inc.", "ticker": "AAPL", "price": 315.0, "fy_end_month": 9,
               "forecast_horizon_N": 4,
               "files": {"is_csv": f"{GOLDEN}/REAL_IS.csv", "bs_csv": f"{GOLDEN}/REAL_BS.csv",
                         "cf_csv": f"{GOLDEN}/REAL_CF.csv", "prices": f"{GOLDEN}/REAL_prices.csv",
                         "dividends": f"{GOLDEN}/REAL_div.csv",
                         "splits": f"{GOLDEN}/REAL_splits.csv"},
               "judgments": {"minority_include": False, "finlease": 0.0,
                             "oi_adj_override": None, "rd_capitalize": True, "rd_life": 5.0,
                             "dps_override": None},
               "cost_of_debt": {"single_ytw": 0.05}}
        path = os.path.join(WORK, "AAPL_base.xlsx")
        AE.build_model(cfg, TEMPLATE, path)
        recalc(path)
        import openpyxl
        intrinsic_before = openpyxl.load_workbook(path, data_only=True)["Valuation"]["B44"].value

        conv = CV.converge_auto(path, K=3)
        norm_eps_N = conv.get("norm_eps_N")
        check(isinstance(norm_eps_N, (int, float)),
              f"normalized EPS at cfg_N computed off the real engine ({norm_eps_N})")

        reports = [TP.terminal_payout_report(ratio, norm_eps_N) for ratio in (0.0, 0.5, 1.0)]
        check(reports[0]["normalized_eps_N"] == reports[1]["normalized_eps_N"] ==
              reports[2]["normalized_eps_N"],
              "normalized_eps_N is identical across every ratio choice (it is read once, "
              "off the same recalc'd workbook, before the ratio is ever applied)")
        check(len({r["implied_dps"] for r in reports}) == 3,
              "the three ratios DO produce three different implied terminal dividends "
              "(the gate is not a no-op)")

        intrinsic_after = openpyxl.load_workbook(path, data_only=True)["Valuation"]["B44"].value
        check(intrinsic_after == intrinsic_before,
              "computing all three terminal-payout reports touched the workbook not at all -- "
              "V(EPS) (Valuation!B44) is bit-identical before and after "
              f"({intrinsic_before!r} == {intrinsic_after!r})")
        print("  (terminal_payout_report takes no workbook argument and writes nothing -- this "
              "assertion exists so a future refactor that accidentally gave it one would be "
              "caught here rather than by an outside observer noticing a moved value)")

    print(f"\n{_passed} passed, {_failed} failed")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
