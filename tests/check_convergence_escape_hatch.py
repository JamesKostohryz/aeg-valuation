#!/usr/bin/env python3
"""test_convergence_hatch_yaml.py — does `convergence.reviewed: true` in a REAL
companies/<T>.yaml actually clear the truncation gate, end to end?

WHY THIS EXISTS. test_run_scenarios.py already proves that a cfg DICT carrying
convergence_reviewed=True clears Gate A -- but it hand-builds that dict (GATE_CFG), so it
never exercises the part of the path anyone would actually doubt: yaml file on disk ->
pipeline/config.py load_config() -> normalized key name -> run_scenarios' cfg.get().
On 2026-08-20 a fleet run printed

    Escape hatches as this run read them:
    {'convergence_reviewed': False, 'funding_reviewed': False, 'terminal_reviewed': True}

and the question raised was whether the documented escape hatch is inert -- i.e. whether the
error message's own suggested remedy is a lie, for every future company, not just for the one
in front of us. (It was not inert: that particular line came from a company whose yaml has no
`convergence:` block at all. See outputs/KO_REFUSED.csv.) This test settles the general
question on demand instead of by inspection.

THE DESIGN IS AN A/B ON ONE LINE. The same golden AAPL engine, the same single scenario, the
same everything -- two company yaml files written to disk that differ ONLY by the two lines

    convergence:
      reviewed: true

Both carry funding.reviewed and terminal.payout_ratio/terminal.reviewed, so the funding and
terminal-payout gates are cleared in BOTH arms and the truncation gate is the only variable.
Arm 1 must refuse on truncation; arm 2 must value and write the CSV. Nothing here changes a
valuation number: the review flags are excluded from config_hash and gate whether a number
publishes, not what it is.

Run:  AAPL_ENG_WORK=/tmp/anch2 python3 test_convergence_hatch_yaml.py
"""
import csv
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "pipeline")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import aeg_engine as AE                                      # noqa: E402
import config as CFG                                         # noqa: E402
import run_scenarios as RS                                   # noqa: E402
from recalc_lo import recalc                                 # noqa: E402

GOLDEN = os.path.join(_ROOT, "tests", "golden", "AAPL")
TEMPLATE = os.path.join(_ROOT, "MODEL_TEMPLATE.xlsx")
WORK = os.environ.get("AAPL_ENG_WORK") or "/tmp/_hatch_yaml_work"
OUT = os.path.join(WORK, "out_hatch")
os.makedirs(OUT, exist_ok=True)

_p = _f = 0


def ok(cond, msg):
    global _p, _f
    if cond:
        _p += 1
        print("  PASS", msg)
    else:
        _f += 1
        print("  FAIL", msg)


# The company config a forecaster would actually commit, minus the one block under test.
# horizon_N/reviewed are mandatory (config.py's forecast gate); funding + terminal are set so
# those two gates are cleared in BOTH arms.
_YAML_COMMON = """\
company: "Hatch Fixture Co"
ticker: AAPL
fy_end_month: 9

forecast:
  horizon_N: 4
  reviewed: true

funding:
  reviewed: true
  note: "test fixture, not a real call"

terminal:
  payout_ratio: 0.5
  reviewed: true
  note: "test fixture, not a real call"

judgments:
  minority_include: false
  finlease: 0.0
  rd_capitalize: true
  rd_life: 5.0

cost_of_debt:
  source: single_ytw
  single_ytw: 0.05
"""

_YAML_HATCH = """
convergence:
  reviewed: true
  note: "the analyst asserts in writing that this truncation is acceptable"
"""


def _write(name, text):
    path = os.path.join(WORK, name)
    with open(path, "w") as fh:
        fh.write(text)
    return path


print("== the two company yamls differ by exactly the convergence block ==")
CFG_NO_HATCH = _write("hatch_off.yaml", _YAML_COMMON)
CFG_HATCH = _write("hatch_on.yaml", _YAML_COMMON + _YAML_HATCH)
cfg_off = CFG.load_config(CFG_NO_HATCH)
cfg_on = CFG.load_config(CFG_HATCH)
ok(cfg_off["convergence_reviewed"] is False,
   "no convergence block -> convergence_reviewed False (absent means false, the safe side)")
ok(cfg_on["convergence_reviewed"] is True,
   "convergence.reviewed: true in a file on disk -> convergence_reviewed True out of load_config")
ok(cfg_off["funding_reviewed"] is True and cfg_on["funding_reviewed"] is True,
   "funding.reviewed is true in BOTH arms, so the funding gate is not the variable")
