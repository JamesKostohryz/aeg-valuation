"""
idio/score_ticker.py -- score ONE ticker, any time, against a frozen idio_snapshot_latest.json.

A PORT of AEG-Project `tools/idio_score_ticker.py`, landed alongside idio/score_v2.py and
idio/snapshot_build.py.

WHAT THIS IS FOR. James, 2026-08-21: "I want this entire system to be fully in production, so
that I can get an ERP for ANY stock and this includes stocks that are not in the coverage
universe. The methodology for estimating the ERP of a stock that is not in the coverage universe
needs to be in place so that this does not bite me later." This module is that methodology, made
runnable, for both cases:

  1. AN IN-COVERAGE TICKER (one of the 499 in risk_group_map_v2.csv). Default behaviour reads
     that ticker's own frozen raw numbers out of the snapshot and combines them with TODAY's
     live market ERP -- so a name whose price hasn't moved much scores exactly as
     idio_risk_score_v2.py's last full run said, but the dollar premium still moves with the
     market every day. Pass fresh semidev/spread_30y_pp/put_iv_365d to override any of its
     frozen numbers with a same-day re-pull, without touching anyone else's score.

  2. AN OUT-OF-COVERAGE TICKER (not in the 499). Requires the caller to supply at least one raw
     measure (semidev at minimum -- see idio/semidev.py, company-agnostic, works on price
     history alone) AND a risk_group. The risk group is NOT guessed automatically -- assigning a
     company to a risk group is a business-judgment call, the same kind of call the 28-group
     table itself was built on (docs/RESULTS-Risk-Group-Classification-V2-2026-08-21.md), and
     this project's standing discipline keeps judgment calls human-reviewed rather than silently
     automated. suggest_group() narrows the choice to a short, defensible list using the same
     GICS sub-industry data the 499-name table itself is classified on, so the human step is
     "confirm one of these three," not "invent one from nothing."

WHAT "SCORE" MEANS HERE, PRECISELY. Every block in idio_risk_score_v2.py is a PERCENTILE inside
a population. For an in-coverage name the population is "the other 498 names, this instant." For
an any-time single ticker, re-deriving that population from scratch would defeat the entire point
of freezing a snapshot -- so this module reads the ticker's percentile against the FROZEN
population instead: same tie-averaging philosophy (percentile_of below), generalized to a point
that is not itself a member of the frozen set. This is a real, stated design choice, not free --
see the note on percentile_of.

THE CALIBRATION CONSTANT k IS NEVER FROZEN. `premium = k * combined_score` where
`k = live_market_erp / cap_weighted_avg_combined_score_at_snapshot_build`. The market ERP is
fetched fresh on every call (market_erp_live.py already does this; nothing new here). Only the
denominator -- the universe's own average positioning -- comes from the frozen snapshot. This is
exactly the "universe updated occasionally, any stock updated any time" split James asked for.

    from idio_score_ticker import load_snapshot, score_ticker, suggest_group
    snap = load_snapshot()
    score_ticker("AAPL", snap)                                   # in-coverage, frozen numbers
    score_ticker("AAPL", snap, semidev=24.1)                     # in-coverage, same-day override
    score_ticker("NEWCO", snap, semidev=31.4, risk_group="Regional Banks")   # out-of-coverage

    python3 tools/idio_score_ticker.py AAPL
    python3 tools/idio_score_ticker.py NEWCO --semidev 31.4 --risk-group "Regional Banks"
    python3 tools/idio_score_ticker.py NEWCO --suggest-group "Banks - Regional"

NOT A VALUATION. No figure this module produces may be quoted for any company without the same
review any other idio-score output requires -- this module changes HOW a score is computed, not
the standing rule that a suggested premium is a default an analyst can and should override.
"""
from __future__ import annotations

import argparse
import bisect
import collections
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

SNAPSHOT_LATEST = os.path.join(ROOT, "outputs", "idio_snapshot_latest.json")


class OutOfCoverageError(ValueError):
    pass


