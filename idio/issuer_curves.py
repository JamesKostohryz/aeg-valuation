#!/usr/bin/env python3
"""
idio/issuer_curves.py — give every company a credit term structure. THE ONLY FITTER.

A VERBATIM PORT of AEG-Project `tools/region2_issuer_curves_2026-08-19.py`. Nothing about the
arithmetic, the filters, the tier boundaries, the functional form or the adoption rules was
touched in the move: the ONLY edits are where files are read from and written to. `git log -p`
on this file's first commit is the diff, and `tests/test_issuer_curves.py` proves the port
reproduces the committed `outputs/issuer_widen_latest.csv` BYTE FOR BYTE from committed inputs.
There is no second fitter and there must never be one.

WHY IT IS IN THE REPOSITORY NOW. `outputs/issuer_widen_latest.csv` carries a `generated` date and
`idio/erp.py::ISSUER_WIDEN_MAX_AGE_DAYS = 45`. Past that the reader returns `(None, reason)`,
`company_curve.build()` raises `PremiumRefused`, and EVERY valuation on the system stops — on
2026-10-03 for the 2026-08-19 vintage. Region 2 became load-bearing on 2026-08-20, so nothing
regenerating this file is a scheduled outage. `.github/workflows/issuer_curves.yml` re-runs it
monthly.

FRESH INPUTS OR IT IS A FOSSIL WITH A NEW TIMESTAMP. Re-running the fit on a frozen bond
snapshot moves the `generated` date without moving the data, which is exactly this project's
standing failure mode. `--max-bond-age-days` REFUSES when the primary bond file is older than
the limit, so the workflow cannot quietly re-stamp stale prices.

RUNS THE PRE-REGISTERED PLAN IN
AEG-Project/docs/PREREG-Region2-Issuer-Curves-and-Tier3-2026-08-19.md. Every filter, tier
boundary, functional form, directional hypothesis and adoption rule in this file was written
down before the first fit was run. Where the run departs from the plan it says so out loud
rather than quietly.

WHAT IT PRODUCES (into --outdir, default the repository's outputs/)
    issuer_widen_latest.csv   widen_i(t), t = 1..30, every name  <- read by idio/erp.py
    issuer_curve_fit.csv      per-issuer diagnostics
    tier3_fit.json            the cross-sectional slope fit; carries `generated`, which is the
                              date idio/erp.py ages against

INPUTS
    data/bond_spreads/bond_spreads_live.csv   1,449 priced bonds, 174 issuers   (committed)
    outputs/idio_universe_latest.csv          the 499-name universe + semidev    (committed)
    <real-yields>/outputs/bonds_used_<T>.csv  second source, issuers the pull missed
    <real-yields>/outputs/market_credit_latest_annual.csv   the Treasury leg for that source

WHY THE FIT IS ON THE ISSUER'S OWN BONDS AND NOT ON THE RATING CURVE. The nine curves in
production before this landed are the aggregate investment-grade shape scaled by one number per
issuer -- verified 2026-08-19 by dividing cod_<T>_annual.csv by ig_index_spread and finding the
ratio constant to about one percent across all thirty tenors. That is a level fit, not a curve
fit, and James's instruction was that the estimate should come from the company's own yields.

Usage:
    python3 idio/issuer_curves.py [--outdir outputs] [--bonds PATH] [--universe PATH]
                                  [--real-yields DIR] [--max-bond-age-days N]
                                  [--no-quality-gates]
"""
from __future__ import annotations

import csv
import json
import math
import os
import sys

# ------------------------------------------------------------------ PATHS (the only edit)
# In the working folder this read AEG_HOME/outputs/... and wrote to a dated research directory.
# In the repository the inputs are committed and the output is the file idio/erp.py reads.
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

def _arg(flag, default=None):
    """--flag VALUE, read straight off argv. No argparse, to keep this module importable and
    dependency-free exactly as the original was."""
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default

