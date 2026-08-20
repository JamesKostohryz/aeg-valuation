#!/usr/bin/env python3
"""
tests/test_market_semidev_bridge.py — the historical risk input, and the ways it can go wrong.

Guards `idio/market_semidev_bridge.py`, which reconstructs a VIX-equivalent back to 1929 from the
market's own downside semi-deviation so that abnormal-earnings-growth valuation can be run before
options existed. Pre-registered in
AEG-Project/docs/PREREG-Semidev-ERP-Bridge-2026-08-20.md.

FOUR THINGS ARE GUARDED, and the third is the one that would be silent.

  THE STATISTIC IS IMPORTED, NOT REIMPLEMENTED. The company premium and the historical market
  bridge must be the SAME downside semi-deviation. A second implementation that drifts by a few
  per cent would put the market and the companies on different risk scales, and every historical
  premium would be wrong in a way no identity check could see.

  THE LAG IS ZERO AND THAT IS DELIBERATE. Production uses 60 trading days so a company is not
  charged for its own recent price action. The market bridge uses 0, worth 18 points of
  correlation. If somebody "harmonizes" these two by making the market use 60, the fit silently
  degrades from 0.806 to 0.622 and nothing else changes.

  IT MUST NOT ACQUIRE LOOK-AHEAD. A negative lag would let the reconstruction see returns that
  had not happened yet. It was tested and REJECTED on the evidence (0.802, worse than lag 0), so
  a future negative lag would be both wrong and unjustified.

  THE FALSIFIERS MUST STILL BE ABLE TO FIRE. One of them, F2, DID fire on the pre-registered
  out-of-sample test. A guard that has been quietly relaxed to make a result pass is worse than
  no guard, so the thresholds are pinned here.
"""
import math
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "idio"))

import market_semidev_bridge as B   # noqa: E402
import semidev as SD                # noqa: E402


# ------------------------------------------------------------------ one statistic, not two

def test_the_bridge_imports_the_production_statistic_rather_than_copying_it():
    src = open(os.path.join(ROOT, "idio", "market_semidev_bridge.py"), encoding="utf-8").read()
    assert "import semidev as SD" in src
    assert "SD._semidev_about" in src, "the bridge must call the production primitive"
    assert "def _semidev_about" not in src, (
        "the bridge has its own copy of the semi-deviation. The market and the companies would "
        "then be on two risk scales that can drift apart silently.")


def test_the_market_statistic_matches_the_company_primitive_exactly():
    """Same numbers out of both paths on the same window."""
    rdates, rets, _, _ = B.load_sp500()
    i = len(rets) - 1
    got = B.market_semidev(rets, i, lag=0)
    n1, n2 = int(round(SD.TRADING_DAYS)), int(round(2 * SD.TRADING_DAYS))
    w1, w2 = rets[i - n1:i], rets[i - n2:i]
    want = 0.5 * SD._semidev_about(w1, sum(w1) / len(w1)) * 100.0 \
         + 0.5 * SD._semidev_about(w2, sum(w2) / len(w2)) * 100.0
    assert abs(got - want) < 1e-12


# ------------------------------------------------------------------ the lag

def test_the_market_lag_is_zero_and_the_company_lag_is_not():
    assert B.MARKET_LAG == 0, (
        "the market bridge lag has been changed from 0. Production's 60-day lag exists so a "
        "COMPANY is not charged for its own recent price action; applied to the market aggregate "
        "it costs 18 points of correlation (0.806 -> 0.622).")
    assert SD.LAG_TRADING_DAYS == 60, "the COMPANY statistic must keep its 60-day lag"


def test_the_bridge_never_looks_forward():
    assert B.MARKET_LAG >= 0, (
        "a negative lag would end the window AFTER the as-of date, letting the reconstruction "
        "see returns that had not happened. It was tested and rejected on the evidence: a "
        "quarter-ahead window scores 0.802, WORSE than lag 0's 0.806.")


def test_zero_lag_really_does_beat_the_production_lag():
    """The measurement the departure rests on. If this ever reverses, the departure is wrong."""
    rdates, rets, _, _ = B.load_sp500()
    vix = B.load_vix1y()
    out = {}
    for lag in (0, 60):
        sd = dict(B.series(rdates, rets, lag=lag))
        pairs = [(sd[d], vix[d]) for d in sorted(vix) if d in sd]
        out[lag] = B.corr([p[0] for p in pairs], [p[1] for p in pairs])
    assert out[0] > out[60] + 0.10, (
        "lag 0 corr %.4f vs lag 60 corr %.4f -- the reason for the departure has evaporated"
        % (out[0], out[60]))


