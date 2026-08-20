#!/usr/bin/env python3
"""
tests/test_idio_company_curve.py — the wire itself.

`idio/company_curve.py` is the function that fills `finrate_idio`, the row that carried thirty
zeros from the day it was installed until 2026-08-20. Everything in this file is about the two
ways that wire can fail while every other check in the repository stays green:

  IT COULD GO BACK TO ZERO.   A premium that silently becomes zero puts every company back on the
                              market rate, and the four-method tie -- an internal-consistency
                              proof -- ties perfectly either way. So the tests assert the series
                              is NOT inert, that it MOVES when its inputs move, and that every
                              missing input REFUSES rather than defaulting.
  IT COULD BE OFF BY A HUNDRED. `idio/erp.py` works in percentage points and the engine's Market
                              Data rows are annual decimals. A units slip is a hundredfold error
                              in every discount rate on the system, and it would tie.

No network: the market ERP curve is passed in by the caller, which is also how the real code
takes it, so the premium is always normalized against the same curve the valuation is using.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "idio"))

import erp as IE            # noqa: E402
import company_curve as CC  # noqa: E402

OUT = os.path.join(ROOT, "outputs")

# A market ERP curve in ANNUAL DECIMALS, the shape rate_feed delivers: ~4.1% at the front
# decaying to ~2.0% at thirty years.
MKT = [(0.0413 - (0.0413 - 0.0204) * (t - 1) / 29.0) for t in range(1, 31)]


def _needs_live_credit():
    try:
        IE.mel.fetch_market_credit(log=None)
        return False
    except Exception:
        return True


live = pytest.mark.skipif(_needs_live_credit(),
                          reason="COMMON(t) is read live off real-yields; no network here")


# ------------------------------------------------------------------ units

def test_units_percentage_points_in_annual_decimals_out():
    """The single most dangerous mistake in this file, and the cheapest to check."""
    assert CC._pct(0.0413) == pytest.approx(4.13)
    assert CC._dec(4.13) == pytest.approx(0.0413)
    assert CC._dec(CC._pct(0.0413)) == pytest.approx(0.0413)


@live
def test_the_series_is_in_decimals_not_percentage_points():
    r = CC.build("KO", MKT, outdir=OUT, log=None)
    s, p = r["series"], r["provenance"]
    # The provenance is in pp, the series in decimals: they must differ by exactly 100.
    assert s[0] == pytest.approx(p["premium_1y_pp"] / 100.0, abs=1e-8)   # provenance is rounded to 6dp in pp
    assert s[29] == pytest.approx(p["premium_30y_pp"] / 100.0, abs=1e-8)
    assert max(abs(x) for x in s) < 0.15, "a premium above 15 percentage points is a units slip"


@live
def test_the_series_has_exactly_thirty_tenors():
    """set_idio raises on any other length; better to fail here, where the message is useful."""
    assert len(CC.build("KO", MKT, outdir=OUT, log=None)["series"]) == 30


# ------------------------------------------------------------------ not inert

@live
def test_the_premium_is_not_zero():
    """The failure this whole change exists to end. A zero series is indistinguishable from the
    unwired state, and it ties."""
    s = CC.build("KO", MKT, outdir=OUT, log=None)["series"]
    assert any(abs(x) > 1e-9 for x in s), "the premium is inert — this is the unwired state"


@live
def test_a_riskier_company_pays_more_than_a_safer_one():
    """The ordering the statistic exists to produce. If this ever fails the premium has stopped
    depending on the risk measure, which no identity check can see."""
    ko = CC.build("KO", MKT, outdir=OUT, log=None)["provenance"]
    snps = CC.build("SNPS", MKT, outdir=OUT, log=None)["provenance"]
    assert ko["semidev"] < snps["semidev"]
    assert ko["premium_collapsed_pp"] < snps["premium_collapsed_pp"]
    assert ko["premium_collapsed_pp"] < 0 < snps["premium_collapsed_pp"], (
        "a company well below the cap-weighted average risk should earn a DISCOUNT, and one "
        "well above should pay a premium")


@live
def test_the_premium_moves_when_the_market_curve_moves():
    """It is normalized against the market ERP the valuation is using, so it cannot be
    indifferent to it."""
    a = CC.build("KO", MKT, outdir=OUT, log=None)["provenance"]["premium_1y_pp"]
    b = CC.build("KO", [x * 1.5 for x in MKT], outdir=OUT, log=None)["provenance"]["premium_1y_pp"]
    assert abs(b - a) > 1e-6, "the premium ignored a 50% move in the market ERP"


@live
def test_an_out_of_universe_company_can_be_priced_on_its_own_statistic():
    """A name that is not an index constituent still gets a premium, from its own measured
    semi-deviation, against the index it is being compared to."""
    r = CC.build("ZZZZ", MKT, outdir=OUT, semidev_override=40.0, log=None)
    p = r["provenance"]
    assert p["in_universe"] is False
    assert p["semidev"] == pytest.approx(40.0)
    assert p["premium_collapsed_pp"] > 0


# ------------------------------------------------------------------ refuses, never defaults

def test_a_company_with_no_risk_statistic_refuses():
    """Giving it zero would price it as exactly average, silently — the whole defect in one
    line."""
    with pytest.raises(CC.PremiumRefused, match="no risk statistic"):
        CC.build("NOTATICKER", MKT, outdir=OUT, log=None)


def test_a_short_market_curve_refuses():
    with pytest.raises(CC.PremiumRefused, match="tenors"):
        CC.build("KO", MKT[:10], outdir=OUT, log=None)


def test_a_missing_universe_refuses(tmp_path):
    with pytest.raises(CC.PremiumRefused, match="universe is unusable"):
        CC.build("KO", MKT, outdir=str(tmp_path), log=None)


def test_an_unknown_durability_category_refuses():
    with pytest.raises(CC.PremiumRefused, match="durability category"):
        CC.build("KO", MKT, outdir=OUT, obs_category="Q", log=None)


# ------------------------------------------------------------------ obsolescence honesty

def test_region3_is_declared_invisible_on_a_thirty_tenor_grid():
    """It is zero at EVERY category on a 1..30 grid, because the earliest onset is year 30. The
    provenance says so on every run, so nobody can read the zero as evidence that obsolescence
    has been priced. This is the assertion that has to fail the day the terminal grid lands."""
    assert CC.region3_is_visible(IE.GRID) is False
    for cat, ory in CC.CATEGORY_ORY.items():
        r3 = IE.region3(ory)
        assert all(abs(v) < 1e-12 for v in r3.values()), (cat, ory)


@live
def test_the_provenance_records_that_obsolescence_did_not_enter():
    p = CC.build("KO", MKT, outdir=OUT, log=None)["provenance"]
    assert p["region3_visible_on_this_grid"] is False
    assert p["region3_30y_pp"] == pytest.approx(0.0, abs=1e-12)
    assert p["declared_obsolescence_year"] in CC.CATEGORY_ORY.values()


@live
def test_the_provenance_carries_what_a_reader_needs_to_audit_the_number():
    p = CC.build("KO", MKT, outdir=OUT, log=None)["provenance"]
    for k in ("semidev", "capw_avg_semidev", "semidev_ratio", "universe_asof",
              "issuer_curves_generated", "common_vintage", "m_common", "region2_tier",
              "premium_collapsed_pp"):
        assert k in p and p[k] is not None, k
