"""Primary-source gross borrowings, capitalized leases, and the debt-feed guard.

WHY THIS MODULE EXISTS
----------------------
The vendor balance-sheet feed carries a row labelled "Total Debt". For Apple it
agrees with Securities and Exchange Commission primary source to the dollar for
fiscal 2012 through fiscal 2021 and then diverges: +$812mn in fiscal 2022,
+$859mn in fiscal 2023, +$12,430mn in fiscal 2024 and +$13,720mn in fiscal 2025.
The first two gaps are Apple's noncurrent finance leases to the dollar; the last
two are every capitalized lease it carries. The vendor folded leases into the
row partway through the series and did not restate the earlier years, so the
series changes definition in the middle of itself.

The objection is not whether a lease is debt. It is that a series which changes
definition partway through cannot be differenced across the break, and the row
is an input to the anchor: `in_debt` (Inputs B5) is read straight off it, net
financial obligations is `in_debt - in_cash - in_sti`, and net operating assets
is plugged from common equity plus net financial obligations. A wrong figure
there moves the operating side and the financing side together and reprices the
whole forecast. Established by direct perturbation on 2026-08-09: substituting
primary source for the vendor row moved Apple's tied engine equity from 87.1659
to 89.8409 per share, about three times the mechanical effect of the debt change
itself, with the four-method tie green at 1.3e-14 in BOTH runs. The tie is
structurally blind to this class of error.

WHAT THIS MODULE DOES, AND DELIBERATELY DOES NOT DO
---------------------------------------------------
It does NOT change any valuation number. `in_debt` still comes from the vendor
row exactly as before. This module ingests the primary-source series alongside
it, carries capitalized lease liabilities as a SEPARATE labelled line so that
either treatment of leases is computable from the same feed, and REPORTS every
year where the two disagree beyond a stated tolerance. Reporting rather than
silently preferring is the durable part. Which definition the engine should
value on is a judgment that has not been made and is not made here.

The guard's shape is taken from `debt_feed_disagreements()` in the Apple
buyback study (`AEG Buyback Study/code/build.py`), generalized from one
hard-coded company to any ticker.

WHY THE VERDICT IS CONSERVATIVE, WHICH MATTERS MORE THAN THE COVERAGE
---------------------------------------------------------------------
Reconstructing gross borrowings from XBRL does not generalize cleanly. Filers
tag the same economic quantity differently and inconsistently across years: some
carry `LongTermDebtNoncurrent` plus `LongTermDebtCurrent`, some only
`DebtLongtermAndShorttermCombinedAmount`, some fold capitalized leases into
`LongTermDebtAndCapitalLeaseObligations` and tag nothing else at the fiscal year
end. A guard built on an incomplete reconstruction reports disagreements that
are OUR OWN ingestion gaps, and a guard that cries wolf is a guard that gets
ignored — which would be worse than no guard.

So this module distinguishes two failures that look alike:

  * the VENDOR disagrees with primary source, which is a finding about the feed;
  * OUR construction cannot be corroborated, which is a finding about us.

It claims the first only when it can prove it. Proof is a CLEAN BREAK: the two
series agree to within tolerance for at least `MIN_CORROBORATING_YEARS`
consecutive early years, and every disagreeing year comes after every agreeing
year. Agreement to the dollar with an independently sourced vendor feed
corroborates the construction — two independent routes reconciling is the same
discipline that found the defect in the first place — and a clean break is the
signature of a definitional change, as against intermittent small gaps, which
are the signature of a reconstruction that never worked.

Anything else is reported as UNVERIFIED, with the numbers shown and no claim
attached. As of 2026-08-09 that is most of the fleet, and saying so plainly is
the correct output, not a shortfall to be papered over. Finishing the
per-filer tag work is separate, tracked work.
"""

import csv
import datetime as _dt
import json
import os
import time
import urllib.request

SEC_UA = os.environ.get(
    "SEC_USER_AGENT",
    "AEG valuation engine james@jameskostohryz.com")