def load_snapshot(path=None):
    p = path or SNAPSHOT_LATEST
    if not os.path.exists(p):
        raise FileNotFoundError(
            "%s does not exist. Build it first: python3 tools/idio_snapshot_build.py --write" % p)
    return json.load(open(p))


def percentile_of(value, sorted_frozen_values):
    """Where `value` falls inside a FROZEN sorted population, tie-averaged, in [0,1].

    This is percentile_of, not idio_risk_score_v2.pct_ranks -- deliberately a different
    function. pct_ranks ranks members of a set against each other (denominator n-1, so the
    population's own min/max land exactly on 0/1). percentile_of reads an EXTERNAL point against
    a population it is not a member of (denominator n, count-below-plus-half-ties), the standard
    "percentile of score" convention. A value at or beyond the frozen population's own extreme
    lands at or near 0 or 1 without needing to be inserted into the array. The two conventions
    agree almost exactly in the middle of a large population and diverge only in the tails,
    where the difference is a fraction of a rank on a 1-100 scale -- immaterial next to the
    99-point score range, and disclosed here rather than silently absorbed.
    """
    n = len(sorted_frozen_values)
    if n == 0:
        return 0.5
    lo = bisect.bisect_left(sorted_frozen_values, value)
    hi = bisect.bisect_right(sorted_frozen_values, value)
    equal = hi - lo
    return (lo + 0.5 * equal) / n


def _to_score(pct):
    return 1.0 + 99.0 * pct


BLOCK_LABELS = dict(volatility="Volatility (semi-deviation + put-IV)", credit="Credit spread",
                     industry="Industry (risk group)", within_industry="Within-industry rank")


def _rank_of_score(score, n):
    """1 = safest, n = riskiest -- read directly off the block's own percentile (score-1)/99
    rather than re-deriving it from raw values, so this always agrees with the score that was
    actually published, including when the score itself is an ADJUSTED figure (the volatility
    block's put-IV nudge) that no longer corresponds to a single raw value's position."""
    if n <= 0:
        return None
    pct = (score - 1.0) / 99.0
    return max(1, min(n, 1 + int(round(pct * (n - 1)))))


def build_decomposition(blocks, combined, k, snapshot, detail, grp):
    """James, 2026-08-21: 'for all 4 categories of risk show the rank..., the percentile
    rank..., indicated idiosyncratic ERP... And for the final idiosyncratic ERP, we get the
    same thing... it should tell him for each risk category, when each rank and score was last
    updated.' This builds exactly that -- one entry per block plus one for the combined score,
    each with rank/n, percentile, an INDICATED ERP (what the premium would be if this block
    alone were the whole score: k x block_score -- the same k, so the four numbers and the
    final are directly comparable), and the vintage of the data behind it.

    The indicated-ERP figures are PRE-FLOOR by construction (a floor is a property of the
    combined company, not of one block in isolation) -- if a floor bound the final premium,
    the four indicated figures will not average exactly to the published suggested_idio_erp_pct,
    and that gap is the floor's own size, not an error. floor_applied on the parent result says
    so explicitly.
    """
    vint = snapshot.get("vintages", {})
    pop_n = dict(
        volatility=len(snapshot.get("semidev_all", [])),
        credit=len(snapshot.get("credit_spread_all", [])),
        industry=len(snapshot.get("group_scores", {})),
        within_industry=(detail.get("within_industry", {}) or {}).get("group_n"),
    )
    vint_key = dict(volatility="semidev", credit="credit_spread", industry="risk_group",
                     within_industry="risk_group")
    rows = []
    for name in ("volatility", "credit", "industry", "within_industry"):
        if name not in blocks:
            continue
        score = blocks[name]
        n = pop_n.get(name)
        rank = _rank_of_score(score, n) if n else None
        pct_rank = round((score - 1.0) / 99.0 * 100.0, 1)
        v = vint.get(vint_key[name], {})
        rows.append(dict(
            block=name, label=BLOCK_LABELS[name],
            rank=rank, n_population=n,
            rank_label=("%d of %d (1 = safest)" % (rank, n) if rank and n else None),
            percentile_rank=pct_rank,
            score_1_100=round(score, 2),
            indicated_idio_erp_pct=round(k * score, 4),
            data_as_of=v.get("as_of"), data_basis=v.get("basis"),
        ))
    n_final = len(snapshot.get("combined_score_all", [])) or snapshot.get("n_universe")
    rank_final = _rank_of_score(combined, n_final) if n_final else None
    final = dict(
        rank=rank_final, n_population=n_final,
        rank_label=("%d of %d (1 = safest)" % (rank_final, n_final) if rank_final and n_final else None),
        percentile_rank=round((combined - 1.0) / 99.0 * 100.0, 1),
        combined_score_1_100=round(combined, 2),
    )
    return dict(risk_group=grp, blocks=rows, final=final,
                 snapshot_vintage_date=snapshot.get("vintage_date"))


