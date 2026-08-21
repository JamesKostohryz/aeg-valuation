"""
eodhd_options.py -- correct retrieval of a full end-of-day option chain from the
EODHD / UnicornBay marketplace feed.

WHY THIS MODULE EXISTS
----------------------
The first version of svix_layer1.py fetched chains with

    filter[tradetime_from] = D
    filter[tradetime_to]   = D

on the belief that `tradetime` selected the end-of-day snapshot date. It does not.
Per the vendor's own field table, `tradetime` is "last market activity date" -- the
date the contract last TRADED. Filtering on it therefore returns only the contracts
that happened to print a trade that day and silently discards every listed contract
that was quoted but not traded.

That is a large and DIRECTIONAL loss. Options that do not trade on a given day are
overwhelmingly the deep out-of-the-money wings, which is exactly the region SVIX^2
integrates over. Measured on 12 August 2026:

    PepsiCo, 4 September 2026 expiry:  37 contracts traded,  106 listed
    Coca-Cola, 15 January 2027 expiry: 24 contracts traded,   60 listed
    Apple, 15 January 2027 expiry:    109 contracts traded,  194 listed

The vendor supplies a real end-of-day bid and ask (with their own timestamps) for
listed-but-untraded contracts, so nothing is lost by including them -- and the SVIX
estimator uses bid/ask midpoints, never last-trade prices, so untraded contracts are
exactly as usable as traded ones.

HOW THE FEED IS ACTUALLY ORGANISED
----------------------------------
There is NO filter for the end-of-day snapshot date. The only place the date appears
is the record id, formatted `{contract}-{YYYY-MM-DD}`. Records come back ordered by
expiry descending, and within an expiry by snapshot date descending. So the way to
get one day's chain is:

  1. Enumerate the live expiries from the `contracts` endpoint (cheap, cacheable).
  2. For each expiry, page the `eod` endpoint with `filter[exp_date_eq]` and pick out
     the records whose id ends in the date you want. Because the ordering is date
     descending, the most recent dates are at low offsets.

`page[offset]` is capped at 10,000 by the vendor, which bounds how far back a single
expiry can be walked: about 10,000 / (contracts per day) trading days. For a large
name with 200 contracts on an expiry that is roughly 48 trading days. Any sampling
window must respect that bound; `plan_pages()` computes it.

COST. One request against these endpoints costs TEN API calls against the daily
100,000 allowance, and the marketplace allowance runs on a rolling 24-hour window
rather than resetting at midnight. Every response is cached to disk, so a re-run is
free; the first pass has to be right.

MEASUREMENT ONLY. Nothing here reads or writes the sealed workbook.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import time
import urllib.parse
import urllib.request

BASE = "https://eodhd.com/api"
EOD = BASE + "/mp/unicornbay/options/eod"
CONTRACTS = BASE + "/mp/unicornbay/options/contracts"
PAGE = 1000
MAX_OFFSET = 10000          # vendor limit; requesting beyond it errors or truncates


def read_token(explicit=None):
    """Locate the API token. Never returns it to a printer -- callers must not log it."""
    if explicit:
        return explicit
    env = os.environ.get("EODHD_API_KEY")
    if env:
        return env
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (os.path.join(os.path.dirname(here), ".eodhd-token"),
                 os.path.expanduser("~/AEG-Project/.eodhd-token")):
        if os.path.exists(cand):
            return open(cand).read().strip()
    return None


class OptionFeed:
    """Cached, budgeted access to the UnicornBay option endpoints."""

    def __init__(self, token, cache_dir="outputs/.svix_cache", pause=0.1, verbose=False):
        self.token = token
        self.cache_dir = cache_dir
        self.pause = pause
        self.verbose = verbose
        self.requests = 0          # network requests actually made
        self.cache_hits = 0
        os.makedirs(cache_dir, exist_ok=True)

    # ------------------------------------------------------------------ plumbing

    @property
    def api_calls(self):
        """Requests translated into the vendor's billing unit."""
        return self.requests * 10

    def _cache_path(self, key):
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in key)
        return os.path.join(self.cache_dir, safe + ".json")

    def _get(self, url, params, cache_key):
        path = self._cache_path(cache_key)
        if os.path.exists(path):
            self.cache_hits += 1
            with open(path) as f:
                return json.load(f)
        q = dict(params)
        q["api_token"] = self.token
        full = url + "?" + urllib.parse.urlencode(q)
        last = None
        for attempt in range(4):
            try:
                with urllib.request.urlopen(full, timeout=120) as r:
                    data = json.loads(r.read().decode())
                self.requests += 1
                # Write through a temporary file and rename, so a cache entry is
                # either absent or complete. Several workers share this directory.
                tmp = path + f".tmp{os.getpid()}_{id(self)}"
                with open(tmp, "w") as f:
                    json.dump(data, f)
                os.replace(tmp, path)
                time.sleep(self.pause)
                return data
            except Exception as e:              # never include `full`: it carries the token
                last = f"{type(e).__name__}: {e}"
                if attempt < 3:
                    time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"request failed after 4 attempts: {last}")

    # ---------------------------------------------------------------- expiries

    def expiries(self, ticker, exp_from, exp_to, refresh_key=""):
        """
        Live expiries for one underlying inside a window, with the number of listed
        contracts on each. Returns {exp_date: n_contracts}.

        This uses the `contracts` endpoint, which is a snapshot of what is currently
        listed rather than a per-day record, so it is cached once per window and
        reused across every sampled date.
        """
        out, off = {}, 0
        while off <= MAX_OFFSET:
            params = {
                "filter[underlying_symbol]": ticker,
                "filter[exp_date_from]": exp_from,
                "filter[exp_date_to]": exp_to,
                "fields[options-contracts]": "exp_date",
                "page[limit]": PAGE,
                "page[offset]": off,
            }
            key = f"exps_{ticker}_{exp_from}_{exp_to}_{off}{refresh_key}"
            data = self._get(CONTRACTS, params, key)
            rows = data.get("data", []) if isinstance(data, dict) else []
            for r in rows:
                e = r.get("attributes", {}).get("exp_date")
                if e:
                    out[e] = out.get(e, 0) + 1
            if len(rows) < PAGE:
                break
            off += PAGE
        return out

    # ------------------------------------------------------------------- chains

    def expiry_slice(self, ticker, exp_date, trade_dates, n_contracts_hint=None,
                     max_pages=12):
        """
        Every end-of-day record for one underlying and one expiry, restricted to the
        requested snapshot dates.

        trade_dates: iterable of ISO dates wanted.
        Returns {trade_date: [attribute dicts]} -- dates with no data are absent.

        Paging stops as soon as the records being returned are older than the oldest
        requested date, so asking for recent dates is cheap.
        """
        want = set(trade_dates)
        oldest = min(want)
        found = {}
        off = 0
        pages = 0
        while off <= MAX_OFFSET and pages < max_pages:
            params = {
                "filter[underlying_symbol]": ticker,
                "filter[exp_date_eq]": exp_date,
                "page[limit]": PAGE,
                "page[offset]": off,
            }
            key = f"eod_{ticker}_{exp_date}_{off}"
            data = self._get(EOD, params, key)
            rows = data.get("data", []) if isinstance(data, dict) else []
            if not rows:
                break
            seen_older = False
            for r in rows:
                rid = r.get("id") or ""
                d = rid[-10:]
                if len(d) != 10 or d[4] != "-":
                    continue
                if d in want:
                    found.setdefault(d, []).append(r.get("attributes", {}))
                elif d < oldest:
                    seen_older = True
            pages += 1
            if len(rows) < PAGE or seen_older:
                break
            off += PAGE
        return found

    def chain(self, ticker, trade_dates, exp_from, exp_to, max_pages=12):
        """
        Full listed chain for one underlying across a set of snapshot dates.

        Returns {trade_date: [rows]}, each row an attribute dict with `exp_date`,
        `type`, `strike`, `bid`, `ask`, `open_interest`, `volume`, ...

        This is the function svix_layer1 should call. It replaces the old
        tradetime-filtered fetch, which returned only traded contracts.
        """
        exps = self.expiries(ticker, exp_from, exp_to)
        out = {d: [] for d in trade_dates}
        for e in sorted(exps):
            got = self.expiry_slice(ticker, e, trade_dates,
                                    n_contracts_hint=exps[e], max_pages=max_pages)
            for d, rows in got.items():
                out.setdefault(d, []).extend(rows)
        return {d: rows for d, rows in out.items() if rows}


    # -------------------------------------------------------------- rate curve

    def treasury_curve(self, date_from, date_to):
        """
        United States Treasury constant-maturity yields, pulled LIVE.

        WHY AN EXTERNAL RATE IS NEEDED AFTER ALL. svix_core.py was written on the
        premise that put-call parity supplies both the forward and the discount
        factor, so no rate feed is required. That premise holds for EUROPEAN options.
        Listed single-stock options in the United States are AMERICAN, and their deep
        in-the-money quotes sit at or near immediate-exercise intrinsic value rather
        than at the discounted forward value. That drags the parity regression's slope
        toward minus one and therefore the implied discount factor toward one.

        Measured on Apple's 17 December 2027 expiry (492 days) on 12 August 2026, the
        parity regression implies a rate of 1.4 per cent; the Treasury curve that day
        was near 4.2 per cent at that tenor, and Apple's own forward-to-spot carry
        independently implies about 4.2 per cent. The parity estimate is wrong, and it
        is wrong by more the longer the expiry.

        This is a live feed read at run time, not a curve copied out of a prose
        document -- the failure mode 00-START-HERE.md warns about. The date the curve
        was read is recorded alongside every number that uses it.

        Returns {date: {tenor_label: rate_percent}}.
        """
        params = {"from": date_from, "to": date_to, "fmt": "json"}
        data = self._get(BASE + "/ust/yield-rates", params,
                         f"ust_{date_from}_{date_to}")
        rows = data.get("data", data) if isinstance(data, dict) else data
        out = {}
        for r in rows or []:
            out.setdefault(r["date"], {})[r["tenor"]] = r["rate"]
        return out


