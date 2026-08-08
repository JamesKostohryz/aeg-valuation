#!/usr/bin/env python3
"""Fail-loud tests for the per-company config loader."""
import os, tempfile
import config as CFG

# resolve companies/AAPL.yaml relative to the repo root, wherever the test is run from
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AAPL_CFG = os.path.join(_ROOT, "companies", "AAPL.yaml")

_p = _f = 0
def ok(c, m):
    global _p, _f
    if c: _p += 1; print("  PASS", m)
    else: _f += 1; print("  FAIL", m)

def write(txt):
    fd, path = tempfile.mkstemp(suffix=".yaml"); os.close(fd)
    open(path, "w").write(txt); return path

def expect_error(txt, needle, m):
    global _p, _f
    p = write(txt)
    try:
        CFG.load_config(p); _f += 1; print("  FAIL", m, "(no error)")
    except CFG.ConfigError as e:
        if needle.lower() in str(e).lower(): _p += 1; print("  PASS", m)
        else: _f += 1; print("  FAIL", m, f"(wrong: {e})")
    finally:
        os.unlink(p)

print("== valid config ==")
c = CFG.load_config(AAPL_CFG)
ok(c["ticker"] == "AAPL" and c["fy_end_month"] == 9, "AAPL parses")
ok(len(c["config_hash"]) == 16, "config hash present")
ok(c["cost_of_debt"]["seed_ytw"] == 0.05, "seed_ytw defaulted")
# hash is stable and decision-only (price/rates excluded)
ok(CFG.load_config(AAPL_CFG)["config_hash"] == c["config_hash"], "hash deterministic")

# P2: cfg_N is a REQUIRED input with no default, so every fixture below that exercises
# some OTHER gate has to supply it — otherwise the horizon gate fires first and the test
# proves nothing about the gate it names. HORIZON is that minimum valid block.
HORIZON = "forecast:\n  horizon_N: 4\n"

print("== P2: explicit forecast horizon (cfg_N) ==")
ok(c["forecast_horizon_N"] == 4, "AAPL horizon parses as 4")
ok(c["horizon_reviewed"] is False, "AAPL horizon flagged not-yet-reviewed")
# 4 must remain a completely ordinary choice: no error, no warning, no special casing.
_p4 = write("company: A\nticker: A\nforecast:\n  horizon_N: 4\n  reviewed: true\n")
try:
    _c4 = CFG.load_config(_p4)
    ok(_c4["forecast_horizon_N"] == 4 and _c4["horizon_reviewed"] is True,
       "horizon 4 chosen deliberately is accepted with no flag")
finally:
    os.unlink(_p4)
for _n in (1, 8, 15, 30):
    _pn = write(f"company: A\nticker: A\nforecast:\n  horizon_N: {_n}\n")
    try:
        ok(CFG.load_config(_pn)["forecast_horizon_N"] == _n, f"horizon {_n} accepted")
    finally:
        os.unlink(_pn)
# the horizon changes the valuation, so it must change the config hash
_pa = write("company: A\nticker: A\nforecast:\n  horizon_N: 4\n")
_pb = write("company: A\nticker: A\nforecast:\n  horizon_N: 8\n")
try:
    ok(CFG.load_config(_pa)["config_hash"] != CFG.load_config(_pb)["config_hash"],
       "horizon is part of the config hash")
finally:
    os.unlink(_pa); os.unlink(_pb)
expect_error("company: A\nticker: A\n", "horizon_N", "missing horizon aborts")
expect_error("company: A\nticker: A\nforecast:\n  horizon_N: 0\n", "between 1 and 30",
             "horizon 0 aborts")
expect_error("company: A\nticker: A\nforecast:\n  horizon_N: 31\n", "between 1 and 30",
             "horizon 31 aborts")
expect_error("company: A\nticker: A\nforecast:\n  horizon_N: four\n", "horizon_N",
             "non-numeric horizon aborts")

print("== P1/P3: policy overrides ==")
_po = write("company: A\nticker: A\n" + HORIZON +
            "judgments:\n  payout_override: 0.14\n  ppe_life_override: 10.5\n")
try:
    _c = CFG.load_config(_po)
    ok(_c["judgments"]["payout_override"] == 0.14, "payout_override parses")
    ok(_c["judgments"]["ppe_life_override"] == 10.5, "ppe_life_override parses")
finally:
    os.unlink(_po)
_pn2 = write("company: A\nticker: A\n" + HORIZON)
try:
    _c = CFG.load_config(_pn2)
    ok(_c["judgments"]["payout_override"] is None and
       _c["judgments"]["ppe_life_override"] is None,
       "both overrides default to null (derive from filings)")
finally:
    os.unlink(_pn2)
expect_error("company: A\nticker: A\n" + HORIZON + "judgments:\n  payout_override: 2.5\n",
             "payout_override", "implausible payout override aborts")
expect_error("company: A\nticker: A\n" + HORIZON + "judgments:\n  ppe_life_override: 99\n",
             "ppe_life_override", "implausible plant life override aborts")

print("== fail-loud gates ==")
expect_error("ticker: X\n", "company", "missing company aborts")
expect_error("company: A\nticker: A\nfy_end_month: 13\n", "fy_end_month", "bad month aborts")
expect_error("company: A\nticker: A\n" + HORIZON + "judgments:\n  rd_capitalize: true\n  rd_life: 0\n",
             "rd_life", "rd_capitalize without life aborts")
expect_error("company: A\nticker: A\n" + HORIZON + "price:\n  source: override\n", "override", "override price w/o value aborts")
expect_error("company: A\nticker: A\n" + HORIZON + "cost_of_debt:\n  source: bananas\n", "source", "bad COD source aborts")
expect_error("company: A\nticker: A\n" + HORIZON + "cost_of_debt:\n  source: single_ytw\n", "single_ytw", "single_ytw w/o value aborts")

print(f"\n{_p} passed, {_f} failed")
raise SystemExit(1 if _f else 0)
