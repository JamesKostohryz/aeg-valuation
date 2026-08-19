"""
idio/feed.py — rebuild the company-premium universe from live data.

WHAT WAS WRONG. `idio_erp.py` read three files to get its two inputs:

    semi-deviation   AEG-Project/outputs/2026-08-17-rank-residual/rank_residual_scored.csv
    cap weights      AEG-Project/outputs/2026-08-16-universe-repair/price_test_flat_erp.csv
                     AEG-Project/outputs/2026-08-16-validation2/price_test_validation2.csv

All three are DATED ONE-SHOT OUTPUTS of measurement scripts, in a working folder that is not a
repository. Nothing recomputed any of them. Shipped as it stood, every company's premium would
have been frozen at its 17 August 2026 value permanently while every test stayed green — which
is this project's signature failure, in the newest place it could possibly have appeared.

WHAT THIS DOES. Pulls daily adjusted closes from EODHD for the declared universe plus the market
proxy, recomputes the blended residual semi-deviation, recomputes cap weights from live price
and shares outstanding, and writes `outputs/idio_universe_latest.csv`. Monthly is ample: the
statistic blends one- and two-year windows on a sixty-trading-day lag, so it cannot move quickly
by construction.

THE UNIVERSE IS DECLARED, NOT DISCOVERED. `idio/universe.txt` holds the 228 tickers, committed
and diffable. A feed that silently changes its own membership would move every cap-weighted
normalizer without anything appearing to change — the same defect one level up. Adding or
removing a name is a commit somebody can see.

FAIL-CLOSED ON COVERAGE. If fewer than MIN_COVERAGE of the universe resolves, the run refuses
and leaves the previous file in place. The cap-weighted average semi-deviation is the
DENOMINATOR of every company's premium, so a partial universe does not produce slightly worse
premiums — it produces wrong ones, quietly, for every name including the ones that did resolve.

NO PRICE HISTORY IS COMMITTED. The statistic needs about two and a quarter years; this pulls
three. The 585-file historical cache in the working folder is a research asset and stays there.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import semidev as SD  # noqa: E402

EODHD_BASE = "https://eodhd.com/api"
UNIVERSE_FILE = os.path.join(HERE, "universe.txt")

HISTORY_YEARS = 3           # ~2.25 are needed; 3 leaves room for holidays and halts
MIN_COVERAGE = 0.90         # refuse below this share of the declared universe
MAX_PRICE_AGE_DAYS = 7      # a market proxy staler than this means the feed is broken
REQUEST_PAUSE_S = 0.05


class FeedRefused(Exception):
    """Nothing is written; the previous universe file stands."""


def load_universe(path: str = UNIVERSE_FILE) -> list:
    with open(path) as f:
        return [ln.strip().upper() for ln in f if ln.strip() and not ln.startswith("#")]


# ------------------------------------------------------------------ EODHD

def _get(url: str, timeout: int = 30):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


def fetch_prices(ticker: str, api_key: str, start: str, timeout: int = 30):
    """[(date, adjusted_close)] ascending, or None. Adjusted close ONLY: the statistic is a
    total-return measure and the market proxy is on the same basis, so mixing in raw closes
    would put a dividend yield into the residual for exactly the names that pay one."""
    q = urllib.parse.urlencode(dict(api_token=api_key, fmt="json", from_=start, period="d"))
    q = q.replace("from_=", "from=")
    try:
        rows = _get(f"{EODHD_BASE}/eod/{ticker}.US?{q}", timeout=timeout)
    except Exception:
        return None
    if not isinstance(rows, list) or not rows:
        return None
    out = []
    for r in rows:
        d, c = r.get("date"), r.get("adjusted_close", r.get("close"))
        if d and c:
            try:
                out.append((d, float(c)))
            except (TypeError, ValueError):
                pass
    out.sort()
    return out or None


def fetch_shares(ticker: str, api_key: str, timeout: int = 30):
    """Most recent shares outstanding from EODHD fundamentals, or None."""
    q = urllib.parse.urlencode(dict(api_token=api_key, fmt="json",
                                    filter="outstandingShares::annual"))
    try:
        d = _get(f"{EODHD_BASE}/fundamentals/{ticker}.US?{q}", timeout=timeout)
    except Exception:
        return None
    if not isinstance(d, dict):
        return None
    best = None
    for v in d.values():
        try:
            yr, sh = int(v.get("dateFormatted", v.get("date", "0"))[:4]), float(v.get("shares"))
        except (TypeError, ValueError, AttributeError):
            continue
        if sh > 0 and (best is None or yr > best[0]):
            best = (yr, sh)
    return best[1] if best else None


# ------------------------------------------------------------------ the build

def build(api_key: str, asof: str | None = None, universe=None, log=print) -> dict:
    asof = asof or dt.date.today().isoformat()
    tickers = universe if universe is not None else load_universe()
    start = (dt.date.fromisoformat(asof) - dt.timedelta(days=int(HISTORY_YEARS * 366))).isoformat()

    log(f"idio feed: {len(tickers)} declared names, as of {asof}, history from {start}")

    market = fetch_prices(SD.MARKET, api_key, start)
    if not market:
        raise FeedRefused(f"market proxy {SD.MARKET} returned no prices — nothing can be "
                          f"computed without it")
    age = (dt.date.fromisoformat(asof) - dt.date.fromisoformat(market[-1][0])).days
    if age > MAX_PRICE_AGE_DAYS:
        raise FeedRefused(f"{SD.MARKET} latest close is {market[-1][0]}, {age} days before "
                          f"{asof}. The price feed is stale, not the market closed.")
    log(f"  market {SD.MARKET}: {len(market)} closes, latest {market[-1][0]}")

    rows, no_price, no_semidev, no_shares = [], [], [], []
    for i, t in enumerate(tickers, 1):
        time.sleep(REQUEST_PAUSE_S)
        px = fetch_prices(t, api_key, start)
        if not px:
            no_price.append(t)
            continue
        sd = SD.blended_semidev(px, market, asof=asof)
        if sd is None:
            no_semidev.append(t)
            continue
        sh = fetch_shares(t, api_key)
        if sh is None:
            no_shares.append(t)
        price = px[-1][1]
        rows.append(dict(ticker=t, semidev=round(sd, 6), price=round(price, 6),
                         shares=(round(sh, 2) if sh else ""),
                         market_cap=(round(price * sh, 2) if sh else ""),
                         px_asof=px[-1][0], n_closes=len(px)))
        if i % 25 == 0:
            log(f"  ... {i}/{len(tickers)}")

    coverage = len(rows) / float(len(tickers))
    log(f"  resolved {len(rows)}/{len(tickers)} ({coverage:.1%}); "
        f"no price {len(no_price)}, no semidev {len(no_semidev)}, no shares {len(no_shares)}")
    if coverage < MIN_COVERAGE:
        raise FeedRefused(
            f"only {coverage:.1%} of the declared universe resolved (floor {MIN_COVERAGE:.0%}). "
            f"The cap-weighted average semi-deviation is the DENOMINATOR of every company's "
            f"premium, so a partial universe gives wrong premiums for every name, including the "
            f"ones that did resolve. Refusing; the previous file stands.")

    capped = [r for r in rows if r["market_cap"] != ""]
    if not capped:
        raise FeedRefused("no name has both a price and a share count; no cap weights possible")

    return dict(asof=asof, rows=sorted(rows, key=lambda r: r["ticker"]), coverage=coverage,
                no_price=no_price, no_semidev=no_semidev, no_shares=no_shares,
                market_asof=market[-1][0], n_capped=len(capped))


FIELDS = ["ticker", "semidev", "price", "shares", "market_cap", "px_asof", "n_closes"]


def write(result: dict, outdir: str, log=print) -> str:
    os.makedirs(outdir, exist_ok=True)
    latest = os.path.join(outdir, "idio_universe_latest.csv")
    for path in (latest, os.path.join(outdir, "idio_universe_%s.csv" % result["asof"])):
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            for r in result["rows"]:
                w.writerow(r)
    meta = os.path.join(outdir, "idio_universe_latest.json")
    with open(meta, "w") as f:
        json.dump({k: v for k, v in result.items() if k != "rows"}, f, indent=2)
        f.write("\n")
    log(f"  wrote {os.path.basename(latest)} ({len(result['rows'])} names) + a dated copy")
    return latest


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Rebuild the company-premium universe.")
    ap.add_argument("--outdir", default="outputs")
    ap.add_argument("--asof", default=None)
    ap.add_argument("--limit", type=int, default=None, help="first N names only (smoke runs)")
    a = ap.parse_args(argv)
    key = os.environ.get("EODHD_API_KEY")
    if not key:
        print("EODHD_API_KEY not set", file=sys.stderr)
        return 2
    uni = load_universe()[: a.limit] if a.limit else None
    try:
        res = build(key, asof=a.asof, universe=uni)
    except FeedRefused as e:
        print(f"\nREFUSED, nothing written: {e}", file=sys.stderr)
        return 2
    write(res, a.outdir)
    print(f"\nOK — {len(res['rows'])} names, coverage {res['coverage']:.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