# Committed identifiers for the onboarded names, so a run never depends on a
# network lookup for a company we already carry. Unknown tickers fall through to
# the Securities and Exchange Commission's own ticker file, which is what makes
# onboarding an arbitrary ticker possible without editing the repository.
CIK_MAP = {
    "AAPL": "0000320193", "AZO": "0000866787", "COST": "0000909832",
    "HD": "0000354950", "JNJ": "0000200406", "KO": "0000021344",
    "MCD": "0000063908", "MRK": "0000310158", "NKE": "0000320187",
    "PEP": "0000077476", "PG": "0000080424", "POOL": "0000945841",
    "T": "0000732717", "WMT": "0000104169",
}

# Gross borrowings. Capitalized leases are NOT part of any of these routes —
# they are carried separately, which is the whole point of the module.
#   route_components  the ordinary construction
#   route_debtcurrent noncurrent long-term debt plus the filer's own total
#                     current debt, for filers that tag it that way
#   route_combined    the filer's own single total-debt concept
# Where more than one route is available they are recorded side by side, so a
# later session can see which filers reconcile and which do not.
TAG_LTD_NONCURRENT = "LongTermDebtNoncurrent"
TAG_LTD_CURRENT = "LongTermDebtCurrent"
TAG_LTD = "LongTermDebt"
TAG_DEBT_CURRENT = "DebtCurrent"
TAG_COMBINED = "DebtLongtermAndShorttermCombinedAmount"
TAG_CP = "CommercialPaper"
TAG_CP_NONCURRENT = "CommercialPaperNoncurrent"

BORROWING_TAGS = (TAG_LTD_NONCURRENT, TAG_LTD_CURRENT, TAG_LTD, TAG_DEBT_CURRENT,
                  TAG_COMBINED, TAG_CP, TAG_CP_NONCURRENT)

# Lease liabilities, carried separately and never added to borrowings. Filers
# tag either the split or the single total, and occasionally both with different
# scopes, so both shapes are collected and the candidate set in
# `debt_feed_disagreements` tries each.
OPERATING_LEASE_SPLIT = ("OperatingLeaseLiabilityNoncurrent",
                         "OperatingLeaseLiabilityCurrent")
FINANCE_LEASE_SPLIT = ("FinanceLeaseLiabilityNoncurrent",
                       "FinanceLeaseLiabilityCurrent")
TAG_OPERATING_LEASE_TOTAL = "OperatingLeaseLiability"
TAG_FINANCE_LEASE_TOTAL = "FinanceLeaseLiability"
TAG_CAPITAL_LEASE_TOTAL = "CapitalLeaseObligations"

LEASE_TAGS = (OPERATING_LEASE_SPLIT + FINANCE_LEASE_SPLIT
              + (TAG_OPERATING_LEASE_TOTAL, TAG_FINANCE_LEASE_TOTAL,
                 TAG_CAPITAL_LEASE_TOTAL))

ALL_TAGS = BORROWING_TAGS + LEASE_TAGS

# A vendor row within a tenth of a percent of primary source is agreement. The
# breaks this guard exists to catch run from 0.7% to 76%, so the tolerance is
# nowhere near the signal; it is there to absorb rounding in the vendor's own
# units, not to be tuned.
DEFAULT_TOL_FRAC = 0.001

# Capitalized leases came onto United States balance sheets for fiscal years
# beginning after 15 December 2018, so the break, where there is one, falls
# around fiscal 2019 or 2020. Corroboration is therefore sought in the years
# before that and a clean break is looked for after it.
PRE_LEASE_STANDARD_YEAR = 2018

# How many early years must agree to the dollar before this module is willing to
# say the vendor is wrong rather than that we are. Three is enough to rule out
# coincidence and is met comfortably by any name whose construction actually
# works — Apple agrees in nine.
MIN_CORROBORATING_YEARS = 3

# A break has to be OBSERVED, not inferred across a hole. If the last agreeing
# year and the first disagreeing year are further apart than this, primary
# source is simply missing in between and no claim is made. AT&T is the case
# that argues for it: our construction covers fiscal 2008 to 2011 and then not
# again until fiscal 2019, so the "break" would be eight years of absent data.
MAX_BREAK_GAP_YEARS = 2


class DebtFeedError(Exception):
    """Raised only for programming errors. Data problems are REPORTED, not raised."""


# --------------------------------------------------------------- fetch + cache