BONDS = _arg("--bonds", os.path.join(REPO, "data", "bond_spreads", "bond_spreads_live.csv"))
UNIVERSE = _arg("--universe", os.path.join(REPO, "outputs", "idio_universe_latest.csv"))
OUTDIR = _arg("--outdir", os.path.join(REPO, "outputs"))
WIDEN_NAME = "issuer_widen_latest.csv"   # the name idio/erp.py::load_issuer_widen looks for
GRID = list(range(1, 31))

# A refusal, not a warning. See the module docstring: re-running the fit on stale bonds is the
# defect, not the remedy. 0 or negative disables the check (used by the reproduction test,
# which is pinned to a 2026-08-19 vintage on purpose).
MAX_BOND_AGE_DAYS = int(_arg("--max-bond-age-days", "0") or 0)


class IssuerCurveInputStale(RuntimeError):
    """The primary bond file is older than --max-bond-age-days. Refuses rather than re-stamping
    a frozen snapshot with a fresh `generated` date."""

# ----------------------------------------------------------------- pre-registered filters (S1)
MIN_TENOR_YRS = 0.5           # F1
MIN_SPREAD_BP, MAX_SPREAD_BP = 0.0, 600.0     # F2  (strictly greater than MIN)
MAX_YTM_GAP_BP = 25.0         # F3
MAX_FIT_TENOR_YRS = 50.0      # F4 -- excluded from the FIT, still counted for coverage

# ----------------------------------------------------------------- pre-registered tiers (S2)
T1_MIN_BONDS, T1_MIN_LONGEST, T1_MIN_SPAN = 4, 10.0, 5.0
T2_MIN_BONDS = 2

# ----------------------------------------------------------------- ADDED AFTER THE FIRST RUN
# TWO QUALITY GATES ON TIER 1. NOT PRE-REGISTERED. They are recorded as post-hoc additions
# rather than folded silently into the plan, and `--no-quality-gates` reproduces the first run
# exactly so the cost of each is measurable.
#
# WHY THEY WERE ADDED. The first run's twenty-company table handed JPMorgan the LOWEST cost of
# equity of any name in it -- 4.71%, below Coca-Cola -- because its eight bonds fitted a
# DOWNWARD-sloping credit curve with an R-squared of 0.13. That is not an inverted credit curve,
# it is eight points with no shape in them, and the construction was reading the noise as a
# discount. It is precisely the leapfrog James asked to be checked for.
#
# T1_MIN_TSTAT: tier 1's claim is that the issuer's OWN bonds determine a shape. A slope that
# cannot be distinguished from zero does not determine one, so the issuer is demoted to tier 2 --
# its own level, the cross-sectional slope. This is a statement about the fit, not about the
# answer, and it is symmetric: it demotes flat-looking issuers whichever way the point estimate
# leans.
#
# T1_MAX_SHORTEST: tier 1's claim is a curve measured FROM ONE YEAR OUT. Microsoft's nearest
# bond is 8.5 years away, so its one-year spread is not observed at all -- the fit extrapolates
# it, and returns MINUS 39 basis points, which is impossible. An issuer whose front is
# unobserved is demoted for the same reason.
T1_MIN_TSTAT = 2.0
T1_MAX_SHORTEST_YRS = 3.0

# ----------------------------------------------------------------- pre-registered adoption (S4)
TIER3_MIN_T = 2.0             # beta must clear this, one-sided, with beta > 0

# ----------------------------------------------------------------- DEFECT #10 FIX, 2026-08-20
# The pre-registration (section 2) defines tier 3 as "exactly 1 bond ... that bond places the
# issuer in the cross-section." `tier_of()` has always had a `return 3` branch for it. It was
# unreachable: `fit_issuer()` returned None for any issuer with fewer than two points in the
# fit window, and `tier_of()` sent every None straight to tier 4 before the n_all check that
# would have chosen tier 3. Found and fixed in the AEG-Project working copy 2026-08-20 (see
# AEG-Project docs/RESULTS-Full-Universe-Bond-Pull-2026-08-20.md section 4b/5b), ported here
# verbatim per the standing rule that this file may never become a second fitter.
#
# `--pre-fix-tier3` reproduces the OLD, broken routing exactly, so the cost of this fix is
# measurable rather than asserted -- the same pattern `--no-quality-gates` already uses.
PRE_FIX_TIER3 = "--pre-fix-tier3" in sys.argv


