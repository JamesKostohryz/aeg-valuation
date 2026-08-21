"""
idio/score_v2.py -- the four-block idiosyncratic risk score.

A PORT of AEG-Project `tools/idio_risk_score_v2.py`, landed 2026-08-21 once its inputs were
confirmed live-refreshable in this repository (semi-deviation via idio/feed.py's existing
monthly job; credit via idio/credit_block.py, fed by idio/issuer_curves.py +
idio/bond_reprice.py, already approved for the older company_curve.py system). Only paths
changed -- the arithmetic, guards and thresholds are unchanged.

Builds the score specified in docs/MERGED-SPEC-Idiosyncratic-ERP-Score-2026-08-21.md, section 3,
over the classification in outputs/risk_group_map_v2.csv (see
docs/RESULTS-Risk-Group-Classification-V2-2026-08-21.md for how that map was built).

THE FOUR BLOCKS, each scored 1-100 by tie-averaged percentile rank, 1 = safest:

  1. VOLATILITY. Semi-deviation percentile against the full universe, adjusted for names with
     one-year put-option implied volatility by up to 0.6 of the WITHIN-SUBSET gap between the
     two measures. See _volatility_block for why it is built this way rather than as a
     straight blend -- optioned names are systematically the large calm ones, and blending
     percentiles computed against different universes would silently favour them.

  2. CREDIT. The guarded thirty-year issuer credit spread from credit_spread_block_v2.py,
     which fixed a defect in this project's own extrapolation math -- see that module's
     docstring. Tiers 1-3 only, non-positive-slope curves excluded.

  3. INDUSTRY. The company's risk GROUP score (not sub-industry score) from
     risk_group_map_v2.csv, rescaled linearly 1 + 99*(score-1)/9 to preserve the judgment
     tiers' deliberate spacing. Group-level, not sub-industry-level, because a company moved
     into a new group must stop inheriting the old sub-industry's judgment -- see
     RESULTS-Risk-Group-Classification-V2 section 5.

  4. WITHIN-INDUSTRY. Percentile rank, inside the company's own risk group, of the company's
     own average of blocks 1 and 2 (whichever are available). Shrunk toward the group median
     by n/(n+3) so a small group cannot open its full range on close to a coin flip -- the
     mechanism that would otherwise separate Exxon and Chevron by four points, per the v1
     build.

MISSING DATA: score on whatever blocks are available, equal-weighted among them. Refuse below
two. Publish n_blocks and the weights actually applied on every row. Block 4 requires at least
one of blocks 1 or 2; where only one exists it is flagged as ranking on a single measure.

NOT A VALUATION. No company figure produced here may be quoted for any company. Nothing in this
module is wired into a live valuation -- that step is GATED and requires James's explicit
sign-off, per the standing project discipline.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

GROUP_MAP = os.path.join(ROOT, "outputs", "risk_group_map_v2.csv")
COMPANY_V1 = os.path.join(ROOT, "outputs", "company_idio_erp_judgment_v1.csv")
# outputs/idio_universe_latest.csv is `idio/feed.py`'s own output in the aeg-valuation repo --
# semi-deviation + market cap for the live S&P 500 universe, refreshed automatically every month
# by the idio-universe-refresh GitHub Action (idio_universe.yml). Preferred over COMPANY_V1
# (above), which was a one-time build closed out 2026-08-21 with nothing rebuilding it -- James,
# 2026-08-21: semi-deviation "should refresh once per month." This IS that refresh; it already
# existed for the older company_curve.py system and needed only to be pointed at, not rebuilt.
UNIVERSE_FEED = os.path.join(ROOT, "outputs", "idio_universe_latest.csv")
UNIVERSE_FEED_META = os.path.join(ROOT, "outputs", "idio_universe_latest.json")
CREDIT_BLOCK = os.path.join(ROOT, "outputs", "credit_block_v2.csv")
SVIX_FLEET = os.path.join(ROOT, "outputs", "svix_fleet_v2_cross_section.csv")
OUT_CSV = os.path.join(ROOT, "outputs", "idio_score_latest.csv")
OUT_JSON = os.path.join(ROOT, "outputs", "idio_score_run_meta.json")

IV_WEIGHT = 0.6                  # section 3.5: 60/40 toward the forward-looking measure
SCORE_FLOOR = 1.5                # section 7: raised from 1.0, concurred
CREDIT_FLOOR_MARGIN_PP = 0.25    # PROVISIONAL -- see the results document; not yet James's call
MIN_WEIGHT_COVERAGE = 0.90       # refuse calibration if less of the universe's cap weight scores


# --------------------------------------------------------------------------------------
# tie-averaged percentile ranks, the house convention
# --------------------------------------------------------------------------------------

def pct_ranks(keyed_values):
    """keyed_values: {key: float}. Returns {key: pct in [0,1]}, tie-averaged, 0=lowest."""
    items = list(keyed_values.items())
    if len(items) < 2:
        return {k: 0.5 for k, _ in items}
    order = sorted(range(len(items)), key=lambda i: items[i][1])
    n = len(items)
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and items[order[j + 1]][1] == items[order[i]][1]:
            j += 1
        avg = (i + j) / 2.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return {items[idx][0]: ranks[idx] / (n - 1) for idx in range(n)}


def to_score(pct):
    return 1.0 + 99.0 * pct


# --------------------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------------------

def load_universe():
    rows = list(csv.DictReader(open(GROUP_MAP, newline="", encoding="utf-8")))
    excluded = [r["ticker"] for r in rows if r["data_flag"]]
    rows = [r for r in rows if not r["data_flag"]]
    return rows, excluded


def load_semidev_and_weight():
    """Prefers the monthly-refreshed universe feed; falls back to the frozen v1 file (with a
    loud warning) only if the feed is missing, so an old checkout doesn't silently regress."""
    if os.path.exists(UNIVERSE_FEED):
        sd, cap = {}, {}
        for r in csv.DictReader(open(UNIVERSE_FEED, newline="", encoding="utf-8")):
            if r.get("semidev"):
                sd[r["ticker"]] = float(r["semidev"])
            if r.get("market_cap"):
                cap[r["ticker"]] = float(r["market_cap"])
        total = sum(cap.values())
        wt = {t: c / total for t, c in cap.items()} if total else {}
        return sd, wt
    sys.stderr.write(
        "WARNING: %s not found -- falling back to the FROZEN %s (built once, 2026-08-21, "
        "nothing rebuilds it). Semi-deviation will not reflect anything more recent than that "
        "date. Sync outputs/idio_universe_latest.csv from the aeg-valuation repo.\n"
        % (UNIVERSE_FEED, COMPANY_V1))
    sd, wt = {}, {}
    for r in csv.DictReader(open(COMPANY_V1, newline="", encoding="utf-8")):
        if r["semidev"]:
            sd[r["ticker"]] = float(r["semidev"])
        if r["weight"]:
            wt[r["ticker"]] = float(r["weight"])
    return sd, wt


