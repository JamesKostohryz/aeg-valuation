#!/usr/bin/env python3
"""
tests/test_common_vintage_guard.py — COMMON(t) may not be of unknown age.

THE HOLE THIS CLOSES. `fetch_market_credit` fetches the aggregate investment-grade credit curve
from raw.githubusercontent.com and then asks GitHub's commits API when it was last written.
Unauthenticated, that API allows 60 requests an hour per IP; a shared runner burns it and gets
403. The raw fetch still succeeded, so the function returned a perfectly good curve with
`vintage=None` and `age_days=None` -- and the staleness check is written
`if age is not None and age > MAX_CREDIT_AGE_DAYS`, so it **did not run at all**.

COMMON(t) is charged to EVERY company at EVERY tenor. A curve of unknown age is a silent input
to every discount rate on the system, and the failure surfaced as one None in a provenance dict.

Two things are asserted, because a guard that always fires is as useless as one that never does.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "idio"))
import market_erp_live as M   # noqa: E402


def test_a_curve_whose_age_cannot_be_established_is_refused(monkeypatch):
    """FIRES. Raw fetch fine, vintage lookup dead, no local checkout to fall back to."""
    monkeypatch.setattr(M, "_http_get",
                        lambda url, timeout=20, auth=False: (
                            _raw() if "raw.githubusercontent" in url
                            else (_ for _ in ()).throw(RuntimeError("HTTP 403 rate limited"))))
    monkeypatch.setattr(M, "_local_paths", lambda p: [])
    with pytest.raises(RuntimeError) as e:
        M.fetch_market_credit(log=None)
    msg = str(e.value)
    assert "403" in msg or "vintage" in msg.lower(), msg
    assert "every company" in msg, "the refusal must say what it protects"


def test_it_does_not_fire_when_the_vintage_is_known(monkeypatch):
    """DOES NOT FIRE. Same curve, working vintage lookup."""
    import datetime as dt
    today = dt.date.today().isoformat()

    def fake(url, timeout=20, auth=False):
        if "raw.githubusercontent" in url:
            return _raw()
        return ('[{"commit": {"committer": {"date": "%sT00:00:00Z"}}}]' % today)

    monkeypatch.setattr(M, "_http_get", fake)
    out = M.fetch_market_credit(log=None)
    assert out["vintage"] == today and out["age_days"] == 0
    assert len(out["spread_pct"]) >= 30


def test_a_known_but_old_vintage_is_still_refused(monkeypatch):
    """The check that was being skipped. It must work now that a vintage always exists."""
    def fake(url, timeout=20, auth=False):
        if "raw.githubusercontent" in url:
            return _raw()
        return '[{"commit": {"committer": {"date": "2020-01-01T00:00:00Z"}}}]'

    monkeypatch.setattr(M, "_http_get", fake)
    with pytest.raises(RuntimeError) as e:
        M.fetch_market_credit(log=None)
    assert "days old" in str(e.value)


def test_the_vintage_lookup_is_authenticated_when_a_token_exists():
    """60 requests an hour per IP is what made this fail. Authenticated it is 1,000."""
    seen = {}
    orig = M._http_get

    def spy(url, timeout=20, auth=False):
        seen[url] = auth
        raise RuntimeError("stop here")

    M._http_get = spy
    try:
        try:
            M.fetch_market_credit(log=None)
        except Exception:
            pass
    finally:
        M._http_get = orig
    api = [u for u in seen if "api.github.com" in u]
    assert not api or all(seen[u] for u in api), "the commits API is called unauthenticated"


def _raw():
    head = ("tenor,treasury_nominal,ig_index_spread,real_fwd\n")
    return head + "".join("%d,4.0,0.49,0.02\n" % t for t in range(1, 31))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
