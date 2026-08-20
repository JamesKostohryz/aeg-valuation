#!/usr/bin/env python3
"""
tests/test_issuer_curves.py — the fitter is faithful, and it refuses a fossil.

`idio/issuer_curves.py` is a VERBATIM port of the working-folder tool that produced
`outputs/issuer_widen_latest.csv` on 2026-08-19. It exists in the repository because on
2026-10-03 that file crosses `idio/erp.py::ISSUER_WIDEN_MAX_AGE_DAYS`, the reader refuses,
`company_curve.build()` raises `PremiumRefused`, and EVERY valuation on the system stops.

This file guards the two ways a port like this goes wrong.

  IT COULD BE A DIFFERENT FITTER WEARING THE SAME NAME. The standing instruction was do not
  write a second fitter. A port that is 99% faithful is a second fitter: it would produce a
  plausible file, on the same schedule, under the same name, with every gate green, and every
  company's Region 2 premium would quietly change for a reason nobody chose. So the test
  reproduces the committed output BYTE FOR BYTE from committed inputs -- an md5, not a
  tolerance. There is nothing to argue about with an md5.

  IT COULD BECOME A FOSSIL WITH A FRESH TIMESTAMP. A monthly workflow that re-runs the fit on a
  frozen bond snapshot moves the `generated` date without moving the data -- and `generated` is
  the only thing the staleness reader looks at, so the refit would BUY BACK 45 more days of
  life for prices that never changed. That is this project's standing failure mode with a cron
  schedule attached. So the freshness refusal is tested for DISCRIMINATION: it must fire on an
  old snapshot and must not fire on a fresh one. A guard that always fires and a guard that
  never fires look identical from the outside.

HERMETIC. No network, no EODHD, no real-yields checkout. The second source (the five issuers
the August bond pull missed -- AAPL, GOOG, PG, T, WMT) and the Treasury leg it is stripped
against are frozen under tests/golden/issuer_widen/real_yields/, because a test whose expected
value depends on another repository's HEAD is not a regression test.
"""
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = os.path.join(ROOT, "tests", "golden", "issuer_widen")
FITTER = os.path.join(ROOT, "idio", "issuer_curves.py")

EXPECTED_WIDEN = os.path.join(GOLD, "issuer_widen_2026-08-19.csv")
EXPECTED_TIER3 = os.path.join(GOLD, "tier3_fit_2026-08-19.json")
FROZEN_UNIVERSE = os.path.join(GOLD, "idio_universe_2026-08-19.csv")
FROZEN_RY = os.path.join(GOLD, "real_yields")
# THE FROZEN INPUT. This was the live file until 2026-08-20, when the bond pull was extended
# from 174 to 372 issuers and re-priced. Freezing it is the whole point: a test whose expected
# md5 depends on the CURRENT bond file stops being a test of the code the moment the data is
# refreshed, and would have to be "re-goldened" every month -- which is indistinguishable from
# having no test. The arithmetic runs here; the live data is checked separately below.
FROZEN_BONDS = os.path.join(GOLD, "bond_spreads_2026-08-17.csv")
LIVE_BONDS = os.path.join(ROOT, "data", "bond_spreads", "bond_spreads_live.csv")
BONDS = FROZEN_BONDS


def _md5(path):
    return hashlib.md5(open(path, "rb").read()).hexdigest()


def _run(outdir, *extra, expect_ok=True):
    """Run the ported fitter as the workflow runs it, against frozen inputs."""
    cmd = [sys.executable, FITTER, "--outdir", str(outdir), "--bonds", FROZEN_BONDS,
           "--universe", FROZEN_UNIVERSE, "--real-yields", FROZEN_RY] + list(extra)
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    if expect_ok:
        assert p.returncode == 0, "fitter failed:\n%s\n%s" % (p.stdout[-3000:], p.stderr[-3000:])
    return p


# ------------------------------------------------------------------ the committed inputs exist

def test_the_frozen_fixture_is_the_2026_08_17_pull():
    """What the arithmetic tests below are pinned to. It must never change."""
    rows = list(csv.DictReader(open(FROZEN_BONDS)))
    assert len(rows) == 1449 and len({r["ticker"] for r in rows}) == 174