def _http_json(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": SEC_UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _cache_path(cache_dir, name):
    return os.path.join(cache_dir, name) if cache_dir else None


def resolve_cik(ticker, cache_dir=None, allow_network=True):
    """Ten-digit CIK for a ticker, or None if it cannot be established."""
    tk = (ticker or "").strip().upper()
    if tk in CIK_MAP:
        return CIK_MAP[tk]
    fn = _cache_path(cache_dir, "sec_company_tickers.json")
    data = None
    if fn and os.path.exists(fn):
        try:
            data = json.load(open(fn))
        except Exception:
            data = None
    if data is None and allow_network:
        try:
            data = _http_json("https://www.sec.gov/files/company_tickers.json")
            if fn:
                os.makedirs(os.path.dirname(fn) or ".", exist_ok=True)
                json.dump(data, open(fn, "w"))
        except Exception:
            return None
    if not data:
        return None
    for v in data.values():
        if str(v.get("ticker", "")).upper() == tk:
            return str(v["cik_str"]).zfill(10)
    return None


def fetch_concept(cik, tag, cache_dir=None, allow_network=True, pause=0.2):
    """{period_end_date: value_in_dollars} for one tag, 10-K filings only.

    Where a period end has been reported more than once, the EARLIEST filing is
    kept, so the series is as-originally-reported rather than as-restated. That
    matches how the vendor row is built and keeps the comparison honest.
    """
    fn = _cache_path(cache_dir, f"sec_{cik}_{tag}.json")
    doc = None
    if fn and os.path.exists(fn):
        try:
            doc = json.load(open(fn))
        except Exception:
            doc = None
    if doc is None and allow_network:
        url = (f"https://data.sec.gov/api/xbrl/companyconcept/"
               f"CIK{cik}/us-gaap/{tag}.json")
        try:
            doc = _http_json(url)
        except Exception as e:
            doc = {"__unavailable": str(e)}
        if fn:
            os.makedirs(os.path.dirname(fn) or ".", exist_ok=True)
            json.dump(doc, open(fn, "w"))
        time.sleep(pause)
    if not doc or "units" not in doc:
        return {}
    best = {}
    for f in doc["units"].get("USD", []):
        if f.get("form") not in ("10-K", "10-K/A"):
            continue
        end, filed = f.get("end"), f.get("filed", "9999-99-99")
        if not end:
            continue
        if end not in best or filed < best[end][1]:
            best[end] = (f["val"], filed)
    return {k: v[0] for k, v in best.items()}


# ------------------------------------------------------------------- alignment

def fiscal_year_label(period_end):
    """Fiscal-year label the vendor would give a balance-sheet date.

    The calendar year the fiscal year ends in, except that a fifty-two/fifty-three
    week year ending in the first days of January belongs to the prior year
    (Johnson & Johnson's year ending 2021-01-03 is fiscal 2020). A retailer whose
    year ends in late January or early February is labelled by the calendar year
    it ends in, which is the vendor's convention and the company's own.
    """
    d = _dt.date.fromisoformat(period_end)
    if d.month == 1 and d.day <= 10:
        return d.year - 1
    return d.year


# ---------------------------------------------------------------- construction

def build_primary_series(cik, cache_dir=None, allow_network=True):
    """Rows of primary-source borrowings and capitalized leases, by fiscal year.

    Figures are millions of dollars, matching the vendor tabs. `borrowings_musd`
    is the preferred route; the alternative routes are carried alongside so that
    whether a filer's own tags reconcile is visible rather than assumed.
    """
    if not cik:
        return []
    S = {t: fetch_concept(cik, t, cache_dir, allow_network) for t in ALL_TAGS}
    ends = set()
    for t in BORROWING_TAGS:
        ends |= set(S.get(t, {}))
    rows = []
    for end in sorted(ends):
        def g(tag):
            v = S.get(tag, {}).get(end)
            return None if v is None else v / 1e6

        def total(tags):
            tot, have = 0.0, False
            for t in tags:
                v = g(t)
                if v is not None:
                    tot += v
                    have = True
            return tot if have else None

        nc, cu, lt = g(TAG_LTD_NONCURRENT), g(TAG_LTD_CURRENT), g(TAG_LTD)
        dc, comb = g(TAG_DEBT_CURRENT), g(TAG_COMBINED)
        cp = (g(TAG_CP) or 0.0) + (g(TAG_CP_NONCURRENT) or 0.0)

        routes = {}
        if nc is not None and cu is not None:
            routes["components"] = nc + cu + cp
        if nc is not None and dc is not None:
            routes["debt_current"] = nc + dc
        if comb is not None:
            routes["combined"] = comb
        if not routes and lt is not None:
            routes["long_term_debt_only"] = lt + cp
        if not routes:
            continue
        for name in ("components", "debt_current", "combined", "long_term_debt_only"):
            if name in routes:
                preferred, basis = routes[name], name
                break

        op_split, fin_split = total(OPERATING_LEASE_SPLIT), total(FINANCE_LEASE_SPLIT)
        op_total, fin_total = g(TAG_OPERATING_LEASE_TOTAL), g(TAG_FINANCE_LEASE_TOTAL)
        cap_total = g(TAG_CAPITAL_LEASE_TOTAL)
        op = op_split if op_split is not None else op_total
        fin = fin_split if fin_split is not None else (
            fin_total if fin_total is not None else cap_total)
        lease_all = None
        if op is not None or fin is not None:
            lease_all = (op or 0.0) + (fin or 0.0)

        rows.append({
            "fiscal_year": fiscal_year_label(end),
            "period_end": end,
            "borrowings_musd": preferred,
            "borrowings_basis": basis,
            "routes": routes,
            "lease_liabilities_musd": lease_all,
            "operating_lease_musd": op,
            "finance_lease_musd": fin,
            "operating_lease_noncurrent_musd": g(OPERATING_LEASE_SPLIT[0]),
            "finance_lease_noncurrent_musd": g(FINANCE_LEASE_SPLIT[0]),
        })
    # A single fiscal-year label can collect two balance dates when a company
    # changes its year end. Keep the later date, which is the one the vendor's
    # column for that label describes.
    by_year = {}
    for r in rows:
        prev = by_year.get(r["fiscal_year"])
        if prev is None or r["period_end"] > prev["period_end"]:
            by_year[r["fiscal_year"]] = r
    return [by_year[y] for y in sorted(by_year)]


def vendor_total_debt(reported_bs_csv):
    """{fiscal_year: total debt} from a committed reported balance sheet."""
    rows = list(csv.reader(open(reported_bs_csv)))
    if not rows:
        return {}
    years = rows[0][1:]
    for r in rows:
        if r and r[0].strip() == "Total Debt":
            out = {}
            for y, v in zip(years, r[1:]):
                v = (v or "").strip()
                if not v:
                    continue
                try:
                    out[int(y)] = float(v)
                except ValueError:
                    pass
            return out
    return {}


# ------------------------------------------------------------------- the guard

def _agrees(a, b, tol_frac):
    return abs(a - b) <= max(1.0, tol_frac * abs(b))


# Candidate unit factors for the vendor row. The committed outputs are millions
# of dollars, but a golden fixture is millions divided by a million again (a
# known register item), and a future feed could arrive in units or thousands.
# Rather than assume, the scale is INFERRED by asking which factor makes the two
# series agree in the most years, and the answer is recorded in the report. A
# silent factor of a thousand in a row nobody reads is exactly the failure the
# split-adjusted-price finding warned about, so it is established rather than
# trusted.
CANDIDATE_SCALES = (1.0, 1e3, 1e6, 1e9, 1e-3, 1e-6)


def infer_vendor_scale(vendor, primary, tol_frac=DEFAULT_TOL_FRAC):
    """(factor, years_agreeing) — the multiplier putting the vendor row on
    primary source's units, chosen by agreement count. Ties break toward 1.0."""
    best = (1.0, -1)
    for k in CANDIDATE_SCALES:
        n = sum(1 for r in primary
                if r["fiscal_year"] in vendor
                and _agrees(vendor[r["fiscal_year"]] * k, r["borrowings_musd"], tol_frac))
        if n > best[1]:
            best = (k, n)
    return best


def corroboration(vendor, primary, tol_frac=DEFAULT_TOL_FRAC,
                  min_years=MIN_CORROBORATING_YEARS):
    """Can this module claim the vendor is wrong, or only that it cannot tell?

    Returns (ok, detail). `ok` is True only on a CLEAN BREAK: at least
    `min_years` overlapping years agree to within tolerance, and every
    disagreeing year comes after every agreeing year. Agreement to the dollar
    with an independently sourced feed corroborates our construction; a clean
    break is the signature of a definitional change rather than of a
    reconstruction that never worked.
    """
    pairs = [(r["fiscal_year"], vendor[r["fiscal_year"]], r["borrowings_musd"])
             for r in primary if r["fiscal_year"] in vendor]
    pairs.sort()
    agree_years = [y for y, v, p in pairs if _agrees(v, p, tol_frac)]
    dis_years = [y for y, v, p in pairs if not _agrees(v, p, tol_frac)]
    detail = {
        "overlapping_years": len(pairs),
        "years_agreeing": len(agree_years),
        "years_disagreeing": len(dis_years),
        "first_disagreeing_year": min(dis_years) if dis_years else None,
        "last_agreeing_year": max(agree_years) if agree_years else None,
        "clean_break": bool(dis_years) and bool(agree_years)
                       and min(dis_years) > max(agree_years),
    }
    if len(agree_years) < min_years:
        detail["why_not"] = (
            f"only {len(agree_years)} year(s) agree with primary source; "
            f"{min_years} are required before a disagreement is claimed, because "
            f"too few means our own construction of gross borrowings from the "
            f"filings is probably incomplete for this filer")
        return False, detail
    if dis_years and not detail["clean_break"]:
        detail["why_not"] = (
            f"the two feeds agree and disagree in alternating years (disagreements "
            f"begin {min(dis_years)} but agreement continues to {max(agree_years)}); "
            f"that is the signature of an incomplete reconstruction on our side, "
            f"not of a definitional change on the vendor's")
        return False, detail
    if dis_years:
        hole = min(dis_years) - max(agree_years)
        if hole > MAX_BREAK_GAP_YEARS:
            detail["why_not"] = (
                f"the last agreeing year is fiscal {max(agree_years)} and the first "
                f"disagreeing year is fiscal {min(dis_years)}, {hole} years later, with "
                f"no primary-source coverage in between; the break is inferred across a "
                f"hole in our own data rather than observed, so no claim is made")
            return False, detail
    return True, detail


def debt_feed_disagreements(vendor, primary, tol_frac=DEFAULT_TOL_FRAC):
    """Every year where the vendor row and primary source diverge.

    Generalized from `debt_feed_disagreements()` in the Apple buyback study.
    An empty list means the two feeds agree everywhere they overlap.
    `explained_by_leases` is True when the gap equals one of the capitalized
    lease combinations below, which is the signature of this defect as opposed
    to some other feed problem.
    """
    out = []
    for r in primary:
        y = r["fiscal_year"]
        if y not in vendor:
            continue
        v, p = vendor[y], r["borrowings_musd"]
        gap = v - p
        if _agrees(v, p, tol_frac):
            continue
        # A vendor does not necessarily fold in ALL capitalized leases. Apple's
        # fiscal 2022 and 2023 gaps are the noncurrent finance leases alone, and
        # from fiscal 2024 the gap is every lease component together. Those are
        # the same defect at two stages, not two different defects, so the
        # candidates run from the most complete combination to the narrowest and
        # the first match wins. A gap matching none of them is genuinely
        # unexplained, which is what the RED verdict is for.
        candidates = (
            ("all capitalized leases", r.get("lease_liabilities_musd")),
            ("operating leases", r.get("operating_lease_musd")),
            ("finance leases", r.get("finance_lease_musd")),
            ("noncurrent operating leases", r.get("operating_lease_noncurrent_musd")),
            ("noncurrent finance leases", r.get("finance_lease_noncurrent_musd")),
        )
        explained, gap_equals = False, ""
        for label, cand in candidates:
            if cand is not None and _agrees(gap, cand, tol_frac):
                explained, gap_equals = True, label
                break
        out.append({
            "fiscal_year": y,
            "period_end": r["period_end"],
            "vendor_musd": v,
            "primary_source_musd": p,
            "gap_musd": gap,
            "gap_pct_of_primary": (100.0 * gap / p) if p else None,
            "lease_liabilities_musd": r.get("lease_liabilities_musd"),
            "operating_lease_musd": r.get("operating_lease_musd"),
            "finance_lease_musd": r.get("finance_lease_musd"),
            "explained_by_leases": explained,
            "gap_equals": gap_equals,
            "borrowings_basis": r["borrowings_basis"],
        })
    return out


def audit_debt_feed(ticker, reported_bs_csv, anchor_year=None, cache_dir=None,
                    allow_network=True, tol_frac=DEFAULT_TOL_FRAC):
    """Full report for one company. Never raises on a data problem.

    Verdicts:
      GREEN       the two feeds agree in every overlapping year.
      AMBER       they disagree on a clean break and every gap equals a
                  capitalized lease combination — the known definitional break.
      RED         they disagree on a clean break by something that is NOT
                  leases: an unexplained feed disagreement that wants a human.
      UNVERIFIED  we cannot tell, and say so. Either primary source is
                  unavailable, or our reconstruction of gross borrowings is not
                  corroborated well enough on this filer to accuse the vendor of
                  anything. The numbers are still reported; no claim is attached.
    """
    vendor = vendor_total_debt(reported_bs_csv)
    cik = resolve_cik(ticker, cache_dir=cache_dir, allow_network=allow_network)
    primary = build_primary_series(cik, cache_dir=cache_dir, allow_network=allow_network)
    rep = {
        "ticker": ticker, "cik": cik or "", "anchor_year": anchor_year,
        "verdict": "UNVERIFIED", "note": "", "disagreements": [],
        "anchor_vendor_musd": vendor.get(anchor_year),
        "anchor_primary_source_musd": None,
        "anchor_lease_liabilities_musd": None,
        "anchor_gap_musd": None,
        "corroboration": {},
    }
    if not primary:
        rep["note"] = ("primary source unavailable (no identifier, no network, or "
                       "no usable debt tags filed) — vendor row NOT checked")
        return rep

    # Put the vendor row on primary source's units before anything is compared.
    scale, scale_hits = infer_vendor_scale(vendor, primary, tol_frac=tol_frac)
    rep["vendor_scale_factor"] = scale
    rep["vendor_scale_years_agreeing"] = scale_hits
    if scale != 1.0:
        vendor = {y: v * scale for y, v in vendor.items()}
        rep["anchor_vendor_musd"] = vendor.get(anchor_year)

    anchor_row = next((r for r in primary if r["fiscal_year"] == anchor_year), None)
    if anchor_row:
        rep["anchor_primary_source_musd"] = anchor_row["borrowings_musd"]
        rep["anchor_lease_liabilities_musd"] = anchor_row["lease_liabilities_musd"]
        if rep["anchor_vendor_musd"] is not None:
            rep["anchor_gap_musd"] = (rep["anchor_vendor_musd"]
                                      - anchor_row["borrowings_musd"])

    ok, detail = corroboration(vendor, primary, tol_frac=tol_frac)
    rep["corroboration"] = detail
    if not ok:
        rep["note"] = "cannot verify: " + detail.get("why_not", "insufficient overlap")
        return rep

    dis = debt_feed_disagreements(vendor, primary, tol_frac=tol_frac)
    rep["disagreements"] = dis
    if not dis:
        rep["verdict"] = "GREEN"
        rep["note"] = (f"vendor row agrees with primary source in all "
                       f"{detail['years_agreeing']} overlapping years")
    elif all(d["explained_by_leases"] for d in dis):
        rep["verdict"] = "AMBER"
        rep["note"] = (
            f"agrees to fiscal {detail['last_agreeing_year']}, then disagrees in "
            f"{len(dis)} year(s) from fiscal {detail['first_disagreeing_year']}; every "
            f"gap equals capitalized lease liabilities — the known definitional break")
    else:
        bad = [d["fiscal_year"] for d in dis if not d["explained_by_leases"]]
        rep["verdict"] = "RED"
        rep["years_unexplained"] = bad
        rep["note"] = (
            f"agrees to fiscal {detail['last_agreeing_year']}, then disagrees in "
            f"{len(dis)} year(s); {len(bad)} not explained by leases ({bad}) — "
            f"unexplained feed disagreement")
    return rep


REPORT_COLS = ["ticker", "fiscal_year", "period_end", "vendor_musd",
               "primary_source_musd", "gap_musd", "gap_pct_of_primary",
               "lease_liabilities_musd", "operating_lease_musd",
               "finance_lease_musd", "explained_by_leases", "gap_equals",
               "borrowings_basis", "verdict", "note", "cik", "anchor_year",
               "years_agreeing", "first_disagreeing_year", "vendor_scale_factor"]


def write_report(rep, out_csv):
    """One row per disagreeing year; a single row carrying the verdict if none."""
    c = rep.get("corroboration", {})
    common = {"ticker": rep["ticker"], "verdict": rep["verdict"],
              "note": rep["note"], "cik": rep["cik"],
              "anchor_year": rep["anchor_year"],
              "vendor_scale_factor": rep.get("vendor_scale_factor"),
              "years_agreeing": c.get("years_agreeing"),
              "first_disagreeing_year": c.get("first_disagreeing_year")}
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=REPORT_COLS)
        w.writeheader()
        if not rep["disagreements"]:
            w.writerow(common)
        else:
            for d in rep["disagreements"]:
                row = dict(d)
                row.update(common)
                w.writerow({k: row.get(k) for k in REPORT_COLS})
    return out_csv