def suggest_group(snapshot, gics_sub_industry=None, gics_sector=None, top=5):
    """Rank the snapshot's risk groups by how many in-coverage members share the given GICS
    sub-industry (exact match first) or sector (fallback), so a human can pick one for an
    out-of-coverage ticker rather than inventing an assignment from nothing. Returns a list of
    (risk_group, matching_member_count, sample_tickers)."""
    by_sub = collections.defaultdict(list)
    by_sector = collections.defaultdict(list)
    for t, gi in snapshot["ticker_gics"].items():
        g = snapshot["ticker_group"].get(t)
        if not g:
            continue
        by_sub[gi["sub_industry"]].append((g, t))
        by_sector[gi["sector"]].append((g, t))

    def rank(pairs):
        counts = collections.Counter(g for g, _ in pairs)
        samples = collections.defaultdict(list)
        for g, t in pairs:
            if len(samples[g]) < 4:
                samples[g].append(t)
        return sorted(((g, c, samples[g]) for g, c in counts.items()),
                      key=lambda x: -x[1])[:top]

    if gics_sub_industry and gics_sub_industry in by_sub:
        return dict(matched_on="sub_industry", query=gics_sub_industry,
                     candidates=rank(by_sub[gics_sub_industry]))
    if gics_sector and gics_sector in by_sector:
        return dict(matched_on="sector (no sub-industry match)", query=gics_sector,
                     candidates=rank(by_sector[gics_sector]))
    return dict(matched_on=None, query=gics_sub_industry or gics_sector,
                candidates=[], all_groups=sorted(snapshot["group_scores"]))


def _live_market_erp(log=None):
    import market_erp_live as mkt
    return mkt.fetch_market_erp(log=log or (lambda *a, **k: None))