def test_the_live_bond_snapshot_is_present_and_whole():
    """The input the fit is regenerated FROM. Before this landed it lived only in a working
    folder on one Windows machine, which is not a backup and not a build input.

    Deliberately NOT pinned to a bond count: the pull grows when coverage is extended, and a
    test that has to be edited every time the data improves is a test people learn to edit
    rather than read. What is pinned is that it exists, is not truncated, and carries every
    column the fit reads."""
    assert os.path.exists(LIVE_BONDS), (
        "data/bond_spreads/bond_spreads_live.csv is missing. The fit cannot be regenerated and "
        "the system goes dark when issuer_widen_latest.csv ages out.")
    rows = list(csv.DictReader(open(LIVE_BONDS)))
    assert len(rows) >= 1449, (
        "the live bond file has SHRUNK below the 2026-08-17 pull (%d bonds). Coverage going "
        "backwards is a regression however good the fit is." % len(rows))
    assert len({r["ticker"] for r in rows}) >= 174
    for col in ("ticker", "tenor_yrs", "spread_bp", "ytm_check_gap_bp", "quote_date", "bond_code"):
        assert col in rows[0], "the fit reads %s and it is not in the committed file" % col


def test_the_second_source_is_frozen_not_borrowed_from_another_repository():
    """AAPL, GOOG, PG, T and WMT enter the fit from real-yields, not from the bond pull. If the
    test read them live, this test's expected md5 would change whenever THAT repository ran."""
    for t in ("AAPL", "GOOG", "PG", "T", "WMT"):
        assert os.path.exists(os.path.join(FROZEN_RY, "outputs", "bonds_used_%s.csv" % t))
    assert os.path.exists(os.path.join(FROZEN_RY, "outputs", "market_credit_latest_annual.csv"))


# ------------------------------------------------------------------ THE reproduction assertion

def test_the_port_reproduces_the_committed_widen_file_byte_for_byte(tmp_path):
    """The one that matters. Not 'close to' -- identical.

    If this fails, the PORT is wrong, not the committed file. Do not regenerate the golden.
    """
    _run(tmp_path)
    got = os.path.join(str(tmp_path), "issuer_widen_latest.csv")
    assert _md5(got) == _md5(EXPECTED_WIDEN), (
        "the ported fitter no longer reproduces the file in production.\n"
        "  produced %s\n  expected %s\n"
        "This means idio/issuer_curves.py has drifted from the tool that made the live curves, "
        "so every company's Region 2 premium would change on the next refresh for a reason "
        "nobody chose." % (_md5(got), _md5(EXPECTED_WIDEN)))


def test_the_published_curves_are_reproducible_from_the_live_committed_inputs(tmp_path):
    """Different question from the one above, and both matter. That one asks whether the CODE
    still computes what it used to. This one asks whether the file every valuation actually
    reads was produced by that code from the data in the repository -- so a hand-edited or
    orphaned outputs/issuer_widen_latest.csv fires here.

    The second source lives in another repository and moves on its own, so the tier and widening
    of the handful of names that come from it can drift. Everything else must match exactly.
    """
    out = str(tmp_path)
    cmd = [sys.executable, FITTER, "--outdir", out, "--bonds", LIVE_BONDS,
           "--universe", os.path.join(ROOT, "outputs", "idio_universe_latest.csv"),
           "--real-yields", FROZEN_RY]
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    assert p.returncode == 0, p.stdout[-2000:] + p.stderr[-2000:]
    got = {r["ticker"]: r for r in csv.DictReader(open(os.path.join(out, "issuer_widen_latest.csv")))}
    pub = {r["ticker"]: r for r in
           csv.DictReader(open(os.path.join(ROOT, "outputs", "issuer_widen_latest.csv")))}
    assert set(got) == set(pub), "the published file covers a different set of names"
    bad = [t for t in pub if abs(float(got[t]["widen_30"]) - float(pub[t]["widen_30"])) > 1e-9]
    assert len(bad) <= 6, (
        "%d published names do not reproduce from the committed bond file: %s. Either the "
        "published curves were not produced from this data, or the fitter has drifted."
        % (len(bad), sorted(bad)[:8]))


def test_the_fit_statistics_reproduce_exactly(tmp_path):
    """tier3_fit.json carries the adoption decisions AND the `generated` date the staleness
    reader ages against. Everything except that date must reproduce."""
    _run(tmp_path)
    got = json.load(open(os.path.join(str(tmp_path), "tier3_fit.json")))
    exp = json.load(open(EXPECTED_TIER3))
    assert "generated" in got, "tier3_fit.json must carry `generated` -- idio/erp.py ages on it"
    got.pop("generated"), exp.pop("generated")
    assert got == exp