def semidev_feed_vintage():
    """The universe feed's own as-of date, straight from idio/feed.py's own metadata -- not a
    file-modified-time guess."""
    if os.path.exists(UNIVERSE_FEED_META):
        meta = json.load(open(UNIVERSE_FEED_META))
        return dict(as_of=meta.get("market_asof") or meta.get("asof"),
                    basis="idio/feed.py, monthly GitHub Action (idio_universe.yml)",
                    coverage=meta.get("coverage"))
    return dict(as_of=(dt.date.fromtimestamp(os.path.getmtime(COMPANY_V1)).isoformat()
                        if os.path.exists(COMPANY_V1) else None),
                basis="frozen fallback file, no scheduled refresh", coverage=None)


def load_credit():
    sp, n_fit = {}, {}
    for r in csv.DictReader(open(CREDIT_BLOCK, newline="", encoding="utf-8")):
        sp[r["ticker"]] = float(r["spread_30y_pp"])
        n_fit[r["ticker"]] = int(r["n_fit"])
    return sp, n_fit


def load_put_iv():
    iv = {}
    for r in csv.DictReader(open(SVIX_FLEET, newline="", encoding="utf-8")):
        if r["tenor_days"] == "365" and r["implied_vol_pct"]:
            iv[r["ticker"]] = float(r["implied_vol_pct"])
    return iv


