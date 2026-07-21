#!/usr/bin/env python3
"""test_normalization_fixture.py — SP500 spec §5(2) golden-fixture regression.

Mode A (normalize_series, forward, X=4) must reproduce the fixture's normalized_X4
column to the PENNY, with NaN before month 48.

TOLERANCE — deliberately penny, not bit-exact (COCKPIT 20260721-0842 addendum,
reaffirmed 20260721-0925): the fixture is published at finite precision, so the
engine reproduces it to ~2e-4, not to the bit. Asserting equality would fail on
publish rounding and tell us nothing. 1e-2 is tight enough to catch any real
regression (a genuine break moves this by orders of magnitude) and loose enough to
survive the publish floor.

Fixture: v4 (ISO dates, v4 eff_coe in COE_r) — the terminal oracle for the
ERP<->SP500 loop. The v3 fixture is RETIRED and must not be reintroduced.
"""
import csv
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG = os.path.dirname(_HERE)                 # normalization/
sys.path.insert(0, _PKG)
import normalization_engine as NE             # noqa: E402

FIXTURE = os.path.join(_HERE, "normalized_reference_series.csv")
PENNY = 1e-2          # spec §5(2) "to the penny"; observed worst |delta| ~2e-4
WARMUP = 48           # normalized_X4 is NaN before month 48 (median-of-4 x 12m)

_pass = _fail = 0


def ok(cond, msg):
    global _pass, _fail
    print(("  PASS " if cond else "  FAIL ") + msg)
    if cond:
        _pass += 1
    else:
        _fail += 1


def _col(rows, name):
    out = []
    for r in rows:
        v = (r[name] or "").strip()
        out.append(float(v) if v not in ("", "nan", "NaN", "NA") else np.nan)
    return np.array(out, float)


print("== SP500 spec 5(2): golden-fixture regression (Mode A, forward, X=4) ==")
ok(os.path.exists(FIXTURE), f"fixture present ({os.path.basename(FIXTURE)})")
if not os.path.exists(FIXTURE):
    print(f"\n{_pass} passed, {_fail} failed")
    raise SystemExit(1)

with open(FIXTURE, newline="") as fh:
    rows = list(csv.DictReader(fh))

need = ["date", "E_real", "retention_b", "COE_r", "normalized_X4"]
missing = [c for c in need if c not in (rows[0].keys() if rows else [])]
ok(not missing, f"required columns present (missing: {missing or 'none'})")

E = _col(rows, "E_real")
b = _col(rows, "retention_b")
r = _col(rows, "COE_r")
ref = _col(rows, "normalized_X4")

got = NE.normalize_series(E, b, r, X=4, mode="forward")["normalized"]
ok(len(got) == len(ref), f"length matches fixture ({len(got)} rows)")

m = np.isfinite(ref) & np.isfinite(got)
worst = float(np.max(np.abs(got[m] - ref[m]))) if m.any() else np.inf
ok(m.sum() > 1500, f"comparable rows n={int(m.sum())}")
ok(worst < PENNY, f"reproduces normalized_X4 to the penny "
                  f"(worst |delta| = {worst:.3e} < {PENNY:g})")

# engine must not invent values inside the warm-up window where the fixture is NaN
ok(bool(np.all(~np.isfinite(ref[:WARMUP]))),
   f"fixture NaN before month {WARMUP}")
ok(bool(np.all(~np.isfinite(got[:WARMUP]))),
   f"engine also NaN before month {WARMUP} (no fabricated warm-up values)")

# guard the retired-v3 / date-bug regressions: dates must be ISO and unique
dates = [rw["date"] for rw in rows]
import re  # noqa: E402
ok(all(re.fullmatch(r"\d{4}-\d{2}", d) for d in dates), "dates are ISO YYYY-MM (v4)")
ok(len(dates) == len(set(dates)), "no duplicate dates (October collision fixed)")

print(f"\n{_pass} passed, {_fail} failed")
raise SystemExit(1 if _fail else 0)