TENOR_DAYS = {"1M": 30, "1.5M": 46, "2M": 61, "3M": 91, "4M": 122, "6M": 183,
              "1Y": 365, "2Y": 730, "3Y": 1095, "5Y": 1826, "7Y": 2557,
              "10Y": 3653, "20Y": 7305, "30Y": 10958}


def rate_function(curve_row):
    """
    Turn one day's Treasury row into r(days), continuously compounded, as a decimal.

    Linear interpolation in days on the par-yield quotes, flat outside the quoted
    range. Par yields are treated as annually compounded and converted, which is a
    small correction at these levels but is done rather than ignored.
    """
    pts = sorted((TENOR_DAYS[t], v / 100.0) for t, v in curve_row.items()
                 if t in TENOR_DAYS and v is not None)
    if not pts:
        return None

    def r(days):
        if days <= pts[0][0]:
            y = pts[0][1]
        elif days >= pts[-1][0]:
            y = pts[-1][1]
        else:
            y = pts[-1][1]
            for (da, ya), (db, yb) in zip(pts[:-1], pts[1:]):
                if da <= days <= db:
                    y = ya + (days - da) / (db - da) * (yb - ya)
                    break
        import math as _m
        return _m.log1p(y)          # annually compounded -> continuous
    return r


# ------------------------------------------------------------------- budgeting

def plan_pages(contracts_per_day, n_trading_days):
    """
    Requests needed to walk one expiry back `n_trading_days` snapshots, and whether
    the vendor's 10,000-offset cap makes that impossible.

    Returns (pages, reachable_trading_days). If reachable < n_trading_days the window
    must be shortened -- there is no way around the cap.
    """
    if contracts_per_day <= 0:
        return 0, 0
    rows_needed = contracts_per_day * n_trading_days
    reachable = int((MAX_OFFSET + PAGE) / contracts_per_day)
    pages = min(int((rows_needed + PAGE - 1) // PAGE),
                int(MAX_OFFSET // PAGE) + 1)
    return max(pages, 1), reachable


def trading_days_between(d0, d1):
    """Rough count of weekday sessions between two ISO dates. Ignores holidays, so it
    slightly overstates -- which is the safe direction for a paging budget."""
    a, b = dt.date.fromisoformat(d0), dt.date.fromisoformat(d1)
    if b < a:
        a, b = b, a
    n = 0
    while a < b:
        a += dt.timedelta(days=1)
        if a.weekday() < 5:
            n += 1
    return n