def score_ticker(ticker, snapshot, semidev=None, spread_30y_pp=None, put_iv_365d=None,
                  risk_group=None, market_erp=None, market_erp_meta=None, log=None):
    """Score one ticker against a frozen snapshot. See module docstring for the two cases.

    Any of semidev / spread_30y_pp / put_iv_365d passed explicitly OVERRIDE that ticker's
    frozen value for this call only (nothing is written back to the snapshot). risk_group
    passed explicitly overrides the ticker's frozen group assignment; it is REQUIRED for a
    ticker the snapshot has never seen.
    """
    ticker = ticker.upper()
    in_coverage = ticker in snapshot["ticker_group"]
    no_overrides = (semidev is None and spread_30y_pp is None and put_iv_365d is None
                    and risk_group is None)

    # FAST, EXACT PATH: an in-coverage ticker with nothing overridden reproduces the full run's
    # own numbers exactly -- it is a straight dict read, not a re-derivation through
    # percentile_of. See the module docstring for why this differs from the override path below.
    if in_coverage and no_overrides and ticker in snapshot.get("ticker_combined_score", {}):
        blocks = dict(snapshot["ticker_blocks"][ticker])
        combined = snapshot["ticker_combined_score"][ticker]
        grp = snapshot["ticker_group"][ticker]
        sd = snapshot["ticker_semidev"].get(ticker)
        sp = snapshot["ticker_spread_30y_pp"].get(ticker)
        iv = snapshot["ticker_put_iv_365d"].get(ticker)
        n_blocks = len(blocks)

        if market_erp is None:
            erp_out = _live_market_erp(log=log)
            market_erp = erp_out["eff_erp"]
            market_erp_meta = erp_out
        k = market_erp / snapshot["cap_weighted_avg_combined_score"]
        floor = snapshot["constants"]["score_floor"]
        s = max(combined, floor)
        premium = k * s
        floor_note = ""
        if s > combined:
            floor_note = "score floor applied (%.2f -> %.2f)" % (combined, s)
        if sp is not None:
            own_floor = sp + snapshot["constants"]["credit_floor_margin_pp"]
            if premium < own_floor:
                floor_note = (floor_note + "; " if floor_note else "") + \
                    "credit floor applied (%.3f -> %.3f)" % (premium, own_floor)
                premium = own_floor
        n_fit = snapshot["ticker_credit_n_fit"].get(ticker)
        if "credit" not in blocks:
            reliability = "no credit data -- combined score can shift materially if a credit " \
                           "spread becomes available"
        elif n_fit is not None and n_fit <= 2:
            reliability = "credit spread fit on only %d bond%s -- treat with caution" \
                           % (n_fit, "" if n_fit == 1 else "s")
        else:
            reliability = "full"
        detail_fast = {"note": "exact frozen lookup -- no percentile_of approximation used"}
        if "within_industry" in blocks:
            peers_n = len(snapshot.get("group_peer_avg12", {}).get(grp, []))
            detail_fast["within_industry"] = dict(group_n=peers_n)
        decomposition = build_decomposition(blocks, combined, k, snapshot, detail_fast, grp)
        return dict(
            ticker=ticker, in_coverage=True, refused=False, exact=True,
            risk_group=grp, n_blocks=n_blocks, blocks={k2: round(v, 2) for k2, v in blocks.items()},
            combined_score=round(combined, 3),
            market_erp_pct=market_erp,
            market_erp_source=(market_erp_meta or {}).get("source"),
            market_erp_date=(market_erp_meta or {}).get("date"),
            market_erp_age_days=(market_erp_meta or {}).get("age_days"),
            calibration_k=k, snapshot_vintage=snapshot["vintage_date"],
            suggested_idio_erp_pct=round(premium, 4), floor_applied=floor_note,
            reliability=reliability,
            raw_inputs=dict(semidev=sd, spread_30y_pp=sp, put_iv_365d=iv),
            decomposition=decomposition,
            detail=detail_fast,
        )

    # OVERRIDE / OUT-OF-COVERAGE PATH: at least one input is fresh, or the ticker was never in
    # the snapshot at all. Both place a point that is not itself a frozen population member,
    # via percentile_of -- see that function's docstring for exactly how and why this can differ
    # in the tails from the frozen, exact numbers above.
    sd = semidev if semidev is not None else snapshot["ticker_semidev"].get(ticker)
    sp = spread_30y_pp if spread_30y_pp is not None else snapshot["ticker_spread_30y_pp"].get(ticker)
    iv = put_iv_365d if put_iv_365d is not None else snapshot["ticker_put_iv_365d"].get(ticker)
    grp = risk_group if risk_group is not None else snapshot["ticker_group"].get(ticker)

    if grp is None:
        raise OutOfCoverageError(
            "%s is not in the %d-name coverage universe and no risk_group was supplied. "
            "This is the out-of-coverage case the methodology requires a human judgment call "
            "for -- call suggest_group(snapshot, gics_sub_industry=...) to get a short, "
            "defensible shortlist from the same classification the 499-name table itself "
            "uses, confirm one, then pass it as risk_group." % (ticker, snapshot["n_universe"]))
    if grp not in snapshot["group_scores"]:
        raise OutOfCoverageError(
            "risk_group %r is not one of the %d groups in this snapshot. Valid groups: %s"
            % (grp, len(snapshot["group_scores"]), sorted(snapshot["group_scores"])))
    if sd is None and sp is None:
        raise OutOfCoverageError(
            "%s has neither a semi-deviation nor a credit spread to score on -- at minimum, "
            "semi-deviation is required (idio/semidev.py runs on price history alone, no bond "
            "or options market needed) or this ticker cannot be scored at all." % ticker)

    blocks, detail = {}, {}

    if sd is not None:
        base_pct = percentile_of(sd, snapshot["semidev_all"])
        if iv is not None and len(snapshot["semidev_optioned"]) > 1:
            sd_sub_pct = percentile_of(sd, snapshot["semidev_optioned"])
            iv_sub_pct = percentile_of(iv, snapshot["put_iv_optioned"])
            adj = snapshot["constants"]["iv_weight"] * (iv_sub_pct - sd_sub_pct)
            pct = min(1.0, max(0.0, base_pct + adj))
            detail["volatility"] = dict(has_put_iv=True, semidev_pct_all=base_pct,
                                         semidev_pct_optioned=sd_sub_pct,
                                         put_iv_pct_optioned=iv_sub_pct, adjustment=adj)
        else:
            pct = base_pct
            detail["volatility"] = dict(has_put_iv=False, semidev_pct_all=base_pct)
        blocks["volatility"] = _to_score(pct)

    if sp is not None:
        pct = percentile_of(sp, snapshot["credit_spread_all"])
        blocks["credit"] = _to_score(pct)
        detail["credit"] = dict(spread_pct_all=pct)

    gs = snapshot["group_scores"][grp]
    blocks["industry"] = 1.0 + 99.0 * (gs - 1.0) / 9.0
    detail["industry"] = dict(risk_group=grp, group_score=gs, in_coverage_group=(grp in snapshot["group_peer_avg12"]))

    avg12_inputs = [v for v in (blocks.get("volatility"), blocks.get("credit")) if v is not None]
    if avg12_inputs:
        avg12 = sum(avg12_inputs) / len(avg12_inputs)
        peers = snapshot["group_peer_avg12"].get(grp, [])
        n = len(peers)
        if n < 2:
            blocks["within_industry"] = _to_score(0.5)
            detail["within_industry"] = dict(group_n=n, note="fewer than 2 frozen peers in this group")
        else:
            raw_pct = percentile_of(avg12, peers)
            shrink = n / (n + 3.0)
            shrunk_pct = 0.5 + (raw_pct - 0.5) * shrink
            blocks["within_industry"] = _to_score(shrunk_pct)
            detail["within_industry"] = dict(group_n=n, raw_pct=raw_pct, shrink_factor=round(shrink, 3))

    n_blocks = len(blocks)
    if n_blocks < 2:
        return dict(ticker=ticker, in_coverage=in_coverage, refused=True,
                     reason="only %d of 4 blocks available (need >= 2)" % n_blocks,
                     blocks=blocks, detail=detail)

    combined = sum(blocks.values()) / n_blocks

    if market_erp is None:
        erp_out = _live_market_erp(log=log)
        market_erp = erp_out["eff_erp"]
        market_erp_meta = erp_out

    k = market_erp / snapshot["cap_weighted_avg_combined_score"]
    floor = snapshot["constants"]["score_floor"]
    s = max(combined, floor)
    premium = k * s
    floor_note = ""
    if s > combined:
        floor_note = "score floor applied (%.2f -> %.2f)" % (combined, s)
    if sp is not None:
        own_floor = sp + snapshot["constants"]["credit_floor_margin_pp"]
        if premium < own_floor:
            floor_note = (floor_note + "; " if floor_note else "") + \
                "credit floor applied (%.3f -> %.3f)" % (premium, own_floor)
            premium = own_floor

    n_fit = snapshot["ticker_credit_n_fit"].get(ticker) if in_coverage else None
    if "credit" not in blocks:
        reliability = "no credit data -- combined score can shift materially if a credit " \
                       "spread becomes available"
    elif n_fit is not None and n_fit <= 2:
        reliability = "credit spread fit on only %d bond%s -- treat with caution" \
                       % (n_fit, "" if n_fit == 1 else "s")
    else:
        reliability = "full" if in_coverage else "credit spread supplied externally, fit quality unknown to this module"

    decomposition = build_decomposition(blocks, combined, k, snapshot, detail, grp)
    return dict(
        ticker=ticker, in_coverage=in_coverage, refused=False, exact=False,
        risk_group=grp, n_blocks=n_blocks, blocks={k2: round(v, 2) for k2, v in blocks.items()},
        combined_score=round(combined, 3),
        market_erp_pct=market_erp,
        market_erp_source=(market_erp_meta or {}).get("source"),
        market_erp_date=(market_erp_meta or {}).get("date"),
        market_erp_age_days=(market_erp_meta or {}).get("age_days"),
        calibration_k=k,
        snapshot_vintage=snapshot["vintage_date"],
        suggested_idio_erp_pct=round(premium, 4),
        floor_applied=floor_note,
        reliability=reliability,
        raw_inputs=dict(semidev=sd, spread_30y_pp=sp, put_iv_365d=iv),
        decomposition=decomposition,
        detail=detail,
    )


