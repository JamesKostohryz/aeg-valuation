#!/usr/bin/env python3
"""Fail-loud tests for the per-company config loader."""
import os, tempfile
import config as CFG

# resolve companies/AAPL.yaml relative to the repo root, wherever the test is run from
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AAPL_CFG_SHIPPED = os.path.join(_ROOT, "companies", "AAPL.yaml")

# The shipped company configs carry forecast.reviewed: false, which is a HARD ABORT — an
# unreviewed horizon authorizes no valuation (James's standing rule, 2026-08-09). So the
# tests below that exercise OTHER parts of the loader run against a reviewed COPY. The
# gate itself is tested explicitly further down against the shipped file.
def _reviewed_copy(src):
    txt = open(src).read().replace("reviewed: false", "reviewed: true")
    fd, path = tempfile.mkstemp(suffix=".yaml"); os.close(fd)
    open(path, "w").write(txt); return path

AAPL_CFG = _reviewed_copy(AAPL_CFG_SHIPPED)

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
HORIZON = "forecast:\n  horizon_N: 4\n  reviewed: true\n"

print("== P2: explicit forecast horizon (cfg_N) ==")
# Deliberately NOT pinned to a specific number: cfg_N is an analyst input that changes
# whenever a horizon is reviewed, and a test that hardcodes it turns every legitimate
# judgment into a CI failure. (It did exactly that on 2026-08-09.) Assert the RULE.
ok(isinstance(c["forecast_horizon_N"], int) and 1 <= c["forecast_horizon_N"] <= 30,
   f"AAPL horizon is a valid explicit selection (cfg_N={c['forecast_horizon_N']})")
ok(c["horizon_reviewed"] is True, "a reviewed horizon loads as reviewed")

# Every SHIPPED company config must carry an authorized horizon, or it produces no
# valuation. This is the fleet-wide standing check.
import glob
_unauth = []
# NB: not _f — that is the global failure counter used by ok()/expect_error().
for _cfgpath in sorted(glob.glob(os.path.join(_ROOT, "companies", "*.yaml"))):
    try:
        CFG.load_config(_cfgpath)
    except CFG.ConfigError as _e:
        _unauth.append(f"{os.path.basename(_cfgpath)}: {str(_e).splitlines()[0][:60]}")
ok(not _unauth, f"every shipped company config has an authorized horizon"
                + (f" — UNAUTHORIZED: {_unauth}" if _unauth else ""))

# THE GATE itself. An unreviewed horizon authorizes NO valuation. This is the enforcement
# of "there is no valuation without an explicit selection of a forecast period" — never
# soften it. Tested on synthetic configs so it stays true regardless of what the shipped
# ones happen to carry.
expect_error("company: A\nticker: A\nforecast:\n  horizon_N: 8\n",
             "no authorized forecast horizon", "a horizon with no reviewed flag ABORTS")
expect_error("company: A\nticker: A\nforecast:\n  horizon_N: 8\n  reviewed: false\n",
             "no authorized forecast horizon", "reviewed: false ABORTS")
# 4 must remain a completely ordinary choice: no error, no warning, no special casing.
_p4 = write("company: A\nticker: A\nforecast:\n  horizon_N: 4\n  reviewed: true\n")
try:
    _c4 = CFG.load_config(_p4)
    ok(_c4["forecast_horizon_N"] == 4 and _c4["horizon_reviewed"] is True,
       "horizon 4 chosen deliberately is accepted with no flag")
finally:
    os.unlink(_p4)
for _n in (1, 8, 15, 30):
    _pn = write(f"company: A\nticker: A\nforecast:\n  horizon_N: {_n}\n  reviewed: true\n")
    try:
        ok(CFG.load_config(_pn)["forecast_horizon_N"] == _n, f"horizon {_n} accepted")
    finally:
        os.unlink(_pn)
# the horizon changes the valuation, so it must change the config hash
_pa = write("company: A\nticker: A\nforecast:\n  horizon_N: 4\n  reviewed: true\n")
_pb = write("company: A\nticker: A\nforecast:\n  horizon_N: 8\n  reviewed: true\n")
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

print("== convergence review flag (the escape hatch for the REVIEW refusal) ==")
# Assert the RULE, never a particular company's answer: absent means false (the safe
# direction, so a new or untouched config can never silently clear the gate), an explicit
# true parses, and the note is carried through for the record. Toggling it must not change
# the config hash, because it gates whether a number is PUBLISHED, not what the number is.
_cv0 = write("company: A\nticker: A\n" + HORIZON)
_cv1 = write("company: A\nticker: A\n" + HORIZON +
             "convergence:\n  reviewed: true\n  note: horizon stops mid-cycle; accepted\n")
try:
    _c0 = CFG.load_config(_cv0)
    _c1 = CFG.load_config(_cv1)
    ok(_c0["convergence_reviewed"] is False,
       "convergence.reviewed absent defaults to FALSE (gate stays armed)")
    ok(_c0["convergence_note"] == "", "convergence.note absent defaults to empty")
    ok(_c1["convergence_reviewed"] is True, "convergence.reviewed: true parses")
    ok(_c1["convergence_note"].startswith("horizon stops"), "convergence.note is carried through")
    ok(_c0["config_hash"] == _c1["config_hash"],
       "reviewing does NOT change the config hash (it publishes a number, it does not move one)")
finally:
    os.unlink(_cv0); os.unlink(_cv1)
_cvf = write("company: A\nticker: A\n" + HORIZON + "convergence:\n  reviewed: false\n")
try:
    ok(CFG.load_config(_cvf)["convergence_reviewed"] is False, "explicit false parses as false")
finally:
    os.unlink(_cvf)
expect_error("company: A\nticker: A\n" + HORIZON + "convergence: 3\n", "convergence",
             "a non-mapping convergence block aborts")

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