ok(cfg_off["terminal_reviewed"] is True and cfg_on["terminal_reviewed"] is True
   and cfg_off["terminal_payout_ratio"] == 0.5,
   "terminal payout policy is set in BOTH arms, so the terminal gate is not the variable")
ok(cfg_off["config_hash"] == cfg_on["config_hash"],
   "the two configs hash identically -- the flag gates publication, it does not move a number")

print("== build the base engine (golden AAPL, the standard harness fixture) ==")
BUILD = {"company": "Hatch Fixture Co", "ticker": "AAPL", "price": 315.0, "fy_end_month": 9,
         "forecast_horizon_N": 4,
         "files": {"is_csv": f"{GOLDEN}/REAL_IS.csv", "bs_csv": f"{GOLDEN}/REAL_BS.csv",
                   "cf_csv": f"{GOLDEN}/REAL_CF.csv", "prices": f"{GOLDEN}/REAL_prices.csv",
                   "dividends": f"{GOLDEN}/REAL_div.csv", "splits": f"{GOLDEN}/REAL_splits.csv"},
         "judgments": {"minority_include": False, "finlease": 0.0, "oi_adj_override": None,
                       "rd_capitalize": True, "rd_life": 5.0, "dps_override": None},
         "cost_of_debt": {"single_ytw": 0.05}}
BASE = os.path.join(WORK, "hatch_base.xlsx")
AE.build_model(BUILD, TEMPLATE, BASE)
recalc(BASE)
ok(os.path.exists(BASE), "base engine built and recalculated")

# One scenario, N=4: this fixture's forecast stops while abnormal earnings growth is still
# running, so Gate A (terminal condition) trips. That is the whole point -- we need a run that
# the truncation gate REFUSES so there is something for the hatch to clear.
SCEN = [{"name": "bear", "probability": 1.0, "mode": "Enterprise", "N": 4,
         "drivers": {"tax_rate": [0.30] * 4}}]

print("== arm 1: hatch ABSENT -> the truncation gate must refuse ==")
_csv_path = os.path.join(OUT, "AAPL_scenarios.csv")
if os.path.exists(_csv_path):
    os.remove(_csv_path)
try:
    RS.run_scenarios(BASE, SCEN, ticker="AAPL", price=315.0, out_dir=OUT, recalc=recalc,
                     work_dir=WORK, run_timestamp="2026-08-20T00:00:00Z", cfg=cfg_off)
    ok(False, "a scenario tripping Gate A with no sign-off aborts the run")
    _msg_off = ""
except RS.ScenariosError as e:
    _msg_off = str(e)
    ok("truncation review required" in _msg_off.lower(),
       "the run refuses on the truncation gate (the gate really does fire on this fixture)")
    ok("'convergence_reviewed': False" in _msg_off,
       "the refusal reports the hatch it read as False, from a yaml that genuinely omits it")
    ok("unfunded distribution" not in _msg_off.lower()
       and "terminal distribution policy" not in _msg_off.lower()
       and "terminal payout review" not in _msg_off.lower(),
       "the funding and terminal gates are already cleared, so truncation is the only refusal")
ok(not os.path.exists(_csv_path), "fail-closed: no scenarios CSV was written")

print("== arm 2: SAME run, hatch PRESENT -> the gate must be cleared ==")
rep = RS.run_scenarios(BASE, SCEN, ticker="AAPL", price=315.0, out_dir=OUT, recalc=recalc,
                       work_dir=WORK, run_timestamp="2026-08-20T00:00:00Z", cfg=cfg_on)
ok(rep["rows"] == 1 and rep["scenarios"] == ["bear"],
   "the identical scenario now values -- convergence.reviewed: true CLEARED the truncation gate")
ok(os.path.exists(_csv_path), "the scenarios CSV was written")
with open(_csv_path, newline="") as fh:
    ROWS = list(csv.DictReader(fh))
_num = {r["scenario"]: r["intrinsic_value_per_share_real"] for r in ROWS}
ok("bear" in _num and float(_num["bear"]) > 0,
   f"the cleared scenario carries a real intrinsic value ({_num.get('bear')})")
_ties = [float(r["tie_residual"]) for r in ROWS if r.get("tie_residual")]
ok(len(_ties) == 1 and max(_ties) < 1e-9,
   f"the four-method tie still holds at machine precision ({_ties}) -- the hatch cleared a "
   f"publication gate, it did not weaken the arithmetic")

print(f"\n{_p} passed, {_f} failed")
raise SystemExit(1 if _f else 0)
