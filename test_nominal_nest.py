#!/usr/bin/env python3
"""test_nominal_nest.py — Increment 0 gate: nominal reframe, term-structure AEG, Stage B-1.

WHAT THIS GATES, in order of importance.

1. THE CROSS-TAB IDENTITY (the property that matters).
   Valuation!B52 — the published headline, built by the abnormal-earnings-growth form —
   must equal DCF Reconciliation!B45 — the residual-income form, which is the leg the
   four-method tie is actually proven on. Two independent constructions of the same
   quantity from the same inputs must agree.

   Before the term-structure correction they did NOT. The AEG form discounted the path at
   the per-year cost-of-equity curve but capitalised every AEG term at a single long-run
   rate, which is valid only on a flat curve. On the live Apple fixture that understated
   the headline by 4.4%; on a steep curve the error reaches 22.6%; on an INVERTED curve it
   changes sign. Nothing in the engine compared the two tabs, so a green four-method tie
   coexisted with a materially wrong published number for as long as the engine existed.

   This is a PROPERTY, not a memorised number: it keeps holding when the fixture, the
   forecast or the rate feed changes. It is the strongest assertion in this file, and it
   is also enforced in-sheet on every build by Audit!B72, which feeds Audit!B5.

   test_curve_shapes.py extends the same property across curve SHAPES, which is what
   actually catches this class of defect.

2. The four-method tie and audit status stay green in every configuration.

3. The ten equity values, as a drift detector. These are measured on the current engine:
   Stage A nominal reframe + Stage B-1 cash tax on the historical-cost depreciation basis
   + the term-structure AEG correction + the Enterprise per-anchor-share fix.

   Enterprise-mode numbers additionally reflect the per-anchor-share fix. The Valuation
   tab used to roll book value per CURRENT share while the share count was shrinking
   through buybacks, which is not a valid clean-surplus roll — the correct per-share roll
   carries an extra buyback-dilution term. It now works per ANCHOR share, matching what
   DCF Reconciliation has always done in aggregate.

THE FLAT-CURVE CASE. With cfg_coe_mode = "Single" the curve is flat, and on a flat curve
the term-structure correction provably collapses to nothing. That is now asserted directly:
the AEG form and the residual-income form must agree to the last bit in that case.

It used to be asserted indirectly, as a delta against the flat-curve value of the engine
before the correction (109.000664184498), with the whole movement expected to be Stage
B-1's depreciation tax charge (0.096021570) and nothing else. That historical reference was
retired on 2026-08-08. It could no longer be recomputed — it was measured on a superseded
template AND on three inputs that have since been corrected per company — so the delta had
stopped measuring the correction and started measuring the input changes too. The two
constants are kept below as an audit trail only. The direct assertion is strictly stronger,
because it tests the property rather than a historical difference.

Run:  python3 test_nominal_nest.py            (uses ./MODEL_TEMPLATE.xlsx)
      python3 test_nominal_nest.py <template>
"""
import os, sys, shutil, openpyxl

_ROOT = os.path.dirname(os.path.abspath(__file__))
for p in (_ROOT, os.path.join(_ROOT, "pipeline")):
    if p not in sys.path:
        sys.path.insert(0, p)
import aeg_engine as AE
from recalc_lo import recalc

GOLDEN = os.path.join(_ROOT, "tests", "golden", "AAPL")
TEMPLATE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(_ROOT, "MODEL_TEMPLATE.xlsx")
WORK = os.path.join(_ROOT, "_nestwork")
PRICE = 315.0
REL_TOL = 1e-12          # equity value vs golden: relative
TIE_TOL = 1e-9           # four-method tie: absolute
XTAB_TOL = 1e-9          # Valuation AEG form vs DCF Reconciliation RI form: absolute $/sh

# Flat-curve reference points. See PROVENANCE above.
FLAT_PRE_CORRECTION_GOLDEN = 109.000664184498    # real-terms engine at main
FLAT_STAGE_B1_CHARGE = 0.096021570               # Stage B-1 depreciation tax, flat curve

# (cfg_mode, cfg_N, cfg_scenario, cfg_coe_mode) -> equity value per share
#
# BASELINE REBASED 2026-08-08 (P1/P3 plus the dividend-feed fix). These are frozen expected
# values, so they moved when the INPUTS were corrected. The previous baseline was built on
# three inputs that no company had ever chosen: the template base company's 36.5% dividend
# payout seed, its 18-year composite plant life, and a cash-flow-derived dividend per share
# of 1.027724 that silently overrode Apple's filed 0.96 because write_inputs ran before
# apply_market_data resolved it. Apple now runs at a 12.86% dividend payout and a 10.37-year
# plant life, both derived from its own filings.
#
# The base case moved 115.819983568982 -> 106.373075210994, attributed by isolating each
# input on the live engine: payout seed -5.97, plant life -3.74, interaction -0.26. Setting
# all three back to their old values reproduces 115.819983568982 exactly, which is also the
# evidence that the P4 financing-path fix and the P5 value-weighted operations tie moved no
# published number.
#
# Nothing STRUCTURAL moved. Through the whole rebase every case held its cross-tab
# agreement at +0.00e+00, its four-method tie between 0 and 1.2e-14, and its audit status at
# PASS. If a future change moves these numbers again, that is the question to ask first: did
# an input change, or did an identity break? Only the first is a reason to rebase.
CASES = [
    ("Equity",      4, "Consensus", "Term",   106.373075210994),
    ("Equity",      8, "Consensus", "Term",    90.478447361143),
    ("Equity",     15, "Consensus", "Term",    71.098500965495),
    ("Enterprise",  4, "Consensus", "Term",   128.094726972107),
    ("Enterprise",  8, "Consensus", "Term",   139.935655008626),
    ("Enterprise", 15, "Consensus", "Term",   156.048079155291),
    ("Equity",      4, "Bull",      "Term",   104.163184982686),
    ("Equity",      4, "Bear",      "Term",    87.628997052327),
    ("Equity",      4, "Normal",    "Term",    93.595519241455),
    ("Equity",      4, "Consensus", "Single",  99.616363590783),
]
CELL = dict(cfg_N="B26", cfg_coe_mode="B29", cfg_mode="B37", cfg_scenario="B69")

