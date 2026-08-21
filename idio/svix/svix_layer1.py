#!/usr/bin/env python3
"""
svix_layer1.py -- build the Layer 1 idiosyncratic premium cross-section.

MEASUREMENT ONLY. This script does not touch the sealed workbook, does not write a
payload, and cannot move a published valuation. It produces CSVs for James to look at
before anything is decided about wiring it into the engine's `idiosyncratic` hook.
See docs/AEG-Idiosyncratic-Premium-Proposal-2026-08-12.md.

WHAT IT DOES
------------
For each ticker and each sampled trading date:
  1. Pull the FULL listed end-of-day option chain from EODHD / UnicornBay.
  2. For each expiry, take the forward from put-call parity near the money and the
     discount factor from a live rate curve.
  3. Fit the smile and integrate it over the whole strike axis into SVIX^2, with the
     trapezoidal strip carried alongside for comparison.
  4. Interpolate the term structure to the requested tenor.
Then across the universe on each date:
  5. SVIXbar^2 = value-weighted mean of the single-name SVIX^2.
  6. pi_i = 0.5 * (SVIX^2_i - SVIXbar^2)          [Martin-Wagner 2019]
Then average pi_i over the sampling window, because a single option surface is one
day's data and this engine has twice been bitten by one anchor day driving a
permanent line.

THREE CORRECTIONS FROM THE FIRST VERSION, ALL FOUND BY RUNNING IT
-----------------------------------------------------------------
1. THE CHAIN WAS TWO-THIRDS MISSING. The old fetch filtered on `tradetime`, which
   the vendor documents as "last market activity date" -- so it returned only the
   contracts that happened to trade that day and dropped every listed contract that
   was merely quoted. Untraded contracts are overwhelmingly the wings, which is
   precisely the region SVIX^2 integrates. PepsiCo's 4 September 2026 expiry: 37
   contracts traded, 106 listed.

2. THE DISCOUNT FACTOR CANNOT BE FITTED FROM AMERICAN QUOTES. Deep in-the-money
   listed options sit at immediate-exercise intrinsic value, which drags the parity
   slope toward minus one. Apple's 492-day expiry implied a 1.4 per cent rate against
   a Treasury curve at 4.2 per cent. The rate is now read live and imposed, and the
   forward alone comes from the options. Cross-check: with the rate imposed, the
   forward-to-spot carry now implies each company's actual dividend yield -- Apple
   0.3 per cent, Coca-Cola 2.3 to 3.0, PepsiCo 3.4 to 5.0. Under the old fit they all
   implied roughly zero, which is obviously wrong for a staple.

3. THE 730-DAY TENOR DOES NOT EXIST. The longest listed expiry is 583 days. It is
   dropped rather than extrapolated to.

USAGE
-----
  python3 tools/svix_prefetch.py --universe tools/universe_layer1.txt \\
      --dates 2026-08-06,2026-08-07,2026-08-10,2026-08-11,2026-08-12
  python3 tools/svix_layer1.py --universe tools/universe_layer1.txt \\
      --dates 2026-08-06,2026-08-07,2026-08-10,2026-08-11,2026-08-12 \\
      --tenors 365 --out outputs/svix_fleet
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import math
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from eodhd_options import OptionFeed, read_token, rate_function
from svix_core import interpolate_variance, annualize, cross_section_premium
from svix_slices import build_slices, vega_weights
from svix_surface import fit_svi_slice, svix2_from_svi, synthetic_variance_share
from svix_characteristics import build_characteristics, PeerMatcher

# Spec section 7. Set at 0.35 in the spec as a first pass; the section 6 validation
# run of 13 August 2026 measured the error either side of it and the number holds:
# below 0.35 the median absolute error of the completed estimate is about 40 basis
# points of annualized premium, above 0.45 it is about 70 to 78. See
# outputs/svix_validation_by_synthetic_share.csv.
MAX_SYNTHETIC_SHARE = 0.35

# From the same run, expiries 180 to 600 days, scored against the fitted curve on the
# full ladder. These are the precision weights the spec's section 5 triangulation
# asks for, and they are measured rather than guessed.
LEG_ERROR_BPS = {"direct": 45.0, "peer": 40.0}


def fit_one(sl, peer_svis=None):
    """
    Complete one slice: fit, integrate, and produce every disclosure field the spec's
    section 7 requires. Returns (svix2, info) with svix2 None if refused.

    The full-freedom fit is taken from the checkpoint on the slice (`sl.full`) rather
    than recomputed.
    """
    info = {"fit_mode": "refused", "reason": "", "n_strikes_observed": sl.n_usable,
            "strike_span_lo": sl.span_lo, "strike_span_hi": sl.span_hi,
            "synthetic_variance_share": None, "peer_group_n": 0}
    if len(sl.kw) < 6:
        info["reason"] = f"only {len(sl.kw)} invertible quotes"
        return None, info

    w = vega_weights(sl.kw)
    legs = []

    d = getattr(sl, "full", None)
    if d and not d["butterfly_bad"]:
        sv, share = d["svix2"], d["share"]
        if sv and 0 < sv < 25 and share is not None and share <= MAX_SYNTHETIC_SHARE:
            from svix_surface import SVI as _SVI
            legs.append(("direct", sv, share, _SVI(*d["svi"])))

    if peer_svis:
        b = statistics.median([p.b for p in peer_svis])
        rho = statistics.median([p.rho for p in peer_svis])
        s = statistics.median([p.s for p in peer_svis])
        borrowed = fit_svi_slice(sl.kw, weights=w, fixed_wings=(b, rho, s))
        if borrowed.ok and not borrowed.butterfly_bad:
            sv = svix2_from_svi(borrowed.svi)
            share = synthetic_variance_share(borrowed.svi, sl.k_lo, sl.k_hi)
            if sv and 0 < sv < 25 and share is not None and share <= MAX_SYNTHETIC_SHARE:
                legs.append(("peer", sv, share, borrowed.svi))
        info["peer_group_n"] = len(peer_svis)

    if not legs:
        info["reason"] = ("no leg survived: no arbitrage-free fit inside the "
                          f"{MAX_SYNTHETIC_SHARE} synthetic-share ceiling")
        return None, info

    # Precision-weighted blend, spec section 5, with the variances taken from the
    # section 6 validation rather than guessed. The history leg is NOT built, so its
    # weight is zero and that is stated rather than hidden.
    num = den = 0.0
    for name, sv, share, svi in legs:
        v = LEG_ERROR_BPS[name] ** 2
        num += sv / v
        den += 1.0 / v
    blended = num / den

    info.update({
        "fit_mode": "+".join(n for n, _, _, _ in legs),
        "synthetic_variance_share": max(share for _, _, share, _ in legs),
        "leg_weights": ";".join(
            f"{n}={(1.0 / LEG_ERROR_BPS[n] ** 2) / den:.2f}" for n, _, _, _ in legs)
        + ";history=0.00 (leg not built)",
        "svi": legs[0][3],
        "reason": "",
    })
    return blended, info


def load_universe(path):
    seen, out = set(), []
    with open(path) as f:
        for ln in f:
            t = ln.strip().upper()
            if t and not t.startswith("#") and t not in seen:
                seen.add(t)
                out.append(t)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", required=True)
    ap.add_argument("--dates", required=True)
    ap.add_argument("--tenors", default="365")
    ap.add_argument("--out", default="outputs/svix_fleet")
    ap.add_argument("--cache", default="outputs/.svix_cache")
    ap.add_argument("--coefficient", type=float, default=0.5)
    ap.add_argument("--exp-from-days", type=int, default=20)
    ap.add_argument("--exp-to-days", type=int, default=600)
    ap.add_argument("--peer-n", type=int, default=20)
    ap.add_argument("--index", default="GSPC.INDX")
    ap.add_argument("--no-crash-capture", action="store_true")
    ap.add_argument("--shard", default="0/1",
                    help="i/n -- fit only every n-th ticker, so several processes "
                         "can share the work. The checkpoint files make it safe.")
    ap.add_argument("--fit-only", action="store_true",
                    help="stop after checkpointing fits; do not build the "
                         "cross-section")
    ap.add_argument("--fit-min-days", type=int, default=140,
                    help="skip expiries shorter than this; they cannot bracket a "
                         "365-day tenor")
    ap.add_argument("--seconds", type=int, default=85,
                    help="checkpoint and stop after this long, so a run "
                         "fits in one shell call; re-run to continue")
    args = ap.parse_args()

    tenors = [int(t) for t in args.tenors.split(",") if t.strip()]
    if any(t > 583 for t in tenors):
        print("REFUSED: the longest listed expiry on this feed is 583 days. A tenor "
              "beyond it would be pure extrapolation. Drop it.")
        return 2

    tickers = load_universe(args.universe)
    dates = sorted(d.strip() for d in args.dates.split(",") if d.strip())
    token = read_token()
    if not token:
        print("ERROR: no API token found.")
        return 2
    feed = OptionFeed(token, args.cache)

    print(f"universe : {len(tickers)} tickers")
    print(f"dates    : {len(dates)} sessions, {dates[0]} .. {dates[-1]}")
    print(f"tenors   : {tenors} days")

    curve = feed.treasury_curve(
        (dt.date.fromisoformat(dates[0]) - dt.timedelta(days=12)).isoformat(),
        dates[-1])
    rate_by_date = {}
    for d in dates:
        avail = [k for k in curve if k <= d]
        if avail:
            rate_by_date[d] = (rate_function(curve[max(avail)]), max(avail))
    print(f"rate curve: read live, {len(rate_by_date)}/{len(dates)} dates matched")

    # ---- market caps and the matching vector, both needed anyway
    market = None
    if not args.no_crash_capture:
        try:
            from market_declines import eod, drawdown_episodes
            idx = eod(token, args.index, "1950-01-01")
            market = drawdown_episodes([x for x, _ in idx], [c for _, c in idx], 0.10)
            print(f"market declines: {len(market)} episodes of 10% or more since "
                  f"{idx[0][0]}")
        except Exception as e:
            print(f"crash capture unavailable ({e}) -- peer matching degrades")
    chars = build_characteristics(token, tickers, dates[-1], market_episodes=market,
                                  verbose=False)
    matcher = PeerMatcher(chars)
    caps = {t: c["market_cap"] for t, c in chars.items() if c.get("market_cap")}
    print(f"market caps: {len(caps)}/{len(tickers)} retrieved")

    # ---- slices, with the full-freedom fit done once and CHECKPOINTED
    #
    # Fitting the whole universe takes about a quarter of an hour, which is longer
    # than a single shell session here will run. So each ticker's slices and its
    # full-freedom fits are written to disk as they are produced, and re-running
    # simply picks up where it stopped. Nothing is recomputed and nothing is refetched.
    fitdir = os.path.join(os.path.dirname(args.cache) or ".", ".svix_fits")
    os.makedirs(fitdir, exist_ok=True)
    tag = f"{dates[0]}_{dates[-1]}_{len(dates)}_min{args.fit_min_days}"

    import json
    import time as _time
    start = _time.time()
    shard_i, shard_n = (int(x) for x in args.shard.split("/"))
    pending = []
    for i, t in enumerate(tickers, 1):
        p = os.path.join(fitdir, f"{t}_{tag}.json")
        if os.path.exists(p):
            continue
        if shard_n > 1 and (i - 1) % shard_n != shard_i:
            continue
        pending.append((i, t, p))

    if pending:
        print(f"fitting: {len(pending)} tickers still to do "
              f"({len(tickers) - len(pending)} already checkpointed)")
    t0 = dt.date.fromisoformat(dates[0])
    for i, t, p in pending:
        if _time.time() - start > args.seconds:
            print(f"\nTIME LIMIT with {len(tickers) - i + 1} tickers left. "
                  f"Re-run exactly the same command to continue -- every fit so far "
                  f"is checkpointed and no data will be refetched.")
            return 3
        try:
            chains = feed.chain(
                t, dates,
                (t0 + dt.timedelta(days=args.exp_from_days)).isoformat(),
                (t0 + dt.timedelta(days=args.exp_to_days)).isoformat())
        except Exception as e:
            print(f"  [{i}/{len(tickers)}] {t}: FETCH FAILED -- {e}")
            chains = {}
        recs = []
        for d, rows in sorted(chains.items()):
            if d not in rate_by_date:
                continue
            for sl in build_slices(t, d, rows, rate_by_date[d][0]):
                # Only expiries that can bracket the requested tenor are fitted. The
                # published number is a 365-day tenor interpolated between listed
                # expiries, so a 23-day slice cannot contribute to it, and fitting
                # every weekly expiry on 136 names costs three quarters of the run
                # for nothing. Short expiries remain available to the validation
                # harness, which does look at them.
                if sl.days < args.fit_min_days:
                    continue
                rec = {"ticker": t, "date": d, "exp_date": sl.exp_date,
                       "days": sl.days, "forward": sl.forward,
                       "discount": sl.discount, "n_listed": sl.n_listed,
                       "n_usable": sl.n_usable, "k_lo": sl.k_lo, "k_hi": sl.k_hi,
                       "parity_agreement": sl.parity_agreement,
                       "svix2_trapezoid": sl.svix2_trapezoid,
                       "kw": sl.kw, "full": None}
                if len(sl.kw) >= 6:
                    f = fit_svi_slice(sl.kw, weights=vega_weights(sl.kw))
                    if f.ok:
                        sv = svix2_from_svi(f.svi)
                        rec["full"] = {
                            "svi": list(f.svi.as_tuple()),
                            "butterfly_bad": f.butterfly_bad,
                            "svix2": sv,
                            "share": synthetic_variance_share(f.svi, sl.k_lo, sl.k_hi),
                            "rmse_w": f.rmse_w}
                recs.append(rec)
        tmp = p + ".tmp"
        with open(tmp, "w") as f:
            json.dump(recs, f)
        os.replace(tmp, p)
        if i % 10 == 0 or i == len(tickers):
            print(f"  [{i}/{len(tickers)}] {t}: {len(recs)} slices "
                  f"| {_time.time() - start:.0f}s")

    # ---- load every checkpoint
    from svix_slices import Slice
    all_slices = {}
    for t in tickers:
        p = os.path.join(fitdir, f"{t}_{tag}.json")
        if not os.path.exists(p):
            continue
        for rec in json.load(open(p)):
            sl = Slice(ticker=rec["ticker"], date=rec["date"],
                       exp_date=rec["exp_date"], days=rec["days"],
                       forward=rec["forward"], discount=rec["discount"],
                       otm_puts=[], otm_calls=[],
                       kw=[tuple(x) for x in rec["kw"]],
                       n_listed=rec["n_listed"], n_quoted=0,
                       n_usable=rec["n_usable"], k_lo=rec["k_lo"], k_hi=rec["k_hi"],
                       parity_agreement=rec["parity_agreement"],
                       svix2_trapezoid=rec["svix2_trapezoid"])
            sl.full = rec["full"]
            all_slices.setdefault((rec["ticker"], rec["date"]), []).append(sl)
    print(f"loaded {sum(len(v) for v in all_slices.values())} slices from "
          f"{len(all_slices)} ticker-dates")
    if args.fit_only:
        print("--fit-only: stopping before the cross-section.")
        return 0

    # ---- peer pool: every slice that fits at full freedom, arbitrage-free
    from svix_surface import SVI
    pool = []
    for (t, d), sls in all_slices.items():
        for sl in sls:
            f = sl.full
            if not f or f["butterfly_bad"] or len(sl.kw) < 12 or sl.n_usable < 30:
                continue
            pool.append((t, d, sl.days, _atm_w(sl), SVI(*f["svi"])))
    print(f"peer pool: {len(pool)} arbitrage-free slices from well-populated ladders")

    def peers_for(sl):
        atm = _atm_w(sl)
        cands = []
        for (tk, dd, days, patm, svi) in pool:
            if tk == sl.ticker or dd != sl.date:
                continue
            if not (0.625 <= days / sl.days <= 1.6):
                continue
            dist = matcher.distance(sl.ticker, tk, atm, patm)
            if math.isfinite(dist):
                cands.append((dist, svi))
        cands.sort(key=lambda x: x[0])
        return [s for _, s in cands[:args.peer_n]]

    # ---- complete every slice, then interpolate to the tenors
    expiry_rows, per_obs = [], []
    for (t, d), sls in sorted(all_slices.items()):
        obs_fit, obs_trap = [], []
        for sl in sorted(sls, key=lambda x: x.days):
            sv, info = fit_one(sl, peers_for(sl))
            expiry_rows.append(dict(
                ticker=t, date=d, exp_date=sl.exp_date, days=sl.days,
                forward=f"{sl.forward:.4f}", discount=f"{sl.discount:.6f}",
                n_listed=sl.n_listed, n_strikes_observed=sl.n_usable,
                strike_span_lo=f"{sl.span_lo:.3f}", strike_span_hi=f"{sl.span_hi:.3f}",
                svix2_trapezoid=("" if sl.svix2_trapezoid is None
                                 else f"{sl.svix2_trapezoid:.6f}"),
                svix2_completed=("" if sv is None else f"{sv:.6f}"),
                fit_mode=info["fit_mode"],
                synthetic_variance_share=(
                    "" if info["synthetic_variance_share"] is None
                    else f"{info['synthetic_variance_share']:.4f}"),
                peer_group_n=info["peer_group_n"],
                leg_weights=info.get("leg_weights", ""),
                parity_agreement=f"{sl.parity_agreement:.4f}",
                refusal_reason=info["reason"]))
            if sv is not None:
                obs_fit.append((sl.days, sv))
            if sl.svix2_trapezoid:
                obs_trap.append((sl.days, sl.svix2_trapezoid))

        for tenor in tenors:
            v, mode = interpolate_variance(obs_fit, tenor)
            vt, _ = interpolate_variance(obs_trap, tenor)
            if v is None or mode == "extrap_long":
                # Do not extrapolate past the last listed expiry, ever.
                continue
            per_obs.append({"ticker": t, "date": d, "tenor_days": tenor,
                            "svix2": v, "svix2_trapezoid": vt, "mode": mode,
                            "n_expiries_used": len(obs_fit)})

    if not per_obs:
        print("\nNo usable observations. Nothing written.")
        return 1

    # ---- cross-section
    premium_samples, premium_med_samples, date_diags = {}, {}, []
    for tenor in tenors:
        for d in dates:
            snap = {r["ticker"]: r["svix2"] for r in per_obs
                    if r["date"] == d and r["tenor_days"] == tenor}
            w = {k: caps[k] for k in snap if k in caps}
            if len(w) < 2:
                continue
            prem, bar, diag = cross_section_premium(snap, w, args.coefficient)
            assert abs(diag["vw_mean_premium"]) < 1e-12, (
                "INVARIANT VIOLATED: the value-weighted mean premium is not zero "
                f"({diag['vw_mean_premium']:.3e}) on {d} at {tenor}d.")
            for k, v in prem.items():
                premium_samples.setdefault((k, tenor), []).append(v)
            for k, v in diag["premiums_median_benchmark"].items():
                premium_med_samples.setdefault((k, tenor), []).append(v)
            date_diags.append({
                "date": d, "tenor_days": tenor, "n_names": diag["n"],
                "svixbar2_vw": diag["svixbar2_value_weighted"],
                "svix2_median": diag["svix2_median"],
                "median_minus_vw": diag["median_minus_vw_benchmark"],
                "median_minus_vw_premium_bps": 10000 * (
                    annualize(-args.coefficient * diag["median_minus_vw_benchmark"],
                              tenor) or 0.0),
                "vw_mean_premium": diag["vw_mean_premium"]})

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    f_cs = args.out + "_cross_section.csv"
    with open(f_cs, "w", newline="") as f:
        wtr = csv.writer(f)
        wtr.writerow(["ticker", "tenor_days", "n_dates", "svix2_mean",
                      "implied_vol_pct", "premium_bps", "premium_sd_bps",
                      "premium_bps_median_benchmark", "premium_bps_trapezoid_only",
                      "market_cap", "sector"])
        for (t, tenor), vals in sorted(premium_samples.items()):
            mean_pi = statistics.fmean(vals)
            sd = statistics.stdev(vals) if len(vals) > 1 else 0.0
            svs = [r["svix2"] for r in per_obs
                   if r["ticker"] == t and r["tenor_days"] == tenor]
            sv = statistics.fmean(svs)
            iv = 100 * math.sqrt(max(math.log(1 + sv), 0.0) / (tenor / 365.0))
            medv = premium_med_samples.get((t, tenor), [])
            trap = [r["svix2_trapezoid"] for r in per_obs
                    if r["ticker"] == t and r["tenor_days"] == tenor
                    and r["svix2_trapezoid"]]
            # what the OLD estimator would have said, benchmarked the same way
            trap_bps = ""
            if trap:
                bars = [dd["svixbar2_vw"] for dd in date_diags
                        if dd["tenor_days"] == tenor]
                if bars:
                    trap_bps = f"{10000 * (annualize(args.coefficient * (statistics.fmean(trap) - statistics.fmean(bars)), tenor) or 0.0):.1f}"
            wtr.writerow([
                t, tenor, len(vals), f"{sv:.6f}", f"{iv:.2f}",
                f"{10000 * (annualize(mean_pi, tenor) or 0):.1f}",
                f"{10000 * sd * 365 / tenor:.1f}",
                (f"{10000 * (annualize(statistics.fmean(medv), tenor) or 0):.1f}"
                 if medv else ""),
                trap_bps,
                caps.get(t, ""), (chars.get(t) or {}).get("sector", "")])

    written = [f_cs]
    for name, data in (("_by_date.csv", date_diags), ("_by_expiry.csv", expiry_rows)):
        if data:
            p = args.out + name
            with open(p, "w", newline="") as f:
                wtr = csv.DictWriter(f, fieldnames=list(data[0].keys()))
                wtr.writeheader()
                wtr.writerows(data)
            written.append(p)
    for p in written:
        print(f"wrote {p}")

    print(f"\nINVARIANT HELD: the value-weighted mean premium was zero to 1e-12 on "
          f"every date and tenor.")
    print(f"API: {feed.requests} requests ({feed.api_calls:,} calls), "
          f"{feed.cache_hits} cached")
    return 0


def _atm_w(sl):
    if not sl.kw:
        return None
    k, w = min(sl.kw, key=lambda t: abs(t[0]))
    return w if w > 0 else None


if __name__ == "__main__":
    sys.exit(main())
