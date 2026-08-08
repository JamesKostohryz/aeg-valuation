#!/usr/bin/env python3
"""test_cod_fallback.py — unit tests for the cost-of-debt priority ladder
(cod_fallback.resolve_cod): issuer_bonds > published > synthetic, plus the real_cod >=
real_rf validation gate. Closes a coverage gap flagged in AEG-Coverage-Map-2026-08-08.md
(no automated tests previously; only a __main__ demo that printed but never asserted).

`resolve_cod` is a pure function once `curve`/`bonded_cod`/`fundamentals` are supplied
directly, so this needs no network access and no engine build — a synthetic curve is
enough to exercise the full ladder and the gate logic exactly as documented in the
module's own docstring and comments.

Checks:
  1. issuer_bonds passes bonded_cod through unchanged, GREEN, source recorded.
  2. issuer_bonds below the real risk-free at any tenor is a genuine anomaly -> RED,
     spread_nonneg=False, NOT floored (a real traded price should never be silently
     overwritten).
  3. published rating resolves from the curve, GREEN.
  4. synthetic (fundamentals) resolves via synthetic_rating, AMBER.
  5. published/synthetic dipping below real_rf is basis noise -> FLOORED at real_rf
     exactly (not aborted), spread_nonneg=True after flooring.
  6. fail-loud: unknown rating, missing curve, missing fundamentals for the synthetic
     leg, and (per the module's own priority-order comment) bonded_cod short-circuits
     the ladder even when a published_rating is also supplied.

Usage: python3 test_cod_fallback.py
"""
import sys
from cod_fallback import resolve_cod, RATINGS

_p = _f = 0
def check(c, m):
    global _p, _f
    if c: _p += 1; print(f"  PASS  {m}")
    else: _f += 1; print(f"  FAIL  {m}")

TENORS = [1, 5, 10, 20, 30]
REAL_RF = [0.015, 0.017, 0.019, 0.021, 0.022]
CURVE = {r: [REAL_RF[i] + 0.005 * (k + 1) for i in range(len(TENORS))]
         for k, r in enumerate(RATINGS)}   # AAA tightest spread .. CCC widest, all > real_rf
CURVE["real_fwd"] = REAL_RF
CURVE["tenor"] = TENORS

print("== issuer_bonds: passthrough, GREEN, unchanged values ==")
bonded = [rf + 0.01 for rf in REAL_RF]
rc, p = resolve_cod(bonded_cod=bonded, bonded_rating="A", real_rf=REAL_RF, curve=CURVE)
check(rc == bonded, "bonded_cod values passed through unchanged")
check(p["cod_source"] == "issuer_bonds" and p["audit"] == "GREEN", "provenance = issuer_bonds/GREEN")
check(p["spread_nonneg"] is True, "spread_nonneg true when every tenor clears real_rf")

print("== issuer_bonds priority: bonded_cod wins even if published_rating is also given ==")
rc2, p2 = resolve_cod(bonded_cod=bonded, bonded_rating="A", published_rating="AAA",
                       real_rf=REAL_RF, curve=CURVE)
check(p2["cod_source"] == "issuer_bonds", "bonded_cod short-circuits the ladder over published_rating")

print("== issuer_bonds below real_rf: genuine anomaly, RED, NOT floored ==")
bad_bonded = list(bonded); bad_bonded[2] = REAL_RF[2] - 0.002   # tenor 10 priced below real risk-free
rc3, p3 = resolve_cod(bonded_cod=bad_bonded, bonded_rating="A", real_rf=REAL_RF, curve=CURVE)
check(p3["audit"] == "RED", f"issuer bond below real_rf -> RED (got {p3['audit']})")
check(p3.get("spread_nonneg") is False, "spread_nonneg False on a real traded-bond anomaly")
check(rc3[2] == bad_bonded[2], "a genuine issuer-bond anomaly is NOT silently floored/overwritten")
check(any("below_rf" in f for f in p3["flags"]), "anomaly flag recorded")

print("== published rating: resolves from curve, GREEN ==")
rc4, p4 = resolve_cod(published_rating="BBB", real_rf=REAL_RF, curve=CURVE)
check(rc4 == CURVE["BBB"], "published rating pulls the matching curve column")
check(p4["cod_source"] == "published" and p4["audit"] == "GREEN", "provenance = published/GREEN")

print("== synthetic leg: derives rating from fundamentals, AMBER ==")
fundamentals = dict(ebit=8e9, interest_expense=2e9, total_debt=60e9, assets=300e9)  # icr=4 -> BBB
rc5, p5 = resolve_cod(fundamentals=fundamentals, real_rf=REAL_RF, curve=CURVE)
check(p5["rating"] == "BBB", f"synthetic rating from ICR=4 -> BBB (got {p5['rating']})")
check(p5["cod_source"] == "synthetic" and p5["audit"] == "AMBER", "provenance = synthetic/AMBER")
check(rc5 == CURVE["BBB"], "synthetic leg pulls the same curve column as the published leg would")

print("== rating-curve leg dipping below real_rf: basis noise -> FLOORED exactly, not aborted ==")
curve_low = {k: (list(v) if k not in ("real_fwd", "tenor") else v) for k, v in CURVE.items()}
curve_low["AAA"] = [rf - 0.001 for rf in REAL_RF]   # AAA spread dips just under real_rf everywhere
rc6, p6 = resolve_cod(published_rating="AAA", real_rf=REAL_RF, curve=curve_low)
check(rc6 == REAL_RF, "floored real_cod equals real_rf exactly at every dipped tenor")
check(p6.get("spread_nonneg") is True, "spread_nonneg True after flooring (not an abort condition)")
check(any("floored_at_rf" in f for f in p6["flags"]), "floor flag recorded")

print("== fail-loud guards ==")
try:
    resolve_cod(published_rating="XYZ-not-a-rating", real_rf=REAL_RF, curve=CURVE)
    check(False, "unknown rating should raise ValueError")
except ValueError:
    check(True, "unknown rating raises ValueError")
try:
    resolve_cod(published_rating="AAA", real_rf=REAL_RF, curve=None)
    check(False, "missing curve should raise ValueError")
except ValueError:
    check(True, "missing curve raises ValueError")
try:
    resolve_cod(real_rf=REAL_RF, curve=CURVE)   # no bonded_cod, no published_rating, no fundamentals
    check(False, "missing fundamentals for the synthetic leg should raise ValueError")
except ValueError:
    check(True, "missing fundamentals (no bonded/published/synthetic path available) raises ValueError")

print(f"\n{_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
