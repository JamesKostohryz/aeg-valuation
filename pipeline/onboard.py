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
  cost_of_debt         Only ever 'bond_list', and only when the bond-based curve validates.
                       We never invent a discount rate; an unbonded name requires a human to
                       supply single_ytw / ytw_points.
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
def render_config(ticker, company, fy_end_month, readiness_detail):
    t = ticker.upper()
    return f'''# Per-company statement-adjustment config — {company}
# AUTO-GENERATED by pipeline/onboard.py. Every field is a committed, reviewable judgment:
# change it in a PR and the restated statements change deterministically.
#
# Rate readiness at onboarding: {readiness_detail}
company: "{company}"
ticker: {t}
fy_end_month: {fy_end_month}          # 0 = auto-detect from statement dates

judgments:
  minority_include: false      # exclude minority interest from common equity
  finlease: 0.0                # finance/capital-lease obligations to add back (0 = none)
  oi_adj_override: null        # override operating-income adjustment (null = derived)
  rd_capitalize: false         # DEFAULT false: R&D capitalization is documented INERT in the
                               # engine, so false is the honest default. Set true (with
                               # rd_life) only as a deliberate judgment for an R&D-heavy name.
  rd_life: 5.0                 # (unused while rd_capitalize is false)
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

cost_of_debt:
  source: bond_list            # validated against the live cod_{t} curve at onboarding

bonded: true                   # cod_{t} / company_{t} published upstream and contract-valid

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

    ready, detail = check_rate_readiness(t, local_dir=local_dir)
    if not ready:
        feeds = missing_feeds(t, local_dir=local_dir)
        raise OnboardError(
            f"RATE FEED NOT READY for {t} — the engine cannot price it yet.\n"
            f"  contract error : {detail}\n"
            f"  per-feed status: " + ", ".join(f"{k}={v}" for k, v in feeds.items()) + "\n"
            f"  These are produced by the RATE side (real-yields company.yml -> asfp.run_company),\n"
            f"  not by this repo. Ask the rate chat to publish {t}, then re-run onboarding.\n"
            f"  Refusing to write a config that would fail mid-valuation.")

    facts = {"company": company_name, "fy_end_month": fy_end_month or 0}
    if not company_name:
        got = detect_company_facts(t, cached_dir=cached_dir, api_key=api_key)
        facts["company"] = got["company"] or t
        if fy_end_month is None:
            facts["fy_end_month"] = got["fy_end_month"]

    text = render_config(t, facts["company"], facts["fy_end_month"], detail)
    os.makedirs(out_dir, exist_ok=True)
    with open(path, "w") as fh:
        fh.write(text)

    # round-trip through the real loader so we never emit a config it would reject
    try:
        import config as CFG
    except ImportError:
        sys.path.insert(0, os.path.join(_HERE))
        import config as CFG
    try:
        norm = CFG.load_config(path)
    except Exception as e:
        os.remove(path)
        raise OnboardError(f"generated config failed validation (not written): {e}")

    return {"ticker": t, "path": path, "company": facts["company"],
            "fy_end_month": facts["fy_end_month"], "config_hash": norm.get("config_hash"),
            "readiness": detail}


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
        ready, detail = check_rate_readiness(t, local_dir=args.rate_feed_dir)
        print(f"[onboard] {t} rate readiness: {'READY' if ready else 'NOT READY'}")
        print(f"  {detail}")
        if not ready:
            for k, v in missing_feeds(t, local_dir=args.rate_feed_dir).items():
                print(f"    {k:8} {v}")
        return 0 if ready else 1

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
    print(f"  readiness   : {rep['readiness']}")
    print("  NEXT: review the file (spinoff / expect_zero_rd_wedge / rd_capitalize are "
          "conservative defaults), then run the valuation to prove it TIES before trusting it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
