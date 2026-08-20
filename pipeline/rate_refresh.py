#!/usr/bin/env python3
"""
pipeline/rate_refresh.py — keep every onboarded company's rate side from going stale.

THE PROBLEM THIS EXISTS FOR. A company's cost of equity and cost of debt come from three files
published by real-yields: coe_v2_<T>_latest_annual.csv, cod_<T>_annual.csv and company_<T>.csv.
The GLOBAL curve is rebuilt daily. Those three are not: they are written only when somebody
dispatches real-yields' company-data workflow FOR THAT TICKER, and nothing scheduled it.

Measured 2026-08-19, before this existed:

    AAPL  2026-07-15   36 days      PEP  2026-08-03   17 days
    T     2026-07-20   31 days      KO   2026-08-03   17 days
    POOL  2026-07-29   22 days

The Coca-Cola valuation published that day ran on a cost-of-equity and cost-of-debt curve built
on 3 August. Nothing said so, and nothing could: the four-method tie is an internal-consistency
proof and it ties exactly as well on a curve from last year.

rate_feed.py now warns past 30 days and refuses past 90. That makes the staleness VISIBLE and
puts a floor under it. This makes it stop happening.

WHAT IT DOES NOT DO, DELIBERATELY. It does not re-decide the durability category. OBS_CATEGORY
selects the obsolescence elevator preset and lands in the published cost-of-equity curve, so a
refresh that re-chose it would silently move every company's discount rate with no diff to see --
the same class of defect as the frozen list, arriving from the opposite direction. real-yields'
company-data workflow takes obs_category=KEEP, which reuses what run_stamp_<T>.csv records for
that ticker. This dispatches KEEP and nothing else.

FAIL-SOFT PER COMPANY, FAIL-LOUD IN AGGREGATE. One ticker failing to dispatch must not stop the
other fourteen, so each is attempted and the failures are collected. The run then exits non-zero
if any failed, because a refresh that quietly skipped half the fleet is how the fleet gets old.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time
import urllib.error
import urllib.request

RY_OWNER = "JamesKostohryz"
RY_REPO = "real-yields"
RY_WORKFLOW = "company.yml"
API = "https://api.github.com"

# A dispatch is cheap; the workflow behind it is not. Space them so a fifteen-company refresh
# does not queue fifteen concurrent runners against the same repository.
DISPATCH_PAUSE_S = 20


class RefreshError(Exception):
    pass


def onboarded_tickers(companies_dir: str = "companies") -> list:
    """Every company with a committed config. The refresh follows the configs rather than a
    second list, so a company cannot be onboarded into the system and left out of the refresh."""
    out = set()
    for p in glob.glob(os.path.join(companies_dir, "*.yaml")):
        t = os.path.splitext(os.path.basename(p))[0].upper()
        if t:
            out.add(t)
    # Sorted AFTER uppercasing, not before: sorting the filenames puts a lower-case config
    # after every upper-case one, so the dispatch order stopped matching the printed order.
    return sorted(out)


def _api(path: str, token: str, method: str = "GET", body=None):
    req = urllib.request.Request(
        API + path, method=method,
        data=(json.dumps(body).encode() if body is not None else None),
        headers={"Authorization": "Bearer " + token,
                 "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json",
                 "User-Agent": "aeg-rate-refresh"})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
        return r.status, (json.loads(raw) if raw else None)


def dispatch(ticker: str, token: str, ref: str = "main") -> None:
    """Ask real-yields to rebuild this company's rate side, reusing its recorded durability."""
    path = f"/repos/{RY_OWNER}/{RY_REPO}/actions/workflows/{RY_WORKFLOW}/dispatches"
    status, _ = _api(path, token, "POST",
                     {"ref": ref,
                      "inputs": {"ticker": ticker, "obs_category": "KEEP", "ory_override": ""}})
    if status != 204:
        raise RefreshError(f"dispatch returned HTTP {status}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Refresh every onboarded company's rate side.")
    ap.add_argument("--companies-dir", default="companies")
    ap.add_argument("--only", default=None, help="comma-separated tickers (a smoke run)")
    ap.add_argument("--dry-run", action="store_true",
                    help="list what would be dispatched and exit 0 without dispatching")
    ap.add_argument("--pause", type=float, default=DISPATCH_PAUSE_S)
    a = ap.parse_args(argv)

    tickers = ([t.strip().upper() for t in a.only.split(",") if t.strip()]
               if a.only else onboarded_tickers(a.companies_dir))
    if not tickers:
        print("no onboarded companies found — nothing to refresh", file=sys.stderr)
        return 2

    print(f"rate refresh: {len(tickers)} onboarded companies -> "
          f"{RY_OWNER}/{RY_REPO} {RY_WORKFLOW} (obs_category=KEEP)")
    for t in tickers:
        print(f"  {t}")
    if a.dry_run:
        print("\n--dry-run: nothing dispatched")
        return 0

    token = os.environ.get("CROSS_REPO_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        print("CROSS_REPO_TOKEN not set — a cross-repository dispatch needs a token with "
              "actions:write on real-yields. The default GITHUB_TOKEN cannot reach another "
              "repository.", file=sys.stderr)
        return 2

    failed = []
    for i, t in enumerate(tickers, 1):
        try:
            dispatch(t, token)
            print(f"  [{i}/{len(tickers)}] {t} dispatched")
        except (RefreshError, urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
            failed.append((t, str(e)[:120]))
            print(f"  [{i}/{len(tickers)}] {t} FAILED: {e}", file=sys.stderr)
        if i < len(tickers):
            time.sleep(a.pause)

    print(f"\ndispatched {len(tickers) - len(failed)}/{len(tickers)}")
    if failed:
        # Loud in aggregate. A refresh that quietly skipped part of the fleet is how the fleet
        # gets old, and the age is exactly what nothing was watching before.
        print("FAILED: " + ", ".join(f"{t} ({e})" for t, e in failed), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