# ================================================================= tiny stats, no dependencies

def ols(x, y):
    """y = a + b x. Returns (a, b, t_b, r2, n). Written out rather than imported so this tool
    runs in any sandbox and so the arithmetic is inspectable."""
    n = len(x)
    if n < 3:
        return None
    mx = sum(x) / n
    my = sum(y) / n
    sxx = sum((v - mx) ** 2 for v in x)
    if sxx <= 0:
        return None
    sxy = sum((x[i] - mx) * (y[i] - my) for i in range(n))
    b = sxy / sxx
    a = my - b * mx
    resid = [y[i] - (a + b * x[i]) for i in range(n)]
    sse = sum(r * r for r in resid)
    sst = sum((v - my) ** 2 for v in y)
    if n <= 2:
        return a, b, float("nan"), float("nan"), n
    se_b = math.sqrt((sse / (n - 2)) / sxx) if sse > 0 else 0.0
    t_b = b / se_b if se_b > 0 else float("inf")
    r2 = 1.0 - sse / sst if sst > 0 else float("nan")
    return a, b, t_b, r2, n


# ================================================================= load and filter

def load_bonds():
    rows, dropped = [], {"tenor": 0, "spread": 0, "ytmgap": 0, "dup": 0, "parse": 0}
    seen = {}
    for r in csv.DictReader(open(BONDS)):
        try:
            t = float(r["tenor_yrs"])
            s = float(r["spread_bp"])
            g = abs(float(r["ytm_check_gap_bp"]))
            tk = r["ticker"].strip()
            code = r["bond_code"].strip()
            qd = r.get("quote_date", "")
        except (KeyError, TypeError, ValueError):
            dropped["parse"] += 1
            continue
        if t < MIN_TENOR_YRS:
            dropped["tenor"] += 1
            continue
        if not (MIN_SPREAD_BP < s <= MAX_SPREAD_BP):
            dropped["spread"] += 1
            continue
        if g > MAX_YTM_GAP_BP:
            dropped["ytmgap"] += 1
            continue
        prev = seen.get(code)
        if prev is not None:
            dropped["dup"] += 1
            if qd <= prev["quote_date"]:
                continue
        seen[code] = dict(ticker=tk, code=code, tenor=t, spread_pp=s / 100.0, quote_date=qd)
    for v in seen.values():
        rows.append(v)

    # SECOND SOURCE, ADDED AFTER THE FIRST RUN AND RECORDED AS SUCH. The first run LOST five
    # names that already had curves in production -- AAPL, PG, T, WMT and GOOG -- because the
    # August bond pull's two research samples never covered them, while `real-yields` has held
    # their bonds all along in `outputs/bonds_used_<T>.csv`. Losing coverage that already
    # existed is a regression however good the new fit is, so both sources are read.
    #
    # Those files carry a yield to worst and no matched Treasury, so the spread is stripped here
    # against the same nominal Treasury curve the aggregate credit grid publishes. Bonds already
    # present from the primary source are NOT added twice: the primary wins, because it carries
    # a dated quote and an internal yield-consistency check and this one carries neither.
    have = set(r["ticker"] for r in rows)
    tsy = load_treasury_curve()
    added = {}
    for path, tkr in iter_bonds_used():
        if tkr in have or tsy is None:
            continue
        for r in csv.DictReader(open(path)):
            try:
                t = float(r["years"])
                y = float(r["ytw"]) * 100.0
            except (KeyError, TypeError, ValueError):
                continue
            s = y - interp(tsy, t)
            if t < MIN_TENOR_YRS or not (MIN_SPREAD_BP < s * 100.0 <= MAX_SPREAD_BP):
                continue
            rows.append(dict(ticker=tkr, code=r.get("cusip") or r.get("description", ""),
                             tenor=t, spread_pp=s, quote_date=""))
            added[tkr] = added.get(tkr, 0) + 1
    if added:
        print("  second source (real-yields bonds_used_<T>.csv), issuers the August pull "
              "missed: %s" % ", ".join("%s(%d)" % (k, v) for k, v in sorted(added.items())))

    by = {}
    for r in rows:
        by.setdefault(r["ticker"], []).append(r)
    return by, dropped


