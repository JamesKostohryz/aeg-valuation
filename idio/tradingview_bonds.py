#!/usr/bin/env python3
"""
idio/tradingview_bonds.py — the bonds of the company being valued, from the better source.

WHY THIS EXISTS, AND IT IS NOT A PREFERENCE. On 2026-08-20 EODHD priced the Activision
Blizzard 3.4% Jun-2027 -- a bond Microsoft inherited in 2023 -- at 98.27, yielding 5.575%.
TradingView, off ICE Data Services and FactSet, prices the same bond at 99.08, and an
independent bisection from that price, coupon and maturity gives 4.552%. That is 102 basis
points on a 0.82-year bond, and every EODHD print for it carries `volume: 0`, so they are
stale marks rather than trades. It inverted Microsoft's whole fitted credit curve.

Our integrity check PASSED it, at -0.5bp, because it compares the vendor's yield with the
vendor's price. It cannot see a wrong price. Internally consistent, externally wrong, every
gate green -- the shape of every defect on this project's standing-suspicion list.

WHAT THIS SOURCE ADDS THAT EODHD CANNOT
  ISSUER IDENTITY, ALREADY RIGHT.   TradingView lists the Activision bonds on Microsoft's own
      page and FINRA has re-badged them MSFT58280xx. The alias table in idio/bond_coverage.py
      exists only because EODHD's master does not know who owns what. This source does.
  AMOUNT OUTSTANDING.   The fit is equal-weighted, so a $45m unrated stub counts as much as a
      $6.25bn AAA benchmark. That is how one bad quote on one tiny bond moved a curve. With the
      amount outstanding, it can be weighted properly.
  AGENCY RATINGS.   S&P and Fitch, per bond. `synthetic_rating.py` infers a rating from
      interest coverage, which is meaningless for a financial -- it rates JPMorgan CCC.

YIELD TO MATURITY, NOT YIELD TO WORST. TradingView publishes yield to worst. James pointed out
that it also publishes price, coupon and maturity, which is everything the bisection needs, so
we compute YTM ourselves with the SAME function the EODHD path uses and keep their YTW as the
cross-check. That is strictly better than the check it replaces: it compares our arithmetic
against an INDEPENDENT vendor rather than against the same vendor's other column. Validated on
eleven Microsoft and Activision bonds from 0.8 to 35 years -- agreement within 2 basis points.

USD ONLY. Microsoft's EUR paper is on the same page and cannot be struck against a US Treasury
curve. It is dropped, and counted in the ledger rather than silently skipped.

HOW IT IS USED. Not scraped on a schedule -- the data is ICE/FactSet licensed and automated
collection is against TradingView's terms. The page is fetched in-session, by a person or an
assistant working WITH that person, for the one company being valued, and handed to this
module. That also matches how the system is used: valuations happen on demand, not on a cron.

    python3 idio/tradingview_bonds.py --ticker MSFT --page msft.md \\
        --out data/bond_spreads/tv_MSFT.csv

NOT A VALUATION.
"""
from __future__ import annotations

import csv
import os
import re
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from bond_reprice import build_curves, curve_on, interp, ytm   # noqa: E402  the SAME arithmetic


def _arg(flag, default=None):
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


# The published table is: Symbol | YTW % | Price % | Coupon % | Maturity | Outstanding |
#                         Face value | S&P | Fitch | Issuer
_PCT = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*%\s*$")
_ISO = re.compile(r"^\s*(\d{4}-\d{2}-\d{2})\s*$")
_AMT = re.compile(r"([\d,]+(?:\.\d+)?)\s*([KMB]?)\s*([A-Z]{3})")
_MULT = {"": 1.0, "K": 1e3, "M": 1e6, "B": 1e9}
_TITLE = re.compile(r'\[([^\]]+)\]\([^)]*\)\s*$')


class TradingViewParseError(RuntimeError):
    pass


def _num(cell):
    m = _PCT.match(cell or "")
    return float(m.group(1)) if m else None


def _amount(cell):
    m = _AMT.search(cell or "")
    if not m:
        return None, None
    return float(m.group(1).replace(",", "")) * _MULT.get(m.group(2), 1.0), m.group(3)


def _label(cell):
    """The human bond name out of the markdown link soup in the first column."""
    m = _TITLE.search((cell or "").strip())
    if m:
        return m.group(1).strip()
    parts = re.findall(r"\[([^\]]+)\]", cell or "")
    return (parts[-1] if parts else (cell or "")).strip()


def parse_page(text):
    """Rows off a fetched TradingView bond page. Tolerant of the surrounding page furniture:
    only lines that look like a data row of the right shape are taken."""
    out = []
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 9:
            continue
        ytw, px, cpn = _num(cells[1]), _num(cells[2]), _num(cells[3])
        mat = _ISO.match(cells[4])
        if px is None or cpn is None or not mat:
            continue                       # header, separator, or a row without a price
        amt, amt_ccy = _amount(cells[5])
        face, face_ccy = _amount(cells[6])
        out.append(dict(name=_label(cells[0]), ytw_pct=ytw, price=px, coupon=cpn,
                        maturity=mat.group(1), amount=amt, currency=face_ccy or amt_ccy,
                        sp_rating=(cells[7] or "").strip(),
                        fitch_rating=(cells[8] or "").strip(),
                        issuer=_label(cells[9]) if len(cells) > 9 else ""))
    if not out:
        raise TradingViewParseError(
            "no bond rows found on this page. Expected the published table "
            "Symbol | YTW %% | Price %% | Coupon %% | Maturity | Outstanding | Face | S&P | "
            "Fitch | Issuer.")
    return out


MAX_YTM_YTW_GAP_BP = 50.0     # the same 50bp limit the EODHD path uses, against a better column