def test_the_preregistered_falsifiers_still_read_as_they_did(tmp_path):
    """The two pre-registered adoption rules FAILED on 2026-08-19 and the fallbacks that were
    used instead are in production. Pinning them means a port that silently ADOPTED a rule --
    changing every tier-2/3/4 name's slope -- cannot pass."""
    _run(tmp_path)
    j = json.load(open(os.path.join(str(tmp_path), "tier3_fit.json")))
    assert j["adopted"] is False, "the tier-3 spread-conditioned slope was NOT adopted"
    assert j["level_adopted"] is False, "the semidev level imputation was NOT adopted"
    assert j["mean_slope_fallback"] == pytest.approx(0.1997216104023884, abs=0.0)
    assert j["n_tier1"] == 81 and j["tier_counts"]["2"] == 71


# ------------------------------------------------------------------ the post-hoc gates, labelled

def test_the_posthoc_quality_gates_are_still_labelled_posthoc():
    """T1_MIN_TSTAT and T1_MAX_SHORTEST_YRS were added AFTER the first run and are not part of
    the pre-registration. A port that quietly folded them into the plan would erase the
    distinction between what was fixed in advance and what was chosen after seeing the answer."""
    src = open(FITTER, encoding="utf-8").read()
    assert "T1_MIN_TSTAT = 2.0" in src
    assert "T1_MAX_SHORTEST_YRS = 3.0" in src
    assert "ADDED AFTER THE FIRST RUN" in src
    assert "NOT PRE-REGISTERED" in src


def test_no_quality_gates_still_reproduces_the_ungated_run(tmp_path):
    """`--no-quality-gates` is what makes the cost of the two post-hoc gates measurable. It has
    to keep working, and it has to CHANGE something -- a switch that does nothing is not a
    switch."""
    gated, ungated = tmp_path / "g", tmp_path / "u"
    _run(gated)
    _run(ungated, "--no-quality-gates")
    a = json.load(open(os.path.join(str(gated), "tier3_fit.json")))
    b = json.load(open(os.path.join(str(ungated), "tier3_fit.json")))
    assert b["n_tier1"] > a["n_tier1"], (
        "--no-quality-gates promoted nobody. The 13 issuers the gates demote (JPMorgan, "
        "Microsoft, Procter & Gamble among them) should return to tier 1 without them.")
    assert b["n_tier1"] == 94 and a["n_tier1"] == 81
    assert _md5(os.path.join(str(gated), "issuer_widen_latest.csv")) != \
           _md5(os.path.join(str(ungated), "issuer_widen_latest.csv"))


def test_the_gates_demote_jpmorgan_and_microsoft_for_the_stated_reasons(tmp_path):
    """The two names the gates were written for. JPMorgan's eight bonds fitted a downward slope
    with R-squared 0.13 and handed it the lowest cost of equity of any name in the table;
    Microsoft's nearest bond is 8.5 years out so its one-year spread is extrapolated, not
    observed. If a refresh ever silently promotes them, that is the leapfrog James asked to be
    checked for and it should fail here first."""
    _run(tmp_path)
    fit = {r["ticker"]: r for r in
           csv.DictReader(open(os.path.join(str(tmp_path), "issuer_curve_fit.csv")))}
    assert int(fit["JPM"]["tier"]) == 2, "JPMorgan must not be tier 1: its slope t-stat is -0.94"
    assert abs(float(fit["JPM"]["t_b"])) < 2.0
    # ON THE FROZEN 2026-08-17 FIXTURE Microsoft is demoted for the OTHER gate -- its nearest
    # bond is 8.5 years out, so its one-year spread is extrapolated, not observed, and the
    # extrapolation returns MINUS 39 basis points. On the LIVE data it is still tier 2 but for a
    # different reason: the 2026-08-20 pull added the Activision Blizzard bonds Microsoft
    # inherited in 2023, which put an observation at 0.82 years -- and that bond is a $45m
    # unrated stub at 162bp against Microsoft's own 22bp ten-year paper, so the equal-weighted
    # fit inverts. Both demotions are correct; neither is the right answer, and the fix is to
    # weight the fit by amount outstanding.
    assert int(fit["MSFT"]["tier"]) == 2, "Microsoft must not be tier 1 on this fixture"
    assert float(fit["MSFT"]["shortest"]) > 3.0, "the frozen fixture has no Microsoft front bond"


# ------------------------------------------------------------------ the fossil guard