def fetch_market_erp():
    try:
        import market_erp_live as mkt
        out = mkt.fetch_market_erp(log=lambda *a, **k: None)
        return out["eff_erp"], out
    except Exception as e:                     # noqa: BLE001
        raise SystemExit("cannot proceed without the live market ERP: %s" % e)


# --------------------------------------------------------------------------------------
# block 1 -- volatility, with the scale-trap correction from the merged spec section 3.5
# --------------------------------------------------------------------------------------

def volatility_block(semidev, put_iv):
    """Returns {ticker: (score_1_100, detail_dict)}."""
    p_sd_all = pct_ranks(semidev)

    optioned = {t: semidev[t] for t in semidev if t in put_iv}
    p_sd_sub = pct_ranks(optioned) if len(optioned) > 1 else {}
    p_iv_sub = pct_ranks({t: put_iv[t] for t in optioned}) if len(optioned) > 1 else {}

    out = {}
    for t in semidev:
        base = p_sd_all[t]
        if t in p_sd_sub:
            adj = IV_WEIGHT * (p_iv_sub[t] - p_sd_sub[t])
            pct = min(1.0, max(0.0, base + adj))
            out[t] = (to_score(pct), dict(has_put_iv=True, semidev_pct_all=base,
                                           semidev_pct_sub=p_sd_sub[t], put_iv_pct_sub=p_iv_sub[t],
                                           put_iv_adjustment=adj))
        else:
            out[t] = (to_score(base), dict(has_put_iv=False, semidev_pct_all=base,
                                            semidev_pct_sub=None, put_iv_pct_sub=None,
                                            put_iv_adjustment=0.0))
    return out


# --------------------------------------------------------------------------------------
# block 2 -- credit
# --------------------------------------------------------------------------------------

def credit_block(spread):
    p = pct_ranks(spread)
    return {t: to_score(p[t]) for t in spread}


# --------------------------------------------------------------------------------------
# block 3 -- industry, at group level
# --------------------------------------------------------------------------------------

def industry_block(rows):
    out = {}
    for r in rows:
        gs = float(r["group_score"])
        out[r["ticker"]] = 1.0 + 99.0 * (gs - 1.0) / 9.0
    return out


# --------------------------------------------------------------------------------------
# block 4 -- within-industry, shrunk
# --------------------------------------------------------------------------------------

def within_industry_block(rows, block1, block2):
    """Rank each company's own average of blocks 1/2 (whichever exist) against its group
    peers on the same basis, then shrink toward the group median by n/(n+3)."""
    group_of = {r["ticker"]: r["risk_group"] for r in rows}
    groups = {}
    for t, g in group_of.items():
        groups.setdefault(g, []).append(t)

    avg12, n_measures = {}, {}
    for t in group_of:
        vals = [v for v in (block1.get(t), block2.get(t)) if v is not None]
        if vals:
            avg12[t] = sum(vals) / len(vals)
            n_measures[t] = len(vals)

    out = {}
    for g, members in groups.items():
        peers = {t: avg12[t] for t in members if t in avg12}
        n = len(peers)
        if n < 2:
            for t in peers:
                out[t] = (to_score(0.5), dict(group_n=n, shrunk=True, raw_pct=0.5,
                                               ranked_on_n_measures=n_measures.get(t)))
            continue
        raw = pct_ranks(peers)
        shrink = n / (n + 3.0)
        for t in peers:
            shrunk_pct = 0.5 + (raw[t] - 0.5) * shrink
            out[t] = (to_score(shrunk_pct), dict(group_n=n, shrunk=True, raw_pct=raw[t],
                                                  shrink_factor=round(shrink, 3),
                                                  ranked_on_n_measures=n_measures.get(t)))
    return out


# --------------------------------------------------------------------------------------
# assembly
# --------------------------------------------------------------------------------------

