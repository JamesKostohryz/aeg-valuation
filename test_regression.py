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
    """Run a self-contained test script as a subprocess; PASS iff it exits 0.

    A name beginning `-m ` is a module invocation (`-m pytest ...`) rather than a script, so
    that a pytest suite can be listed here alongside the standalone scripts."""
    argv = name.split() if name.startswith("-m ") else [name]
    cwd = _PIPE if (not name.startswith("-m ")
                    and os.path.exists(os.path.join(_PIPE, name))) else _ROOT
    r = subprocess.run([sys.executable] + argv, cwd=cwd, capture_output=True, text=True)
    # Fall back to stderr when a suite dies before printing anything. A failing check whose
    # reason reads "<no output>" tells the reader nothing and trains them to skip it; the first
    # CI run of the idio block failed exactly that way, and the reason (pytest not installed on
    # the runner) was sitting in stderr the whole time.
    tail = (r.stdout.strip().splitlines()
            or r.stderr.strip().splitlines() or ["<no output>"])[-1]
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
    run_unit("normalization/normalization_engine.py")
    # SP500 spec 5(2): Mode A reproduces the v4 golden fixture to the penny (~2e-4;
    # penny not bit-exact, per COCKPIT 20260721-0842 addendum).
    run_unit("normalization/tests/test_normalization_fixture.py")
    # E2 truncation gates (was: the convergence period; the increment was retired 2026-08-12) +
    # correction (peak catches down, trough catches up) + the reconciliation guard.
    run_unit("test_convergence.py")
    # Unfunded-distribution guard (2026-08-11). Under the canonical operating closure the
    # distribution is a residual, and a residual can come out negative — an implied equity
    # issuance nobody forecast. Thirteen checks that the guard discriminates rather than
    # merely fires, driving the real engine for each case.
    run_unit("test_funding_check.py")
    # Terminal (continuing-period) distribution-policy gate (2026-08-12): what the company
    # does after cfg_N, dividends-only, no default. Discrimination tests plus the property
    # that matters most -- it cannot move the published value, pinned against the real engine.
    run_unit("test_terminal_payout.py")
    # The standing WIRING check. test_convergence.py passed here on every run for weeks while
    # convergence.py was imported by nothing except itself, so the feature reached no valuation
    # at all and no check could see it. This fails when any module in pipeline/ has no importer
    # outside its own test.
    run_unit("test_orphan_modules.py")
    # AEG-Coverage-Map-2026-08-08.md: nine every-build modules that previously had zero
    # automated coverage. Each builds+recalcs the golden AAPL engine independently and
    # re-derives its numbers from raw cells rather than re-testing the module against itself.
    run_unit("test_synthetic_rating.py")
    run_unit("test_cod_fallback.py")
    run_unit("test_deflator_extend.py")
    run_unit("test_repoint_fy0.py")
    run_unit("test_scorecard.py")
    run_unit("test_aeg_schedule.py")
    run_unit("test_dupont_extract.py")
    run_unit("test_fact_sheet.py")
    run_unit("test_restated_split.py")
    # REGISTER ITEM 12: a stock split must not change market capitalization.
    # Company-independent arithmetic, and an error class the four-method tie is
    # structurally blind to -- the tie never looks at the price series.
    run_unit("test_market_cap_split.py")
    # THE LEASE RULING decision logic: apply only where two independent routes agree,
    # never subtract leases from a year already on borrowings, and hand back figures in
    # the vendor's own units. All three were got wrong once and are silent if regressed.
    run_unit("test_lease_ruling.py")
    # Phase 1, Property 8 -- the continuing period must begin at a NORMALIZED, neutral earnings
    # level with abnormal growth already zero -- is still enforced, but no longer by adjusting
    # value. test_convergence_start.py was retired on 2026-08-12 along with the convergence
    # increment it tested; its assertions were that a peak marks value DOWN and a trough UP, and
    # there is no longer any mark. Property 8 is now two REFUSALS at the truncation point, both
    # covered by test_convergence.py above: gate A, abnormal earnings growth must be spent at the
    # stop year, and gate B, EPS there must sit at the normalized level. The published value is
    # the engine value, so unlike the old increment it is fully inside the four-method tie and
    # every other check in this harness can see it.
    # See docs/AEG-CONVERGENCE-RETIRED-2026-08-12.md.
    # Phase 1, Property 4: post-horizon years cannot move value. Measured at exactly
    # 0.0 on N=4 and N=8 under four adversarial perturbations. Drives the engine, so
    # it needs LibreOffice and costs real wall-clock -- full scope only.
    if full:
        run_unit("test_horizon_gating.py")
        # Phase 1, Property 5, full-retention end. Zero retention is already covered by
        # test_zero_growth.py. Three builds with recalculation, so full scope only.
        run_unit("test_full_retention.py")
    # S1 — three suites that existed but were run by nothing: absent from this list and
    # from every workflow. test_curve_shapes.py is the five-curve-shape property test that
    # exposed the AEG-vs-residual-income cross-tab gap in PR #3, the largest correctness
    # defect this engine has had (up to 22.6% on an inverted curve). Leaving the test that
    # caught it out of the harness is the worst possible place to have a gap.
    run_unit("test_curve_shapes.py")
    run_unit("test_disclose.py")
    # P1/P2/P3/P4/P5 — per-company policy inputs, the Valuation row-11 financing path, and
    # the value-weighted operations tie.
    run_unit("test_policy_inputs.py")
    # The anchor-date convention, checked against the dividend discount model — an oracle
    # OUTSIDE the four spokes. All four legs share the timing convention, so a wrong anchor
    # date would leave the four-method tie reading 1e-15 while every published number was
    # wrong by the anchor year's retained earnings. The tie cannot see this class of error.
    run_unit("test_anchor_timing.py")
    # PHASE 1 PROPERTY SUITE — the engine measured against closed forms computed OUTSIDE the
    # model, which is the only kind of evidence that can answer "is the arithmetic right?".
    # The four-method tie cannot answer it: all four legs are transformations of one restated
    # stream sharing one timing convention, so they agree for any forecast and any anchor,
    # including wrong ones.
    #   Property 1 — unit-scale invariance. Multiply every currency input by k; every
    #                per-share output must be bit-identical.
    #   Property 2 — the zero-abnormal-growth reduction. Strip the abnormal growth out of
    #                the forecast and the valuation must collapse to forward normal earnings
    #                over the cost of equity, and to a dividend discount model summed in
    #                plain Python.
    run_unit("test_scale_invariance.py")
    run_unit("test_zero_growth.py")
    # S5 — the three previously untested on-demand modules. apply_payload is the sole
    # writer of cfg_N and the payout seed, i.e. the only path by which the two most
    # powerful judgments in the model can be set at all.
    run_unit("test_apply_payload.py")
    run_unit("test_run_scenarios.py")
    # The reviewed forecast is a repository artifact (2026-08-13). Offline; no recalc. Guards
    # the rule that a company with a forecast on file is never valued payload-free -- the
    # failure that quarantined PepsiCo's published outputs at commit 33a6b5a.
    run_unit("test_reviewed_forecast.py")
    run_unit("test_kit_feeds.py")
    # THE DEPENDENCY WIRING. requirements.txt called itself the source of truth for every
    # workflow while two of them installed a hand-kept list instead, so pyarrow and pytest both
    # reached the code and never reached the runner. Checks that every workflow installs from
    # the file, that none keeps a substitute list beside it, and that every third-party import
    # in the repository -- including the ones inside functions, which is where an optional
    # dependency always hides -- is declared. No imports of its own beyond the standard
    # library, so it can never be the test that fails for want of a package.
    run_unit("test_workflow_deps.py")
    # The rate-side refresh dispatcher. Offline; every cross-repository call is intercepted, so
    # what it proves is WHAT it would send -- above all that it sends obs_category=KEEP. Sending
    # a concrete category would silently re-decide every company's durability judgment, which
    # lands in the published cost-of-equity curve, on every scheduled run.
    run_unit("test_rate_refresh.py")
    # THE COMPANY-PREMIUM PACKAGE. Until 2026-08-19 nothing ran these on a push: they live in
    # tests/, but this harness never listed them, and idio-universe-refresh -- the only workflow
    # that did run them -- fires on a monthly cron and on manual dispatch. So a change to
    # idio/erp.py ran no test at all, on a module whose whole purpose is to set a discount rate.
    # They are hermetic and cost under a second between them.
    #   test_idio_feed        the ported risk statistic, pinned to the 2026-08-17 research values
    #   test_idio_region2_common  COMMON(t): the T4 identity at every tenor, the front-tenor
    #                         identity unchanged, no reordering, and NOT INERT
    #   test_idio_membership  the three membership guards, each shown to discriminate
    run_unit("-m pytest tests/test_idio_feed.py tests/test_idio_region2_common.py "
             "tests/test_idio_membership.py tests/test_idio_company_curve.py -q")
    # The debt-feed guard (2026-08-09). The vendor "Total Debt" row is `in_debt`, which
    # sets net financial obligations and, through the identity that plugs net operating
    # assets, reprices the whole forecast — and the four-method tie stays green at 1e-14
    # whether the figure is right or wrong, so the tie cannot police it. These tests are
    # offline and deterministic: they check that the guard claims the vendor is wrong ONLY
    # on a clean, observed break, and refuses on the three ways our own reconstruction of
    # gross borrowings from the filings can look like a vendor defect.
    run_unit("test_debt_feed.py")
    # Ten configurations, each a build + recalc, so it is too slow for every run. Stage 3
    # covers the same ground more cheaply on the standard path; this is the exhaustive
    # cross-tab version and belongs on --full rather than nowhere, which is where it was.
    if full:
        run_unit("test_nominal_nest.py")

    print("== Stage 2: build golden AAPL + standing tie check ==")
    files = {"is_csv": f"{GOLDEN}/REAL_IS.csv", "bs_csv": f"{GOLDEN}/REAL_BS.csv",
             "cf_csv": f"{GOLDEN}/REAL_CF.csv", "prices": f"{GOLDEN}/REAL_prices.csv",
             "dividends": f"{GOLDEN}/REAL_div.csv", "splits": f"{GOLDEN}/REAL_splits.csv"}
    cfg = {"company": "Apple Inc.", "ticker": "AAPL", "price": 315.0, "files": files,
           "fy_end_month": 9,
           "forecast_horizon_N": 4,   # P2: cfg_N is required and has no default; 4 is the
                                     # horizon these fixtures have always run at.
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
        check(res["base_tie"] < 1e-9, f"disclosure tie (base {res['base_tie']:.0e})")
        check("idiosyncratic_haircut_ps" not in res,
              "the deleted idiosyncratic haircut is absent from the disclosure")
        recon = (res["base_equity_ps"] + res["debt_capital_gain_ps"]
                 - (res.get("depreciation_anchor_penalty_ps") or 0.0))  # Increment 1 term
        check(abs(recon - res["adjusted_equity_ps"]) < 1e-9, "bridge sums to adjusted equity")
    except Exception as e:
        check(False, f"disclosure stage errored: {e}")

    shutil.rmtree(WORK, ignore_errors=True)
    print(f"\n{'ALL REGRESSION CHECKS PASSED' if _fail == 0 else f'{_fail} REGRESSION CHECK(S) FAILED'}")
    sys.exit(1 if _fail else 0)


if __name__ == "__main__":
    main()