# ------------------------------------------------------------------ the committed inputs

def test_the_committed_history_is_present_and_whole():
    rdates, rets, adates, aclose = B.load_sp500()
    assert len(aclose) > 25000, "the S&P daily series is truncated (%d closes)" % len(aclose)
    assert adates[0] <= "1928-01-01" and adates[-1] >= "2026-01-01"
    vix = B.load_vix1y()
    assert len(vix) > 4800, "the VIX1Y calibration fixture is truncated (%d days)" % len(vix)
    assert min(vix) <= "2007-01-03", "VIX1Y must start at the true 2007-01-03 beginning"


def test_the_1970s_splice_is_not_a_smoothed_fabrication():
    """Recorded as a suspicion IN ADVANCE in the pre-registration, section 6, because a market
    semi-deviation of 12.73 at the October 1974 trough looked implausibly calm. It is not: the
    era's annualized vol is 19.0% against a 48% drawdown, and semi-deviation runs about 0.70x
    total vol in EVERY era. The suspicion was wrong and this pins the check that cleared it."""
    _, _, adates, aclose = B.load_sp500()
    import statistics as st
    def ann_vol(a, b):
        c = [aclose[k] for k, d in enumerate(adates) if a <= d <= b]
        r = [math.log(c[i] / c[i - 1]) for i in range(1, len(c))]
        zero = sum(1 for x in r if abs(x) < 1e-12) / len(r)
        return st.pstdev(r) * math.sqrt(252) * 100.0, zero
    v74, z74 = ann_vol("1973-01-01", "1974-12-31")
    v08, _ = ann_vol("2008-01-01", "2008-12-31")
    assert 15.0 < v74 < 25.0, "1973-74 annualized vol %.1f%% is not the historical ~19%%" % v74
    assert z74 < 0.05, "%.1f%% of 1973-74 days have a zero return -- the splice is interpolated" % (100 * z74)
    assert v08 > v74, "2008 must be more volatile than 1973-74 (%.1f vs %.1f)" % (v08, v74)


# ------------------------------------------------------------------ the falsifiers can still fire

def test_the_preregistered_thresholds_have_not_been_relaxed():
    """F2 FIRED on the pre-registered test. A threshold quietly widened to make it pass is worse
    than no threshold at all."""
    assert B.F1_MIN_OOS_CORR == 0.60
    assert B.F2_MAX_COND_SD_RATIO == 2.0
    assert B.F4_MAX_SPLICE_STEP == 5.0
    assert (B.F5_VIX_LO, B.F5_VIX_HI) == (5.0, 100.0)


def test_the_relationship_survives_out_of_sample_in_both_directions():
    """F1. This is the falsifier that decides whether the bridge is real at all."""
    res = B.calibrate_and_validate(log=lambda *a: None)
    for name, a, b, c, s_all, s_cond, s_calm in res["results"]:
        assert c >= B.F1_MIN_OOS_CORR, "%s: out-of-sample correlation %.4f" % (name, c)
        assert b > 0, "%s: fitted slope %.4f is not positive (F3)" % (name, b)


def test_the_reconstruction_reaches_1930_and_produces_possible_numbers():
    """F5, and the reach the whole exercise is for."""
    res = B.calibrate_and_validate(log=lambda *a: None)
    rows = B.reconstruct(res)
    assert rows[0]["date"] < "1931-01-01", "the reconstruction starts at %s" % rows[0]["date"]
    assert len(rows) > 25000
    bad = [r for r in rows if not (B.F5_VIX_LO <= r["vix_equiv"] <= B.F5_VIX_HI)]
    assert not bad, "%d reconstructed days are impossible, worst %s" % (len(bad), bad[:1])
    assert all(r["martin_erp_pct"] >= 0 for r in rows)


def test_the_splice_prefers_live_data_where_live_data_exists():
    """The bridge is a substitute, not a replacement. Where VIX1Y exists it must win."""
    res = B.calibrate_and_validate(log=lambda *a: None)
    rows = {r["date"]: r for r in B.reconstruct(res)}
    late = [r for d, r in rows.items() if d >= B.SPLICE_END and r["vix1y_live"] != ""]
    assert late, "no live-period rows found"
    r = late[-1]
    assert r["source"] == "live" and abs(r["vix_equiv"] - float(r["vix1y_live"])) < 1e-9, (
        "after the splice window the reconstruction must BE the live VIX1Y, not a blend of it")
    early = [r for d, r in rows.items() if d < B.SPLICE_START]
    assert all(r["source"] == "bridge" for r in early[-50:])


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