def print_decomposition(result):
    """Plain-text version of `decomposition` -- the table an analyst actually reads before
    deciding whether to override the suggested premium."""
    if result.get("refused"):
        print("REFUSED: %s" % result.get("reason"))
        return
    d = result["decomposition"]
    print("%s -- idiosyncratic risk decomposition (risk group: %s)" % (result["ticker"], d["risk_group"]))
    print("%-32s %-14s %8s %12s %10s" % ("block", "rank", "pctile", "indic. ERP", "as of"))
    for b in d["blocks"]:
        print("%-32s %-14s %7s%% %11s%% %10s"
              % (b["label"], b["rank_label"] or "-", b["percentile_rank"],
                 b["indicated_idio_erp_pct"], b["data_as_of"] or "-"))
    f = d["final"]
    print("-" * 82)
    print("%-32s %-14s %7s%% %11s%%" % ("COMBINED (final)", f["rank_label"] or "-",
                                          f["percentile_rank"], result["suggested_idio_erp_pct"]))
    if result.get("floor_applied"):
        print("  note: %s" % result["floor_applied"])
    print("  snapshot vintage: %s" % d["snapshot_vintage_date"])


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("ticker")
    ap.add_argument("--semidev", type=float)
    ap.add_argument("--spread-30y-pp", type=float, dest="spread")
    ap.add_argument("--put-iv-365d", type=float, dest="put_iv")
    ap.add_argument("--risk-group")
    ap.add_argument("--suggest-group", dest="suggest", help="GICS sub-industry to match against")
    ap.add_argument("--snapshot", help="path override; default outputs/idio_snapshot_latest.json")
    args = ap.parse_args()

    snap = load_snapshot(args.snapshot)

    if args.suggest:
        res = suggest_group(snap, gics_sub_industry=args.suggest)
        print("matched on: %s (query=%r)" % (res["matched_on"], res["query"]))
        for g, c, samples in res["candidates"]:
            print("  %-28s %3d in-coverage members  e.g. %s" % (g, c, ", ".join(samples)))
        if not res["candidates"]:
            print("  no match -- all %d groups: %s" % (len(res["all_groups"]), res["all_groups"]))
        return 0

    out = score_ticker(args.ticker, snap, semidev=args.semidev, spread_30y_pp=args.spread,
                        put_iv_365d=args.put_iv, risk_group=args.risk_group, log=print)
    print()
    print_decomposition(out)
    print()
    print(json.dumps(out, indent=2))
    print("\nNOT A VALUATION.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
