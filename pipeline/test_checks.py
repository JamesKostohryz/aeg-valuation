#!/usr/bin/env python3
"""Unit tests for the standing tie check (pure function, no recalc)."""
import checks as CK

_p = _f = 0
def ok(c, m):
    global _p, _f
    if c: _p += 1; print("  PASS", m)
    else: _f += 1; print("  FAIL", m)

good = {"audit_status": "PASS — all identities tie", "max_identity_tie": 1.5e-15, "mode_tie": 0}
o, d = CK.tie_check(good)
ok(o and d["tie_check"] == "PASS", "clean results pass")

o, d = CK.tie_check({**good, "audit_status": "FAIL — investigate"})
ok(not o and "audit" in " ".join(d["reasons"]).lower(), "audit FAIL trips check")

o, d = CK.tie_check({**good, "max_identity_tie": 6.0e-3})
ok(not o and "residual" in " ".join(d["reasons"]).lower(), "broken tie residual trips check")

o, d = CK.tie_check({**good, "mode_tie": 0.5})
ok(not o and "disagree" in " ".join(d["reasons"]).lower(), "mode disagreement trips check")

o, d = CK.tie_check({**good, "mode_tie": None})
ok(o, "single-mode (mode_tie None) still passes")

o, d = CK.tie_check({**good, "max_identity_tie": None})
ok(not o, "missing tie value fails safe")

print(f"\n{_p} passed, {_f} failed")
raise SystemExit(1 if _f else 0)
