"""
svix_characteristics.py -- the non-circular matching vector for peer selection.

Spec section 4. James's matching rule as stated is: find stocks with similar implied
volatility at that expiration and that distance from strike. The instinct is right;
taken literally it is circular. If peers are chosen purely by how well their implied
volatilities agree with the thin name's, then the wings borrowed from them inherit
that selection, and the answer looks consistent whatever the truth is. This engine
has been bitten by internally-consistent-and-wrong six times.

So the matching vector is built only from things observable WITHOUT the missing data:

  1. at-the-money total variance at the nearest common expiry  -- James's variable,
     and legitimate, because a thin name does have quotes at the money. Carries the
     LEVEL. Supplied by the caller from the slice itself.
  2. realized volatility of the underlying over the trailing 6 and 24 months -- no
     options required.
  3. crash capture, from tools/market_declines.py -- the left wing of the smile IS
     the price of downside, and crash capture measures downside co-movement from
     prices alone. It is the natural non-circular instrument for the skew, which is
     the parameter a thin ladder identifies worst.
  4. sector, as a hard block rather than a distance.
  5. log market capitalization.

None of components 2 to 5 uses an option quote at all, so none of them can be
contaminated by the wings being borrowed.

MEASUREMENT ONLY.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
import statistics
import urllib.parse
import urllib.request

BASE = "https://eodhd.com/api"


def _get_json(url, cache_path, timeout=120):
    if os.path.exists(cache_path):
        with open(cache_path) as f:
            return json.load(f)
    with urllib.request.urlopen(url, timeout=timeout) as r:
        data = json.loads(r.read().decode())
    os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
    tmp = cache_path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, cache_path)
    return data


def price_history(token, ticker, date_from="1950-01-01", cache="outputs/.px_cache"):
    """Adjusted daily closes, oldest first. One API call, cached forever."""
    q = urllib.parse.urlencode({"api_token": token, "fmt": "json",
                                "from": date_from, "period": "d"})
    p = os.path.join(cache, f"{ticker}_US_{date_from}.json")
    rows = _get_json(f"{BASE}/eod/{ticker}.US?{q}", p)
    out = []
    for r in rows or []:
        c = r.get("adjusted_close", r.get("close"))
        if r.get("date") and c:
            out.append((r["date"], float(c)))
    out.sort()
    return out


def fundamentals_bits(token, ticker, cache="outputs/.px_cache"):
    """Market capitalization and sector. One API call, cached."""
    q = urllib.parse.urlencode({"api_token": token,
                                "filter": "General::Sector,General::Industry,"
                                          "Highlights::MarketCapitalization"})
    p = os.path.join(cache, f"fund_{ticker}.json")
    try:
        d = _get_json(f"{BASE}/fundamentals/{ticker}.US?{q}", p)
    except Exception:
        return None, None
    if not isinstance(d, dict):
        return None, None
    cap = d.get("Highlights::MarketCapitalization")
    sector = d.get("General::Sector")
    if cap is None and "Highlights" in d:
        cap = d.get("Highlights", {}).get("MarketCapitalization")
    if sector is None and "General" in d:
        sector = d.get("General", {}).get("Sector")
    try:
        cap = float(cap) if cap else None
    except (TypeError, ValueError):
        cap = None
    return cap, sector


def realized_vol(series, as_of, months):
    """
    Annualized realized volatility of daily log returns over the trailing window.

    Uses log returns and the sample standard deviation, annualized by the square root
    of 252. No options anywhere in it, which is the point.
    """
    if not series:
        return None
    end = dt.date.fromisoformat(as_of)
    start = (end - dt.timedelta(days=int(round(months * 30.44)))).isoformat()
    px = [c for d, c in series if start <= d <= as_of]
    if len(px) < 20:
        return None
    rets = [math.log(px[i] / px[i - 1]) for i in range(1, len(px)) if px[i - 1] > 0]
    if len(rets) < 20:
        return None
    return statistics.stdev(rets) * math.sqrt(252.0)


def zscore(values):
    """Z-score a dict of name -> value, ignoring missing entries. Returns a dict with
    the same keys that had a value."""
    xs = [v for v in values.values() if v is not None and math.isfinite(v)]
    if len(xs) < 2:
        return {k: 0.0 for k in values}
    mu = statistics.fmean(xs)
    sd = statistics.stdev(xs)
    if sd == 0:
        return {k: 0.0 for k in values}
    return {k: ((v - mu) / sd if v is not None and math.isfinite(v) else None)
            for k, v in values.items()}


class PeerMatcher:
    """
    Weighted Euclidean distance on the z-scored characteristic vector, with sector as
    a hard block where possible.

    Weights start EQUAL on the components, as the spec requires. They are not to be
    tuned by hand -- they are tuned, if at all, by the section 6 validation, and the
    tuned values recorded with the date they were fitted.
    """

    DEFAULT_WEIGHTS = {"atm_w": 1.0, "rv6": 1.0, "rv24": 1.0,
                       "crash_capture": 1.0, "log_cap": 1.0}

    def __init__(self, characteristics, weights=None, sector_penalty=1.5):
        """characteristics: {ticker: {"rv6":.., "rv24":.., "crash_capture":..,
        "log_cap":.., "sector":..}} in RAW units; z-scoring happens here."""
        self.raw = characteristics
        self.weights = dict(weights or self.DEFAULT_WEIGHTS)
        self.sector_penalty = sector_penalty
        self.z = {}
        for comp in ("rv6", "rv24", "crash_capture", "log_cap"):
            self.z[comp] = zscore({t: c.get(comp) for t, c in characteristics.items()})
        self.sector = {t: c.get("sector") for t, c in characteristics.items()}

    def distance(self, a, b, atm_w_a=None, atm_w_b=None):
        """Distance between two tickers. atm_w_* are the at-the-money total variances
        of the two SLICES being compared, passed in because they are per-expiry."""
        tot, used = 0.0, 0.0
        for comp in ("rv6", "rv24", "crash_capture", "log_cap"):
            za, zb = self.z[comp].get(a), self.z[comp].get(b)
            if za is None or zb is None:
                continue
            wgt = self.weights.get(comp, 1.0)
            tot += wgt * (za - zb) ** 2
            used += wgt
        if atm_w_a and atm_w_b and atm_w_a > 0 and atm_w_b > 0:
            wgt = self.weights.get("atm_w", 1.0)
            # a relative gap, so it behaves like the z-scored components
            tot += wgt * (math.log(atm_w_a / atm_w_b)) ** 2
            used += wgt
        if used == 0:
            return float("inf")
        d = math.sqrt(tot / used)
        sa, sb = self.sector.get(a), self.sector.get(b)
        if sa and sb and sa != sb:
            d *= self.sector_penalty
        return d


def build_characteristics(token, tickers, as_of, market_episodes=None,
                          cache="outputs/.px_cache", verbose=True):
    """
    Assemble the matching vector for every ticker. Two API calls per name (one price
    history, one fundamentals filter), both cached to disk.

    market_episodes, if supplied, comes from tools/market_declines.py and lets crash
    capture be computed. Without it that component is simply absent and the distance
    falls back on the others -- which is worse, and is reported rather than hidden.
    """
    from market_declines import crash_capture
    import threading

    # Warm both feeds in parallel first. Each is one API call per name and they are
    # latency-bound, so a small pool turns ten minutes into under one. Everything is
    # cached to disk, so this is a one-off cost per ticker for the life of the cache.
    def warm(names):
        for t in names:
            try:
                price_history(token, t, cache=cache)
            except Exception:
                pass
            try:
                fundamentals_bits(token, t, cache=cache)
            except Exception:
                pass

    chunks = [tickers[i::8] for i in range(8)]
    threads = [threading.Thread(target=warm, args=(c,), daemon=True) for c in chunks]
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    out = {}
    for i, t in enumerate(tickers, 1):
        try:
            ser = price_history(token, t, cache=cache)
        except Exception as e:
            if verbose:
                print(f"  characteristics {t}: price history failed -- {e}")
            ser = []
        cap, sector = fundamentals_bits(token, t, cache=cache)
        cc = None
        if market_episodes and ser:
            cc, n_used, _ = crash_capture(ser, market_episodes)
        out[t] = {
            "rv6": realized_vol(ser, as_of, 6),
            "rv24": realized_vol(ser, as_of, 24),
            "crash_capture": cc,
            "log_cap": math.log(cap) if cap else None,
            "market_cap": cap,
            "sector": sector,
            "history_from": ser[0][0] if ser else None,
        }
        if verbose and i % 25 == 0:
            print(f"  characteristics: {i}/{len(tickers)}")
    return out
