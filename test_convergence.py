#!/usr/bin/env python3
"""test_convergence.py — the truncation gates.

REWRITTEN 2026-08-12, on James's ruling. The convergence period no longer adjusts value; see the
header of pipeline/convergence.py and docs/AEG-CONVERGENCE-RETIRED-2026-08-12.md. What is tested
here is the contract that replaced it:

  1. the published value IS the engine value -- no increment, ever, and nothing outside the tie
  2. gate A, the terminal condition: abnormal earnings growth must be spent at the stop year
  3. gate B, the neutral level: EPS at the stop year must sit at a normalized level
  4. the normalizer itself, which now only feeds gate B and never moves a number

The old suite asserted that a peak "catches down" and a trough "catches up" in VALUE. Those
assertions described a tool that has been retired and they are gone. What they were reaching for
-- that a forecast stopped off-trend must not publish quietly -- is now asserted as a refusal.
"""
import os, sys, statistics, tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pipeline"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import convergence as C


ROOT = os.path.dirname(os.path.abspath(__file__))


def _build_aapl():
    import aeg_engine as AE
    from recalc_lo import recalc
    G = os.path.join(ROOT, "tests", "golden", "AAPL"); T = os.path.join(ROOT, "MODEL_TEMPLATE.xlsx")
    files = {"is_csv": f"{G}/REAL_IS.csv", "bs_csv": f"{G}/REAL_BS.csv", "cf_csv": f"{G}/REAL_CF.csv",
             "prices": f"{G}/REAL_prices.csv", "dividends": f"{G}/REAL_div.csv",
             "splits": f"{G}/REAL_splits.csv"}
    cfg = {"company": "Apple Inc.", "ticker": "AAPL", "price": 315.0, "files": files,
           "fy_end_month": 9, "forecast_horizon_N": 4,
           "judgments": {"minority_include": False, "finlease": 0.0, "oi_adj_override": None,
                         "rd_capitalize": True, "rd_life": 5.0, "dps_override": None},
           "cost_of_debt": {"single_ytw": 0.05}}
    out = os.path.join(tempfile.mkdtemp(prefix="convtest_"), "_convtest_aapl.xlsx")
    AE.build_model(cfg, T, out); recalc(out); return out


ENG = os.environ.get("AAPL_ENG") or _build_aapl()
import openpyxl
_WB = openpyxl.load_workbook(ENG, data_only=True)
_V = _WB["Valuation"]

_fails = []
def check(c, m):
    print(("  PASS  " if c else "  FAIL  ") + m)
    if not c:
        _fails.append(m)


# ---------------------------------------------------------------- 1. no adjustment, ever
print("== the published value is the engine value ==")
r = C.converge_auto(ENG, K=3)
N = r["N"]
check(C.CONVERGENCE_ADJUSTS_VALUE is False, "the convergence increment is retired")
check(r["converge_value_ps"] == 0.0, f"increment is exactly zero ({r['converge_value_ps']!r})")
check(r["corrected_intrinsic"] == r["eng_intrinsic"],
      f"published equals engine ({r['eng_intrinsic']:.4f})")
check(r["schedule"] == [], "no convergence schedule is produced")
for _K in (0, 1, 3, 8):
    _x = C.converge_auto(ENG, K=_K)
    check(_x["corrected_intrinsic"] == _x["eng_intrinsic"], f"K={_K} moves no value")

print("== the whole published number is inside the four-method tie ==")
_pr = C.period_report(ENG, r)
_blocks = {b["period"]: b for b in _pr["blocks"]}
check(_blocks["convergence"]["n_years"] == 0, "convergence block is empty")
check(abs(_blocks["combined"]["pv_contribution_ps"] -
          _blocks["explicit"]["pv_contribution_ps"]) < 1e-12,
      "combined PV equals explicit PV -- nothing sits outside the explicit period")
for k, v in _pr["identity_checks"].items():
    if "resid" in k:
        check(v < C.PERIOD_TIE_TOL, f"{k} = {v:.1e}")


# ---------------------------------------------------------------- 2. gate A, terminal condition
print("== gate A: abnormal earnings growth must be spent at the stop year ==")

class _Fake:
    """Minimal stand-in for the Valuation sheet: rows 23 (AEG) and 24 (PV contribution)."""
    def __init__(self, aeg, con):
        self._r = {23: [None] + list(aeg), 24: [None] + list(con)}
        self.max_column = len(aeg) + 1
    def cell(self, r, c):
        class _C:
            pass
        o = _C(); o.value = self._r.get(r, [])[c - 1] if c - 1 < len(self._r.get(r, [])) else None
        return o

def _term(aeg, con, N, value=100.0):
    return C.terminal_aeg_check(_Fake(aeg, con), N, value)

_rising = _term([1.0, 1.1, 1.2, 1.4], [1.0, 1.1, 1.2, 1.4], 3)
check(_rising["verdict"] == "REVIEW", f"a RISING stream refuses (factor {_rising['decay']:.3f})")
check(_rising["tail_frac"] is None, "a rising stream has no convergent tail to price")
check("still GROWING" in _rising["reason"], "the refusal says why")