_fails = []


def check(ok, msg):
    print(f"  {'PASS' if ok else 'FAIL'}  {msg}")
    if not ok:
        _fails.append(msg)


def _cfg():
    f = {k: f"{GOLDEN}/REAL_{v}.csv" for k, v in dict(
        is_csv="IS", bs_csv="BS", cf_csv="CF",
        prices="prices", dividends="div", splits="splits").items()}
    return {"company": "Apple Inc.", "ticker": "AAPL", "price": PRICE, "files": f,
            "fy_end_month": 9,
            "forecast_horizon_N": 4,   # P2: cfg_N is required and has no default; 4 is the
                                      # horizon these fixtures have always run at.
            "judgments": {"minority_include": False, "finlease": 0.0,
                          "oi_adj_override": None, "rd_capitalize": True,
                          "rd_life": 5.0, "dps_override": None},
            "cost_of_debt": {"single_ytw": 0.05}}


def main():
    os.makedirs(WORK, exist_ok=True)
    base = os.path.join(WORK, "AAPL_nest_base.xlsx")
    AE.build_model(_cfg(), TEMPLATE, base)

    print("== Increment 0 gate: cross-tab identity, four-method tie, goldens ==")
    for mode, N, scen, coe, want in CASES:
        p = os.path.join(WORK, f"AAPL_{mode}_{N}_{scen}_{coe}.xlsx")
        shutil.copy(base, p)
        wb = openpyxl.load_workbook(p)
        for k, v in dict(cfg_mode=mode, cfg_N=N, cfg_scenario=scen, cfg_coe_mode=coe).items():
            wb["Inputs"][CELL[k]] = v
        wb.save(p)
        recalc(p)
        r = AE.read_results(p, price=PRICE)
        d = openpyxl.load_workbook(p, data_only=True)
        got = r.get("equity_value")
        tie = r.get("max_identity_tie")
        audit = r.get("audit_status")
        ri = d["DCF Reconciliation"]["B45"].value
        tag = f"{mode:<10} N={N:<2} {scen:<9} {coe:<6}"

        if not isinstance(got, (int, float)):
            check(False, f"{tag} equity_value unreadable ({got!r})")
            continue

        # (1) the property: the two constructions must agree
        if isinstance(ri, (int, float)):
            check(abs(got - ri) < XTAB_TOL,
                  f"{tag} cross-tab AEG vs RI  {got - ri:+.2e}  (AEG {got:.9f} / RI {ri:.9f})")
        else:
            check(False, f"{tag} DCF Reconciliation!B45 unreadable ({ri!r})")

        # (3) drift detector
        rel = abs(got - want) / abs(want)
        check(rel < REL_TOL, f"{tag} equity {got:.12f} vs golden {want:.12f}  (rel {rel:.1e})")

        # (2) tie + audit
        check(isinstance(tie, (int, float)) and abs(tie) < TIE_TOL,
              f"{tag} four-method tie {tie:.1e}")
        check(bool(audit) and str(audit).startswith("PASS"), f"{tag} audit {audit!r}")

        # FLAT CURVE. The property is that the term-structure correction landed in PR #3
        # contributes exactly nothing when the cost-of-equity curve is flat, so the AEG form
        # and the residual-income form must agree to the last bit.
        #
        # This used to be asserted indirectly, as a delta against
        # FLAT_PRE_CORRECTION_GOLDEN — the flat-curve value of the engine as it stood at
        # main BEFORE PR #3 — with the whole movement expected to be Stage B-1's
        # depreciation charge and nothing else. That historical reference was retired on
        # 2026-08-08 and both constants are kept above only as an audit trail. It could no
        # longer be recomputed: it was measured on a superseded template AND on three inputs
        # that have since been corrected per company (the payout seed, the plant life and
        # the dividend feed), so the delta stopped measuring the correction and started
        # measuring the input changes as well. Rebasing it against the current engine would
        # have made it circular — deriving the reference from the answer it checks.
        #
        # The direct assertion below is strictly stronger than the delta it replaces, since
        # it tests the property itself rather than a historical difference, and
        # test_curve_shapes.py independently confirms the same zero across five curve shapes
        # including the inverted one.
        if coe == "Single":
            _xtab = (got - ri) if isinstance(ri, (int, float)) else float("nan")
            check(abs(_xtab) < 1e-12,
                  f"{tag} FLAT CURVE: the AEG and residual-income forms agree to "
                  f"{_xtab:+.2e} — the term-structure correction contributes exactly zero "
                  f"when the curve is flat")

    print()
    if _fails:
        print(f"{len(_fails)} NEST CHECK(S) FAILED")
        return 1
    print("ALL NEST CHECKS PASSED — the two forms tie, the flat curve is unmoved by the "
          "correction, and the four-method tie holds")
    return 0


if __name__ == "__main__":
    sys.exit(main())
