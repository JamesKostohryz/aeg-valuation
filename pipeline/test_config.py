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

print("== fail-loud gates ==")
expect_error("ticker: X\n", "company", "missing company aborts")
expect_error("company: A\nticker: A\nfy_end_month: 13\n", "fy_end_month", "bad month aborts")
expect_error("company: A\nticker: A\njudgments:\n  rd_capitalize: true\n  rd_life: 0\n",
             "rd_life", "rd_capitalize without life aborts")
expect_error("company: A\nticker: A\nprice:\n  source: override\n", "override", "override price w/o value aborts")
expect_error("company: A\nticker: A\ncost_of_debt:\n  source: bananas\n", "source", "bad COD source aborts")
expect_error("company: A\nticker: A\ncost_of_debt:\n  source: single_ytw\n", "single_ytw", "single_ytw w/o value aborts")

print(f"\n{_p} passed, {_f} failed")
raise SystemExit(1 if _f else 0)
