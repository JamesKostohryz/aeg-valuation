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

THE MEMBERSHIP IS MEASURED, AND THE CHANGE IS VISIBLE. Until 2026-08-19 `idio/universe.txt`
was a hand-committed list that nothing updated: the refresh rebuilt the statistic FOR THE
DECLARED NAMES but never the names themselves, so roughly twenty-five constituents a year would
have drifted out of it with every gate green — the same class of defect as the frozen research
outputs above, one level up. `idio/membership.py` now reads the constituents from the EODHD
GSPC.INDX payload, refuses a payload that is the wrong size or too far from the committed list,
and rewrites `universe.txt` as an OUTPUT of the run. The file stays in the repository because
the commit diff is how a membership change becomes something a person can see, and because a
past valuation has to be reproducible against the membership of its own date.

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

import membership as MB  # noqa: E402
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
    """The committed record of the membership the LAST refresh used. This is no longer the
    input to a refresh — `membership.resolve()` is — but it remains the reproducible record,
    and it is what an offline reader (a test, a re-run of a past valuation) reads."""
    return MB.read_committed(path)


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

def build(api_key: str, asof: str | None = None, universe=None, log=print,
          membership: dict | None = None) -> dict:
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
                market_asof=market[-1][0], n_capped=len(capped),
                membership=membership)


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
    ap.add_argument("--accept-membership", action="store_true",
                    help="ratify an index membership change larger than membership.MAX_DRIFT. "
                         "Deliberate and logged; the diff on universe.txt is the record.")
    ap.add_argument("--frozen-membership", action="store_true",
                    help="use the committed universe.txt without consulting the index. For "
                         "reproducing a past run; NOT for a scheduled refresh.")
    a = ap.parse_args(argv)
    key = os.environ.get("EODHD_API_KEY")
    if not key:
        print("EODHD_API_KEY not set", file=sys.stderr)
        return 2

    # 1) MEMBERSHIP FIRST. The names are an input the refresh used to take on faith. A wrong
    #    or partial list does not give slightly worse premiums, it moves the cap-weighted
    #    denominator and gives wrong ones for every name, so it is resolved and gated before a
    #    single price is pulled.
    mem = None
    if a.frozen_membership:
        tickers = load_universe()
        print(f"membership FROZEN at the committed list ({len(tickers)} names) — "
              f"reproduction mode, not a refresh")
    else:
        try:
            mem = MB.resolve(key, accept=a.accept_membership)
        except MB.MembershipRefused as e:
            print(f"\nREFUSED, nothing written: {e}", file=sys.stderr)
            return 2
        tickers = mem["tickers"]

    uni = tickers[: a.limit] if a.limit else tickers
    try:
        res = build(key, asof=a.asof, universe=uni, membership=(
            {k: v for k, v in mem.items() if k != "tickers"} if mem else {"frozen": True}))
    except FeedRefused as e:
        print(f"\nREFUSED, nothing written: {e}", file=sys.stderr)
        return 2
    write(res, a.outdir)

    # 2) universe.txt is an OUTPUT now. Written only on a full, unrefused run: a --limit smoke
    #    run must never be able to shrink the committed membership to its first N names.
    if mem and not a.limit:
        MB.write_committed(mem["tickers"], asof=res["asof"])
        print(f"  rewrote idio/universe.txt ({len(mem['tickers'])} names) — commit the diff")

    print(f"\nOK — {len(res['rows'])} names, coverage {res['coverage']:.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
