#!/usr/bin/env python3
"""
tests/test_tradingview_bonds.py — the better bond source, and the traps in it.

WHY THIS SOURCE EXISTS AT ALL is a defect, not a preference, and the fixture in this file IS
that defect: EODHD priced the Activision Blizzard 3.4% Jun-2027 at 98.27 (yield 5.575%, and
every print carrying volume 0) while ICE/FactSet priced it at 99.08. 102 basis points on a
0.82-year bond. It inverted Microsoft's entire fitted credit curve, and our integrity check
passed it at -0.5bp because that check compares the vendor's yield with the vendor's own price.

Three things are guarded here, and the middle one is the one nobody would have predicted.

  THE ARITHMETIC IS OURS, NOT THEIRS. TradingView publishes yield to WORST. We compute yield to
  MATURITY from their price, coupon and maturity with the SAME bisection the EODHD path uses,
  and keep their yield to worst as a cross-check -- which is a better check than the one it
  replaces, because it is against an independent vendor rather than the same vendor's other
  column. The test pins that agreement on real bonds from 0.8 to 35 years.

  THE SAME BOND IS LISTED TWICE. Re-badged acquisition paper appears under BOTH the legacy
  issuer and the acquirer -- the Activision 3.4% Jun-2027 as a $45m NR line at 99.08 and as a
  $354m AAA line at 99.71. Same coupon, same maturity, one bond, and the two rows are 58 basis
  points apart, which is wider than Microsoft's entire credit curve. Fitting both double-counts
  it AND drags the front end. This is the trap that comes WITH the better source, and it is
  invisible unless you look for it: both rows are real, both are correctly priced by their own
  lights, and nothing about them is malformed.

  CURRENCY. Microsoft's euro paper sits on the same page and cannot be struck against a US
  Treasury curve. Dropped, and counted.

HERMETIC. The fixture is a frozen copy of Microsoft's published page as fetched 2026-08-20.
"""
import csv
import math
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "idio"))

import tradingview_bonds as TV   # noqa: E402
from bond_reprice import ytm     # noqa: E402

PAGE = os.path.join(ROOT, "tests", "golden", "tradingview", "MSFT_2026-08-20.md")
FRED = os.path.join(ROOT, "tests", "golden", "bond_reprice", "fred")


def _rows():
    return TV.parse_page(open(PAGE, encoding="utf-8").read())


def _spreads(**kw):
    import bond_reprice as BR
    BR.FREDDIR = FRED                       # frozen Treasury pillars; no network
    return TV.to_spreads(_rows(), "MSFT", quote_date="2026-08-20",
                         curves=BR.build_curves(), log=None, **kw)


# ------------------------------------------------------------------ parsing

def test_the_published_table_parses():
    rows = _rows()
    assert len(rows) == 35, "expected the 35 rows on Microsoft's page, got %d" % len(rows)
    r = [x for x in rows if "3.041%" in x["name"]][0]
    assert r["price"] == 55.58 and r["coupon"] == 3.041 and r["maturity"] == "2062-03-17"
    assert r["amount"] == 1.93e9 and r["currency"] == "USD" and r["sp_rating"] == "AAA"


def test_the_amount_outstanding_is_read_and_scaled():
    """The field that makes size-weighting possible, and the reason one $45m stub could move a
    curve fitted on $6.25bn benchmarks."""
    rows = _rows()
    amts = [r["amount"] for r in rows if r["amount"]]
    assert max(amts) == 6.25e9 and min(amts) == 5.65e6
    assert max(amts) / min(amts) > 1000


def test_the_legal_issuer_is_carried_so_acquisitions_are_visible():
    """TradingView attributes the Activision paper to Microsoft. That is the whole reason the
    alias table in idio/bond_coverage.py had to be hand-patched for EODHD."""
    iss = {r["issuer"] for r in _rows()}
    assert "Activision Blizzard, Inc." in iss and "Microsoft Corp." in iss


def test_a_page_with_no_table_refuses_rather_than_returning_nothing():
    with pytest.raises(TV.TradingViewParseError):
        TV.parse_page("# Some page\n\nNo bonds here.\n")


# ------------------------------------------------------------------ our arithmetic vs theirs

