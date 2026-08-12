#!/usr/bin/env python3
"""test_erp_override_validation.py -- Hole A (AEG-D1-MECHANISM-FOUND-2026-08-12).

Before this, 'erp_override' and 'bonded' were read directly off the raw payload
dict in pipeline/run_company.py, bypassing apply_payload.validate_payload()'s
allowlist entirely -- no bounds check, no schema, and the whole read was wrapped
in a blanket `except Exception: pass`, so even a malformed value was silently
dropped rather than rejected. That is the mechanism behind the 2026-08-10
PepsiCo run, which discounted the company on a flat 154.69bp real ERP at all
thirty tenors instead of its own published curve (see
docs/AEG-D1-MECHANISM-FOUND-2026-08-12.md in the AEG-Project working folder).

This test locks in apply_payload.validate_overrides(): erp_override must be a
numeric, in-bounds, real decimal fraction, and must carry a non-empty
erp_override_reason. Absent either field, the run aborts instead of silently
proceeding on default behaviour.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
for _p in (_ROOT, os.path.join(_ROOT, "pipeline")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import apply_payload as AP   # noqa: E402

_p = _f = 0


def ok(cond, msg):
    global _p, _f
    if cond:
        _p += 1; print("  PASS", msg)
    else:
        _f += 1; print("  FAIL", msg)


def expect_ok(payload, msg):
    try:
        AP.validate_overrides(payload)
        ok(True, msg)
    except AP.PayloadError as e:
        ok(False, f"{msg} (unexpectedly rejected: {e})")


def expect_reject(payload, needle, msg):
    try:
        AP.validate_overrides(payload)
        ok(False, f"{msg} (was accepted, should have been rejected)")
    except AP.PayloadError as e:
        ok(needle.lower() in str(e).lower(), f"{msg} (error: {e})")


print("== erp_override / bonded validation (Hole A) ==")
expect_ok({}, "empty payload accepted (no override fields present)")
expect_ok({"bonded": True}, "valid bonded=True accepted")
expect_ok({"bonded": False}, "valid bonded=False accepted")
expect_ok({"erp_override": 0.0155, "erp_override_reason": "CAPM bull case, beta 0.55"},
          "valid in-bounds, labelled erp_override accepted")

print("== the exact shape of the 2026-08-10 PepsiCo defect ==")
expect_reject({"erp_override": 0.0155}, "reason",
              "erp_override with NO reason is rejected")
expect_reject({"erp_override": 0.0155, "erp_override_reason": "   "}, "reason",
              "erp_override with a blank reason is rejected")
expect_reject({"erp_override": 1.5469, "erp_override_reason": "x"}, "out of range",
              "erp_override=1.5469 (154.69% -- a raw percent typed where a decimal "
              "was expected, exactly the PEP-shaped bug) is rejected")

print("== type/shape guards ==")
expect_reject({"erp_override": "1.55%", "erp_override_reason": "x"}, "numeric",
              "non-numeric erp_override is rejected")
expect_reject({"erp_override": True, "erp_override_reason": "x"}, "numeric",
              "a bare boolean erp_override is rejected (bool is a Python int)")
expect_reject({"bonded": "yes"}, "true/false",
              "non-boolean bonded is rejected")

print(f"\n{_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
