#!/usr/bin/env python3
"""probe_lease_ruling.py — READ ONLY. What does the approved lease ruling actually change?

James approved, 2026-08-09: feed the debt row from primary-source BORROWINGS only, in every
year, so the engine stops switching lease treatments partway through a company's history.

Before changing anything, establish per company whether the anchor year's borrowings figure
can be CORROBORATED TWO INDEPENDENT WAYS. The valuation depends on the anchor year alone --
proved to fifteen significant figures on Apple -- so that is the year that has to be right:

    route 1:  primary-source borrowings, reconstructed from the filer's own XBRL tags
    route 2:  vendor total debt MINUS tagged capitalized lease liabilities

They are built from different data by different paths. If they agree, the anchor is
corroborated and the ruling can be applied to that company with evidence. If they disagree,
or either is missing, it cannot -- and we say so rather than quietly picking one.

This writes nothing and changes nothing.
"""
import csv
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
for _p_ in (_ROOT, os.path.join(_ROOT, "pipeline")):
    if _p_ not in sys.path:
        sys.path.insert(0, _p_)

import debt_feed as DF          # noqa: E402
import yaml                     # noqa: E402

CACHE = os.environ.get("SEC_CACHE_DIR") or "/tmp/_sec_cache"
TOL = 0.01          # 1% — filers round; a lease-sized gap is far larger than rounding


def anchor_year_of(bs_csv):
    """Latest fiscal year present in the reported balance sheet."""
    with open(bs_csv) as fh:
        for row in csv.reader(fh):
            if row and row[0].strip().lower() in ("fiscal year", "year"):
                yrs = [int(x) for x in row[1:] if str(x).strip().lstrip("-").isdigit()]
                if yrs:
                    return max(yrs)
    return None


def probe(ticker):
    bs = os.path.join(_ROOT, "outputs", f"{ticker}_reported_bs.csv")
    if not os.path.exists(bs):
        return {"ticker": ticker, "verdict": "NO DATA", "note": "no reported_bs.csv"}
    try:
        vendor = DF.vendor_total_debt(bs)
    except Exception as e:
        return {"ticker": ticker, "verdict": "NO DATA", "note": f"vendor read failed: {e}"}
    if not vendor:
        return {"ticker": ticker, "verdict": "NO DATA", "note": "empty vendor series"}

    ay = max(vendor)
    try:
        cik = DF.resolve_cik(ticker, CACHE)
        primary = {r["fiscal_year"]: r for r in DF.build_primary_series(cik, CACHE)}
    except Exception as e:
        return {"ticker": ticker, "verdict": "NO PRIMARY", "anchor_year": ay,
                "vendor": vendor.get(ay), "note": str(e)[:60]}

    p = primary.get(ay)
    v = vendor.get(ay)
    if p is None or v is None:
        return {"ticker": ticker, "verdict": "NO PRIMARY", "anchor_year": ay,
                "vendor": v, "note": f"no primary row for FY{ay}"}

    # Scale: the vendor tabs are in the engine's inferred per-ticker scale, not always $mm.
    scale, scale_years = DF.infer_vendor_scale(vendor, list(primary.values()))
    v_musd = v * (scale or 1.0)

    borrow = p["borrowings_musd"]
    leases = p["lease_liabilities_musd"]
    route2 = None if leases is None else v_musd - leases

    out = {"ticker": ticker, "anchor_year": ay, "vendor_musd": v_musd,
           "primary_borrowings": borrow, "leases": leases, "vendor_less_leases": route2,
           "basis": p.get("borrowings_basis"), "scale": scale,
           "scale_years": scale_years}

    if borrow is None:
        out["verdict"] = "NO PRIMARY"
        out["note"] = "no borrowings route resolved from the filer's tags"
    elif route2 is None:
        # No leases tagged. If vendor already equals borrowings, the row never had leases
        # in it and the ruling is a no-op for this name.
        out["verdict"] = "NO LEASES IN ROW" if abs(v_musd - borrow) <= TOL * max(1.0, borrow) \
            else "UNCORROBORATED"
        out["note"] = "no lease tags; vendor equals borrowings" if out["verdict"].startswith("NO L") \
            else "no lease tags, and vendor does not equal borrowings — gap unexplained"
    elif abs(route2 - borrow) <= TOL * max(1.0, abs(borrow)):
        out["verdict"] = "CORROBORATED"
        out["note"] = "two independent routes agree"
    else:
        out["verdict"] = "UNCORROBORATED"
        out["note"] = f"routes disagree by {route2 - borrow:,.0f}m"
    if borrow:
        out["move_musd"] = borrow - v_musd
        out["move_pct"] = 100.0 * (borrow - v_musd) / v_musd if v_musd else None
    return out


def main():
    comps = sorted(f[:-5] for f in os.listdir(os.path.join(_ROOT, "companies"))
                   if f.endswith(".yaml"))
    rows = [probe(t) for t in comps]

    print(f"{'tkr':<5} {'FY':<5} {'vendor $m':>12} {'borrowings $m':>14} "
          f"{'leases $m':>11} {'v-leases $m':>12} {'move $m':>10} {'move %':>8}  verdict")
    print("-" * 108)
    for r in rows:
        f = lambda k, w=12, d=0: (f"{r[k]:>{w},.{d}f}" if isinstance(r.get(k), (int, float))
                                  else " " * (w - 1) + "-")            # noqa: E731
        print(f"{r['ticker']:<5} {str(r.get('anchor_year','-')):<5} "
              f"{f('vendor_musd')} {f('primary_borrowings',14)} {f('leases',11)} "
              f"{f('vendor_less_leases')} {f('move_musd',10)} {f('move_pct',8,1)}  "
              f"{r['verdict']}")

    print()
    for v in ("CORROBORATED", "NO LEASES IN ROW", "UNCORROBORATED", "NO PRIMARY", "NO DATA"):
        got = [r['ticker'] for r in rows if r.get('verdict') == v]
        if got:
            print(f"{v:<18} {len(got):>2}  {' '.join(got)}")
    print()
    for r in rows:
        if r.get("verdict") in ("UNCORROBORATED", "NO PRIMARY", "NO DATA"):
            print(f"  {r['ticker']}: {r.get('note','')}")


if __name__ == "__main__":
    main()
