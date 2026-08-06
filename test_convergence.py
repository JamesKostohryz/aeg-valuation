#!/usr/bin/env python3
"""test_convergence.py — E2 convergence self-tests. Builds the golden AAPL engine (like the
regression Stage 2) so it runs standalone in CI, then checks faithfulness + correction."""
import os, sys
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
           "judgments": {"minority_include": False, "finlease": 0.0, "oi_adj_override": None,
                         "rd_capitalize": True, "rd_life": 5.0, "dps_override": None},
           "cost_of_debt": {"single_ytw": 0.05}}
    out = os.path.join("/tmp", "_convtest_aapl.xlsx")
    AE.build_model(cfg, T, out); recalc(out); return out

ENG = os.environ.get("AAPL_ENG") or _build_aapl()
import openpyxl
V = openpyxl.load_workbook(ENG, data_only=True)["Valuation"]
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
print("== auto normalized line (model default: last-4 walked fwd at normal g, median) ==")
nl = C.normalized_eps_at_N(ENG, X=4)
check(nl > epsN, f"AAPL below-normal grower normalizes UP: norm[N]={nl:.3f} > actual[N]={epsN:.3f}")
ra = C.converge_auto(ENG, K=3)
check(abs(ra["norm_eps_N"] - nl) < 1e-9 and ra["corrected_intrinsic"] > eng,
      f"converge_auto lifts AAPL to {ra['corrected_intrinsic']:.2f} (from {eng:.2f}), verdict {ra['verdict']}")
print(f"\n{'ALL CONVERGENCE TESTS PASSED' if fails==0 else f'{fails} FAILED'}"); sys.exit(1 if fails else 0)