def console_line(rep):
    """One plain-language line for the run log."""
    a, p = rep.get("anchor_vendor_musd"), rep.get("anchor_primary_source_musd")
    tail = ""
    if a is not None and p is not None:
        tail = (f"  anchor FY{rep['anchor_year']}: vendor {a:,.0f} vs primary source "
                f"{p:,.0f} (gap {rep['anchor_gap_musd']:+,.0f}m)")
    return f"[debt-feed] {rep['verdict']}: {rep['note']}{tail}"


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Vendor total-debt row against primary source.")
    ap.add_argument("tickers", nargs="+")
    ap.add_argument("--outputs-dir", default="outputs")
    ap.add_argument("--cache-dir", default=None)
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--write", action="store_true",
                    help="write <TICKER>_debt_feed.csv into --outputs-dir")
    a = ap.parse_args()
    for tk in a.tickers:
        bs = os.path.join(a.outputs_dir, f"{tk}_reported_bs.csv")
        if not os.path.exists(bs):
            print(f"[debt-feed] {tk}: no {bs}")
            continue
        yrs = vendor_total_debt(bs)
        anchor = max(yrs) if yrs else None
        rep = audit_debt_feed(tk, bs, anchor_year=anchor, cache_dir=a.cache_dir,
                              allow_network=not a.offline)
        print(f"\n=== {tk} ===")
        print(console_line(rep))
        for d in rep["disagreements"]:
            lz = d["lease_liabilities_musd"]
            lz_s = f"{lz:,.0f}" if lz is not None else "-"
            tag = ("= " + d["gap_equals"]) if d["explained_by_leases"] else "UNEXPLAINED"
            print(f"    FY{d['fiscal_year']}  vendor {d['vendor_musd']:>12,.0f}  "
                  f"primary {d['primary_source_musd']:>12,.0f}  "
                  f"gap {d['gap_musd']:>+11,.0f}  leases {lz_s:>10}  {tag}")
        if a.write:
            print("   ->", write_report(rep, os.path.join(a.outputs_dir,
                                                          f"{tk}_debt_feed.csv")))