def interp(knots, x):
    ks = sorted(knots)
    if x <= ks[0]:
        return knots[ks[0]]
    if x >= ks[-1]:
        return knots[ks[-1]]
    for i in range(1, len(ks)):
        if x <= ks[i]:
            x0, x1 = ks[i - 1], ks[i]
            w = (x - x0) / (x1 - x0)
            return knots[x0] * (1 - w) + knots[x1] * w
    return knots[ks[-1]]


def _real_yields_bases():
    """Where real-yields might be. Same search order as the working-folder original, with an
    explicit --real-yields / RY_REPO first so CI and the hermetic test can point it at a
    checkout rather than guessing from a home directory that does not exist on a runner."""
    return (_arg("--real-yields", ""), os.environ.get("RY_REPO", ""),
            os.environ.get("AEG_REAL_YIELDS", ""),
            os.path.join(os.path.dirname(REPO), "real-yields"),
            os.path.join(os.path.dirname(REPO), "GitHub", "real-yields"))


def load_treasury_curve():
    """The nominal Treasury curve, from the same published file COMMON(t) is read off."""
    for base in _real_yields_bases():
        p = os.path.join(base or "", "outputs", "market_credit_latest_annual.csv")
        if base and os.path.exists(p):
            out = {}
            for r in csv.DictReader(open(p)):
                try:
                    out[float(r["tenor"])] = float(r["treasury_nominal"])
                except (KeyError, TypeError, ValueError):
                    continue
            return out or None
    return None


def iter_bonds_used():
    for base in _real_yields_bases():
        d = os.path.join(base or "", "outputs")
        if base and os.path.isdir(d):
            for fn in sorted(os.listdir(d)):
                if fn.startswith("bonds_used_") and fn.endswith(".csv"):
                    yield os.path.join(d, fn), fn[len("bonds_used_"):-len(".csv")]
            return


# ================================================================= per-issuer curve fit

def fit_issuer(bonds):
    """Pre-registered primary: spread(t) = a + b ln(t), OLS, equal weights, tenors <= 50y.

    Returns a dict for every issuer that has at least one bond. Coverage fields (n_all,
    longest, shortest, longest_fit, span) are ALWAYS populated so tier_of() can route
    correctly even when too few points fall in the fit window to measure a slope -- that is
    the defect #10 fix: the pre-2026-08-20 version returned None in that case, which sent the
    issuer to tier 4 before tier_of() ever got to look at n_all.

    a_pp/b_pp are populated here when >=2 points allow a slope to be measured. For exactly one
    usable point they are left as None -- a placeholder, not a silent zero -- and resolved in
    main() once the tier-1-derived common slope is known, from that single bond's own spread.
    `--pre-fix-tier3` restores the old None-on-too-few-points behavior exactly, for the control
    diff that measures what this fix changed."""
    pts = [b for b in bonds if b["tenor"] <= MAX_FIT_TENOR_YRS]
    if PRE_FIX_TIER3 and len(pts) < 2:
        return None
    if not bonds:
        return None
    out = dict(n_fit=len(pts), n_all=len(bonds),
               longest=max(b["tenor"] for b in bonds),
               longest_fit=(max(b["tenor"] for b in pts) if pts else 0.0),
               shortest=min(b["tenor"] for b in bonds))
    out["span"] = out["longest_fit"] - out["shortest"]
    if len(pts) >= 3:
        x = [math.log(b["tenor"]) for b in pts]
        y = [b["spread_pp"] for b in pts]
        f = ols(x, y)
        if f is not None:
            a, b, t_b, r2, n = f
            out.update(a_pp=a, b_pp=b, t_b=t_b, r2=r2)
            xs = [math.sqrt(b_["tenor"]) for b_ in pts]
            fr = ols(xs, y)
            out["b_sqrt_pp"] = fr[1] if fr else float("nan")
            return out
    elif len(pts) == 2:
        x = [math.log(b["tenor"]) for b in pts]
        y = [b["spread_pp"] for b in pts]
        if abs(x[1] - x[0]) >= 1e-12:
            # exactly two points: the line through them. No standard error exists.
            b = (y[1] - y[0]) / (x[1] - x[0])
            a = y[0] - b * x[0]
            out.update(a_pp=a, b_pp=b, t_b=float("nan"), r2=float("nan"),
                       b_sqrt_pp=float("nan"))
            return out
    # Fewer than two usable fit-window points (typically exactly one bond -- tier 3). No
    # slope is observable from this issuer's own bonds, so a_pp/b_pp stay unresolved here.
    # The longest bond overall (fit-window or not; F4 excludes a century bond from the FIT,
    # never from coverage) is kept as the single-point anchor.
    longest_bond = max(bonds, key=lambda b: b["tenor"])
    out.update(a_pp=None, b_pp=None, t_b=float("nan"), r2=float("nan"), b_sqrt_pp=float("nan"),
               single_tenor=longest_bond["tenor"], single_spread=longest_bond["spread_pp"])
    return out


