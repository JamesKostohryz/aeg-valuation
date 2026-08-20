#!/usr/bin/env python3
"""
idio/bond_reprice.py — re-price the issuer bonds, so the credit curves are not a fossil.

A PORT of AEG-Project `tools/bond_eod_pull.py` + `tools/bond_spread_build2.py`, joined into one
module. The pricing arithmetic is carried across UNCHANGED -- the clean-price function, the
bisection yield to maturity, the 50-basis-point vendor-disagreement drop, the FRED pillar
interpolation onto each bond's OWN quote date, the 1-basis-point spread floor and the null-yield
rule are the same lines. `tests/test_bond_reprice.py` proves it reproduces the committed
`data/bond_spreads/bond_spreads_live.csv` BYTE FOR BYTE from the 2026-08-17 price cache, so a
drift in the port is distinguishable from a move in the market.

WHY THIS EXISTS. `idio/issuer_curves.py` regenerates the credit curves from
`bond_spreads_live.csv`. Scheduling THAT alone would re-stamp a frozen 2026-08-17 bond snapshot
with a fresh `generated` date every month and buy the system another 45 days of life for prices
that never moved -- a fossil with a new timestamp, which is precisely this project's standing
failure mode. This module is what makes the timestamp true.

WHAT IT COSTS. One EODHD `eod/{CODE}.BOND` call per bond, measured at 10 API units, against a
100,000-unit allowance that resets DAILY. 1,615 named bonds = 16,150 units, about 16% of a
single day's allowance, once a month, at no incremental dollar cost. Approved by James
2026-08-20. `--dry-run` prints the bill and spends nothing.

THE REFERENCE DATA IS STATIC AND COMMITTED. `data/bond_spreads/bond_reference.csv` carries each
bond's issuer, name and coupon -- facts that do not change between now and maturity, distilled
from the 1,615-file `bond_cache` in the working folder so the repository does not carry 6.4 MB
of vendor JSON. Only the PRICE is re-pulled.

    python3 idio/bond_reprice.py --dry-run
    python3 idio/bond_reprice.py --cache /tmp/px --out data/bond_spreads/bond_spreads_live.csv

NOT A VALUATION. No premium, no discount rate, no pricing error is produced here.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def _arg(flag, default=None):
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


REFERENCE = _arg("--reference", os.path.join(REPO, "data", "bond_spreads", "bond_reference.csv"))
OUTFILE = _arg("--out", os.path.join(REPO, "data", "bond_spreads", "bond_spreads_live.csv"))
CACHE = _arg("--cache", os.path.join(REPO, "outputs", ".bond_px_cache"))
FREDDIR = _arg("--fred-cache", os.path.join(REPO, "outputs", ".fred_cache"))
FROM = _arg("--from", "")            # blank -> 11 weeks back from today, as the original did
WORKERS = int(_arg("--workers", "16"))
API_UNITS_PER_BOND = 10              # MEASURED 2026-08-17, not estimated. See the pre-commitment.

# ---- carried across verbatim from bond_spread_build2.py -------------------------------------
PILLARS = [("DGS3MO", 0.25), ("DGS1", 1.0), ("DGS2", 2.0), ("DGS3", 3.0),
           ("DGS5", 5.0), ("DGS7", 7.0), ("DGS10", 10.0), ("DGS20", 20.0),
           ("DGS30", 30.0)]
M1 = re.compile(r'(\d{1,2})([A-Za-z]{3})(\d{4})')
M2 = re.compile(r'(\d{1,2})-([A-Za-z]{3})-(\d{2})\b')
CPN = re.compile(r'(\d+(?:\.\d+)?)\s*%')
CPN2 = re.compile(r'^\s*\S+\s+(\d+(?:\.\d+)?)\s+\d{1,2}-[A-Za-z]{3}-\d{2}')
MON = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


class BondRepriceError(RuntimeError):
    pass


# ================================================================= the Treasury leg (FRED)

def fred_series(s):
    p = os.path.join(FREDDIR, s + ".csv")
    if not os.path.exists(p):
        u = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={s}"
        open(p, "wb").write(urllib.request.urlopen(u, timeout=60).read())
    out = {}
    for row in csv.reader(open(p)):
        if len(row) < 2 or row[0] in ("observation_date", "DATE"):
            continue
        try:
            out[date.fromisoformat(row[0])] = float(row[1]) / 100.0
        except ValueError:
            continue
    return out


def build_curves():
    os.makedirs(FREDDIR, exist_ok=True)
    ser = {s: fred_series(s) for s, _ in PILLARS}
    days = sorted(set().union(*[set(v) for v in ser.values()]))
    curves = {}
    for d in days:
        pts = [(t, ser[s][d]) for s, t in PILLARS if d in ser[s]]
        if len(pts) >= 6:
            curves[d] = sorted(pts)
    return curves


def curve_on(curves, d):
    for k in range(0, 12):
        c = curves.get(d - timedelta(days=k))
        if c:
            return c, d - timedelta(days=k)
    return None, None


def interp(pts, t):
    if t <= pts[0][0]:
        return pts[0][1]
    if t >= pts[-1][0]:
        return pts[-1][1]
    for i in range(1, len(pts)):
        if t <= pts[i][0]:
            (x0, y0), (x1, y1) = pts[i - 1], pts[i]
            return y0 + (y1 - y0) * (t - x0) / (x1 - x0)
    return pts[-1][1]


# ================================================================= bond mechanics, unchanged

def parse_maturity(name):
    m = M1.search(name or "")
    if m and MON.get(m.group(2).lower()):
        try:
            return date(int(m.group(3)), MON[m.group(2).lower()], int(m.group(1)))
        except ValueError:
            return None
    m = M2.search(name or "")
    if m and MON.get(m.group(2).lower()):
        y = int(m.group(3))
        try:
            return date(2000 + y if y < 90 else 1900 + y,
                        MON[m.group(2).lower()], int(m.group(1)))
        except ValueError:
            return None
    return None


def pv(cp, y, T, freq=2):
    """Clean price of a par-100 bond, semi-annual, fractional first period, accrued removed."""
    n, r, c = T * freq, y / freq, cp / 100 * 100 / freq
    if r <= -0.99:
        return 1e9
    frac = n - int(n)
    m = int(n) + (1 if frac > 0 else 0)
    tot = sum(c / (1 + r) ** (k - (1 - frac) if frac > 0 else k) for k in range(1, m + 1))
    tot += 100.0 / (1 + r) ** n
    if frac > 0:
        tot -= c * (1 - frac)          # accrued interest -> clean price
    return tot


def ytm(px, cp, T):
    lo, hi = -0.5, 2.0
    for _ in range(160):
        mid = (lo + hi) / 2
        if pv(cp, mid, T) > px:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


# ================================================================= the pull

def load_reference():
    rows = list(csv.DictReader(open(REFERENCE)))
    if not rows:
        raise BondRepriceError("%s is empty" % REFERENCE)
    return rows


def _fetch(code):
    p = os.path.join(CACHE, code + ".json")
    if os.path.exists(p):
        return 0
    token = os.environ.get("EODHD_API_KEY", "")
    if not token:
        raise BondRepriceError(
            "EODHD_API_KEY is not set. Refusing to pull. In CI it is a repository secret; "
            "locally, export it. It is never printed and never committed.")
    frm = FROM or (date.today() - timedelta(days=77)).isoformat()
    url = f"https://eodhd.com/api/eod/{code}.BOND?api_token={token}&fmt=json&from={frm}"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=45) as r:
                body = r.read().decode("utf-8", "replace")
            try:
                d = json.loads(body)
            except ValueError:
                d = {"_error": body[:120]}
            json.dump(d, open(p, "w"))
            return 1
        except Exception as e:                                   # noqa: BLE001
            if attempt == 2:
                json.dump({"_error": str(e)[:200]}, open(p, "w"))
                return 1
            time.sleep(1.5 * (attempt + 1))
    return 1


def pull_prices(ref):
    os.makedirs(CACHE, exist_ok=True)
    todo = [r["bond_code"] for r in ref
            if not os.path.exists(os.path.join(CACHE, r["bond_code"] + ".json"))]
    # --limit exists because a sandbox session cannot hold a process open long enough to pull
    # three thousand bonds in one call. The pull is resumable by construction (an existing cache
    # file is skipped), so chunking is safe; a partial run leaves a smaller `todo` for the next.
    missing = len(todo)
    limit = int(_arg("--limit", "0") or 0)
    if limit > 0:
        todo = todo[:limit]
    units = len(todo) * API_UNITS_PER_BOND
    print("EODHD PULL: %d bonds already cached, %d missing, %d to pull this call = %s API units "
          "(%.1f%% of a 100,000-unit daily allowance, which resets daily)"
          % (len(ref) - missing, missing, len(todo), "{:,}".format(units), units / 1000.0))
    if "--dry-run" in sys.argv:
        print("  --dry-run: nothing spent, nothing written.")
        return False
    if not todo:
        return True
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        n = sum(ex.map(_fetch, todo))
    print("  pulled %d in %.0fs" % (n, time.time() - t0))
    return True


# ================================================================= the build

def build(ref, curves):
    st = dict(files=0, no_series=0, no_yield=0, no_maturity=0, matured=0, frn=0,
              no_curve=0, no_coupon=0, check_run=0, check_fail=0, floored=0)
    rows = []
    for r in sorted(ref, key=lambda r: r["bond_code"]):
        code = r["bond_code"]
        p = os.path.join(CACHE, code + ".json")
        if not os.path.exists(p):
            continue
        st["files"] += 1
        tkr, sample, cat_name = r["ticker"], r["sample"], r["catalog_name"]
        try:
            ser = json.load(open(p))
        except ValueError:
            ser = None
        if not isinstance(ser, list) or not ser:
            st["no_series"] += 1
            continue
        last = ser[-1]
        y = last.get("yield")
        px = last.get("price")
        # A yield of exactly 0 is this feed's null, not a rate: 83 rows carried it, several on
        # bonds priced at 99 with a 3.9% coupon. Treated as missing, not floored to 1bp.
        if y is None or px is None or float(y) <= 0:
            st["no_yield"] += 1
            continue
        qdate = date.fromisoformat(last["date"])

        name = r["vendor_name"] or cat_name or ""
        if "FRN" in name.upper():
            st["frn"] += 1
            continue
        mat = parse_maturity(name) or parse_maturity(cat_name)
        if mat is None:
            st["no_maturity"] += 1
            continue
        tenor = (mat - qdate).days / 365.25
        if tenor <= 0:
            st["matured"] += 1
            continue

        cur, cdate = curve_on(curves, qdate)
        if cur is None:
            st["no_curve"] += 1
            continue

        y = float(y) / 100.0
        px = float(px)
        try:
            cp = float(r["coupon"])
        except (TypeError, ValueError):
            cp = None
        if cp is None:
            m = CPN.search(name) or CPN2.search(name) or CPN.search(cat_name) \
                or CPN2.search(cat_name)
            cp = float(m.group(1)) if m else None

        gap = None
        if cp is not None:
            st["check_run"] += 1
            gap = ytm(px, cp, tenor) - y
            if abs(gap) > 0.005:                 # 50bp vendor disagreement -> DROP, per section 8
                st["check_fail"] += 1
                continue
        else:
            st["no_coupon"] += 1

        tsy = interp(cur, tenor)
        sp = y - tsy
        if sp < 0.0001:
            st["floored"] += 1
            sp = 0.0001
        rows.append(dict(
            ticker=tkr, sample=sample, bond_code=code, bond_name=name,
            quote_date=qdate.isoformat(), curve_date=cdate.isoformat(),
            maturity=mat.isoformat(), tenor_yrs=round(tenor, 4),
            coupon=cp, price=round(px, 4), yield_pct=round(y * 100, 4),
            tsy_pct=round(tsy * 100, 4), spread_bp=round(sp * 10000, 2),
            ytm_check_gap_bp=None if gap is None else round(gap * 10000, 1)))

    rows.sort(key=lambda r: (r["ticker"], r["tenor_yrs"]))
    return rows, st


def report(rows, st):
    print("\nBUILD LEDGER - every bond accounted for")
    for k, v in st.items():
        print(f"  {k:14s} {v}")
    print(f"  USABLE         {len(rows)}")
    print(f"  companies total: {len({r['ticker'] for r in rows})}")
    print("\nF8 INERT-COLUMN CHECK (non-null / distinct / min / median / max)")
    for col in ("tenor_yrs", "yield_pct", "tsy_pct", "spread_bp", "price"):
        v = sorted(r[col] for r in rows if r[col] is not None)
        print(f"  {col:11s} {len(v):5d} / {len(set(v)):5d} / {v[0]:9.2f} / "
              f"{v[len(v)//2]:9.2f} / {v[-1]:9.2f}")
    today = date.today()
    qa = sorted((today - date.fromisoformat(r["quote_date"])).days for r in rows)
    print(f"  quote age days vs today: median {qa[len(qa)//2]}  "
          f"p90 {qa[9*len(qa)//10]}  max {qa[-1]}")


def main():
    ref = load_reference()
    print("REFERENCE: %d bonds across %d issuers (committed, static)"
          % (len(ref), len({r["ticker"] for r in ref})))
    if not pull_prices(ref):
        return 0
    curves = build_curves()
    print("FRED curves loaded: %d dates, latest %s" % (len(curves), max(curves)))
    rows, st = build(ref, curves)
    if not rows:
        raise BondRepriceError("the build produced zero usable bonds. Refusing to write an "
                               "empty file over a good one.")
    os.makedirs(os.path.dirname(OUTFILE) or ".", exist_ok=True)
    with open(OUTFILE, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    report(rows, st)
    print("\nWROTE %s -- %d bonds" % (OUTFILE, len(rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
