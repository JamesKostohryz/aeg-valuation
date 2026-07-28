"""Hermetic test of the generalized cost-of-debt ladder + validation gate (offline, tiny curve)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cod_fallback import resolve_cod, RATINGS


def _curve():
    base = [0.02, 0.03, 0.04]
    bump = {"AAA": 0.002, "AA": 0.004, "A": 0.006, "BBB": 0.012, "BB": 0.02, "B": 0.035, "CCC": 0.08}
    c = {r: [b + bump[r] for b in base] for r in RATINGS}
    c["real_fwd"] = list(base); c["tenor"] = [1, 2, 3]
    return c


def test_ladder_and_gate():
    c = _curve(); rf = c["real_fwd"]
    rc, p = resolve_cod(bonded_cod=[x + 0.01 for x in rf], bonded_rating="A", real_rf=rf)
    assert p["cod_source"] == "issuer_bonds" and p["audit"] == "GREEN" and p["spread_nonneg"]
    rc, p = resolve_cod(published_rating="BBB", curve=c, real_rf=rf)
    assert p["cod_source"] == "published" and rc == c["BBB"] and p["audit"] == "GREEN"
    rc, p = resolve_cod(fundamentals=dict(ebit=8e9, interest_expense=2e9, total_debt=60e9, assets=300e9),
                        curve=c, real_rf=rf)
    assert p["cod_source"] == "synthetic" and p["audit"] == "AMBER" and p["rating"] == "BBB" and p["spread_nonneg"]
    rc, p = resolve_cod(fundamentals=dict(ebit=-2e9, interest_expense=3e9, total_debt=50e9, assets=100e9),
                        curve=c, real_rf=rf)
    assert p["rating"] == "CCC" and "negative_ebit_distress_floor" in p["flags"]
    rc, p = resolve_cod(fundamentals=dict(ebit=50e9, interest_expense=0.0, total_debt=0.0, assets=300e9),
                        curve=c, real_rf=rf)
    assert p["rating"] == "AAA" and "de_minimis_debt" in p["flags"]
    # gate catches a negative spread on a RATED name (cod below rf) -> RED
    rc, p = resolve_cod(bonded_cod=[x - 0.01 for x in rf], bonded_rating="A", real_rf=rf)
    assert p["spread_nonneg"] is False and p["audit"] == "RED"
    # de-minimis / net-cash: AAA curve dipping below rf must FLOOR at rf, NOT abort.
    # Simulate the AAPL edge: rf sits a hair ABOVE the AAA cod at one tenor.
    rf_hi = list(c["AAA"]); rf_hi[1] = c["AAA"][1] + 0.005   # push rf above AAA at tenor 2
    rc, p = resolve_cod(fundamentals=dict(ebit=50e9, interest_expense=0.0, total_debt=0.0, assets=300e9),
                        curve=c, real_rf=rf_hi)
    assert "de_minimis_debt" in p["flags"]
    assert p["spread_nonneg"] is True and p["audit"] != "RED"
    assert any("de_minimis_floored_at_rf" in f for f in p["flags"])
    assert rc[1] >= rf_hi[1] - 1e-12   # floored to rf at the crossing tenor
    print("cod ladder + gate + de-minimis floor OK")


if __name__ == "__main__":
    test_ladder_and_gate()
