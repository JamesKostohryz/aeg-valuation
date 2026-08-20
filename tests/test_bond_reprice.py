#!/usr/bin/env python3
"""
tests/test_bond_reprice.py — the prices are re-pulled, and the arithmetic did not move.

`idio/bond_reprice.py` is what stops `idio/issuer_curves.py` becoming a monthly fossil-stamping
machine. Scheduling the fit without this would re-write `generated` every month onto the frozen
2026-08-17 bond snapshot, buy the system another 45 days of life, and report success — the exact
shape of every defect on this project's standing-suspicion list.

Two things are guarded here.

  THE PRICING ARITHMETIC MUST NOT HAVE MOVED IN THE PORT. It is joined from two working-folder
  tools, and a spread that is quietly 10bp different feeds straight into every issuer curve and
  from there into every company's Region 2 premium — with the four-method tie perfectly green,
  because a spread is an input to the discount rate and the tie cannot see the discount rate's
  provenance. So the test rebuilds 113 real bonds from their real cached price series and
  asserts EVERY FIELD of EVERY ROW against the committed file. Not a tolerance: equality.

  THE DROP PATHS MUST STILL DROP. 166 of the 1,615 named bonds do not survive the filters — a
  null yield, an unparseable maturity, a bond that has matured, and five that disagree with the
  vendor's own yield by more than 50 basis points. If a port silently let those through, the
  curves would be fitted on junk and nothing else in the system would notice. The fixture
  deliberately includes 25 bonds that must NOT appear in the output.

HERMETIC. The price series and a 2026 slice of the FRED pillars are frozen under
tests/golden/bond_reprice/. No EODHD call, no FRED call, no API units. The FRED slice is the
2026-08-17 VINTAGE on purpose: FRED publishes the Treasury curve with a lag, so re-running today
against live FRED legitimately picks a nearer curve_date for bonds quoted on 14 August. That is
a better number, not a regression — but it is not what the committed file was built from, so
pinning the vintage is what makes this test about the code.
"""
import csv
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = os.path.join(ROOT, "tests", "golden", "bond_reprice")
TOOL = os.path.join(ROOT, "idio", "bond_reprice.py")

REF_SUBSET = os.path.join(GOLD, "bond_reference_subset.csv")
EXPECTED = os.path.join(GOLD, "expected_rows.csv")
PX = os.path.join(GOLD, "px")
FRED = os.path.join(GOLD, "fred")

LIVE_REF = os.path.join(ROOT, "data", "bond_spreads", "bond_reference.csv")
LIVE_BONDS = os.path.join(ROOT, "data", "bond_spreads", "bond_spreads_live.csv")


def _rows(path):
    return list(csv.DictReader(open(path)))


def _build(tmp_path, *extra):
    out = os.path.join(str(tmp_path), "bond_spreads_live.csv")
    cmd = [sys.executable, TOOL, "--reference", REF_SUBSET, "--cache", PX,
           "--fred-cache", FRED, "--out", out] + list(extra)
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    assert p.returncode == 0, "re-pricer failed:\n%s\n%s" % (p.stdout[-3000:], p.stderr[-3000:])
    return out, p


# ------------------------------------------------------------------ the committed reference

def test_the_static_reference_is_committed_and_complete():
    """Issuer, name and coupon are facts that do not change before maturity. Committing them is
    what lets a monthly refresh pull ONLY the price, instead of carrying 6.4MB of vendor JSON."""
    ref = _rows(LIVE_REF)
    assert len(ref) == 1615, "expected the 1,615 named reachable bonds, got %d" % len(ref)
    for col in ("bond_code", "ticker", "sample", "catalog_name", "vendor_name", "coupon"):
        assert col in ref[0]
    assert sum(1 for r in ref if r["coupon"]) >= 1088, (
        "the coupon column has lost rows. Without a coupon the 50bp vendor-disagreement check "
        "cannot run and the bond is waved through unchecked.")


def test_every_bond_in_the_live_file_is_in_the_reference():
    """If the reference ever fell behind, a monthly rebuild would silently drop issuers and the
    fit would quietly lose coverage — which is a regression however good the fit is."""
    ref = {r["bond_code"] for r in _rows(LIVE_REF)}
    live = {r["bond_code"] for r in _rows(LIVE_BONDS)}
    missing = live - ref
    assert not missing, "%d priced bonds have no reference row: %s" % (
        len(missing), sorted(missing)[:6])


# ------------------------------------------------------------------ THE arithmetic assertion