def test_our_yield_to_maturity_agrees_with_their_yield_to_worst():
    """The replacement integrity gate. If this drifts, either the bisection is wrong or the
    page's price and yield columns disagree -- and either is a reason to stop."""
    from datetime import date
    qd = date(2026, 8, 20)
    gaps = []
    for r in _rows():
        if r["ytw_pct"] is None or r["currency"] != "USD":
            continue
        T = (date.fromisoformat(r["maturity"]) - qd).days / 365.25
        if T <= 0:
            continue
        gaps.append((abs(ytm(r["price"], r["coupon"], T) * 10000 - r["ytw_pct"] * 100),
                     r["name"]))
    gaps.sort()
    med = gaps[len(gaps) // 2][0]
    p90 = gaps[int(0.9 * len(gaps))][0]
    # THE DISTRIBUTION, NOT THE WORST CASE. A single loose threshold set above the worst bond
    # tells you nothing and quietly ratchets upward every time one bond misbehaves. The median
    # is the statement that the arithmetic is right; the tail is a statement about individual
    # bonds, and one of them IS different: Microsoft's 4.875% Dec-2043 sits 10.3bp off, alone,
    # against a median of 0.6bp. It is below par, so yield to worst should equal yield to
    # maturity, and it does not -- most likely a make-whole call priced to a par call date.
    # Worth knowing, not worth dropping, and nowhere near the 50bp production gate.
    assert med < 2.0, "median yield disagreement %.2f bp -- the bisection is wrong" % med
    assert p90 < 5.0, "p90 yield disagreement %.2f bp" % p90
    assert gaps[-1][0] < TV.MAX_YTM_YTW_GAP_BP, (
        "%s disagrees by %.1f bp, past the production gate" % (gaps[-1][1], gaps[-1][0]))
    outliers = [(g, n) for g, n in gaps if g > 5.0]
    assert len(outliers) <= 1, "more than one bond now disagrees materially: %s" % outliers


def test_a_bond_whose_price_and_yield_disagree_is_dropped():
    """The 50bp gate must DISCRIMINATE, not merely exist. A guard that never fires and a guard
    that always fires look identical from the outside."""
    rows = _rows()
    victim = [r for r in rows if r["ytw_pct"] is not None and r["currency"] == "USD"][0]
    victim = dict(victim, ytw_pct=victim["ytw_pct"] + 5.0)   # 500bp off
    import bond_reprice as BR
    BR.FREDDIR = FRED
    out, st = TV.to_spreads([victim], "MSFT", quote_date="2026-08-20",
                            curves=BR.build_curves(), log=None)
    assert st["check_fail"] == 1 and not out


# ------------------------------------------------------------------ the duplicate-listing trap

def test_the_same_bond_listed_twice_is_de_duplicated():
    """One bond, one coupon, one maturity, two rows, 58 basis points apart."""
    out, st = _spreads()
    assert st.get("deduped", 0) == 5, (
        "expected 5 duplicate listings on this page (the re-badged Activision paper); got %s. "
        "If this is 0 the de-duplication has stopped working and the front of every acquirer's "
        "curve is double-counted." % st.get("deduped"))
    keys = [(round(float(r["coupon"]), 4), r["maturity"]) for r in out]
    assert len(keys) == len(set(keys)), "a duplicate issue survived: %s" % keys


def test_de_duplication_keeps_the_larger_line_not_the_legacy_stub():
    out, _ = _spreads()
    r = [x for x in out if x["maturity"] == "2027-06-15"][0]
    assert r["amount_outstanding"] == 353_600_000, (
        "de-duplication kept the $45m unexchanged Activision rump over the $354m re-badged "
        "line. The rump is the worse-marked of the two and it is 58bp wider.")
    assert float(r["spread_bp"]) < 20.0


def test_euro_paper_is_dropped_not_struck_against_a_treasury_curve():
    out, st = _spreads()
    assert st["not_usd"] == 2
    assert all(r["ticker"] == "MSFT" for r in out)


# ------------------------------------------------------------------ what it buys

def test_the_curve_is_upward_sloping_and_well_determined():
    """The point of the exercise. On EODHD's data Microsoft's fitted curve INVERTED -- slope
    -0.142, t = -1.94, R-squared 0.158 -- and the quality gate demoted it to tier 2, correctly,
    on data that was wrong. On this source it is a real credit curve.

    If this ever fails, do not adjust the threshold. Look at the bonds."""
    out, _ = _spreads()
    use = [r for r in out if 0.5 <= float(r["tenor_yrs"]) <= 50]
    x = [math.log(float(r["tenor_yrs"])) for r in use]
    y = [float(r["spread_bp"]) / 100.0 for r in use]
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((v - mx) ** 2 for v in x)
    b = sum((x[i] - mx) * (y[i] - my) for i in range(n)) / sxx
    res = [y[i] - (my - b * mx + b * x[i]) for i in range(n)]
    sse = sum(r * r for r in res)
    sst = sum((v - my) ** 2 for v in y)
    t = b / math.sqrt((sse / (n - 2)) / sxx)
    assert b > 0, "Microsoft's credit curve should widen with tenor, not invert (b=%.4f)" % b
    assert t > 2.0, "the slope must clear the tier-1 t-statistic gate (t=%.2f)" % t
    assert 1 - sse / sst > 0.5, "R-squared %.3f -- the shape is not determined" % (1 - sse / sst)


def test_size_weighting_tightens_the_fit_rather_than_changing_its_sign():
    """Weighting by amount outstanding is a GATED change to the fitter, not landed yet. What is
    asserted here is only that it is an improvement in precision and not a change of story: a
    weighting scheme that flipped a slope would be choosing an answer, not measuring one."""
    out, _ = _spreads()
    use = [r for r in out if 0.5 <= float(r["tenor_yrs"]) <= 50]
    x = [math.log(float(r["tenor_yrs"])) for r in use]
    y = [float(r["spread_bp"]) / 100.0 for r in use]
    w = [float(r["amount_outstanding"] or 1) for r in use]

    def slope(weights):
        W = sum(weights)
        mx = sum(a * b for a, b in zip(weights, x)) / W
        my = sum(a * b for a, b in zip(weights, y)) / W
        sxx = sum(wi * (xi - mx) ** 2 for wi, xi in zip(weights, x))
        return sum(wi * (xi - mx) * (yi - my) for wi, xi, yi in zip(weights, x, y)) / sxx

    assert slope([1.0] * len(x)) > 0 and slope(w) > 0
    assert abs(slope(w) - slope([1.0] * len(x))) < 0.15


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
