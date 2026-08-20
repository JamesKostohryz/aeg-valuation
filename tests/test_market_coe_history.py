#!/usr/bin/env python3
"""
tests/test_market_coe_history.py — the replacement historical cost of equity, and the thing it replaced.

`real-yields/history/FINAL_decomposition_v4_1877_2026.csv` sat 0.52 percentage points above the
live equity risk premium for the same month -- eff_erp 3.887 against 3.370 for June 2026 -- with
no splice logic anywhere, nothing building the file, and `coe_history.py` reading it from a
hardcoded /tmp path. `coe_history_KO.csv` and the live `coe_v2_KO_latest_annual.csv` were on two
different premium levels at the same time.

It is superseded, not reconciled. This guards the replacement, and in particular guards the two
ways the replacement could quietly become the thing it replaced.
"""
import csv
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "idio"))

import market_coe_history as H   # noqa: E402


def _rows():
    return H.build(log=lambda *a: None)


def test_the_real_rate_leg_is_the_provenance_flagged_curve():
    """Reused unchanged, and deliberately: it is a RATE curve, not a risk construction, and the
    supersession is of the ERP side. Every cell carries a flag saying whether it is market TIPS,
    Groen synthetic, breakeven-implied or regime-extrapolated -- which is exactly the pattern the
    rest of this reconstruction should be held to."""
    c = H.load_real_curve()
    assert len(c) > 1600, "the historical real curve is truncated (%d months)" % len(c)
    assert min(c) <= "1877-01-01" and max(c) >= "2026-01-01"
    srcs = {r["src1"] for r in c.values()}
    assert "regime-extrapolated" in srcs and "breakeven-implied" in srcs, (
        "the provenance flags have been stripped. A historical real rate with no flag saying how "
        "it was obtained is exactly the kind of number this project keeps being bitten by.")


def test_the_series_reaches_1929_and_is_monthly():
    rows = _rows()
    assert len(rows) > 1100
    assert rows[0]["month"] < "1930-01", "starts at %s" % rows[0]["month"]
    assert rows[-1]["month"] >= "2026-01"
    months = [r["month"] for r in rows]
    assert len(months) == len(set(months)), "more than one observation in some month"
    assert months == sorted(months)


def test_live_data_wins_wherever_it_exists():
    """The bridge is a substitute for a period with no options, not a replacement for the live
    method. If a reconstructed value ever displaced a live one, the recent history would silently
    stop being the real thing."""
    rows = _rows()
    recent = [r for r in rows if r["month"] >= "2013-01"]
    assert recent and all(r["erp_source"] == "live" for r in recent), (
        "months after the splice window are not on live data: %s"
        % [r["month"] for r in recent if r["erp_source"] != "live"][:5])
    old = [r for r in rows if r["month"] < "2007-01"]
    assert old and all(r["erp_source"] == "bridge" for r in old[-24:])


def test_every_month_declares_where_both_legs_came_from():
    rows = _rows()
    for r in rows:
        assert r["erp_source"] in ("bridge", "blend", "live")
        assert r["real_rf_1y_source"], "%s has no real-rate provenance" % r["month"]


def test_the_cost_of_equity_is_the_sum_of_its_two_legs():
    """No hidden third term. If a constant ever creeps in, this fails."""
    rows = _rows()
    n = 0
    for r in rows:
        if r["real_coe_1y_pct"] is None or r["real_rf_1y_pct"] is None:
            continue
        assert abs(r["real_coe_1y_pct"] - (r["real_rf_1y_pct"] + r["market_erp_1y_pct"])) < 1e-6
        n += 1
    assert n > 1000


def test_the_levels_are_possible_across_a_century():
    rows = _rows()
    erp = [r["market_erp_1y_pct"] for r in rows]
    assert min(erp) > 0.0, "a negative equity risk premium at %s" % rows[erp.index(min(erp))]["month"]
    assert max(erp) < 40.0, "an equity risk premium of %.1f%% at %s" % (
        max(erp), rows[erp.index(max(erp))]["month"])
    coe = [r["real_coe_1y_pct"] for r in rows if r["real_coe_1y_pct"] is not None]
    assert min(coe) > -10.0 and max(coe) < 45.0


def test_the_depression_and_the_crisis_are_the_two_extremes():
    """A century-long risk series that does not put 1932 and 2009 near the top is measuring
    something other than risk."""
    rows = {r["month"]: r for r in _rows()}
    calm = rows["2026-06"]["market_erp_1y_pct"]
    for ym in ("1932-06", "2009-03"):
        assert rows[ym]["market_erp_1y_pct"] > 2.5 * calm, (
            "%s premium %.2f%% is not far above today's %.2f%%"
            % (ym, rows[ym]["market_erp_1y_pct"], calm))


def test_the_module_says_what_it_supersedes_and_what_it_does_not_yet_do():
    """The two honest gaps -- the term structure past one year, and the company leg -- are
    declared. An undeclared gap is how a partial build gets used as a finished one."""
    src = open(os.path.join(ROOT, "idio", "market_coe_history.py"), encoding="utf-8").read()
    assert "FINAL_decomposition_v4" in src and "SUPERSEDES" in src
    assert "0.52" in src, "the measured break must stay recorded"
    assert "TERM STRUCTURE BEYOND ONE YEAR" in src
    assert "THE COMPANY LEG" in src


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