def test_the_port_reproduces_every_field_of_every_row(tmp_path):
    """The one that matters. 113 real bonds, every column, exact equality."""
    out, _ = _build(tmp_path)
    got = {r["bond_code"]: r for r in _rows(out)}
    exp = {r["bond_code"]: r for r in _rows(EXPECTED)}
    assert set(got) == set(exp), (
        "different bonds survived the filters.\n  only produced: %s\n  only expected: %s"
        % (sorted(set(got) - set(exp))[:8], sorted(set(exp) - set(got))[:8]))
    bad = []
    for code in sorted(exp):
        for k in exp[code]:
            if got[code][k] != exp[code][k]:
                bad.append("%s.%s: produced %r, committed %r" % (code, k, got[code][k],
                                                                 exp[code][k]))
    assert not bad, ("the pricing arithmetic has moved in the port. Every one of these feeds an "
                     "issuer credit curve and from there a company's discount rate, and the "
                     "four-method tie cannot see any of it:\n  " + "\n  ".join(bad[:20]))


def test_the_row_order_is_reproducible(tmp_path):
    """Sorted by (ticker, tenor). A build whose row order depends on filesystem iteration order
    produces a different file from identical data, and every diff becomes unreadable."""
    a, _ = _build(tmp_path / "a")
    b, _ = _build(tmp_path / "b")
    assert open(a, "rb").read() == open(b, "rb").read()
    rows = _rows(a)
    keys = [(r["ticker"], float(r["tenor_yrs"])) for r in rows]
    assert keys == sorted(keys)


# ------------------------------------------------------------------ the drop paths still drop

def test_the_bonds_that_must_be_dropped_are_dropped(tmp_path):
    """25 fixture bonds fail a filter. They must not reach the output."""
    out, _ = _build(tmp_path)
    got = {r["bond_code"] for r in _rows(out)}
    ref = {r["bond_code"] for r in _rows(REF_SUBSET)}
    exp = {r["bond_code"] for r in _rows(EXPECTED)}
    must_drop = ref - exp
    assert len(must_drop) == 25, "the fixture no longer exercises the drop paths"
    leaked = must_drop & got
    assert not leaked, ("%d bonds that fail a pre-registered filter reached the output: %s. The "
                        "curves would be fitted on junk." % (len(leaked), sorted(leaked)))


def test_the_vendor_disagreement_check_actually_runs(tmp_path):
    """Section 8 of the pre-commitment: yield to maturity is recomputed independently from clean
    price, coupon and tenor, and a bond disagreeing with the vendor by more than 50bp is DROPPED.
    A check that never runs is not a check, so the ledger has to show it running."""
    _, p = _build(tmp_path)
    ledger = {}
    for line in p.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].isdigit():
            ledger[parts[0]] = int(parts[1])
    assert ledger.get("check_run", 0) > 100, "the ytm cross-check ran on almost nothing: %s" % ledger
    assert "check_fail" in ledger


def test_the_spread_floor_is_a_floor_not_a_default(tmp_path):
    """Spreads below 1bp are floored to 1bp. Nothing may be NEGATIVE, and the floor must not
    have swallowed the distribution."""
    out, _ = _build(tmp_path)
    sp = [float(r["spread_bp"]) for r in _rows(out)]
    assert min(sp) >= 1.0
    assert sum(1 for s in sp if s == 1.0) < len(sp) * 0.2, (
        "more than a fifth of spreads are sitting exactly on the floor — the yields or the "
        "Treasury leg are wrong, not the bonds")


# ------------------------------------------------------------------ it spends nothing by accident

def test_dry_run_spends_nothing_and_writes_nothing(tmp_path):
    """--dry-run prints the bill. James approves the spend; a tool that can quietly spend 16,150
    API units because a flag was mistyped is not acceptable."""
    out = os.path.join(str(tmp_path), "x.csv")
    p = subprocess.run([sys.executable, TOOL, "--reference", REF_SUBSET,
                        "--cache", str(tmp_path / "empty"), "--fred-cache", FRED,
                        "--out", out, "--dry-run"], capture_output=True, text=True, cwd=ROOT)
    assert p.returncode == 0, p.stderr[-2000:]
    assert "API units" in p.stdout and "nothing spent" in p.stdout
    assert not os.path.exists(out)


def test_it_refuses_to_pull_without_a_key(tmp_path, monkeypatch):
    """No key must be a loud refusal, not a silent empty pull that writes a shorter file over a
    good one."""
    env = dict(os.environ)
    env.pop("EODHD_API_KEY", None)
    p = subprocess.run([sys.executable, TOOL, "--reference", REF_SUBSET,
                        "--cache", str(tmp_path / "nocache"), "--fred-cache", FRED,
                        "--out", os.path.join(str(tmp_path), "y.csv")],
                       capture_output=True, text=True, cwd=ROOT, env=env)
    assert p.returncode != 0
    assert "EODHD_API_KEY" in p.stderr


def test_the_api_cost_is_the_measured_one_not_an_estimate():
    """10 units per bond was MEASURED on 2026-08-17 against the account's own usage counter. If
    somebody changes this constant to a guess, the number James approves stops being real."""
    src = open(TOOL, encoding="utf-8").read()
    assert "API_UNITS_PER_BOND = 10" in src
    assert "MEASURED" in src


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