def tier_of(f, gates=True):
    if f is None:
        return 4, ""
    ok = (f["n_fit"] >= T1_MIN_BONDS and f["longest_fit"] >= T1_MIN_LONGEST
          and f["span"] >= T1_MIN_SPAN)
    why = ""
    if ok and gates:
        t = f["t_b"]
        if not (t == t) or abs(t) < T1_MIN_TSTAT:
            ok, why = False, "slope not distinguishable from zero (t=%.2f)" % (t if t == t else 0)
        elif f["shortest"] > T1_MAX_SHORTEST_YRS:
            ok, why = False, "front unobserved (nearest bond %.1fy)" % f["shortest"]
    if ok:
        return 1, ""
    if f["n_all"] >= T2_MIN_BONDS:
        return 2, why
    return 3, why


# ================================================================= freshness

def _bond_file_date():
    """The newest quote_date in the primary bond file. The FILE's mtime is worthless here -- a
    re-commit or a checkout resets it while the prices inside stay frozen, which is precisely
    how a fossil acquires a fresh timestamp."""
    newest = ""
    for r in csv.DictReader(open(BONDS)):
        q = (r.get("quote_date") or "").strip()
        if len(q) == 10 and q > newest:
            newest = q
    return newest or None


def _refuse_if_bonds_are_stale():
    if MAX_BOND_AGE_DAYS <= 0:
        return
    import datetime as _dt
    q = _bond_file_date()
    if not q:
        raise IssuerCurveInputStale(
            "%s carries no parseable quote_date, so its age cannot be established. Refusing to "
            "re-stamp a bond snapshot of unknown vintage." % BONDS)
    age = (_dt.date.today() - _dt.date.fromisoformat(q)).days
    if age > MAX_BOND_AGE_DAYS:
        raise IssuerCurveInputStale(
            "the newest bond quote in %s is %s, %d days old (limit %d). Re-running the fit now "
            "would move the `generated` date without moving the data. Re-price the bonds "
            "(tools/bond_eod_pull.py + bond_spread_build2.py, ~1,449 quotes x 10 EODHD units) "
            "before regenerating." % (BONDS, q, age, MAX_BOND_AGE_DAYS))
    print("BOND SNAPSHOT: newest quote %s, %d days old (limit %d) -- fresh enough to refit."
          % (q, age, MAX_BOND_AGE_DAYS))
    print()


# ================================================================= main

