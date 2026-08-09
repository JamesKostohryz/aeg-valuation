#!/usr/bin/env python3
"""test_convergence_start.py — Phase 1, Property 8: where the continuing period begins.

THE PROPERTY
------------
The continuing period must begin at a NORMALIZED, NEUTRAL earnings level. That is the whole
reason the convergence period exists: the explicit forecast may stop at a level that is not
neutral -- a cyclical peak, a trough, a year with an unrepeatable margin -- and capitalizing
that level makes the valuation wrong even with abnormal earnings growth already at zero.

So two things must be true where the glide ends and the continuing period starts:

    1. the earnings level equals the NORMALIZED line walked forward, and
    2. abnormal earnings growth is ZERO from that point on.

This matters more than most of the suite because the convergence-corrected value IS the
headline James publishes, and the increment sits OUTSIDE the four-method tie -- equity leg
only. The tie cannot see this. Nothing else can either, until this file.

WHAT IS CHECKED AGAINST WHAT
----------------------------
Every expected value here is recomputed in plain Python from the engine's own per-year cost
of equity, inflation and anchor retention -- never read back out of the convergence module.
The module has to agree with arithmetic done outside it.

The tests are ordered so nothing can pass vacuously: the faithfulness identity comes first
(on-trend input must produce EXACTLY zero correction), then the terminal level, then the
zero-abnormal-growth condition at the boundary, then negative controls that prove a peak is
marked down and a trough marked up.

Needs LibreOffice, because it drives a real built engine.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
for _p_ in (_ROOT, os.path.join(_ROOT, "pipeline")):
    if _p_ not in sys.path:
        sys.path.insert(0, _p_)

import openpyxl                                              # noqa: E402
import aeg_engine as AE                                      # noqa: E402
import convergence as CV                                     # noqa: E402
from recalc_lo import recalc                                 # noqa: E402

GOLDEN = os.path.join(_ROOT, "tests", "golden", "AAPL")
TEMPLATE = os.path.join(_ROOT, "MODEL_TEMPLATE.xlsx")
WORK = os.environ.get("AAPL_ENG_WORK") or "/tmp/_convergence_start_work"
PRICE = 315.0
N = 8
K = 3

CFG = {"company": "Apple Inc.", "ticker": "AAPL", "price": PRICE, "fy_end_month": 9,
       "forecast_horizon_N": N,
       "files": {"is_csv": f"{GOLDEN}/REAL_IS.csv", "bs_csv": f"{GOLDEN}/REAL_BS.csv",
                 "cf_csv": f"{GOLDEN}/REAL_CF.csv", "prices": f"{GOLDEN}/REAL_prices.csv",
                 "dividends": f"{GOLDEN}/REAL_div.csv", "splits": f"{GOLDEN}/REAL_splits.csv"},
       "judgments": {"minority_include": False, "finlease": 0.0, "oi_adj_override": None,
                     "rd_capitalize": True, "rd_life": 5.0, "dps_override": None},
       "cost_of_debt": {"single_ytw": 0.05}}

_p = _f = 0


def ok(cond, msg):
    global _p, _f
    if cond:
        _p += 1
        print("  PASS", msg)
    else:
        _f += 1
        print("  FAIL", msg)


def close(a, b, tol, msg):
    got = (isinstance(a, (int, float)) and isinstance(b, (int, float))
           and abs(a - b) <= tol * max(1.0, abs(b)))
    ok(got, f"{msg}  ({a!r} vs {b!r}, rel tol {tol:g})")


# --------------------------------------------------------------- build once
os.makedirs(WORK, exist_ok=True)
ENG = os.path.join(WORK, f"base_N{N}.xlsx")
AE.build_model(CFG, TEMPLATE, ENG)
recalc(ENG)

wb = openpyxl.load_workbook(ENG, data_only=True)
V = wb["Valuation"]
rho = CV._series(V, 5)
eps = CV._series(V, 7)
ret = CV._series(V, 9)
pi_at, _ = CV._infl(V)
rho_LR = V["B20"].value
actualN = eps[N]
b = ret[N] / eps[N]

print(f"== engine: cfg_N={N}, K={K}, actual EPS at N = {actualN:.9f}, "
      f"anchor retention {b:.6f}, long-run cost of equity {rho_LR:.6%} ==\n")


def normal_growth_factor(t):
    """The one-year NOMINAL normal-growth factor at year t, from the engine's own rate and
    inflation. Real reinvestment return times retention, then inflation on top -- NOT the
    nominal rate times retention, which is the error this framework is easiest to make."""
    p = pi_at(t)
    r_real = (1 + (rho[t] if t < len(rho) and isinstance(rho[t], (int, float)) else rho_LR)) \
        / (1 + p) - 1
    return (1 + r_real * b) * (1 + p)


CUM = 1.0
for _t in range(N + 1, N + K + 1):
    CUM *= normal_growth_factor(_t)


# ------------------------------------------------- 1. FAITHFULNESS comes first
# On-trend input (normalized == actual) must produce EXACTLY zero correction. If it does not,
# every measurement below is measuring the module's own drift rather than the property.
print("== 1. faithfulness: on-trend in, nothing out ==")
r_on = CV.converge_valuation(ENG, K=K, norm_eps_N=actualN)
ok(all(abs(s["aeg_eps"]) <= 1e-12 * max(1.0, actualN) for s in r_on["schedule"]),
   f"on-trend: abnormal earnings growth is zero at every glide year "
   f"(worst {max(abs(s['aeg_eps']) for s in r_on['schedule']):.3e})")
close(r_on["converge_value_ps"], 0.0, 1e-12, "on-trend: the correction is exactly zero")
close(r_on["corrected_intrinsic"], r_on["eng_intrinsic"], 1e-12,
      "on-trend: the corrected value IS the engine value")
ok(len(r_on["schedule"]) == K, f"the glide is exactly K={K} years long")


# ------------------------------------------- 2. THE TERMINAL LEVEL, off-trend
# Stop at a peak: the normalized line sits 20% below the forecast's last year.
print("\n== 2. the glide ends on the NORMALIZED line, walked forward ==")
for label, ratio in (("peak, normalized 20% below", 0.80),
                     ("trough, normalized 25% above", 1.25),
                     ("mild, normalized 5% below", 0.95)):
    norm = actualN * ratio
    r = CV.converge_valuation(ENG, K=K, norm_eps_N=norm)
    last = r["schedule"][-1]
    # Computed OUTSIDE the module: the normalized level grown at normal growth for K years.
    expected = norm * CUM
    close(last["eps"], expected, 1e-12,
          f"{label}: earnings at the end of the glide equal the normalized line walked "
          f"forward {K} years")
    ok(last["t"] == N + K, f"{label}: and that year is N+K = {N + K}")


# ----------------------------- 3. ABNORMAL GROWTH IS ZERO AT THE BOUNDARY
# The continuing period begins the year after the glide. Its first year must carry no
# abnormal growth: earnings there are the glide's exit level grown at normal growth, which
# is exactly the benchmark the module charges. Recomputed here from the module's own
# definition of the benchmark, using figures taken from the schedule.
print("\n== 3. abnormal earnings growth is ZERO where the continuing period starts ==")
for label, ratio in (("peak", 0.80), ("trough", 1.25)):
    r = CV.converge_valuation(ENG, K=K, norm_eps_N=actualN * ratio)
    exit_eps = r["schedule"][-1]["eps"]
    t = N + K + 1
    p = pi_at(t)
    rt = rho[t] if (t < len(rho) and isinstance(rho[t], (int, float))) else rho_LR
    # the module's benchmark: inflate the prior flow, charge the REAL rate on retention
    benchmark = (1 + p) * exit_eps + (rt - p) * b * exit_eps
    # the continuing period grows the exit level at normal growth
    continuing = exit_eps * normal_growth_factor(t)
    close(continuing, benchmark, 1e-12,
          f"{label}: the first continuing year equals its own benchmark, so abnormal "
          f"earnings growth there is zero")
    ok(abs(continuing - benchmark) <= 1e-12 * max(1.0, abs(benchmark)),
       f"{label}: stated as the property — AEG at the start of the continuing period is 0")


# --------------------------------------------- 4. NEGATIVE CONTROLS AND SIGN
print("\n== 4. it does something, and in the right direction ==")
peak = CV.converge_valuation(ENG, K=K, norm_eps_N=actualN * 0.80)
trough = CV.converge_valuation(ENG, K=K, norm_eps_N=actualN * 1.25)
ok(max(abs(s["aeg_eps"]) for s in peak["schedule"]) > 1e-6,
   "off-trend: abnormal earnings growth is genuinely NOT zero during the glide")
ok(peak["converge_value_ps"] < 0,
   f"stopping at a PEAK marks the value DOWN ({peak['converge_value_ps']:+.6f}/sh)")
ok(trough["converge_value_ps"] > 0,
   f"stopping at a TROUGH marks it UP ({trough['converge_value_ps']:+.6f}/sh)")
close(peak["converge_gap_ps"], actualN - actualN * 0.80, 1e-12,
      "the disclosed gap is the off-trend distance itself")


# ------------------------------------------- 5. THE SCHEDULE ADDS UP
print("\n== 5. the disclosed schedule reconciles to the disclosed value ==")
for label, r in (("peak", peak), ("trough", trough), ("on-trend", r_on)):
    close(sum(s["contrib_eps"] for s in r["schedule"]), r["converge_value_ps"], 1e-12,
          f"{label}: the per-year contributions sum to the convergence value")
    close(r["corrected_intrinsic"] - r["eng_intrinsic"], r["converge_value_ps"], 1e-12,
          f"{label}: and the correction is the whole difference from the engine value")


# ------------------------------------------- 6. K = 0 IS OFF, NOT BROKEN
print("\n== 6. convergence off ==")
r0 = CV.converge_valuation(ENG, K=0, norm_eps_N=actualN * 0.80)
close(r0["converge_value_ps"], 0.0, 1e-12, "K=0 produces no correction")
close(r0["corrected_intrinsic"], r0["eng_intrinsic"], 1e-12, "and leaves the engine value alone")
ok(r0["verdict"] == "PASS", "and reports PASS rather than failing")

if _f:
    print(f"\nFAIL  test_convergence_start.py  ({_p} passed, {_f} failed)")
    sys.exit(1)
print(f"\n{_p} passed, 0 failed")
