#!/usr/bin/env python3
"""test_convergence.py — E2 convergence self-tests. Builds the golden AAPL engine (like the
regression Stage 2) so it runs standalone in CI, then checks faithfulness + correction.

REWRITTEN 2026-08-11. Three checks here previously hard-coded that Apple is a below-normal
grower and that the correction therefore lifts value. That was never a property of the
convergence period; it was a property of the value-neutral rate the normalizer used to walk
its anchors, which under the canonical operating closure collapses to 0.134% a year against
earnings that track 5.26%. The checks are replaced by the properties they were reaching for —
direction follows the gap, and the booked value reconciles — plus the tests that would have
caught the defect: the normalizer must be SILENT on a series with no cycle in it, and must
still fire on a genuine one.
"""
import os, sys, statistics, tempfile
ROOT = os.path.dirname(os.path.abspath(__file__)); PIPE = os.path.join(ROOT, "pipeline")
for p in (ROOT, PIPE):
    if p not in sys.path: sys.path.insert(0, p)
import convergence as C

def _build_aapl():
    import aeg_engine as AE
    from recalc_lo import recalc
    G = os.path.join(ROOT, "tests", "golden", "AAPL"); T = os.path.join(ROOT, "MODEL_TEMPLATE.xlsx")
    files = {"is_csv": f"{G}/REAL_IS.csv", "bs_csv": f"{G}/REAL_BS.csv", "cf_csv": f"{G}/REAL_CF.csv",
             "prices": f"{G}/REAL_prices.csv", "dividends": f"{G}/REAL_div.csv", "splits": f"{G}/REAL_splits.csv"}
    cfg = {"company": "Apple Inc.", "ticker": "AAPL", "price": 315.0, "files": files, "fy_end_month": 9,
    "forecast_horizon_N": 4,   # P2: cfg_N is required and has no default; 4 is the
                              # horizon these fixtures have always run at.
           "judgments": {"minority_include": False, "finlease": 0.0, "oi_adj_override": None,
                         "rd_capitalize": True, "rd_life": 5.0, "dps_override": None},
           "cost_of_debt": {"single_ytw": 0.05}}
    out = os.path.join(tempfile.mkdtemp(prefix="convtest_"), "_convtest_aapl.xlsx")
    AE.build_model(cfg, T, out); recalc(out); return out

ENG = os.environ.get("AAPL_ENG") or _build_aapl()
import openpyxl
_WB = openpyxl.load_workbook(ENG, data_only=True)
V = _WB["Valuation"]
fails = 0
def check(c, m):
    global fails; print(f"  {'PASS' if c else 'FAIL'}  {m}"); fails += (0 if c else 1)

r0 = C.converge_valuation(ENG, K=3, norm_eps_N=None); eng = r0["eng_intrinsic"]; N = r0["N"]
epsN = V.cell(7, 2 + N).value
print("== faithfulness ==")
check(abs(r0["corrected_intrinsic"] - eng) < 1e-9, f"convergence OFF reproduces engine ({eng:.4f})")
r1 = C.converge_valuation(ENG, K=3, norm_eps_N=epsN)
check(abs(r1["corrected_intrinsic"] - eng) < 1e-9, f"on-trend reproduces engine exactly (diff {abs(r1['corrected_intrinsic']-eng):.1e})")
check(all(abs(s["aeg_eps"]) < 1e-9 for s in r1["schedule"]), "on-trend convergence AEG identically 0")

print("== correction ==")
rp = C.converge_valuation(ENG, K=3, norm_eps_N=epsN*0.80)
check(rp["corrected_intrinsic"] < eng and rp["converge_value_ps"] < 0, f"peak catches down: {rp['corrected_intrinsic']:.2f} < {eng:.2f}")
check(rp["verdict"] == "REVIEW", "large gap flags REVIEW")
rt = C.converge_valuation(ENG, K=3, norm_eps_N=epsN*1.25)
check(rt["corrected_intrinsic"] > eng and rt["converge_value_ps"] > 0, f"trough catches up: {rt['corrected_intrinsic']:.2f} > {eng:.2f}")

