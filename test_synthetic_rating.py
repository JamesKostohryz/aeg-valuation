#!/usr/bin/env python3
"""test_synthetic_rating.py — unit tests for the zero-touch synthetic credit rating
(synthetic_rating.py), the AMBER fallback leg of the cost-of-debt ladder (issuer_bonds >
published > synthetic). Nothing here touches the sealed engine or the four-method tie;
this closes a coverage gap flagged in AEG-Coverage-Map-2026-08-08.md — the module had a
__main__ demo block but no automated pass/fail assertions.

Checks, in order of the module's own documented ladder logic:
  1. de-minimis-debt short-circuits to AAA (interest expense ~0, or debt ~0, or
     debt/assets < 5%) regardless of EBIT.
  2. missing EBIT defaults to BBB with an explicit flag (never a silent guess).
  3. negative EBIT or negative coverage floors at CCC (distress floor) even if the
     interest-coverage arithmetic alone would land higher.
  4. the interest-coverage table buckets are monotonic and each boundary lands on the
     side the table specifies (>= threshold -> the better rating), tested exactly AT
     each threshold and just below it.
  5. a synthetic AAA carries the "synthetic_AAA_review" flag (never silently trusted).

Usage: python3 test_synthetic_rating.py
"""
import sys
from synthetic_rating import synthetic_rating, _ICR_TABLE

_p = _f = 0
def check(c, m):
    global _p, _f
    if c: _p += 1; print(f"  PASS  {m}")
    else: _f += 1; print(f"  FAIL  {m}")

print("== de-minimis debt -> AAA regardless of EBIT ==")
r, m = synthetic_rating(ebit=None, interest_expense=0.0, total_debt=0.0, assets=300e9)
check(r == "AAA", f"zero interest expense + zero debt -> AAA (got {r})")
check("de_minimis_debt" in m["flags"], "de-minimis flag set")
r, m = synthetic_rating(ebit=-5e9, interest_expense=1e6, total_debt=0.5e9, assets=100e9)
check(r == "AAA", f"debt/assets<5% -> AAA even with negative EBIT (got {r})")

print("== missing EBIT -> BBB, explicitly flagged ==")
r, m = synthetic_rating(ebit=None, interest_expense=2e9, total_debt=60e9, assets=300e9)
check(r == "BBB", f"EBIT missing -> BBB default (got {r})")
check("ebit_missing_default_BBB" in m["flags"], "missing-EBIT flag set (never a silent guess)")

print("== negative EBIT / negative coverage -> CCC distress floor ==")
r, m = synthetic_rating(ebit=-2e9, interest_expense=3e9, total_debt=50e9, assets=100e9)
check(r == "CCC", f"negative EBIT -> CCC floor (got {r})")
check("negative_ebit_distress_floor" in m["flags"], "distress-floor flag set")
r, m = synthetic_rating(ebit=1e9, interest_expense=-2e9, total_debt=50e9, assets=100e9)
check(r == "CCC", f"negative interest expense (icr<0) -> CCC floor (got {r})")

print("== coverage-table boundaries are exact and monotonic ==")
check(list(_ICR_TABLE) == sorted(_ICR_TABLE, key=lambda x: -x[0]),
      "table is sorted descending by threshold (first match wins correctly)")
for thr, want in _ICR_TABLE:
    ebit, interest, debt, assets = thr * 1e9, 1e9, 500e9, 1000e9  # debt/assets=0.5, clears de-minimis
    r, m = synthetic_rating(ebit=ebit, interest_expense=interest, total_debt=debt, assets=assets)
    check(r == want, f"coverage exactly {thr:g}x -> {want} (got {r}, coverage={m['coverage']})")
    r2, m2 = synthetic_rating(ebit=ebit - 0.01e9, interest_expense=interest, total_debt=debt, assets=assets)
    check(r2 != want or want == "CCC",
          f"coverage just below {thr:g}x -> NOT {want} (got {r2})")
r, m = synthetic_rating(ebit=1.0e9, interest_expense=1.5e9, total_debt=40e9, assets=80e9)  # icr=0.667
check(r == "CCC", f"coverage below every table threshold -> CCC (got {r}, coverage={m['coverage']})")

print("== synthetic AAA is flagged for review, never silently trusted ==")
r, m = synthetic_rating(ebit=120e9, interest_expense=3e9, total_debt=120e9, assets=400e9)
check(r == "AAA", f"very high coverage -> AAA (got {r})")
check("synthetic_AAA_review" in m["flags"], "synthetic AAA carries the review flag")

print(f"\n{_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