def to_spreads(rows, ticker, quote_date=None, curves=None, log=print):
    """Bond rows -> the bond_spreads_live shape the fitter consumes, plus amount_outstanding.

    The spread is struck on OUR yield to maturity, computed from THEIR price, coupon and
    maturity, against the Treasury curve of the quote date.
    """
    qd = date.fromisoformat(quote_date) if quote_date else date.today()
    curves = curves if curves is not None else build_curves()
    cur, cdate = curve_on(curves, qd)
    if cur is None:
        raise TradingViewParseError("no Treasury curve within 12 days of %s" % qd)

    out = []
    st = dict(rows=len(rows), not_usd=0, matured=0, no_price=0, check_run=0, check_fail=0,
              floored=0)
    for r in rows:
        if (r["currency"] or "USD") != "USD":
            st["not_usd"] += 1                      # EUR paper cannot be struck against DGS
            continue
        mat = date.fromisoformat(r["maturity"])
        tenor = (mat - qd).days / 365.25
        if tenor <= 0:
            st["matured"] += 1
            continue
        if not r["price"] or r["price"] <= 0:
            st["no_price"] += 1
            continue
        y = ytm(r["price"], r["coupon"], tenor)
        gap = None
        if r["ytw_pct"] is not None:
            st["check_run"] += 1
            gap = (y * 100 - r["ytw_pct"]) * 100     # basis points
            if abs(gap) > MAX_YTM_YTW_GAP_BP:
                st["check_fail"] += 1
                continue
        tsy = interp(cur, tenor)
        sp = y - tsy
        if sp < 0.0001:
            st["floored"] += 1
            sp = 0.0001
        out.append(dict(
            ticker=ticker, sample="tradingview", bond_code="TV:%s" % r["name"][:48],
            bond_name=r["name"], quote_date=qd.isoformat(), curve_date=cdate.isoformat(),
            maturity=r["maturity"], tenor_yrs=round(tenor, 4), coupon=r["coupon"],
            price=round(r["price"], 4), yield_pct=round(y * 100, 4),
            tsy_pct=round(tsy * 100, 4), spread_bp=round(sp * 10000, 2),
            ytm_check_gap_bp=None if gap is None else round(gap, 1),
            amount_outstanding=None if r["amount"] is None else int(r["amount"]),
            sp_rating=r["sp_rating"], fitch_rating=r["fitch_rating"], issuer=r["issuer"]))
    # ------------------------------------------------------------------ DE-DUPLICATION
    # THE SAME BOND IS LISTED TWICE when an acquired issuer's paper has been re-badged. The
    # Activision 3.4% Jun-2027 appears as ATVI (legacy CUSIP US00507VAM19, $45m, NR, priced
    # 99.08) AND as MSFT5828001 (re-badged, $354m, AAA, priced 99.71). One bond, one coupon,
    # one maturity, two rows -- and 58 BASIS POINTS apart, which is more than the whole width
    # of Microsoft's credit curve. Fitting both double-counts it and drags the front end.
    #
    # The larger amount outstanding wins: the re-badged line carries the full remaining issue
    # and the legacy line is the unexchanged rump, so the bigger one is the better-traded and
    # better-marked of the two. Recorded, never silent.
    best = {}
    for r in out:
        k = (round(float(r["coupon"]), 4), r["maturity"])
        prev = best.get(k)
        if prev is None or (r["amount_outstanding"] or 0) > (prev["amount_outstanding"] or 0):
            if prev is not None:
                st["deduped"] = st.get("deduped", 0) + 1
                if log:
                    log("  DUPLICATE ISSUE %s %s: keeping %s ($%.0fm, %sbp) over %s ($%.0fm, %sbp)"
                        % (r["coupon"], r["maturity"], r["issuer"] or "?",
                           (r["amount_outstanding"] or 0) / 1e6, r["spread_bp"],
                           prev["issuer"] or "?", (prev["amount_outstanding"] or 0) / 1e6,
                           prev["spread_bp"]))
            best[k] = r
        else:
            st["deduped"] = st.get("deduped", 0) + 1
    out = list(best.values())
    out.sort(key=lambda r: r["tenor_yrs"])
    if log:
        log("TRADINGVIEW LEDGER for %s - every row accounted for" % ticker)
        for k, v in st.items():
            log("  %-12s %d" % (k, v))
        log("  USABLE       %d" % len(out))
        if out:
            amts = [r["amount_outstanding"] for r in out if r["amount_outstanding"]]
            log("  tenors %.2fy to %.2fy ; spreads %.1f to %.1f bp"
                % (out[0]["tenor_yrs"], out[-1]["tenor_yrs"],
                   min(r["spread_bp"] for r in out), max(r["spread_bp"] for r in out)))
            if amts:
                log("  amount outstanding: smallest $%.0fm, largest $%.0fm, ratio %.0fx"
                    % (min(amts) / 1e6, max(amts) / 1e6, max(amts) / max(min(amts), 1)))
            iss = sorted({r["issuer"] for r in out if r["issuer"]})
            if len(iss) > 1:
                log("  legal issuers on this page: %s" % ", ".join(iss))
    return out, st


def write(rows, path):
    if not rows:
        raise TradingViewParseError("refusing to write an empty bond file")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return path


def main():
    ticker = _arg("--ticker")
    page = _arg("--page")
    if not ticker or not page:
        print(__doc__)
        print("ERROR: --ticker and --page are both required.")
        return 2
    rows = parse_page(open(page, encoding="utf-8").read())
    out, _ = to_spreads(rows, ticker, quote_date=_arg("--quote-date"))
    path = write(out, _arg("--out", os.path.join(ROOT, "data", "bond_spreads",
                                                 "tv_%s.csv" % ticker)))
    print("\nWROTE %s -- %d bonds" % (path, len(out)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