print("== HARD RULE: zero AEG in the continuing period ==")
# James, 2026-08-11: "There is zero AEG in the continuing period. That is a hard rule."
# The glide must have fully arrived on the normalized line by the last convergence year, so
# that continuing at the normal rate from there books nothing further. Checked for a gap in
# each direction, not just the fixture's own.
_rho = C._series(V, 5); _pi, _ = C._infl(V); _b = C._series(V, 9)[N] / epsN
for _tag, _r in (("catching down", rp), ("catching up", rt)):
    _last = _r["schedule"][-1]; _t = _last["t"] + 1
    _rt = _rho[_t] if _t < len(_rho) and isinstance(_rho[_t], (int, float)) else V["B20"].value
    _p = _pi(_t)
    _grown = _last["eps"] * ((1 + _p) + (_rt - _p) * _b)
    _normal = (1 + _p) * _last["eps"] + (_rt - _p) * _b * _last["eps"]
    check(abs(_grown - _normal) < 1e-12, f"AEG at the first continuing-period year, {_tag}: {_grown-_normal:.2e}")
    check(abs(_last["eps"] / _r["schedule"][0]["eps"]) > 0, f"glide completes its transition ({_tag})")

print("== the normal line is derived, not assumed ==")
# The rate that walks the anchors is re-derived per company from that company's own path.
# By identity b_{t-1} * RORE_t is the realized growth of the line, normalized by median across
# the trailing window. Year N is excluded from its own trend estimate.
g_auto = C._normal_line_growth(C._series(V, 7), N)
check(isinstance(g_auto, float), f"normal-line growth derived from the engine path: {g_auto:+.4%}")
_flat = [10.0] * 9
check(abs(C._normal_line_growth(_flat, 8)) < 1e-15, "flat series -> flat normal line (0.00%)")
_geo = [10.0 * 1.07 ** i for i in range(9)]
check(abs(C._normal_line_growth(_geo, 8) - 0.07) < 1e-12, "series on a 7% line -> 7% normal line")
_spike = [10.0 * 1.07 ** i for i in range(9)]; _spike[8] *= 1.60
check(abs(C._normal_line_growth(_spike, 8) - 0.07) < 1e-12,
      "a spike AT year N does not contaminate its own trend estimate (year N excluded)")
_spike2 = [10.0 * 1.07 ** i for i in range(9)]; _spike2[6] *= 1.60
check(abs(C._normal_line_growth(_spike2, 8) - 0.07) < 0.02,
      "a spike inside the window is rejected by the median")
check(C._normal_line_growth([0.0, 0.0, 0.0], 2) == 0.0, "no usable observation -> flat, never a fabricated drift")

print("== the normalizer is silent when there is no cycle, and fires when there is ==")
# The defect this replaces: the normalizer reported an identical -7.0% "above normal" at every
# year of a series with no cycle in it, so it corrected companies that needed no correcting and
# mis-sized the ones that did. A normalization of a series with no cycle must return that
# series. Synthetic, so it tests the property rather than the fixture.
def _norm(series, t, X=4):
    g = C._normal_line_growth(series, t, X=X)
    return statistics.median([series[t - a] * (1 + g) ** a for a in range(1, X + 1) if t - a >= 0])
_smooth = [10.0 * 1.053 ** i for i in range(9)]
check(abs(_norm(_smooth, 8) / _smooth[8] - 1) < 1e-9,
      f"no cycle -> normalized equals actual ({_norm(_smooth,8):.4f} vs {_smooth[8]:.4f})")
for _n in (5, 6, 7, 8):
    if abs(_norm(_smooth, _n) / _smooth[_n] - 1) > 1e-9:
        check(False, f"no cycle -> zero gap independent of horizon (failed at N={_n})"); break
else:
    check(True, "no cycle -> zero gap at every horizon (N=5,6,7,8), so the horizon cannot move it")
_peak = list(_smooth); _peak[8] *= 1.35
check(_norm(_peak, 8) < _peak[8] * 0.80, f"a genuine peak normalizes DOWN ({_norm(_peak,8):.3f} vs {_peak[8]:.3f})")
_trough = list(_smooth); _trough[8] *= 0.65
check(_norm(_trough, 8) > _trough[8] * 1.20, f"a genuine trough normalizes UP ({_norm(_trough,8):.3f} vs {_trough[8]:.3f})")

