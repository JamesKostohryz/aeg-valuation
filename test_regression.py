#!/usr/bin/env python3
"""test_regression.py — the CI regression harness. One command that proves the engine
still reconciles and the pipeline still works, run on every change so a well-meaning edit
can't quietly break the four-method tie somewhere we're not looking.

Stages:
  1. FAST unit suites (no recalc): rate feed, config, tie-check, and the disclosure round-trip.
  2. BUILD the engine from the golden AAPL extract, recalc, assert the standing tie check.
  3. CONFIG GRID: toggle Equity/Enterprise x Single/Term x scenario x N, recalc each,
     assert the tie check holds every config (this is where drift shows up).
  4. DISCLOSURE: re-point rates from fixtures + run the Option-A bridge; assert both the
     base and idiosyncratic-sensitivity runs tie and the bridge sums.

Usage:  python test_regression.py [--full] [--quick]
        --quick : stages 1-2 + a 4-config grid (fast smoke).   --full : the 24-config grid.
Exit non-zero on any failure == a failed CI check.
"""
import os, sys, subprocess, shutil, itertools

_ROOT = os.path.dirname(os.path.abspath(__file__))
_PIPE = os.path.join(_ROOT, "pipeline")
for p in (_ROOT, _PIPE):
    if p not in sys.path:
        sys.path.insert(0, p)

GOLDEN = os.path.join(_ROOT, "tests", "golden", "AAPL")
FIXTURES = os.path.join(_ROOT, "rate_fixtures")
TEMPLATE = os.path.join(_ROOT, "MODEL_TEMPLATE.xlsx")
WORK = os.path.join(_ROOT, "_regwork")

_fail = 0
def check(cond, msg):
    global _fail
    print(f"  {'PASS' if cond else 'FAIL'}  {msg}")
    if not cond:
        _fail += 1


def run_unit(name):
    """Run a self-contained test script as a subprocess; PASS iff it exits 0."""
    r = subprocess.run([sys.executable, name], cwd=_PIPE if os.path.exists(os.path.join(_PIPE, name)) else _ROOT,
                       capture_output=True, text=True)
    tail = (r.stdout.strip().splitlines() or ["<no output>"])[-1]
    check(r.returncode == 0, f"{name}  ({tail})")


def main():
    full = "--full" in sys.argv
    quick = "--quick" in sys.argv
    os.makedirs(WORK, exist_ok=True)
    import aeg_engine as AE, checks as CK
    from recalc_lo import recalc
    import openpyxl

    print("== Stage 1: fast unit suites ==")
    run_unit("test_rate_feed.py")
    run_unit("test_config.py")
    run_unit("test_checks.py")
    run_unit("test_cost_boundary.py")  # operating-cost boundary-invariance (AT&T wedge guard)
    # SP500 earnings-normalization engine self-test (3 modes ~1e-15 + exact forecast
    # round-trip). Standalone module; imports nothing from the sealed engine.
    run_unit("valuation/normalization/normalization_engine.py")

    print("== Stage 2: build golden AAPL + standing tie check ==")
    files = {"is_csv": f"{GOLDEN}/REAL_IS.csv", "bs_csv": f"{GOLDEN}/REAL_BS.csv",
             "cf_csv": f"{GOLDEN}/REAL_CF.csv", "prices": f"{GOLDEN}/REAL_prices.csv",
             "dividends": f"{GOLDEN}/REAL_div.csv", "splits": f"{GOLDEN}/REAL_splits.csv"}
    cfg = {"company": "Apple Inc.", "ticker": "AAPL", "price": 315.0, "files": files,
           "fy_end_month": 9,
           "judgments": {"minority_include": False, "finlease": 0.0, "oi_adj_override": None,
                         "rd_capitalize": True, "rd_life": 5.0, "dps_override": None},
           "cost_of_debt": {"single_ytw": 0.05}}
    engine = os.path.join(WORK, "AAPL_reg.xlsx")
    AE.build_model(cfg, TEMPLATE, engine)
    recalc(engine)
    r = AE.read_results(engine, price=315.0)
    ok, d = CK.tie_check(r)
    check(ok, f"base tie check PASS (tie={r['max_identity_tie']:.1e}, audit={r['audit_status']!r})")

    print("== Stage 3: config grid ==")
    modes = ["Equity", "Enterprise"]
    coes = ["Single", "Term"]
    scens = ["Consensus", "Bull", "Bear", "Normal"] if full else ["Consensus"]
    Ns = [4, 8, 15] if full else ([4] if quick else [4, 8])
    grid = list(itertools.product(modes, coes, scens, Ns))
    if quick:
        grid = [g for g in grid if g[2] == "Consensus" and g[3] == 4]  # 4 configs
    print(f"  {len(grid)} configs")
    for mode, coe, scen, N in grid:
        wb = openpyxl.load_workbook(engine)
        IN = wb["Inputs"]
        IN["B37"] = mode; IN["B29"] = coe; IN["B69"] = scen; IN["B26"] = N
        gpath = os.path.join(WORK, f"grid_{mode[:2]}_{coe[:2]}_{scen[:2]}_{N}.xlsx")
        wb.save(gpath); recalc(gpath)
        rr = AE.read_results(gpath, price=315.0)
        ok, _ = CK.tie_check(rr)
        check(ok, f"{mode:10s} {coe:6s} {scen:9s} N={N:<2d} tie={rr['max_identity_tie']:.0e} audit={rr['audit_status'][:4]}")
        os.remove(gpath)

    print("== Stage 3b: row-61 opex-wedge structural guard ==")
    w = CK.rd_wedge_report(engine)
    check(w["rev_scaled_consistent"], f"row-61 wedge revenue-proportional (wedge={w['opex_wedge']:.4f}, "
          f"{(100*w['wedge_pct_ebit']):.1f}% of EBIT)")
    check(w["rd_capitalization_wired"] is False,
          "R&D capitalization documented INERT (known gap; no-R&D names unaffected)")

    print("== Stage 4: rate re-point + disclosure bridge ==")
    try:
        import rate_feed as RF, repoint_rates as RP, disclose as D
        feed = RF.load_all("AAPL", cash=0, sti=0, local_dir=FIXTURES)
        dp = os.path.join(WORK, "AAPL_disc.xlsx")
        shutil.copy(engine, dp)
        wb = openpyxl.load_workbook(dp); RP.repoint(wb, feed); wb.save(dp)
        res = D.disclose(dp, feed, price=315.0, recalc=recalc,
                         sens_path=os.path.join(WORK, "AAPL_disc_sens.xlsx"))
        check(res["base_tie"] < 1e-9 and res["sens_tie"] < 1e-9,
              f"disclosure ties (base {res['base_tie']:.0e}, sens {res['sens_tie']:.0e})")
        recon = res["base_equity_ps"] + res["debt_capital_gain_ps"] - res["idiosyncratic_haircut_ps"]
        check(abs(recon - res["adjusted_equity_ps"]) < 1e-9, "bridge sums to adjusted equity")
    except Exception as e:
        check(False, f"disclosure stage errored: {e}")

    shutil.rmtree(WORK, ignore_errors=True)
    print(f"\n{'ALL REGRESSION CHECKS PASSED' if _fail == 0 else f'{_fail} REGRESSION CHECK(S) FAILED'}")
    sys.exit(1 if _fail else 0)


if __name__ == "__main__":
    main()
