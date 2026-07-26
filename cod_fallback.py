"""
cod_fallback.py — generalized cost of debt for ANY ticker (ERP ladder, ratified 2026-07-25).

The cost-of-debt analog of the generalized (universal-K) COE. Priority ladder:
  1. issuer's own bonds (modal S&P rating + fit_offset)      -> cod_source=issuer_bonds  GREEN
  2. a published issuer credit rating, if present            -> cod_source=published     GREEN
  3. synthetic interest-coverage rating (this ticker's EBIT/interest)  -> cod_source=synthetic AMBER
Never silently defaults to BBB. rating -> real_cod_<rating> from the market credit curve
(real-yields market_credit_latest_annual.csv: real_cod_AAA..CCC by tenor). Emits provenance for
the cockpit audit tab (GREEN issuer_bonds/published, AMBER synthetic) + a validation gate.
"""
import rate_feed as RF
from synthetic_rating import synthetic_rating

RATINGS = ["AAA", "AA", "A", "BBB", "BB", "B", "CCC"]


def load_credit_curve(*, base_url=RF.BASE_URL, local_dir=None):
    """The generic rating->real_cod curve by tenor (published by real-yields). Returns
    {rating: [real_cod by tenor], 'real_fwd': [...], 'tenor': [...]}."""
    fname = "market_credit_latest_annual.csv"
    fields, rows = RF._read_rows(RF._fetch_text(fname, base_url=base_url, local_dir=local_dir), fname)
    RF._require_cols(fields, ["tenor", "real_fwd"] + [f"real_cod_{r}" for r in RATINGS], fname)
    rows = sorted(rows, key=lambda r: float(r["tenor"]))
    curve = {r: [float(x[f"real_cod_{r}"]) for x in rows] for r in RATINGS}
    curve["real_fwd"] = [float(x["real_fwd"]) for x in rows]
    curve["tenor"] = [int(float(x["tenor"])) for x in rows]
    return curve


def resolve_cod(*, bonded_cod=None, bonded_rating=None, published_rating=None,
                fundamentals=None, curve=None, real_rf=None):
    """Return (real_cod: list-by-tenor, provenance: dict). Walks the ladder; applies the
    validation gate (real_cod >= real_rf, i.e. spread >= 0, per tenor).
      fundamentals = dict(ebit=, interest_expense=, total_debt=, assets=) for the synthetic leg.
      real_rf = the real forward risk-free by tenor (for the gate); optional.
    """
    prov = {}
    if bonded_cod is not None:
        real_cod = [float(x) for x in bonded_cod]
        prov = {"cod_source": "issuer_bonds", "rating": bonded_rating, "coverage": None,
                "audit": "GREEN", "flags": []}
    else:
        if published_rating in RATINGS:
            rating = published_rating
            prov = {"cod_source": "published", "rating": rating, "coverage": None,
                    "audit": "GREEN", "flags": []}
        else:
            if not fundamentals:
                raise ValueError("resolve_cod: fundamentals required for the synthetic leg")
            rating, meta = synthetic_rating(fundamentals.get("ebit"),
                                            fundamentals.get("interest_expense"),
                                            fundamentals.get("total_debt"),
                                            fundamentals.get("assets"))
            prov = {"cod_source": "synthetic", "rating": rating,
                    "coverage": meta.get("coverage"), "audit": "AMBER",
                    "flags": list(meta.get("flags", []))}
        if curve is None:
            raise ValueError("resolve_cod: credit curve required for the rating fallback")
        if prov["rating"] not in curve:
            raise ValueError(f"resolve_cod: rating {prov['rating']!r} not in credit curve {list(curve)}")
        real_cod = [float(x) for x in curve[prov["rating"]]]
    # validation gate: spread >= 0 (real_cod >= real_rf) per tenor
    if real_rf is not None:
        neg = [i + 1 for i, (c, rf) in enumerate(zip(real_cod, real_rf)) if c < rf - 1e-9]
        prov["spread_nonneg"] = (len(neg) == 0)
        if neg:
            prov["audit"] = "RED"
            prov["flags"].append(f"negative_spread_tenors:{neg[:5]}")
    prov["n_tenors"] = len(real_cod)
    return real_cod, prov


if __name__ == "__main__":
    import os
    ld = os.environ.get("CREDIT_DIR", ".")
    curve = load_credit_curve(local_dir=ld)
    rf = curve["real_fwd"]
    print(f"curve loaded: {len(curve['tenor'])} tenors; ratings {RATINGS}")
    # issuer-bonds passthrough
    rc, p = resolve_cod(bonded_cod=[x + 0.01 for x in rf], bonded_rating="A", real_rf=rf)
    print("issuer_bonds ->", p["cod_source"], p["audit"], p["rating"], "spread_nonneg", p.get("spread_nonneg"))
    # synthetic legs across coverage regimes
    for nm, f in [("mid-cap", dict(ebit=8e9, interest_expense=2e9, total_debt=60e9, assets=300e9)),
                  ("weak",    dict(ebit=1.0e9, interest_expense=1.5e9, total_debt=40e9, assets=80e9)),
                  ("no-debt", dict(ebit=50e9, interest_expense=0.0, total_debt=0.0, assets=300e9))]:
        rc, p = resolve_cod(fundamentals=f, curve=curve, real_rf=rf)
        print(f"synthetic {nm:8s} -> {p['cod_source']} {p['audit']} {p['rating']:4s} "
              f"cov={p['coverage']} real_cod t1={rc[0]:.4f} t10={rc[9]:.4f} spread_nonneg={p.get('spread_nonneg')} {p['flags']}")
