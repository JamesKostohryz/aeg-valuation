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

# --- scale-relative gate (2026-08-09). The residual is denominated in the model's own
#     currency units, so the gate divides by the model's scale before comparing. These
#     cases are the ones an absolute threshold got wrong.

PRODUCTION = {"anchors": {"anchor_real_noa0": 194329.292645619,
                          "anchor_cse0": 73733.0, "anchor_nfo0": 57680.0}}
SEALED = {"anchors": {"anchor_real_noa0": 0.152376629615187,
                      "anchor_cse0": 0.073733, "anchor_nfo0": 0.05768}}

ok(abs(CK.tie_scale(PRODUCTION) - 194329.292645619) < 1e-9, "scale reads the largest anchor")
ok(CK.tie_scale({}) is None, "scale is None when no anchors are present")
ok(CK.tie_scale({"anchors": {"anchor_real_noa0": 0.0, "anchor_cse0": 0.0,
                             "anchor_nfo0": 0.0}}) is None, "all-zero anchors give no scale")

# AAPL as actually committed: 1.88e-09 absolute. The OLD 1e-8 absolute backstop passed
# this only by luck of size; the relative figure is a healthy 9.7e-15.
o, d = CK.tie_check({**good, **PRODUCTION, "max_identity_tie": 1.88447302207351e-09})
ok(o and d["tie_relative"] < 1e-13, f"production-scale AAPL passes (rel={d['tie_relative']:.1e})")

# HD on this branch: 1.34e-08 absolute — this is the run that FAILED the old backstop and
# blocked PR #4. Relative 2.14e-13, the worst ever observed, and still well inside 1e-11.
o, d = CK.tie_check({**good, "anchors": {"anchor_real_noa0": 62523.8},
                     "max_identity_tie": 1.34023139253259e-08})
ok(o and d["tie_relative"] < 1e-12, f"HD passes on the relative gate (rel={d['tie_relative']:.1e})")

# The sealed harness, a million times smaller, must land in the SAME relative band.
o, d = CK.tie_check({**good, **SEALED, "max_identity_tie": 6.77236045021346e-15})
ok(o and 1e-14 < d["tie_relative"] < 1e-13,
   f"sealed harness passes at the same relative precision (rel={d['tie_relative']:.1e})")

# A genuine break must still be caught at BOTH scales — this is the whole point.
o, d = CK.tie_check({**good, **PRODUCTION, "max_identity_tie": 194.329})   # 1e-3 of scale
ok(not o, "a real break at production scale is caught")
o, d = CK.tie_check({**good, **SEALED, "max_identity_tie": 1.5238e-4})     # 1e-3 of scale
ok(not o, "the SAME relative break is caught at harness scale (an absolute gate would miss it)")

# Unreadable anchors must fail closed, not pass on an unverifiable denominator.
o, d = CK.tie_check({**good, "max_identity_tie": 1.88447302207351e-09})
ok(not o and d["tie_scale_known"] is False
   and "scale unreadable" in " ".join(d["reasons"]).lower(),
   "a production-scale residual with no anchors fails closed")

# The absolute sanity rail is secondary and must not bind on legitimate runs.
o, d = CK.tie_check({**good, **PRODUCTION, "max_identity_tie": 1.88447302207351e-09})
ok("sanity rail" not in " ".join(d["reasons"]).lower(), "the absolute rail does not bind normally")

print(f"\n{_p} passed, {_f} failed")
raise SystemExit(1 if _f else 0)
