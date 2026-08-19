"""
idio/universe.py — read the company-premium universe, and refuse a stale one.

The company premium scales every name on `semidev_i / cap-weighted average semidev`. Both halves
come from `outputs/idio_universe_latest.csv`, which `idio/feed.py` rebuilds monthly.

WHY THERE IS A STALENESS GUARD AT ALL. Before this file, those two inputs were read from dated
one-shot research outputs — `rank_residual_scored.csv` of 2026-08-17 and two price-test files of
2026-08-16 — that nothing recomputed. Every company premium would have been pinned to
mid-August 2026 for good, and no test could have noticed, because a frozen number is arithmetically
perfect. The guard is the difference between a feed and a fossil.

TWO TIERS, matching the re-anchor's convention on the market side:

    WARN   older than WARN_AGE_DAYS. Returns the data and sets `stale` on the result. The caller
           decides; nothing is suppressed.
    REFUSE older than MAX_AGE_DAYS, or the file is missing, or fewer than MIN_NAMES resolve.
           Raises. A premium built on a half-year-old risk measure is not a conservative
           approximation of the right answer, it is a different answer.
"""
from __future__ import annotations

import csv
import datetime as dt
import os

LATEST = "idio_universe_latest.csv"
WARN_AGE_DAYS = 45      # the feed is monthly; 45 days means one cycle has been missed
MAX_AGE_DAYS = 120
MIN_NAMES = 100


class UniverseStale(Exception):
    """The universe file is too old, too small, or absent to price anything from."""


def _asof(row_dates):
    good = [d for d in row_dates if d]
    return max(good) if good else None


def load(outdir: str = "outputs", asof: str | None = None, path: str | None = None) -> dict:
    """Returns {semidev, cap, asof, n, stale, age_days}.

    `cap` covers only names with BOTH a price and a share count, which is deliberate: a name
    with a semi-deviation but no market cap still gets a premium, it just does not vote on the
    cap-weighted normalizer. Dropping it from `semidev` too would silently shrink the universe."""
    p = path or os.path.join(outdir, LATEST)
    if not os.path.exists(p):
        raise UniverseStale(
            f"{p} is missing. Run idio/feed.py (workflow: idio-universe-refresh). Refusing "
            f"rather than falling back to the frozen 2026-08-17 research output, which is how "
            f"this input came to be frozen in the first place.")

    semidev, cap, dates = {}, {}, []
    with open(p) as f:
        for r in csv.DictReader(f):
            t = (r.get("ticker") or "").strip()
            if not t:
                continue
            try:
                semidev[t] = float(r["semidev"])
            except (KeyError, TypeError, ValueError):
                continue
            dates.append((r.get("px_asof") or "").strip())
            try:
                mc = float(r["market_cap"])
                if mc > 0:
                    cap[t] = mc
            except (KeyError, TypeError, ValueError):
                pass

    if len(semidev) < MIN_NAMES:
        raise UniverseStale(
            f"{p} has only {len(semidev)} usable names (floor {MIN_NAMES}). The cap-weighted "
            f"average is the denominator of every premium, so a thin universe is wrong for "
            f"every name rather than missing for some.")

    file_asof = _asof(dates)
    today = dt.date.fromisoformat(asof) if asof else dt.date.today()
    age = (today - dt.date.fromisoformat(file_asof)).days if file_asof else None

    if age is not None and age > MAX_AGE_DAYS:
        raise UniverseStale(
            f"{p} is {age} days old (latest close {file_asof}; limit {MAX_AGE_DAYS}). The "
            f"monthly refresh has not run. Refusing to price a company premium off it.")

    return dict(semidev=semidev, cap=cap, asof=file_asof, n=len(semidev),
                n_capped=len(cap), age_days=age,
                stale=bool(age is not None and age > WARN_AGE_DAYS))