def main():
    rows, excluded = load_universe()
    semidev, weight = load_semidev_and_weight()
    spread, credit_n_fit = load_credit()
    put_iv = load_put_iv()
    market_erp, erp_meta = fetch_market_erp()

    b1 = volatility_block(semidev, put_iv)
    b2 = credit_block(spread)
    b3 = industry_block(rows)
    b1_scores = {t: v[0] for t, v in b1.items()}
    b2_scores = b2
    b4 = within_industry_block(rows, b1_scores, b2_scores)

    group_score_of = {r["ticker"]: r["group_score"] for r in rows}
    group_of = {r["ticker"]: r["risk_group"] for r in rows}
    change_of = {r["ticker"]: r["change"] for r in rows}

    out_rows = []
    refused = []
    for r in rows:
        t = r["ticker"]
        blocks = {}
        if t in b1_scores:
            blocks["volatility"] = b1_scores[t]
        if t in b2_scores:
            blocks["credit"] = b2_scores[t]
        if t in b3:
            blocks["industry"] = b3[t]
        if t in b4:
            blocks["within_industry"] = b4[t][0]

        n_blocks = len(blocks)
        if n_blocks < 2:
            refused.append(t)
            continue

        combined = sum(blocks.values()) / n_blocks
        applied_weight = round(1.0 / n_blocks, 4)

        # -- reliability tier --------------------------------------------------------
        #
        # Diagnostic 2 (idio_score_diagnostics.py) shows that dropping the credit block
        # moves a company's combined score by up to +/-29 points on the 1-100 scale --
        # not noise, but a genuinely missing, largely orthogonal risk signal (leverage),
        # confirmed by an r=-0.855 correlation between the shift and how far a company's
        # credit percentile sits from its semi-deviation percentile. A single point
        # estimate with no reliability marker hides that. Two conditions are flagged:
        #   - the credit block is simply absent (n_blocks < 4, missing "credit")
        #   - the credit block IS present but rests on a thin fit (two bonds or fewer),
        #     which is common enough to matter: 101 of 359 surviving curves qualify.
        n_fit = credit_n_fit.get(t)
        if "credit" not in blocks:
            reliability = "no credit data -- combined score can shift materially if a " \
                           "credit spread becomes available (see diagnostic 2)"
        elif n_fit is not None and n_fit <= 2:
            reliability = "credit spread fit on only %d bond%s -- treat with caution" \
                           % (n_fit, "" if n_fit == 1 else "s")
        else:
            reliability = "full"

        row = dict(
            ticker=t, risk_group=group_of[t], group_score=group_score_of[t],
            group_change=change_of[t],
            semidev=semidev.get(t, ""), spread_30y_pp=spread.get(t, ""),
            credit_n_fit=n_fit if n_fit is not None else "",
            put_iv_365d=put_iv.get(t, ""),
            reliability=reliability,
            block_volatility=round(blocks.get("volatility", float("nan")), 2) if "volatility" in blocks else "",
            block_credit=round(blocks.get("credit", float("nan")), 2) if "credit" in blocks else "",
            block_industry=round(blocks.get("industry", float("nan")), 2) if "industry" in blocks else "",
            block_within_industry=round(blocks.get("within_industry", float("nan")), 2) if "within_industry" in blocks else "",
            n_blocks=n_blocks, weight_per_block=applied_weight,
            combined_score=round(combined, 3),
            cap_weight=weight.get(t, ""),
            has_put_iv=b1.get(t, (None, {}))[1].get("has_put_iv", False) if t in b1 else "",
            within_group_n=b4.get(t, (None, {}))[1].get("group_n", "") if t in b4 else "",
            within_group_shrink=b4.get(t, (None, {}))[1].get("shrink_factor", "") if t in b4 else "",
            within_group_ranked_on=b4.get(t, (None, {}))[1].get("ranked_on_n_measures", "") if t in b4 else "",
        )
        out_rows.append(row)

    # -- calibration --------------------------------------------------------------------
    weighted = [(r, weight.get(r["ticker"])) for r in out_rows if r["ticker"] in weight]
    total_w_scored = sum(w for _, w in weighted)
    total_w_universe = sum(weight.values())
    coverage = total_w_scored / total_w_universe if total_w_universe else 0.0

    if coverage < MIN_WEIGHT_COVERAGE:
        raise SystemExit("REFUSED: capitalization weight coverage of the scored universe is "
                          "%.1f%%, below the %.0f%% minimum. Calibrating the market-ERP "
                          "constraint over an unrepresentative universe would silently move "
                          "the scale." % (100 * coverage, 100 * MIN_WEIGHT_COVERAGE))

    cw_avg_score = sum(r["combined_score"] * w for r, w in weighted) / total_w_scored
    k = market_erp / cw_avg_score   # premium_i = k * combined_score_i

    for r in out_rows:
        s = max(r["combined_score"], SCORE_FLOOR)
        premium = k * s
        floor_note = ""
        if s > r["combined_score"]:
            floor_note = "score floor applied (%.2f -> %.2f)" % (r["combined_score"], SCORE_FLOOR)
        if r["spread_30y_pp"] != "":
            own_floor = float(r["spread_30y_pp"]) + CREDIT_FLOOR_MARGIN_PP
            if premium < own_floor:
                floor_note = (floor_note + "; " if floor_note else "") + \
                    "credit floor applied (%.3f -> %.3f)" % (premium, own_floor)
                premium = own_floor
        r["suggested_idio_erp_pct"] = round(premium, 4)
        r["floor_applied"] = floor_note

    cw_check = sum(r["suggested_idio_erp_pct"] * w for r, w in weighted) / total_w_scored

    # -- write --------------------------------------------------------------------------
    fields = ["ticker", "risk_group", "group_score", "group_change", "semidev", "spread_30y_pp",
              "credit_n_fit", "put_iv_365d", "has_put_iv", "block_volatility", "block_credit",
              "block_industry", "block_within_industry", "within_group_n", "within_group_shrink",
              "within_group_ranked_on", "n_blocks", "weight_per_block", "combined_score",
              "cap_weight", "suggested_idio_erp_pct", "floor_applied", "reliability"]
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(sorted(out_rows, key=lambda r: r["ticker"]))

    meta = dict(
        market_erp_pct=market_erp, market_erp_source=erp_meta.get("source"),
        market_erp_date=erp_meta.get("date"), market_erp_age_days=erp_meta.get("age_days"),
        calibration_k=k, cap_weighted_avg_score_before_floors=cw_avg_score,
        cap_weighted_avg_premium_after_floors_pct=cw_check,
        weight_coverage_pct=100 * coverage,
        n_scored=len(out_rows), n_refused=len(refused), refused=sorted(refused),
        n_excluded_data_artifact=len(excluded), excluded=sorted(excluded),
        iv_weight=IV_WEIGHT, score_floor=SCORE_FLOOR,
        credit_floor_margin_pp=CREDIT_FLOOR_MARGIN_PP,
        credit_floor_margin_status="PROVISIONAL -- not yet confirmed by James, see results doc",
    )
    json.dump(meta, open(OUT_JSON, "w"), indent=2)

    print("idio_risk_score_v2: %d scored, %d refused (fewer than two blocks), "
          "%d excluded as data artifacts" % (len(out_rows), len(refused), len(excluded)))
    print("  refused: %s" % refused)
    print()
    print("market ERP: %.4f%% (%s, %s, %d days old)"
          % (market_erp, erp_meta.get("source"), erp_meta.get("date"), erp_meta.get("age_days")))
    print("weight coverage of scored universe: %.2f%%" % (100 * coverage))
    print("calibration constant k = %.5f  (premium = k x combined score)" % k)
    print("cap-weighted avg combined score (pre-floor): %.3f" % cw_avg_score)
    print("cap-weighted avg suggested premium (post-floor): %.4f%%  (target %.4f%%, drift %.4f pp)"
          % (cw_check, market_erp, cw_check - market_erp))
    n_floored = sum(1 for r in out_rows if r["floor_applied"])
    print("names with a floor applied: %d" % n_floored)
    print()
    print("wrote %s" % OUT_CSV)
    print("wrote %s" % OUT_JSON)
    print("NOT A VALUATION. No figure here may be quoted for any company.")


if __name__ == "__main__":
    main()