def main():
    os.makedirs(OUTDIR, exist_ok=True)
    _refuse_if_bonds_are_stale()
    by, dropped = load_bonds()
    print("PRE-REGISTERED FILTERS (docs/PREREG-Region2-Issuer-Curves-and-Tier3-2026-08-19.md)")
    print("  dropped: tenor<%.1fy %d | spread out of (%.0f,%.0f]bp %d | |ytm gap|>%.0fbp %d | "
          "duplicate bond_code %d | unparseable %d"
          % (MIN_TENOR_YRS, dropped["tenor"], MIN_SPREAD_BP, MAX_SPREAD_BP, dropped["spread"],
             MAX_YTM_GAP_BP, dropped["ytmgap"], dropped["dup"], dropped["parse"]))
    print("  surviving: %d bonds across %d issuers"
          % (sum(len(v) for v in by.values()), len(by)))
    print()

    gates = "--no-quality-gates" not in sys.argv
    fits = {t: fit_issuer(v) for t, v in by.items()}
    graded = {t: tier_of(f, gates) for t, f in fits.items()}
    tiers = {t: g[0] for t, g in graded.items()}
    demoted = {t: g[1] for t, g in graded.items() if g[1]}
    t1 = sorted(t for t, k in tiers.items() if k == 1)
    print("TIER-1 QUALITY GATES: %s" % ("ON (t>=%.1f on the slope, nearest bond <=%.1fy)"
                                        % (T1_MIN_TSTAT, T1_MAX_SHORTEST_YRS) if gates
                                        else "OFF (--no-quality-gates)"))
    if demoted:
        print("  demoted from tier 1: %d issuers" % len(demoted))
        for t in sorted(demoted)[:12]:
            print("    %-6s %s" % (t, demoted[t]))
        if len(demoted) > 12:
            print("    ... and %d more" % (len(demoted) - 12))
    print()
    print("TIERS, on the pre-registered boundaries")
    for k in (1, 2, 3):
        names = sorted(t for t, v in tiers.items() if v == k)
        print("  tier %d: %3d issuers   %s" % (k, len(names), ", ".join(names[:14])
                                               + (" ..." if len(names) > 14 else "")))
    print()

    # ---- falsification check 2: how many tier-1 curves invert?
    neg = [t for t in t1 if fits[t]["b_pp"] < 0]
    print("SHAPE. tier-1 slope b (percentage points per e-fold of tenor):")
    bs = sorted(fits[t]["b_pp"] for t in t1)
    print("  min %.4f  p25 %.4f  median %.4f  p75 %.4f  max %.4f"
          % (bs[0], bs[len(bs) // 4], bs[len(bs) // 2], bs[3 * len(bs) // 4], bs[-1]))
    print("  NEGATIVE (inverted) slopes: %d of %d issuers -- %s"
          % (len(neg), len(t1),
             "reported, never clipped" if neg else "none"))
    if len(neg) > len(t1) / 2:
        print("  ** PRE-REGISTERED FALSIFIER 2 HAS FIRED: a majority of issuer credit curves")
        print("     invert. The COMMON(t) argument is in question and this must go to James.")
    print()

    # ---- the tier-3 spread-conditioned slope fit
    x = [fits[t]["a_pp"] for t in t1]
    y = [fits[t]["b_pp"] for t in t1]
    f3 = ols(x, y)
    alpha, beta, t_beta, r2, n3 = f3
    mean_b = sum(y) / len(y)
    adopted = (beta > 0 and t_beta > TIER3_MIN_T)
    print("TIER 3 -- the spread-conditioned slope, pre-registered H1: beta > 0")
    print("  b_i = %.5f + %.5f x s1_i     t(beta) = %.2f   R2 = %.3f   n = %d"
          % (alpha, beta, t_beta, r2, n3))
    print("  equal-weighted mean slope across tier-1 issuers: %.5f" % mean_b)
    xr = [math.log(v) for v in x if v > 0]
    yr = [y[i] for i, v in enumerate(x) if v > 0]
    f3r = ols(xr, yr) if len(xr) >= 3 else None
    if f3r:
        print("  robustness (not adopted), b on ln(s1): beta %.5f  t %.2f  R2 %.3f"
              % (f3r[1], f3r[2], f3r[3]))
    if adopted:
        print("  ADOPTED: beta > 0 and t > %.1f, exactly as pre-registered. Wider issuers widen "
              "more." % TIER3_MIN_T)
    else:
        print("  ** NOT ADOPTED. PRE-REGISTERED FALSIFIER 1 HAS FIRED: beta = %.5f with "
              "t = %.2f fails the beta>0, t>%.1f rule fixed in advance." % (beta, t_beta,
                                                                           TIER3_MIN_T))
        print("     Tiers 2-4 fall back to the equal-weighted mean slope %.5f, and the fact "
              "that the conditioning failed is reported rather than buried." % mean_b)
    print()

    # ---- DEFECT #10 FIX: resolve the one-bond (tier-3) issuers' one-year level now that the
    # common slope (alpha/beta/mean_b/adopted) is known. spread_obs = a + b*ln(tenor_obs).
    # If the tier-3 conditioning is NOT adopted, b = mean_b is a constant and a solves
    # directly. If it IS adopted, b = alpha + beta*a is itself a function of the unknown a,
    # so the two equations are solved together as a fixed point:
    #     a + beta*ln(t)*a = spread - alpha*ln(t)  =>  a = (spread - alpha*ln(t)) / (1 + beta*ln(t))
    def solve_single_point_a(tenor, spread):
        lt = math.log(tenor)
        if abs(lt) < 1e-12:               # the one bond matures at ~1y: b is unidentified
            return spread, (alpha + beta * spread) if adopted else mean_b
        if not adopted:
            return spread - mean_b * lt, mean_b
        denom = 1.0 + beta * lt
        if abs(denom) < 1e-9:              # degenerate fixed point; fall back rather than blow up
            return spread - mean_b * lt, mean_b
        a = (spread - alpha * lt) / denom
        return a, alpha + beta * a

    resolved = []
    for t, f in fits.items():
        if f is not None and f.get("a_pp") is None and "single_tenor" in f:
            a, b = solve_single_point_a(f["single_tenor"], f["single_spread"])
            f["a_pp"], f["b_pp"] = a, b
            resolved.append(t)
    if resolved:
        print("TIER-3 REPAIR (defect #10): %d one-bond issuers given a level from their own "
              "bond instead of falling through to tier 4: %s"
              % (len(resolved), ", ".join(sorted(resolved)[:14])
                 + (" ..." if len(resolved) > 14 else "")))
        print()

    # ---- tier 4: impute s1 from the equity semi-deviation
    semidev, cap = load_universe()
    pairs = [(semidev[t], fits[t]["a_pp"]) for t in fits
             if t in semidev and fits[t] is not None]
    f4 = ols([p[0] for p in pairs], [p[1] for p in pairs])
    a4, b4, t4, r24, n4 = f4
    lvl_adopted = (b4 > 0 and t4 > TIER3_MIN_T)
    print("TIER 4 -- imputing the one-year spread level from the equity semi-deviation")
    print("  s1_i = %.5f + %.5f x semidev_i   t = %.2f   R2 = %.3f   n = %d"
          % (a4, b4, t4, r24, n4))
    print("  %s" % ("ADOPTED: the equity risk statistic does predict the credit level."
                    if lvl_adopted else
                    "** NOT ADOPTED: it does not predict the credit level. Tier-4 names take "
                    "the median tier-1..3 s1 instead, and that is a declared floor, not a fit."))
    s1_all = sorted(fits[t]["a_pp"] for t in fits if fits[t] is not None)
    s1_median = s1_all[len(s1_all) // 2]
    print()

    # ---- assemble widen_i(t) for every name in the universe
    def slope_for(tkr):
        f = fits.get(tkr)
        tier = tiers.get(tkr, 4)
        if tier == 1:
            return f["b_pp"], f["a_pp"], 1
        if f is not None:
            s1 = f["a_pp"]
        elif lvl_adopted and tkr in semidev:
            s1 = a4 + b4 * semidev[tkr]
        else:
            s1 = s1_median
        b = (alpha + beta * s1) if adopted else mean_b
        return b, s1, tier

    rows = []
    universe = sorted(set(list(semidev.keys()) + list(fits.keys())))
    for tkr in universe:
        b, s1, tier = slope_for(tkr)
        w = {h: b * math.log(h) for h in GRID}
        rows.append(dict(ticker=tkr, tier=tier, s1_pp=s1, b_pp=b,
                         n_bonds=(fits[tkr]["n_all"] if fits.get(tkr) else 0),
                         longest_yrs=(fits[tkr]["longest"] if fits.get(tkr) else 0.0),
                         in_universe=int(tkr in semidev),
                         **{"widen_%d" % h: w[h] for h in GRID}))

    path = os.path.join(OUTDIR, WIDEN_NAME)
    with open(path, "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)
    print("WROTE %s -- %d names (%d in the scored universe)"
          % (path, len(rows), sum(r["in_universe"] for r in rows)))

    dpath = os.path.join(OUTDIR, "issuer_curve_fit.csv")
    with open(dpath, "w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["ticker", "tier", "n_all", "n_fit", "shortest", "longest", "longest_fit",
                     "span", "a_pp", "b_pp", "t_b", "r2", "b_sqrt_pp"])
        for t in sorted(fits):
            f = fits[t]
            if f is None:
                continue
            wr.writerow([t, tiers[t], f["n_all"], f["n_fit"], round(f["shortest"], 3),
                         round(f["longest"], 3), round(f["longest_fit"], 3), round(f["span"], 3),
                         round(f["a_pp"], 6), round(f["b_pp"], 6),
                         round(f["t_b"], 3) if f["t_b"] == f["t_b"] else "",
                         round(f["r2"], 4) if f["r2"] == f["r2"] else "",
                         round(f["b_sqrt_pp"], 6) if f["b_sqrt_pp"] == f["b_sqrt_pp"] else ""])
    print("WROTE %s" % dpath)

    jpath = os.path.join(OUTDIR, "tier3_fit.json")
    import datetime as _dt
    json.dump(dict(generated=_dt.datetime.now(_dt.timezone.utc).date().isoformat(),
                   prereg="docs/PREREG-Region2-Issuer-Curves-and-Tier3-2026-08-19.md",
                   form="b_i = alpha + beta * s1_i, tier-1 issuers only",
                   alpha=alpha, beta=beta, t_beta=t_beta, r2=r2, n=n3,
                   adoption_rule="beta > 0 and t(beta) > %.1f" % TIER3_MIN_T,
                   adopted=bool(adopted), mean_slope_fallback=mean_b,
                   n_tier1=len(t1), n_tier1_inverted=len(neg),
                   level_form="s1_i = a + b * semidev_i",
                   level_a=a4, level_b=b4, level_t=t4, level_r2=r24, level_n=n4,
                   level_adopted=bool(lvl_adopted), s1_median=s1_median,
                   tier_counts={str(k): sum(1 for v in tiers.values() if v == k)
                                for k in (1, 2, 3)}),
              open(jpath, "w"), indent=2)
    print("WROTE %s" % jpath)

    # ---- the sensitivity the pre-registration promised: flat beyond the longest bond
    print()
    print("EXTRAPOLATION SENSITIVITY. widen at 30y, tier-1 issuers, fitted curve carried to 30")
    print("  versus held flat beyond each issuer's longest observed maturity:")
    d = []
    for t in t1:
        f = fits[t]
        full = f["b_pp"] * math.log(30.0)
        capped = f["b_pp"] * math.log(min(30.0, max(1.0, f["longest_fit"])))
        d.append(abs(full - capped))
    d.sort()
    print("  |difference| pp:  median %.4f   p90 %.4f   max %.4f   (%d issuers)"
          % (d[len(d) // 2], d[int(0.9 * len(d))], d[-1], len(d)))


def load_universe():
    path = UNIVERSE
    semidev, cap = {}, {}
    for r in csv.DictReader(open(path)):
        t = r["ticker"].strip()
        try:
            semidev[t] = float(r["semidev"])
        except (KeyError, TypeError, ValueError):
            continue
        try:
            cap[t] = float(r["market_cap"])
        except (KeyError, TypeError, ValueError):
            pass
    return semidev, cap


if __name__ == "__main__":
    main()