def test_the_freshness_guard_refuses_a_stale_bond_snapshot(tmp_path):
    """FIRES. The committed snapshot's newest quote is 2026-08-14. Run with a one-day limit and
    the fitter must refuse rather than re-stamp it."""
    p = _run(tmp_path, "--max-bond-age-days", "1", expect_ok=False)
    assert p.returncode != 0, (
        "the fitter re-ran on a bond snapshot older than the limit and would have written a "
        "fresh `generated` date onto frozen prices -- buying 45 more days of life for data "
        "that never moved. That is the fossil this guard exists to stop.")
    assert "IssuerCurveInputStale" in p.stderr or "days old" in p.stderr
    assert not os.path.exists(os.path.join(str(tmp_path), "issuer_widen_latest.csv")), \
        "it refused and wrote the file anyway"


def test_the_freshness_guard_does_not_fire_on_a_fresh_snapshot(tmp_path):
    """DOES NOT FIRE. Same snapshot, a limit wide enough to cover it. A guard that always fires
    stops being read."""
    p = _run(tmp_path, "--max-bond-age-days", "100000")
    assert "fresh enough to refit" in p.stdout
    assert _md5(os.path.join(str(tmp_path), "issuer_widen_latest.csv")) == _md5(EXPECTED_WIDEN)


def test_the_age_is_taken_from_the_quotes_not_the_file_mtime(tmp_path):
    """A checkout, a copy or a re-commit resets a file's mtime while the prices inside stay
    frozen. That is exactly how a fossil acquires a fresh timestamp, so the age must come from
    the newest quote_date INSIDE the file."""
    import time
    copy = tmp_path / "bonds.csv"
    shutil.copy(BONDS, str(copy))
    os.utime(str(copy), (time.time(), time.time()))      # mtime = now; contents unchanged
    p = _run(tmp_path, "--bonds", str(copy), "--max-bond-age-days", "1", expect_ok=False)
    assert p.returncode != 0, (
        "touching the file bought it a clean bill of health. The guard is reading the mtime.")


# ------------------------------------------------------------------ the reader can read it

def test_the_output_is_the_file_the_reader_looks_for(tmp_path):
    """idio/erp.py::load_issuer_widen searches outputs/ for `issuer_widen.csv` FIRST and
    `issuer_widen_latest.csv` second. The fitter must write the name in production, and must
    not create a second file that would shadow it."""
    _run(tmp_path)
    assert os.path.exists(os.path.join(str(tmp_path), "issuer_widen_latest.csv"))
    assert not os.path.exists(os.path.join(str(tmp_path), "issuer_widen.csv")), (
        "the fitter wrote issuer_widen.csv as well. idio/erp.py prefers that name, so the two "
        "files would diverge and the reader would silently take the wrong one.")


def test_erp_can_load_what_the_fitter_wrote(tmp_path):
    """End of the wire. The file the fitter produces has to parse through the production reader
    at the production grid, for every name."""
    sys.path.insert(0, os.path.join(ROOT, "idio"))
    import erp as IE  # noqa: E402
    _run(tmp_path)
    shutil.copy(EXPECTED_TIER3, os.path.join(str(tmp_path), "tier3_fit.json"))
    widen, meta = IE.load_issuer_widen(root=str(tmp_path), asof="2026-08-20", log=None)
    assert widen is not None, "the reader refused the file the fitter just wrote: %s" % (meta,)
    assert len(widen) == 502
    assert meta["tier_counts"][1] == 81 and meta["tier_counts"][2] == 71
    for t in ("AAPL", "KO", "PEP", "JPM"):
        assert len(widen[t]) == 30
    assert widen["AAPL"][1] == 0.0                      # widen(1) = b*ln(1) = 0 by construction
    assert widen["AAPL"][30] > widen["AAPL"][10] > 0.0  # and it widens with tenor


def test_the_reader_still_refuses_the_file_once_it_ages_out(tmp_path):
    """The outage this whole objective is about. Proven, not assumed: at 46 days the reader
    returns None and every valuation stops. That is why the workflow exists."""
    sys.path.insert(0, os.path.join(ROOT, "idio"))
    import erp as IE  # noqa: E402
    _run(tmp_path)
    shutil.copy(EXPECTED_TIER3, os.path.join(str(tmp_path), "tier3_fit.json"))
    widen, reason = IE.load_issuer_widen(root=str(tmp_path), asof="2026-10-04", log=None)
    assert widen is None, "the 45-day staleness limit did not fire on a 46-day-old file"
    assert "generated" in str(reason)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
