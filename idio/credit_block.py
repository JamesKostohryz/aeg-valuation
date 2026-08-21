"""
idio/credit_block.py -- the guarded thirty-year credit spread, block two of the v2
idiosyncratic risk score.

A PORT of AEG-Project `tools/credit_spread_block.py`. The arithmetic, the guard order and the
guard thresholds are unchanged -- the only edits are where the fit is read from (this repo's own
`idio/issuer_curves.py` output, `outputs/issuer_curve_fit.csv`, kept fresh by the same monthly
bond-repricing pipeline Region 2 of the older company_curve.py system already uses) and where
the result is written.

THE FIT ITSELF: spread(t) = a_pp + b_pp * ln(t), fit by OLS on log(tenor). a_pp is the ONE-YEAR
level (ln(1) = 0); b_pp is the slope per unit of log-tenor. Extrapolating this LINEARLY (spread =
a + b*30) instead of via ln(30) overstates a bad slope's effect by roughly 30/ln(30) = 8.8x --
this module uses the correct log form throughout, per the AEG-Project original's own
self-correction (docs/MERGED-SPEC-Idiosyncratic-ERP-Score-2026-08-21.md section 6.1).

THE GUARD, applied in this order:
  1. Tier must be 1, 2 or 3. Tier 4 is imputed from equity semi-deviation and must never enter
     the credit block -- admitting it would make blocks one and two the same number.
  2. b_pp must be strictly positive. A credit curve that does not rise with maturity is not a
     curve; it is a handful of bonds and an unstable regression. THIS IS THE GUARD THAT MATTERS.
  3. The resulting thirty-year spread, a_pp + b_pp*ln(30), must fall in [0.15, 6.0] percentage
     points -- a backstop against a positive-but-absurd slope.

Everything that survives is reported with its extrapolation factor (how many times past the
longest fitted bond the thirty-year figure reaches) as a diagnostic, not a rejection criterion.

    python3 idio/credit_block.py --write

NOT A VALUATION. No company figure produced here may be quoted for any company.
"""
from __future__ import annotations

import csv
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _arg(flag, default=None):
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


SRC = _arg("--src", os.path.join(ROOT, "outputs", "issuer_curve_fit.csv"))
DST = _arg("--out", os.path.join(ROOT, "outputs", "credit_block_v2.csv"))

MIN_PP, MAX_PP = 0.15, 6.0


def thirty_year(a_pp, b_pp):
    return a_pp + b_pp * math.log(30.0)


def extrapolation_factor(longest_fit):
    return 30.0 / longest_fit if longest_fit and longest_fit > 0 else float("inf")


def load_and_guard(src=None):
    rows = list(csv.DictReader(open(src or SRC, newline="", encoding="utf-8")))
    out = []
    rejected = {"tier4_or_worse": [], "nonpositive_slope": [], "output_window": []}

    for r in rows:
        ticker = r["ticker"]
        tier = int(r["tier"])
        a_pp, b_pp = r.get("a_pp"), r.get("b_pp")

        if tier not in (1, 2, 3):
            rejected["tier4_or_worse"].append(ticker)
            continue
        if not a_pp or not b_pp:
            rejected["nonpositive_slope"].append(ticker)
            continue
        a_pp, b_pp = float(a_pp), float(b_pp)

        if b_pp <= 0:
            rejected["nonpositive_slope"].append(ticker)
            continue

        s30 = thirty_year(a_pp, b_pp)
        if not (MIN_PP <= s30 <= MAX_PP):
            rejected["output_window"].append(ticker)
            continue

        longest_fit = float(r["longest_fit"]) if r["longest_fit"] else 0.0
        out.append(dict(
            ticker=ticker, tier=tier, spread_30y_pp=round(s30, 4),
            a_pp_1y=round(a_pp, 4), b_pp=round(b_pp, 6),
            n_fit=int(r["n_fit"]), longest_fit_yrs=round(longest_fit, 2),
            extrapolation_factor=round(extrapolation_factor(longest_fit), 2),
        ))

    return out, rejected, len(rows)


def main():
    out, rejected, n_total = load_and_guard()
    print("credit_block_v2: %d issuer curves read from %s" % (n_total, SRC))
    print("rejected: tier4/unfitted %d, non-positive slope %d, output window %d"
          % (len(rejected["tier4_or_worse"]), len(rejected["nonpositive_slope"]),
             len(rejected["output_window"])))
    print("SURVIVING: %d of %d (%.1f%%)" % (len(out), n_total, 100.0 * len(out) / n_total))
    by_tier = {}
    for r in out:
        by_tier[r["tier"]] = by_tier.get(r["tier"], 0) + 1
    print("  by tier: %s" % dict(sorted(by_tier.items())))

    fields = ["ticker", "tier", "spread_30y_pp", "a_pp_1y", "b_pp", "n_fit",
              "longest_fit_yrs", "extrapolation_factor"]
    if "--write" in sys.argv:
        with open(DST, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            w.writerows(sorted(out, key=lambda r: r["ticker"]))
        print("\nwrote %s" % DST)
    print("NOT A VALUATION. No figure here may be quoted for any company.")


if __name__ == "__main__":
    main()