_flat = _term([1.0, 1.0, 1.0, 1.0], [1.0, 1.0, 1.0, 1.0], 3)
check(_flat["verdict"] == "REVIEW", "a FLAT stream refuses -- it never becomes spent")

_fast = _term([8.0, 4.0, 2.0, 0.02], [8.0, 4.0, 2.0, 0.02], 3)
check(_fast["verdict"] == "PASS",
      f"a small, fast-decaying residual passes (tail {_fast['tail_frac']:.3%} of value)")
check(_fast["decay"] < 1.0, "and it is recorded as decaying")

_slow = _term([10.0, 9.5, 9.0, 8.6], [10.0, 9.5, 9.0, 8.6], 3)
check(_slow["verdict"] == "REVIEW",
      f"a SLOWLY decaying stream refuses on the tail ({_slow['tail_frac']:.0%} of value)")

# the threshold is on the VALUE discarded, not on the level of AEG: same decay, smaller company
_big = _term([8.0, 4.0, 2.0, 0.02], [8.0, 4.0, 2.0, 0.02], 3, value=0.005)
check(_big["verdict"] == "REVIEW",
      f"the SAME residual refuses against a smaller value ({_big['tail_frac']:.1%}) -- the gate is "
      "on value discarded, not on the level of AEG")

check(C.TAIL_FRAC_WARN == 0.01, "discarded-tail tolerance is one percent of value")


# ---------------------------------------------------------------- 3. gate B, neutral level
print("== gate B: EPS at the stop year must be at a normalized level ==")
_epsN = _V.cell(7, 2 + N).value
_on = C.converge_valuation(ENG, K=3, norm_eps_N=_epsN)
check(abs(_on["converge_gap_ps"]) < 1e-9, "on-trend stop -> zero gap")
_off = C.converge_valuation(ENG, K=3, norm_eps_N=_epsN * 0.60)
check(_off["verdict"] == "REVIEW", "a stop 40% above the normalized level refuses")
check("NEUTRAL LEVEL" in _off["verdict_reason"], "and names the gate that failed")
check(_off["corrected_intrinsic"] == _off["eng_intrinsic"],
      "a refused run still adjusts nothing -- it refuses instead")
_near = C.converge_valuation(ENG, K=3, norm_eps_N=_epsN * 0.95)
check("NEUTRAL LEVEL" not in _near["verdict_reason"], "a 5% gap does not trip gate B")


# ---------------------------------------------------------------- 4. the normalizer
print("== the normal line is derived from the company's own path, not assumed ==")
check(abs(C._normal_line_growth([10 * 1.07 ** t for t in range(9)], 8) - 0.07) < 1e-12,
      "a series on a 7% line -> a 7% normal line")
check(abs(C._normal_line_growth([10.0] * 9, 8)) < 1e-15, "a flat series -> a flat normal line")
check(abs(C._normal_line_growth([None] * 9, 8)) < 1e-15,
      "no usable observation -> flat, never a fabricated drift")

def _norm(series, t, X=4):
    g = C._normal_line_growth(series, t, X=X)
    return statistics.median([series[t - a] * (1 + g) ** a for a in range(1, X + 1) if t - a >= 0])

_smooth = [10 * 1.06 ** t for t in range(9)]
check(abs(_norm(_smooth, 8) - _smooth[8]) < 1e-9,
      "no cycle -> the normalized level IS the actual level, so gate B is silent")
_spike = list(_smooth); _spike[8] *= 1.35
check(_norm(_spike, 8) < _spike[8] * 0.80, "a one-year spike at the stop year normalizes DOWN")
_dip = list(_smooth); _dip[8] *= 0.65
check(_norm(_dip, 8) > _dip[8] * 1.20, "a one-year dip at the stop year normalizes UP")
_inside = list(_smooth); _inside[6] *= 1.40
check(abs(_norm(_inside, 8) - _norm(_smooth, 8)) / _norm(_smooth, 8) < 0.05,
      "a spike INSIDE the window is rejected by the median")

# By design, and on James's ruling 2026-08-12: a level a company has SUSTAINED for several years
# is the normal level. The normalizer measures departure from the recent sustained trend, and it
# is not, and must not become, a judge of the business cycle. Ruling out a cyclical truncation is
# the forecaster's job and is enforced by gate A, not here.
_sustained = [10 * 1.05 ** t for t in range(9)]
for k, w in zip(range(6, 9), (0.35, 0.70, 1.0)):
    _sustained[k] *= 1 + 0.25 * w
check(abs(_sustained[8] - _norm(_sustained, 8)) / _sustained[8] < C.GAP_FRAC_WARN,
      "a level sustained for three years IS normal -- gate B stays silent, by design")

print("== the trend rates are published as information, with no verdict attached ==")
_d = C.trend_diagnostics([10 * 1.05 ** t for t in range(11)], 10)
check(set(_d) >= {"g_short", "g_full", "spread"}, "short and whole-path rates are reported")
check(C.trend_diagnostics([10.0] * 5, 4) is None, "too little path -> None, not a fabricated read")


print()
if _fails:
    print(f"{len(_fails)} FAILED")
    for m in _fails:
        print("   - " + m)
    sys.exit(1)
print("ALL TRUNCATION-GATE TESTS PASSED")