# ---------------------------------------------------------------------------
# THE LEASE RULING — approved by James 2026-08-09.
#
# "Feed the debt row from primary-source BORROWINGS only, in every year", so the engine
# stops switching lease treatments partway through a company's history. Background and
# mechanism: claude/00-ENGINE-STATE-SINGLE-SOURCE-OF-TRUTH-2026-08-09.md section 4.
#
# WHY THIS IS NOT A BLIND SUBSTITUTION. Applying the ruling means replacing a figure whose
# defect is KNOWN (the vendor's definition changes mid-series) with one whose accuracy is
# ASSUMED (a reconstruction from the filer's own tags). On 2026-08-09 that reconstruction
# was measured against the fleet and it does not generalize: of fourteen names, four
# corroborate, eight disagree between routes, and two return no usable primary row. Swapping
# all fourteen would trade a known error for an unmeasured one, which is the exact mistake
# this project has been making.
#
# So the switch is made ONLY where the anchor year is corroborated TWO INDEPENDENT WAYS:
#
#     route 1   primary-source borrowings, from the filer's XBRL tags
#     route 2   vendor total debt MINUS tagged capitalized lease liabilities
#
# Different data, different paths. Agreement is evidence; disagreement means one side's tags
# are incomplete and we cannot say which, so nothing changes and the run says so out loud.
#
# The valuation depends on the ANCHOR YEAR ALONE -- established by perturbation to fifteen
# significant figures -- so the anchor is what this resolves. Applying the ruling across the
# whole series, which the DuPont decomposition needs, is a separate register item.