print("== auto normalized line (model default: last-4 walked along the normal line, median) ==")
nl = C.normalized_eps_at_N(ENG, X=4)
ra = C.converge_auto(ENG, K=3)
check(abs(ra["norm_eps_N"] - nl) < 1e-9, f"converge_auto uses normalized_eps_at_N ({nl:.4f})")
# Direction follows the gap, whichever way the gap happens to run for this fixture. gap_ps is
# actual - normalized, so a positive gap (actual above normal) must remove value.
_gap = ra["converge_gap_ps"]; _inc = ra["converge_value_ps"]
check((_gap > 0 and _inc < 0) or (_gap < 0 and _inc > 0) or (abs(_gap) < 1e-12 and abs(_inc) < 1e-9),
      f"correction moves value in the direction the gap implies (gap {_gap:+.4f} -> {_inc:+.4f})")
check(abs(ra["corrected_intrinsic"] - (eng + _inc)) < 1e-9,
      f"corrected = engine + increment ({eng:.4f} {_inc:+.4f} = {ra['corrected_intrinsic']:.4f})")
_ovr = C.normalized_eps_at_N(ENG, X=4, g=0.0)
check(_ovr != nl, f"an explicit g overrides the derived rate ({_ovr:.4f} vs {nl:.4f})")

print("== three-period statistics (explicit / convergence / combined) ==")
# James, 2026-08-09: any figure describing abnormal earnings growth before the continuing
# period must include the convergence years, so the three blocks have to be produced together
# and `combined` has to be exactly the sum of the other two.
rep = C.period_report(ENG, ra)
blocks = {b["period"]: b for b in rep["blocks"]}
check(set(blocks) == {"explicit", "convergence", "combined"},
      f"three period blocks emitted: {sorted(blocks)}")
check(blocks["explicit"]["n_years"] == N and blocks["convergence"]["n_years"] == 3
      and blocks["combined"]["n_years"] == N + 3,
      f"period lengths explicit={blocks['explicit']['n_years']} convergence="
      f"{blocks['convergence']['n_years']} combined={blocks['combined']['n_years']} (cfg_N={N})")
_sum = blocks["explicit"]["pv_contribution_ps"] + blocks["convergence"]["pv_contribution_ps"]
check(abs(_sum - blocks["combined"]["pv_contribution_ps"]) < 1e-9,
      f"combined PV = explicit + convergence ({blocks['combined']['pv_contribution_ps']:.6f})")
# the two value identities period_report self-verifies: the explicit block must rebuild the
# engine's own intrinsic off the no-growth anchor, and the combined block the corrected one.
_ic = rep["identity_checks"]
check(_ic and _ic["explicit_identity_residual"] < 1e-6,
      f"normal value + explicit PV = engine intrinsic (resid {_ic['explicit_identity_residual']:.1e})")
check(_ic and _ic["combined_identity_residual"] < 1e-6,
      f"normal value + combined PV = corrected intrinsic (resid {_ic['combined_identity_residual']:.1e})")
# The arithmetic identity, with no directional claim attached to it: whatever the convergence
# block is worth, the reported increment must be exactly that and nothing else.
check(abs(blocks["convergence"]["pv_contribution_ps"] - ra["converge_value_ps"]) < 1e-9,
      f"convergence block PV equals the reported convergence increment "
      f"({blocks['convergence']['pv_contribution_ps']:+.6f})")

print("== convergence OFF still produces a well-formed three-period report ==")
r_off = C.converge_valuation(ENG, K=0, norm_eps_N=None)
rep0 = C.period_report(ENG, r_off)
b0 = {b["period"]: b for b in rep0["blocks"]}
check(b0["convergence"]["n_years"] == 0 and b0["convergence"]["pv_contribution_ps"] == 0.0,
      "K=0 gives an empty convergence block, not a crash")
check(abs(b0["combined"]["pv_contribution_ps"] - b0["explicit"]["pv_contribution_ps"]) < 1e-12,
      "K=0: combined equals explicit")

print(f"\n{'ALL CONVERGENCE TESTS PASSED' if fails==0 else f'{fails} FAILED'}"); sys.exit(1 if fails else 0)
