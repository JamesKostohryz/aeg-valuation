"""
idio/snapshot_build.py -- freeze the idio risk score's universe into a lookup snapshot.

A PORT of AEG-Project `tools/idio_snapshot_build.py`, landed alongside idio/score_v2.py.

WHY THIS EXISTS. idio_risk_score_v2.py answers one question well -- "score everyone in the
499-name universe today" -- but it cannot answer "score AAPL, right now, without re-pulling
every bond and option chain in the universe" or "score a ticker that was never in the 499 at
all." Both of those are things James asked for explicitly: "I want this entire system to be
fully in production, so that I can get an ERP for ANY stock and this includes stocks that are
not in the coverage universe... The universe should be updated only occasionally, whereas any
specific stock can be updated at any time."

THE SPLIT THIS MODULE MAKES. Two different things were living inside one script:

  SLOW, SHARED STATE (this module freezes it):
    - the distribution of semi-deviation across the universe (and the optioned subset of it)
    - the distribution of 30-year credit spreads across the universe
    - the risk-group table and each group's judgment score
    - each risk group's own peer distribution of (volatility+credit average), for block 4
    - the calibration anchor: the cap-weighted average combined score, as of this snapshot

  FAST, ANY-TIME STATE (idio_score_ticker.py reads it live, every call):
    - the published market ERP (already fetched fresh every call via market_erp_live.py --
      this was already true before this module existed; nothing here changes it)
    - one ticker's own fresh semi-deviation / credit spread / put-IV, if the caller has them

A ticker's score = where its own (fresh, any-time) raw numbers fall inside the (frozen,
occasional) distributions, times a calibration constant that is itself recomputed against
TODAY's live market ERP every time -- so scores move with the market every day even though the
distributions they are read against only move when this snapshot is rebuilt.

WHAT "OCCASIONALLY" SHOULD MEAN. Semi-deviation and credit spreads drift slowly (weeks), the
risk-group judgment table changes only when a company's business changes (rare, human-reviewed).
A weekly or monthly rebuild is almost certainly often enough; there is no evidence in this
project that daily rebuilds would change any published score materially. That cadence is a
recommendation, not yet a scheduled job -- scheduling it is a separate, small step.

REUSES idio_risk_score_v2.py's own loaders and block functions rather than re-implementing them,
for the same reason idio_score_diagnostics.py does: a snapshot that could silently drift from
what the live scorer actually computes would be worse than no snapshot at all.

    python3 tools/idio_snapshot_build.py --write

Writes outputs/idio_snapshot_latest.json AND a dated copy outputs/idio_snapshot_<date>.json, so
a stale live snapshot is at least a diagnosable, dated fact rather than a silent one.

NOT A VALUATION. No company figure produced from this snapshot may be quoted for any company
without the same review any other idio-score output requires.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import score_v2 as S  # noqa: E402

OUT_LATEST = os.path.join(ROOT, "outputs", "idio_snapshot_latest.json")
OUT_DATED_TMPL = os.path.join(ROOT, "outputs", "idio_snapshot_%s.json")


def _file_date(path):
    return dt.date.fromtimestamp(os.path.getmtime(path)).isoformat() if os.path.exists(path) else None


def _max_field(path, field):
    """Latest value of a date-like column, or None if the file/column isn't there. Used to
    recover a real 'as of' date for a data source rather than settling for file-modified-time,
    which only says when someone last ran a script, not when the underlying market data itself
    was observed."""
    if not os.path.exists(path):
        return None
    try:
        vals = [r.get(field) for r in __import__("csv").DictReader(open(path, newline="", encoding="utf-8"))]
        vals = sorted(v for v in vals if v)
        return vals[-1] if vals else None
    except Exception:                                              # noqa: BLE001
        return None


def build_vintages(log=print):
    """Best-available 'as of' date for each of the four legs, PLUS the file-modified fallback
    when a source carries no date column of its own. James, 2026-08-21: 'it should tell him for
    each risk category, when each rank and score was last updated' -- this is that answer,
    computed from the actual source data rather than asserted."""
    bond_primary = os.path.join(ROOT, "data", "bond_spreads", "bond_spreads_live.csv")
    svix_by_date = S.SVIX_FLEET.replace("_cross_section.csv", "_by_date.csv")
    credit_quote = _max_field(bond_primary, "quote_date")
    put_iv_date = _max_field(svix_by_date, "date")
    return dict(
        semidev=S.semidev_feed_vintage(),
        credit_spread=dict(as_of=credit_quote or _file_date(S.CREDIT_BLOCK),
                            basis=("latest bond quote date, primary source" if credit_quote
                                   else "file last built (no quote date recovered)")),
        put_iv=dict(as_of=put_iv_date or _file_date(S.SVIX_FLEET),
                    basis=("latest date in the fitting window" if put_iv_date
                           else "file last built (no fit-window date recovered)")),
        risk_group=dict(as_of=_file_date(S.GROUP_MAP),
                         basis="static by design -- changes only on a reviewed business-driver "
                               "change, not a calendar"),
    )


def build_snapshot(log=print):
    rows, excluded = S.load_universe()
    semidev, weight = S.load_semidev_and_weight()
    spread, credit_n_fit = S.load_credit()
    put_iv = S.load_put_iv()
    market_erp, erp_meta = S.fetch_market_erp()
    vintages = build_vintages(log=log)

    b1 = S.volatility_block(semidev, put_iv)
    b2 = S.credit_block(spread)
    b3 = S.industry_block(rows)
    b1_scores = {t: v[0] for t, v in b1.items()}
    b4 = S.within_industry_block(rows, b1_scores, b2)

    group_of = {r["ticker"]: r["risk_group"] for r in rows}
    group_score_of = {r["ticker"]: float(r["group_score"]) for r in rows}
    gics_of = {r["ticker"]: (r.get("gics_sector", ""), r.get("gics_sub_industry", "")) for r in rows}

    groups = {}
    for t, g in group_of.items():
        groups.setdefault(g, []).append(t)
    group_score_table = {}
    for g, members in groups.items():
        scores = {group_score_of[t] for t in members}
        group_score_table[g] = sorted(scores)[0] if len(scores) == 1 else None
    inconsistent = [g for g, s in group_score_table.items() if s is None]
    if inconsistent:
        raise SystemExit("REFUSED: risk group(s) %s carry more than one group_score in "
                          "risk_group_map_v2.csv -- that file is supposed to hold one score "
                          "per group. Fix the source before freezing a snapshot from it."
                          % inconsistent)

    # the block-4 peer pool per group: each member's own avg of blocks 1/2, whichever exist --
    # exactly the population within_industry_block ranks a company against. Frozen here so a
    # single new ticker can be placed inside that same population without recomputing everyone.
    avg12 = {}
    for t in group_of:
        vals = [v for v in (b1_scores.get(t), b2.get(t)) if v is not None]
        if vals:
            avg12[t] = sum(vals) / len(vals)
    peer_pool = {g: sorted(avg12[t] for t in members if t in avg12) for g, members in groups.items()}

    # combined scores, as idio_risk_score_v2.main() computes them -- frozen per-ticker so the
    # default (no-override) lookup path in idio_score_ticker.py can return the EXACT number the
    # full run would, rather than an approximation from percentile_of. percentile_of is only
    # needed when a caller supplies a fresh number that was never part of this population, or
    # asks about a ticker that was never in it -- see idio_score_ticker.py's module docstring.
    ticker_blocks, ticker_combined = {}, {}
    out_rows = []
    for r in rows:
        t = r["ticker"]
        blocks = {}
        if t in b1_scores:
            blocks["volatility"] = b1_scores[t]
        if t in b2:
            blocks["credit"] = b2[t]
        if t in b3:
            blocks["industry"] = b3[t]
        if t in b4:
            blocks["within_industry"] = b4[t][0]
        if len(blocks) < 2:
            continue
        combined = sum(blocks.values()) / len(blocks)
        ticker_blocks[t] = blocks
        ticker_combined[t] = combined
        out_rows.append((t, combined))

    combined_score_all = sorted(ticker_combined.values())

    weighted = [(t, c, weight[t]) for t, c in out_rows if t in weight]
    total_w_scored = sum(w for _, _, w in weighted)
    total_w_universe = sum(weight.values())
    coverage = total_w_scored / total_w_universe if total_w_universe else 0.0
    if coverage < S.MIN_WEIGHT_COVERAGE:
        raise SystemExit("REFUSED: weight coverage %.1f%% below the %.0f%% minimum -- same "
                          "guard idio_risk_score_v2.py applies, checked again here because "
                          "this snapshot freezes its own independent calibration anchor."
                          % (100 * coverage, 100 * S.MIN_WEIGHT_COVERAGE))
    cw_avg_score = sum(c * w for _, c, w in weighted) / total_w_scored

    today = dt.date.today().isoformat()
    snap = dict(
        vintage_date=today,
        built_from=dict(
            group_map="outputs/risk_group_map_v2.csv",
            semidev_source="outputs/company_idio_erp_judgment_v1.csv",
            credit_source="outputs/credit_spread_block_v2.csv",
            put_iv_source="outputs/svix_fleet_v2_cross_section.csv",
        ),
        n_universe=len(rows), n_scored_for_calibration=len(weighted),
        weight_coverage_pct=round(100 * coverage, 3),
        market_erp_pct_at_build=market_erp,
        market_erp_source_at_build=erp_meta.get("source"),
        market_erp_date_at_build=erp_meta.get("date"),
        cap_weighted_avg_combined_score=cw_avg_score,
        constants=dict(iv_weight=S.IV_WEIGHT, score_floor=S.SCORE_FLOOR,
                       credit_floor_margin_pp=S.CREDIT_FLOOR_MARGIN_PP),
        # -- the frozen distributions --------------------------------------------------
        semidev_all=sorted(semidev.values()),
        semidev_optioned=sorted(semidev[t] for t in semidev if t in put_iv),
        put_iv_optioned=sorted(put_iv[t] for t in semidev if t in put_iv),
        credit_spread_all=sorted(spread.values()),
        group_scores=group_score_table,
        group_peer_avg12=peer_pool,
        # -- per-ticker lookups, so an IN-COVERAGE ticker's fast path needs no distribution
        #    math at all -- just a dict read plus today's live market ERP -----------------
        ticker_group=group_of,
        ticker_gics={t: dict(sector=s, sub_industry=si) for t, (s, si) in gics_of.items()},
        ticker_semidev=semidev,
        ticker_spread_30y_pp=spread,
        ticker_credit_n_fit=credit_n_fit,
        ticker_put_iv_365d=put_iv,
        ticker_cap_weight=weight,
        ticker_blocks=ticker_blocks,
        ticker_combined_score=ticker_combined,
        combined_score_all=combined_score_all,
        vintages=vintages,
    )
    return snap


def main():
    log = print
    snap = build_snapshot(log=log)
    log("SNAPSHOT built %s" % snap["vintage_date"])
    log("  universe: %d names, %d usable for calibration (%.1f%% cap weight)"
        % (snap["n_universe"], snap["n_scored_for_calibration"], snap["weight_coverage_pct"]))
    log("  market ERP at build: %.4f%% (%s, %s)"
        % (snap["market_erp_pct_at_build"], snap["market_erp_source_at_build"],
           snap["market_erp_date_at_build"]))
    log("  cap-weighted avg combined score at build: %.3f" % snap["cap_weighted_avg_combined_score"])
    log("  groups: %d, semidev pop: %d (optioned: %d), credit pop: %d"
        % (len(snap["group_scores"]), len(snap["semidev_all"]), len(snap["semidev_optioned"]),
           len(snap["credit_spread_all"])))
    for leg, v in snap["vintages"].items():
        log("  vintage -- %-13s as of %s  (%s)" % (leg, v["as_of"], v["basis"]))
    if "--write" in sys.argv:
        os.makedirs(os.path.dirname(OUT_LATEST), exist_ok=True)
        json.dump(snap, open(OUT_LATEST, "w"), indent=2)
        json.dump(snap, open(OUT_DATED_TMPL % snap["vintage_date"], "w"), indent=2)
        log("\nWROTE %s" % OUT_LATEST)
        log("WROTE %s" % (OUT_DATED_TMPL % snap["vintage_date"]))
    log("\nNOT A VALUATION.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