ANCHOR_CORROBORATION_TOL = 0.01      # 1%: filers round; a lease-sized gap is far larger


def resolve_anchor_debt_basis(ticker, reported_bs_csv, vendor_scale=None,
                              cache_dir=None, allow_network=True):
    """Decide the anchor-year debt figure the engine should consume.

    Returns a dict that is always safe to act on. `apply` is True only when the ruling can
    be applied with evidence; `debt_musd` then carries borrowings-only for the anchor year.
    Any failure -- no network, no filer match, no tags -- returns apply=False with a reason,
    never an exception, because a debt-feed problem must not take down a valuation run.
    """
    out = {"ticker": ticker, "apply": False, "verdict": "UNRESOLVED", "reason": "",
           "anchor_year": None, "vendor_musd": None, "borrowings_musd": None,
           "leases_musd": None, "vendor_less_leases_musd": None, "scale": vendor_scale}
    try:
        vendor = vendor_total_debt(reported_bs_csv)
        if not vendor:
            out["reason"] = "no vendor total-debt series in the reported balance sheet"
            return out
        ay = max(vendor)
        out["anchor_year"] = ay

        cik = resolve_cik(ticker, cache_dir, allow_network)
        rows = {r["fiscal_year"]: r for r in build_primary_series(cik, cache_dir, allow_network)}
        p = rows.get(ay)
        if p is None:
            out["verdict"] = "NO PRIMARY"
            out["reason"] = f"no primary-source row for fiscal {ay}"
            return out

        if vendor_scale is None:
            vendor_scale, _ = infer_vendor_scale(vendor, list(rows.values()))
        out["scale"] = vendor_scale
        v = vendor[ay] * (vendor_scale or 1.0)
        out["vendor_musd"] = v

        borrow, leases = p["borrowings_musd"], p["lease_liabilities_musd"]
        out["borrowings_musd"], out["leases_musd"] = borrow, leases

        if borrow is None:
            out["verdict"] = "NO PRIMARY"
            out["reason"] = "no borrowings route resolved from this filer's tags"
            return out

        if leases is None:
            # No lease tags. If the vendor row already equals borrowings it never carried
            # leases and the ruling is a no-op; otherwise the gap is unexplained.
            if _agrees(v, borrow, ANCHOR_CORROBORATION_TOL):
                out.update(verdict="NO LEASES IN ROW", apply=False,
                           reason="vendor row already equals borrowings — ruling is a no-op")
            else:
                out.update(verdict="UNCORROBORATED",
                           reason="no lease tags, and the vendor row does not equal "
                                  "borrowings — the gap is unexplained")
            return out

        route2 = v - leases
        out["vendor_less_leases_musd"] = route2
        if _agrees(route2, borrow, ANCHOR_CORROBORATION_TOL):
            out.update(verdict="CORROBORATED", apply=True, debt_musd=borrow,
                       reason=(f"vendor {v:,.0f} less leases {leases:,.0f} = {route2:,.0f} "
                               f"agrees with primary-source borrowings {borrow:,.0f}"))
        else:
            out.update(verdict="UNCORROBORATED",
                       reason=(f"routes disagree by {route2 - borrow:,.0f}m "
                               f"(vendor less leases {route2:,.0f} vs borrowings {borrow:,.0f}) "
                               f"— one side's tags are incomplete and we cannot tell which"))
        return out
    except Exception as e:                       # never take down a valuation run
        out["verdict"] = "ERROR"
        out["reason"] = f"{type(e).__name__}: {e}"[:160]
        return out


def anchor_basis_console_line(res):
    """One plain-language line for the run log."""
    t, v = res["ticker"], res["verdict"]
    if res.get("apply"):
        old, new = res["vendor_musd"], res["borrowings_musd"]
        return (f"[debt-basis] {t} LEASE RULING APPLIED: anchor debt {old:,.0f} -> {new:,.0f} "
                f"({new - old:+,.0f}m, {100.0 * (new - old) / old:+.1f}%). {res['reason']}")
    if v == "NO LEASES IN ROW":
        return f"[debt-basis] {t} no change needed: {res['reason']}"
    return (f"[debt-basis] {t} LEASE RULING NOT APPLIED ({v}): {res['reason']}. The engine is "
            f"still valuing on the vendor row, whose lease definition changes mid-series.")
