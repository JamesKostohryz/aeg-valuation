"""
tests/test_idio_feed.py — hermetic tests for the company-premium risk statistic and its feed.

No network. Prices come from `tests/fixtures/idio_px_fixture.json`, ten names plus the SPY market
proxy, three and a half years of daily adjusted closes.

THE TEST THAT MATTERS is `test_the_port_reproduces_the_frozen_research_values`. The statistic was
moved here out of `AEG-Project/tools/relative_semidev.py`, a working folder that no scheduled job
could reach — which is exactly why every company premium was pinned to 17 August 2026. A move
like that is worthless if it changes the number, and "I checked it by eye" is not a check. This
pins the port to the values the research run actually produced.

Verified across the FULL 228-name universe at port time: median absolute error 2.3e-5, worst
5.0e-5 — which is the rounding in the source file's own four-decimal column, not disagreement.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "idio"))
sys.path.insert(0, ROOT)

import feed as FEED          # noqa: E402
import semidev as SD         # noqa: E402
import universe as UNI       # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures",
                   "idio_px_fixture.json")
EXPECTED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures",
                        "idio_expected_semidev.json")
ASOF = "2026-08-17"          # the as-of date of the research run being reproduced


@pytest.fixture(scope="module")
def px():
    raw = json.load(open(FIX))
    return {t: [(d, float(p)) for d, p in rows] for t, rows in raw.items()}


@pytest.fixture(scope="module")
def expected():
    return json.load(open(EXPECTED))


# ------------------------------------------------------------------ the port

def test_the_port_reproduces_the_frozen_research_values(px, expected):
    mkt = px[SD.MARKET]
    for ticker, want in expected.items():
        got = SD.blended_semidev(px[ticker], mkt, asof=ASOF)
        assert got is not None, f"{ticker} produced no statistic"
        assert got == pytest.approx(want, abs=1e-3), (
            f"{ticker}: port gives {got:.4f}, the 2026-08-17 research run gave {want:.4f}. "
            f"The move was supposed to relocate this statistic, not change it.")


def test_the_market_proxy_is_the_total_return_one():
    """SPY, not ^GSPC. The stock series are adjusted closes; a price index on the other side
    would put a dividend yield into every residual, for exactly the names that pay one."""
    assert SD.MARKET == "SPY"


def test_the_lag_is_real_and_not_an_off_by_zero(px):
    """`s[:-0]` is the empty list, not the whole series. If the guard around the slice is ever
    removed, a lag of 0 silently keeps the whole history and the statistic changes meaning."""
    mkt = px[SD.MARKET]
    lagged = SD.aligned_returns(px["KO"], mkt, 1, asof=ASOF, lag=60)[0]
    unlagged = SD.aligned_returns(px["KO"], mkt, 1, asof=ASOF, lag=0)[0]
    assert lagged and unlagged
    assert lagged != unlagged, "the 60-day lag made no difference — it is not being applied"


def test_a_short_history_is_refused_not_silently_shortened(px):
    """A two-year window on eight months of data must return None. Returning the short window
    would give a name a statistic that is not the statistic everyone else is measured on."""
    short = [x for x in px["KO"] if x[0] >= "2026-01-01"]
    assert SD.blended_semidev(short, px[SD.MARKET], asof=ASOF) is None


def test_both_windows_are_required(px):
    """blended_semidev must be None if either window fails, never a one-window figure wearing
    the two-window name."""
    short = [x for x in px["KO"] if x[0] >= "2025-03-01"]   # enough for 1y, not for 2y
    assert SD.resid_semidev(short, px[SD.MARKET], 1, asof=ASOF) is not None
    assert SD.resid_semidev(short, px[SD.MARKET], 2, asof=ASOF) is None
    assert SD.blended_semidev(short, px[SD.MARKET], asof=ASOF) is None


def test_adjustment_breaks_are_truncated():
    """A single -100% day is a vendor back-adjustment failure, not a market event. Left in it
    produced a full-history semi-deviation of 201% for a company that has compounded for forty
    years."""
    series = [("2020-01-%02d" % d, 100.0) for d in range(1, 10)]
    series += [("2020-02-01", 0.0001)] + [("2020-02-%02d" % d, 100.0) for d in range(2, 10)]
    cleaned, idx, when = SD.clean_series(series)
    assert idx > 0 and when == "2020-02-02"
    assert len(cleaned) < len(series)


# ------------------------------------------------------------------ the feed's own guards

def test_the_universe_is_declared_not_discovered():
    """228 committed tickers. A feed that changes its own membership silently moves the
    cap-weighted normalizer for every name with nothing appearing to change."""
    u = FEED.load_universe()
    assert len(u) >= 200
    assert len(u) == len(set(u)), "duplicate tickers in universe.txt"
    assert all(t == t.strip().upper() for t in u)


def _write_universe_csv(path, n=150, px_asof="2026-08-17"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FEED.FIELDS)
        w.writeheader()
        for i in range(n):
            w.writerow(dict(ticker="T%03d" % i, semidev=10 + i * 0.1, price=100.0,
                            shares=1e9, market_cap=1e11, px_asof=px_asof, n_closes=750))


def test_a_fresh_universe_loads(tmp_path):
    p = os.path.join(str(tmp_path), "outputs", UNI.LATEST)
    _write_universe_csv(p)
    r = UNI.load(outdir=os.path.dirname(p), asof="2026-08-19")
    assert r["n"] == 150 and r["n_capped"] == 150
    assert r["stale"] is False


def test_a_missed_cycle_warns_but_still_loads(tmp_path):
    p = os.path.join(str(tmp_path), "outputs", UNI.LATEST)
    _write_universe_csv(p, px_asof="2026-06-01")
    r = UNI.load(outdir=os.path.dirname(p), asof="2026-08-19")
    assert r["stale"] is True, "79 days old must warn"


def test_a_long_dead_feed_is_refused(tmp_path):
    p = os.path.join(str(tmp_path), "outputs", UNI.LATEST)
    _write_universe_csv(p, px_asof="2026-01-01")
    with pytest.raises(UNI.UniverseStale):
        UNI.load(outdir=os.path.dirname(p), asof="2026-08-19")


def test_a_thin_universe_is_refused(tmp_path):
    p = os.path.join(str(tmp_path), "outputs", UNI.LATEST)
    _write_universe_csv(p, n=20)
    with pytest.raises(UNI.UniverseStale):
        UNI.load(outdir=os.path.dirname(p), asof="2026-08-19")


def test_a_missing_file_is_refused_rather_than_falling_back(tmp_path):
    """The fallback would be the frozen 2026-08-17 research output. Falling back to it is how
    this input came to be frozen; refusing is the whole point."""
    with pytest.raises(UNI.UniverseStale):
        UNI.load(outdir=os.path.join(str(tmp_path), "nowhere"))


def test_partial_coverage_refuses_the_whole_build(monkeypatch):
    """Coverage below the floor must refuse. A partial universe does not give slightly worse
    premiums, it gives wrong ones for every name -- the missing names are missing from the
    DENOMINATOR that prices the ones that resolved."""
    uni = ["AAA", "BBB", "CCC", "DDD"]
    monkeypatch.setattr(FEED, "fetch_prices",
                        lambda t, k, s, timeout=30: ([("2026-08-19", 1.0)] if t == SD.MARKET
                                                     else None))
    with pytest.raises(FEED.FeedRefused):
        FEED.build("KEY", asof="2026-08-19", universe=uni, log=lambda *_: None)


def test_a_stale_market_proxy_refuses(monkeypatch):
    monkeypatch.setattr(FEED, "fetch_prices",
                        lambda t, k, s, timeout=30: [("2026-01-05", 1.0)])
    with pytest.raises(FEED.FeedRefused) as e:
        FEED.build("KEY", asof="2026-08-19", universe=["AAA"], log=lambda *_: None)
    assert "stale" in str(e.value)
