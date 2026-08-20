"""
market_erp_live.py — read the PUBLISHED market ERP instead of typing it.

WHY THIS EXISTS. `tools/idio_erp_anchor_calibration.py` carried `MARKET_ERP_PCT = 3.3654`
as a typed literal. That figure is not arbitrary and it is not wrong -- it is exactly the
effective ERP published on 2026-08-13 (verified against `real-yields` commit `9ee3222`).
It is a frozen snapshot of a number that republishes every weekday at 12:30 UTC. On
2026-08-18 the published figure is 3.3690, so the drift was 0.4bp and harmless. It will
not stay harmless: the August re-anchor moves the effective ERP by roughly 7bp on the
landed vs(T) work alone, and the calibration would have gone on solving against a
five-days-stale constant with nothing anywhere reporting the mismatch.

Same defect class as the held-state pointer fixed in `real-yields` the same day, and the
same remedy: derive it, never type it, and make the fallback announce itself.

THE SOURCE ORDER, AND WHY THE OBVIOUS ONE IS LAST.

  1. `AEG_REAL_YIELDS` env var, if set, pointing at a checkout.
  2. The published file on GitHub raw. This is the primary source. The daily job commits
     `history/ERP_effective_latest.csv` to a PUBLIC repository, so no token is needed and
     what comes back is by definition the number the engine actually published.
  3. A local `real-yields` checkout, if one is present and its own `vintage` column is
     fresh. LAST, not first, and conditionally -- because it goes stale silently. Checked
     on 2026-08-18: `C:\\Users\\james\\Documents\\GitHub\\real-yields` was sitting at
     vintage 2026-07-28 and commit `8a4eab9`, three weeks and many commits behind the
     remote. A resolution order that preferred the local checkout would have quietly
     substituted a July number for an August one. The project's own CLAUDE.md warns that
     this checkout goes stale; this module is what happens when that warning is obeyed.
  4. A dated fallback constant, which RAISES if it is older than `MAX_FALLBACK_AGE_DAYS`.
     A fallback that never expires is just a hardcode with better manners.

Every return says which source answered and how old it is. Nothing here decides anything;
it only reports what the market ERP engine published.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import os

RAW_BASE = "https://raw.githubusercontent.com/JamesKostohryz/real-yields/main/"
EFFECTIVE_PATH = "history/ERP_effective_latest.csv"
FORWARD_PATH = "history/TODAY_forward_curve_latest.csv"

LOCAL_CANDIDATES = [
    os.environ.get("AEG_REAL_YIELDS", ""),
    r"C:\Users\james\Documents\GitHub\real-yields",
    "/sessions/vigilant-modest-dijkstra/mnt/GitHub/real-yields",
    os.path.expanduser("~/Documents/GitHub/real-yields"),
]

# Last-resort values. Dated on purpose: this expires rather than rotting.
FALLBACK = dict(date="2026-08-18", eff_tips_ry=2.5457, eff_erp=3.3690,
                eff_coe=5.9146, duration=25.0)
MAX_FALLBACK_AGE_DAYS = 21

# How stale a LOCAL checkout may be before it is skipped in favour of the network.
MAX_LOCAL_AGE_DAYS = 5

# The value this module replaces, kept only so the change is auditable.
# 3.3654 == the effective ERP published 2026-08-13 (real-yields commit 9ee3222).
SUPERSEDED_HARDCODE = 3.3654
SUPERSEDED_HARDCODE_DATE = "2026-08-13"


def _age_days(iso, asof=None):
    a = dt.date.fromisoformat(asof) if asof else dt.datetime.now(dt.timezone.utc).date()
    return (a - dt.date.fromisoformat(iso)).days


def _http_get(url, timeout=20, auth=False):
    """`auth` adds a bearer token when one is in the environment. GitHub's REST API allows 60
    unauthenticated requests an hour PER IP -- a shared runner or sandbox burns that in minutes
    and then returns 403. That is how the vintage of the aggregate credit curve came back None
    with no error surfaced. Authenticated it is 1,000/hour and 5,000 for a personal token."""
    import os as _os
    import urllib.request
    headers = {"User-Agent": "aeg-market-erp-live"}
    if auth:
        tok = (_os.environ.get("GITHUB_TOKEN") or _os.environ.get("GH_TOKEN")
               or _os.environ.get("CROSS_REPO_TOKEN") or "")
        if tok:
            headers["Authorization"] = "Bearer %s" % tok
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8")


def _parse_effective(text):
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise ValueError("ERP_effective_latest.csv is empty")
    r = rows[-1]
    return dict(date=r["date"],
                eff_tips_ry=float(r["eff_tips_ry"]),
                eff_erp=float(r["eff_erp"]),
                eff_coe=float(r["eff_coe"]),
                duration=float(r["duration"]))


def _local_paths(relpath):
    for base in LOCAL_CANDIDATES:
        if base and os.path.isdir(base):
            p = os.path.join(base, *relpath.split("/"))
            if os.path.exists(p):
                yield p


def fetch_market_erp(asof=None, allow_network=True, log=print):
    """Return the published effective market ERP as a dict with a `source` key.

    Raises RuntimeError if every source fails and the dated fallback has expired.
    """
    errors = []

    if allow_network:
        try:
            out = _parse_effective(_http_get(RAW_BASE + EFFECTIVE_PATH))
            out["source"] = "github-raw"
            out["age_days"] = _age_days(out["date"], asof)
            log("  market ERP: %.4f%% published %s (github raw, %d days old)"
                % (out["eff_erp"], out["date"], out["age_days"]))
            return out
        except Exception as e:                     # noqa: BLE001 -- any failure falls through
            errors.append("github-raw: %s" % e)

    for p in _local_paths(EFFECTIVE_PATH):
        try:
            out = _parse_effective(open(p).read())
        except Exception as e:                     # noqa: BLE001
            errors.append("%s: %s" % (p, e))
            continue
        age = _age_days(out["date"], asof)
        if age > MAX_LOCAL_AGE_DAYS:
            errors.append("%s: vintage %s is %d days old (limit %d) -- local checkouts in "
                          "this project go stale silently, so it is skipped rather than used"
                          % (p, out["date"], age, MAX_LOCAL_AGE_DAYS))
            continue
        out["source"] = "local:%s" % p
        out["age_days"] = age
        log("  market ERP: %.4f%% published %s (local checkout, %d days old)"
            % (out["eff_erp"], out["date"], age))
        return out

    age = _age_days(FALLBACK["date"], asof)
    if age > MAX_FALLBACK_AGE_DAYS:
        raise RuntimeError(
            "no live market ERP available and the dated fallback (%s) is %d days old, past "
            "the %d-day limit. Refusing to calibrate against a stale market ERP -- that is "
            "the defect this module was written to remove. Tried:\n  %s"
            % (FALLBACK["date"], age, MAX_FALLBACK_AGE_DAYS, "\n  ".join(errors)))
    out = dict(FALLBACK)
    out["source"] = "dated-fallback"
    out["age_days"] = age
    log("  ** market ERP: FALLING BACK to the dated constant %.4f%% (%s, %d days old). "
        "Live sources all failed: %s" % (out["eff_erp"], out["date"], age, "; ".join(errors)))
    return out


def fetch_forward_curve(asof=None, allow_network=True, log=print):
    """The 30-tenor published curve. Needed by any construction that attaches a premium at
    a specific tenor rather than to the collapsed effective number.

    Returns (rows, meta) where rows is a list of dicts keyed tenor/fwd_erp/spot_erp/etc.
    """
    errors = []
    text = None
    src = None
    if allow_network:
        try:
            text = _http_get(RAW_BASE + FORWARD_PATH)
            src = "github-raw"
        except Exception as e:                     # noqa: BLE001
            errors.append("github-raw: %s" % e)
    if text is None:
        for p in _local_paths(FORWARD_PATH):
            try:
                text = open(p).read()
                src = "local:%s" % p
                break
            except Exception as e:                 # noqa: BLE001
                errors.append("%s: %s" % (p, e))
    if text is None:
        raise RuntimeError("no forward curve available. Tried:\n  %s" % "\n  ".join(errors))

    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        rows.append({k: (int(v) if k == "tenor" else float(v)) for k, v in r.items()})
    if len(rows) != 30:
        raise RuntimeError("forward curve has %d tenors, expected 30" % len(rows))
    log("  forward curve: %d tenors, fwd_erp 1y=%.4f 30y=%.4f (%s)"
        % (len(rows), rows[0]["fwd_erp"], rows[-1]["fwd_erp"], src))
    return rows, dict(source=src)


def fetch_issuer_credit(ticker, allow_network=True, log=None):
    """The issuer's own fitted real credit curve, from real-yields outputs/cod_<T>_annual.csv.

    Returns dict(tenor -> spread_pct), plus `offset`, `rating` and `has_real_fit`.

    `has_real_fit` is the load-bearing field. `asfp/idio_ts.fit_offset()` returns an offset
    of EXACTLY 1.0 when no bonds were fit at all, in which case the "issuer spread" is a
    generic rating-curve number wearing the ticker's name. Five of the sixteen tickers with
    cost-of-debt data are in that state (AZO, COST, MCD, NKE, POOL). Any construction that
    uses an issuer spread as a LEVEL must filter on this rather than assume it.
    """
    rel = "outputs/cod_%s_annual.csv" % ticker
    text = None
    if allow_network:
        try:
            text = _http_get(RAW_BASE + rel)
        except Exception:                          # noqa: BLE001
            text = None
    if text is None:
        for p in _local_paths(rel):
            try:
                text = open(p).read()
                break
            except Exception:                      # noqa: BLE001
                continue
    if text is None:
        return None

    spread, offset, rating = {}, None, None
    for r in csv.DictReader(io.StringIO(text)):
        try:
            spread[int(round(float(r["tenor"])))] = 100.0 * float(r["spread"])
        except (KeyError, TypeError, ValueError):
            continue
        offset = float(r.get("offset", "nan") or "nan")
        rating = r.get("rating")
    if not spread:
        return None
    has_real_fit = offset is not None and abs(offset - 1.0) > 1e-9
    out = dict(ticker=ticker, spread_pct=spread, offset=offset, rating=rating,
               has_real_fit=has_real_fit)
    if log:
        log("  %s: 1y %.4f%%  30y %.4f%%  offset %.4f  rating %s  real_fit=%s"
            % (ticker, spread.get(1, float("nan")), spread.get(30, float("nan")),
               offset, rating, has_real_fit))
    return out



# --------------------------------------------------------------- aggregate IG credit curve

MARKET_CREDIT_PATH = "outputs/market_credit_latest_annual.csv"
COMMITS_API = ("https://api.github.com/repos/JamesKostohryz/real-yields/commits"
               "?path=%s&per_page=1" % MARKET_CREDIT_PATH)

# How stale the aggregate credit curve may be before it is refused outright. It is rewritten
# every weekday by erp-daily-close, so a fortnight's silence means the job has stopped.
MAX_CREDIT_AGE_DAYS = 14


def fetch_market_credit(allow_network=True, log=None, asof=None):
    """The AGGREGATE investment-grade credit curve, 1..30y, in percent.

    Source: real-yields `outputs/market_credit_latest_annual.csv`, column `ig_index_spread`.
    That column is the ICE BofA IG option-adjusted spread interpolated across the maturity
    buckets 1-3 / 3-5 / 5-7 / 7-10 / 10-15 / 15+ (asfp/credit.py::IG_MATURITY), held flat
    outside the end knots. It is rewritten every weekday, so it is a live series rather than a
    constant.

    THERE IS DELIBERATELY NO DATED FALLBACK. Every other reader in this module degrades to a
    dated constant because a stale market ERP is merely imprecise. A stale or absent aggregate
    credit curve is different in kind: `idio.erp.COMMON(t)` is charged to EVERY company at every
    tenor, so a frozen one would move all 499 published premiums in lockstep and no identity
    check could see it. It raises instead.

    Returns dict(spread_pct={tenor: pct}, source=str, vintage=str|None, age_days=int|None).
    """
    errors = []
    text = src = vintage = None

    if allow_network:
        try:
            text = _http_get(RAW_BASE + MARKET_CREDIT_PATH)
            src = "github-raw"
        except Exception as e:                     # noqa: BLE001
            errors.append("github-raw: %s" % e)
        if text is not None:
            try:
                import json as _json
                j = _json.loads(_http_get(COMMITS_API, auth=True))
                vintage = j[0]["commit"]["committer"]["date"][:10]
            except Exception as e:                 # noqa: BLE001
                errors.append("commits-api: %s" % e)
        # A CURVE WITH NO VINTAGE IS NOT AN ACCEPTABLE CURVE, and it used to be accepted.
        # Until 2026-08-20 the raw fetch succeeding while the commits API 403'd left
        # vintage=None and age_days=None, and the network path then applied NO AGE CHECK AT ALL
        # -- unlike the local path four lines below, which refuses past MAX_CREDIT_AGE_DAYS.
        # COMMON(t) is charged to EVERY company at EVERY tenor, so an unbounded-age aggregate
        # credit curve is a silent input to every discount rate on the system. The comment on
        # the local branch already said the age "is used to REFUSE, never to reassure"; the
        # network branch simply had no age to use.
        #
        # Discarding the text here does not fail the run: it falls through to the local
        # checkout, which HAS a real age check. It only refuses if there is no local copy
        # either -- which is the honest outcome, because at that point nothing in reach can
        # say how old the number is.
        if text is not None and not vintage:
            errors.append("github-raw: fetched, but the vintage could not be established, so "
                          "its age cannot be checked. Falling back to a local checkout.")
            text = src = None

    if text is None:
        for p in _local_paths(MARKET_CREDIT_PATH):
            try:
                raw = open(p).read()
            except Exception as e:                 # noqa: BLE001
                errors.append("%s: %s" % (p, e))
                continue
            # A local checkout carries no vintage column, so the file's own mtime is the only
            # honest age available. It is used to REFUSE, never to reassure.
            v = dt.date.fromtimestamp(os.path.getmtime(p)).isoformat()
            age = _age_days(v, asof)
            if age > MAX_CREDIT_AGE_DAYS:
                errors.append("%s: file is %d days old (limit %d)" % (p, age, MAX_CREDIT_AGE_DAYS))
                continue
            text, src, vintage = raw, "local:%s" % p, v
            break

    if text is None:
        raise RuntimeError(
            "no aggregate IG credit curve available, and there is no fallback by design. "
            "COMMON(t) is charged to every company at every tenor; substituting a constant "
            "would move 499 premiums in lockstep with nothing able to detect it. Tried:\n  %s"
            % "\n  ".join(errors))

    spread = {}
    for r in csv.DictReader(io.StringIO(text)):
        try:
            spread[int(round(float(r["tenor"])))] = float(r["ig_index_spread"])
        except (KeyError, TypeError, ValueError):
            continue
    if len(spread) < 30:
        raise RuntimeError("aggregate IG credit curve has %d tenors, expected at least 30 (%s)"
                           % (len(spread), src))

    # STRUCTURAL, not defensive. Every path above now establishes a vintage -- the network
    # branch discards its text if it cannot, and the local branch derives one from the mtime --
    # so reaching here without one means a new source was added without an age. Refuse, because
    # the guard six lines below is skipped whenever `age` is None, and that skip is exactly the
    # hole this closes: for as long as GitHub's commits API returned 403 the freshness check on
    # COMMON(t) silently did not run at all.
    if not vintage:
        raise RuntimeError(
            "the aggregate IG credit curve was obtained from %s but its vintage could not be "
            "established, so its age cannot be checked. COMMON(t) is charged to every company "
            "at every tenor; a curve of unknown age is a silent input to every discount rate "
            "on the system. Refusing. Tried:\n  %s" % (src, "\n  ".join(errors) or "(nothing)"))
    age = _age_days(vintage, asof)
    if age is not None and age > MAX_CREDIT_AGE_DAYS:
        raise RuntimeError(
            "aggregate IG credit curve is %d days old (vintage %s, limit %d). The weekday "
            "erp-daily-close job that rewrites it has stopped. Refusing rather than charging "
            "every company a frozen COMMON(t)." % (age, vintage, MAX_CREDIT_AGE_DAYS))
    out = dict(spread_pct=spread, source=src, vintage=vintage, age_days=age)
    if log:
        log("  aggregate IG credit: 1y %.4f%%  10y %.4f%%  30y %.4f%%  (%s, vintage %s)"
            % (spread[1], spread[10], spread[30], src, vintage or "unknown"))
    return out


if __name__ == "__main__":
    m = fetch_market_erp()
    print(m)
    drift = m["eff_erp"] - SUPERSEDED_HARDCODE
    print("drift vs the superseded hardcode %.4f (%s): %+.4fpp"
          % (SUPERSEDED_HARDCODE, SUPERSEDED_HARDCODE_DATE, drift))
    rows, meta = fetch_forward_curve()
    print("fwd_erp at 1/2/5/10/30y: %s"
          % [rows[i - 1]["fwd_erp"] for i in (1, 2, 5, 10, 30)])
