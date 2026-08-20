#!/usr/bin/env python3
"""onboard.py — bring a bare ticker to the point where the RUN button can value it
(item 2). Writes companies/<TICKER>.yaml with conservative, documented defaults.

THE GATE: this refuses to onboard a ticker the engine cannot actually price. Readiness
is decided by rate_feed.load_all() against the LIVE feed — the same locked contract the
valuation uses — so we never re-implement the validation and the failure message IS the
contract violation. That check covers, per ticker:
    coe_v2_<T>_latest_annual.csv   6 columns + rf+erp+idio == real_coe (DECOMP_TOL 1e-5)
    cod_<T>_annual.csv             tenor, real_cod, spread, rating, offset
    company_<T>.csv                market_value_of_debt > 0
plus the global curve, all bounds-checked.

CROSS-REPO DEPENDENCY — the thing that actually limits onboarding:
those three per-company files are produced by the RATE side (real-yields company.yml ->
asfp.run_company), not by this repo. A ticker with no coe_v2 published upstream cannot be
onboarded here no matter what we write locally. As of 2026-07-22 only AAPL and T are fully
published; MSFT/KO/HD have a company file and a REDUCED cod (tenor,real_cod only — no
spread/rating/offset) and NO coe_v2, so they look present but fail the contract. This tool
reports exactly which feed is missing so the ask to the rate chat is precise.

WHAT WE DELIBERATELY DO NOT AUTO-DETECT (silent-wrong candidates)
-----------------------------------------------------------------
  spinoff              A historical spin-off (AT&T/WBD factor 1.324 before 2022) cannot be
                       inferred from statements. Defaults to none, and we say so loudly in
                       the generated file: per-share history is WRONG for a company that had
                       one until a human sets it.
  expect_zero_rd_wedge Left false (unasserted). Setting it true is a real assertion — the run
                       ABORTS if the opex wedge isn't ~0 — and that's a judgment about the
                       business, not a default.
  rd_capitalize        Left false. R&D capitalization is documented INERT in the engine, so
                       false is both the safe and the honest default.
  cost_of_debt         Preferred 'bond_list' when the issuer's bond curve validates (bonded).
                       When a name has too few traded bonds, we DO NOT refuse: we emit
                       bonded:false and let the valuation take the wired synthetic-rating ladder
                       (cod_fallback: interest-coverage rating -> real_cod_<rating>, AMBER). A
                       human can still override with single_ytw / ytw_points if the synthetic
                       rating is wrong for the name. Cost of EQUITY (coe_v2) is still required
                       for every name — that is genuinely firm-specific, not a bond dependency.
Everything written here is a committed, reviewable judgment — the point is that a default is
visible in a diff, not buried in code.
"""
import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.dirname(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

COMPANIES_DIR = "companies"
MIN_COD_TENORS = 30


class OnboardError(Exception):
    """Refusal to onboard. Always carries the specific reason."""


# ------------------------------------------------------------------ readiness
def check_rate_readiness(ticker, *, local_dir=None):
    """Ask the locked contract whether the rate side can price this ticker.
    Returns (ready: bool, detail: str)."""
    import rate_feed as RF
    try:
        feed = RF.load_all(ticker, cash=0.0, sti=0.0, local_dir=local_dir, bonded=True)
    except RF.RateFeedError as e:
        return False, str(e)
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
    n = len(feed.get("real_cod") or [])
    if n < MIN_COD_TENORS:
        return False, f"cod curve has {n} tenors, need {MIN_COD_TENORS}"
    mvd = (feed.get("company") or {}).get("market_value_of_debt")
    return True, (f"coe_v2 + cod({n} tenors) + company OK; "
                  f"market_value_of_debt={mvd:.4g}; nfo_basis={feed.get('nfo_basis')}")


def check_rate_readiness_unbonded(ticker, *, local_dir=None):
    """Can we price this name WITHOUT an issuer bond curve? The valuation's synthetic-rating
    cost-of-debt ladder (run_company -> cod_fallback) needs only: (1) the per-company cost of
    EQUITY (coe_v2, still genuinely firm-specific) + the global real curve, both via
    RF.load_all(bonded=False), and (2) the generic by-rating credit curve
    (market_credit_latest_annual.csv) that maps a rating to real_cod_<rating>. Cost of debt is
    then computed from the firm's own interest-coverage rating at valuation time (AMBER).
    Returns (ready: bool, detail: str)."""
    import rate_feed as RF
    try:
        RF.load_all(ticker, cash=0.0, sti=0.0, local_dir=local_dir, bonded=False)
    except RF.RateFeedError as e:
        return False, f"cost-of-equity feed not ready: {e}"
    except Exception as e:
        return False, f"cost-of-equity feed not ready: {type(e).__name__}: {e}"
    try:
        import cod_fallback as CF
        curve = CF.load_credit_curve(local_dir=local_dir)
    except Exception as e:
        return False, f"by-rating credit curve unavailable: {type(e).__name__}: {e}"
    nt = len(curve.get("tenor") or [])
    if nt < MIN_COD_TENORS:
        return False, f"credit curve has {nt} tenors, need {MIN_COD_TENORS}"
    return True, (f"coe_v2 + global curve + by-rating credit curve({nt} tenors) OK; "
                  f"cost of debt from the SYNTHETIC-RATING ladder (AMBER); book NFO")


def missing_feeds(ticker, *, local_dir=None):
    """Which of the three per-company feeds are absent/broken — a precise ask for the
    rate chat rather than 'onboarding failed'."""
    import rate_feed as RF
    out = {}
    for label, fn in (("coe_v2", lambda: RF.load_coe(ticker, local_dir=local_dir)),
                      ("cod", lambda: RF.load_cod(ticker, local_dir=local_dir)),
                      ("company", lambda: RF.load_company(ticker, local_dir=local_dir))):
        try:
            fn()
            out[label] = "OK"
        except Exception as e:
            msg = str(e)
            out[label] = ("MISSING (404)" if "HTTPError" in msg or "404" in msg
                          else f"INVALID: {msg[:120]}")
    return out


# ------------------------------------------------------------------ scope (Rule 5)
FINANCIAL_GICS = "Financials"


def check_scope(ticker, *, api_key=None):
    """Engine A Rule 5: financial companies (banks/insurers) are OUT OF SCOPE. For them debt
    is an operating input, so the enterprise-level NOA = CSE + NFO partition and the
    operating/financing split the engine rests on are meaningless. Best-effort classification
    from EODHD 'General' (GICS sector). Returns (in_scope: bool, detail: str). With no EODHD key
    (e.g. --cached), scope cannot be classified and we let it through (a bank would then fail the
    tie downstream rather than here)."""
    key = api_key or os.environ.get("EODHD_API_KEY")
    if not key:
        return True, "scope unchecked (no EODHD key / cached mode)"
    try:
        import eodhd_puller as EP
        g = EP._http_json(
            f"https://eodhd.com/api/fundamentals/{EP._eodhd_symbol(ticker)}"
            f"?api_token={key}&fmt=json&filter=General") or {}
    except Exception as e:
        return True, f"scope unchecked (EODHD General lookup failed: {type(e).__name__})"
    gic = str(g.get("GicSector") or "").strip()
    sector = str(g.get("Sector") or "").strip()
    industry = str(g.get("Industry") or "").strip()
    if gic == FINANCIAL_GICS or sector == "Financial Services":
        return False, (
            f"{ticker} is a FINANCIAL company (sector={sector!r}, industry={industry!r}, "
            f"GICS={gic!r}) \u2014 OUT OF SCOPE per Engine A Rule 5. Banks and insurers cannot be "
            f"valued at enterprise level: debt is an operating input, so the NOA = CSE + NFO "
            f"partition and the operating/financing split this engine is built on do not apply. "
            f"Use the separate financials approach; do not force this one.")
    return True, f"in scope (sector={sector!r}, GICS={gic!r})"


# ------------------------------------------------------------------ statements
def detect_company_facts(ticker, *, cached_dir=None, api_key=None):
    """Company display name + fiscal-year-end month. fy_end_month=0 means 'auto-detect
    from statement dates', which the loader supports — we prefer 0 over a guess."""
    facts = {"company": None, "fy_end_month": 0, "source": None}
    if cached_dir:
        facts["source"] = f"cached:{cached_dir}"
        for k in ("REAL_IS.csv", "is.csv"):
            if os.path.exists(os.path.join(cached_dir, k)):
                return facts
        raise OnboardError(f"cached dir {cached_dir} has no income-statement CSV")
    key = api_key or os.environ.get("EODHD_API_KEY")
    if not key:
        raise OnboardError(
            "EODHD_API_KEY not set and no --cached dir: cannot verify statements exist. "
            "Refusing to write a config for a ticker whose statements we haven't seen.")
    try:
        import eodhd_puller as EP
        fund = EP._http_json(
            f"https://eodhd.com/api/fundamentals/{EP._eodhd_symbol(ticker)}"
            f"?api_token={key}&fmt=json&filter=General")
        facts["company"] = (fund or {}).get("Name") or None
        facts["source"] = "eodhd:General"
    except Exception as e:
        raise OnboardError(f"EODHD lookup failed for {ticker}: {type(e).__name__}: {e}")
    if not facts["company"]:
        raise OnboardError(f"EODHD returned no company name for {ticker}")
    return facts


# ------------------------------------------------------------------ config
def _cod_block(t, bonded):
    """The cost_of_debt + bonded lines, honest about which pricing path the name takes."""
    if bonded:
        return (
            "cost_of_debt:\n"
            "  source: bond_list            # validated against the live cod_{t} curve at onboarding\n"
            "\n"
            "bonded: true                   # cod_{t} / company_{t} published upstream and contract-valid\n"
        ).replace("{t}", t)
    return (
        "cost_of_debt:\n"
        "  source: bond_list            # PREFERRED but unavailable: {t} has too few traded bonds to\n"
        "                               # fit an issuer curve. Cost of debt is taken from the\n"
        "                               # SYNTHETIC-RATING ladder instead (cod_fallback: the firm's\n"
        "                               # interest-coverage rating -> real_cod_<rating> off the\n"
        "                               # by-rating credit curve), flagged AMBER in the cockpit audit.\n"
        "                               # TO OVERRIDE with your own estimate, replace the two lines\n"
        "                               # above with:  source: single_ytw  and  single_ytw: 0.05\n"
        "                               # (a real yield, e.g. 0.05 = 5%), or source: ytw_points with a\n"
        "                               # [[tenor, ytw], ...] list. That is the manual last resort.\n"
        "\n"
        "bonded: false                  # NO issuer bond curve -> rating-curve cost of debt + book NFO.\n"
        "                               # Cost of EQUITY (coe_v2) is still published upstream and used.\n"
    ).replace("{t}", t)


def render_config(ticker, company, fy_end_month, readiness_detail, *, bonded=True):
    t = ticker.upper()
    return f'''# Per-company statement-adjustment config — {company}
# AUTO-GENERATED by pipeline/onboard.py. Every field is a committed, reviewable judgment:
# change it in a PR and the restated statements change deterministically.
#
# Rate readiness at onboarding: {readiness_detail}
company: "{company}"
ticker: {t}
fy_end_month: {fy_end_month}          # 0 = auto-detect from statement dates

# THE ONE THING ONBOARDING CANNOT DO FOR YOU, LEFT DELIBERATELY BLANK.
#
# forecast.horizon_N is cfg_N, the competitive-advantage period: the number of years YOU judge
# abnormal earnings growth to persist for this company. It is the single most powerful judgment
# in the model -- worth 31% on the Apple fixture between 4 and 30 years -- and rule D1 makes it
# permanently human. There is no default, no suggestion here, and there never will be, because
# suggesting one is how the last default got established.
#
# Until both lines below are filled in and uncommented, {t} is AWAITING FORECAST: it produces no
# valuation, and the fleet run lists it by name every time so it is not forgotten.
#
# forecast:
#   horizon_N:                 # <- your judgment, an integer of years
#   reviewed: true             # <- your confirmation that you chose it for THIS company

judgments:
  minority_include: false      # exclude minority interest from common equity
  finlease: 0.0                # KEEP 0.0. The add-back is NOT wired: in_finlease feeds no engine
                               # formula and NFO = in_debt - in_cash - in_sti, so a non-zero value
                               # silently does nothing (the run refuses it). EODHD 'Total Debt'
                               # already includes capitalized finance leases for most names, so 0.0
                               # is correct; an extra add-back is an engine-backlog item.
  oi_adj_override: null        # KEEP null. NOT a working normalization knob: the economic
                               # restatement anchors on reported operating income, and this value
                               # feeds only an audit identity requiring it to EQUAL reported OI, so
                               # a real override breaks the tie (the run refuses it). To value a
                               # cyclical on a representative base, repoint FY0 to a representative
                               # fiscal year instead. (Normalized-anchor override = engine backlog.)
  rd_capitalize: false         # KEEP false. R&D capitalization is currently INERT: the Cap Engine
                               # reserve is computed but referenced nowhere downstream, so true
                               # changes neither NOA nor operating income (it does NOT capitalize
                               # R&D). Do not set true expecting a capitalized-R&D restatement until
                               # the capitalization increment is wired (engine backlog).
  rd_life: 5.0                 # (unused while rd_capitalize is inert)
  dps_override: null           # override near-term dividend (null = from dividends file)

# !! NOT AUTO-DETECTED — a spin-off cannot be inferred from statements. If {t} has had one,
# per-share history is WRONG until you set these by hand (see companies/T.yaml, factor 1.324
# before 2022 for the WBD spin).
spinoff:
  factor: 1.0                  # contemporaneous-price spinoff factor (1.0 = none)
  before_year: 0               # apply the factor to fiscal years before this (0 = n/a)

price:
  source: market               # "market" = latest close from the staged prices file
  override: null

{_cod_block(t, bonded)}
# Forecast row 61 is the reported-vs-economic operating-expense wedge (R&D + other opex).
# Left UNASSERTED (false) on purpose: setting true makes the run ABORT unless the wedge is
# ~0, which is a real claim about the business. Flip it only once you've seen this name's
# wedge and believe it should be zero (see companies/T.yaml).
expect_zero_rd_wedge: false
'''


def onboard(ticker, *, cached_dir=None, api_key=None, local_dir=None,
            company_name=None, fy_end_month=None, out_dir=COMPANIES_DIR, force=False):
    t = ticker.strip().upper()
    if not t.isalnum():
        raise OnboardError(f"ticker {ticker!r} is not alphanumeric")
    path = os.path.join(out_dir, f"{t}.yaml")
    if os.path.exists(path) and not force:
        raise OnboardError(f"{path} already exists (use --force to overwrite)")

    in_scope, scope_detail = check_scope(t, api_key=api_key)
    if not in_scope:
        raise OnboardError(scope_detail)

    # Two-step readiness: prefer the issuer bond curve; fall back to the synthetic-rating ladder
    # when the name is thin-/no-bond but its cost of equity is published. Only refuse when even the
    # cost-of-equity feed is missing (that IS genuinely not-priceable).
    bonded, detail = True, None
    ready, detail = check_rate_readiness(t, local_dir=local_dir)
    if not ready:
        u_ready, u_detail = check_rate_readiness_unbonded(t, local_dir=local_dir)
        if u_ready:
            bonded, detail = False, u_detail
        else:
            feeds = missing_feeds(t, local_dir=local_dir)
            raise OnboardError(
                f"RATE FEED NOT READY for {t} — the engine cannot price it yet.\n"
                f"  bonded path    : {detail}\n"
                f"  unbonded path  : {u_detail}\n"
                f"  per-feed status: " + ", ".join(f"{k}={v}" for k, v in feeds.items()) + "\n"
                f"  The cost-of-EQUITY feed (coe_v2) is produced by the RATE side (real-yields\n"
                f"  company.yml -> asfp.run_company) and is required for every name. Publish {t}\n"
                f"  upstream, then re-run onboarding. Refusing to write a config that can't price.")

    facts = {"company": company_name, "fy_end_month": fy_end_month or 0}
    if not company_name:
        got = detect_company_facts(t, cached_dir=cached_dir, api_key=api_key)
        facts["company"] = got["company"] or t
        if fy_end_month is None:
            facts["fy_end_month"] = got["fy_end_month"]

    text = render_config(t, facts["company"], facts["fy_end_month"], detail, bonded=bonded)
    os.makedirs(out_dir, exist_ok=True)
    with open(path, "w") as fh:
        fh.write(text)

    # round-trip through the real loader so we never emit a config it would reject
    try:
        import config as CFG
    except ImportError:
        sys.path.insert(0, os.path.join(_HERE))
        import config as CFG
    # Round-trip through the real loader so we never emit a config it would reject -- but
    # WITHOUT the forecast gate, because horizon_N is the one field onboarding cannot supply.
    # It is the judgment onboarding exists to make possible, and requiring it here meant the
    # validator refused every config this tool generated and deleted it again, so no new
    # company could be added to the system at all. Everything else is validated exactly as
    # before. The onboarded company is AWAITING FORECAST until a human sets horizon_N and
    # reviewed: true; it produces no valuation and is named on every fleet run until then.
    try:
        norm = CFG.load_config(path, require_forecast=False)
    except Exception as e:
        os.remove(path)
        raise OnboardError(f"generated config failed validation (not written): {e}")

    return {"ticker": t, "path": path, "company": facts["company"],
            "fy_end_month": facts["fy_end_month"], "config_hash": norm.get("config_hash"),
            "bonded": bonded, "readiness": detail}


def main():
    ap = argparse.ArgumentParser(description="Onboard a bare ticker for the AEG RUN loop.")
    ap.add_argument("ticker")
    ap.add_argument("--cached", help="dir with cached statement CSVs (skips the EODHD lookup)")
    ap.add_argument("--rate-feed-dir", help="local rate CSVs instead of the live feed (testing)")
    ap.add_argument("--company-name", help="override the display name")
    ap.add_argument("--fy-end-month", type=int, help="1..12, or 0 to auto-detect (default 0)")
    ap.add_argument("--out-dir", default=COMPANIES_DIR)
    ap.add_argument("--force", action="store_true", help="overwrite an existing config")
    ap.add_argument("--check-only", action="store_true",
                    help="report rate readiness and exit; write nothing")
    args = ap.parse_args()

    t = args.ticker.strip().upper()
    if args.check_only:
        in_scope, scope_detail = check_scope(t)
        print(f"[onboard] {t} scope: {'IN SCOPE' if in_scope else 'OUT OF SCOPE'} — {scope_detail}")
        if not in_scope:
            return 1
        ready, detail = check_rate_readiness(t, local_dir=args.rate_feed_dir)
        print(f"[onboard] {t} bonded readiness: {'READY' if ready else 'NOT READY'}")
        print(f"  {detail}")
        if not ready:
            u_ready, u_detail = check_rate_readiness_unbonded(t, local_dir=args.rate_feed_dir)
            print(f"[onboard] {t} unbonded (synthetic-rating) readiness: "
                  f"{'READY' if u_ready else 'NOT READY'}")
            print(f"  {u_detail}")
            if not u_ready:
                for k, v in missing_feeds(t, local_dir=args.rate_feed_dir).items():
                    print(f"    {k:8} {v}")
            return 0 if u_ready else 1
        return 0

    try:
        rep = onboard(t, cached_dir=args.cached, local_dir=args.rate_feed_dir,
                      company_name=args.company_name, fy_end_month=args.fy_end_month,
                      out_dir=args.out_dir, force=args.force)
    except OnboardError as e:
        print(f"[onboard] REFUSED: {e}", file=sys.stderr)
        return 1
    print(f"[onboard] wrote {rep['path']}")
    print(f"  company     : {rep['company']}")
    print(f"  fy_end_month: {rep['fy_end_month']} (0 = auto-detect)")
    print(f"  config_hash : {rep['config_hash']}")
    print(f"  cost of debt: {'issuer bonds (bonded)' if rep['bonded'] else 'SYNTHETIC RATING (unbonded, AMBER)'}")
    print(f"  readiness   : {rep['readiness']}")
    print("  NEXT: review the file (spinoff / expect_zero_rd_wedge / rd_capitalize are "
          "conservative defaults), then run the valuation to prove it TIES before trusting it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
