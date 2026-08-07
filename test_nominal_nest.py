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

PROVENANCE OF THE FLAT-CURVE CASE. With cfg_coe_mode = "Single" the curve is flat, and on
a flat curve the term-structure correction provably collapses to nothing. That case reads
108.904642614247 here against 109.000664184498 on the pre-correction real-terms engine at
main. The entire -0.096021570 difference is Stage B-1's depreciation tax charge, a real
economic effect; the AEG correction contributes exactly zero. If that case ever moves by
anything other than a deliberate Stage B change, the correction has stopped being a
generalisation and has started changing answers it was never supposed to touch.

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
CASES = [
    ("Equity",      4, "Consensus", "Term",   115.819983568982),
    ("Equity",      8, "Consensus", "Term",   107.639957703621),
    ("Equity",     15, "Consensus", "Term",    97.5798309008793),
    ("Enterprise",  4, "Consensus", "Term",   130.626227866193),
    ("Enterprise",  8, "Consensus", "Term",   141.828253497193),
    ("Enterprise", 15, "Consensus", "Term",   157.555987326986),
    ("Equity",      4, "Bull",      "Term",   113.508130391957),
    ("Equity",      4, "Bear",      "Term",    96.1823720312737),
    ("Equity",      4, "Normal",    "Term",   102.440741441175),
    ("Equity",      4, "Consensus", "Single", 108.904642614247),
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

        # flat curve: the AEG correction must contribute exactly nothing, so the only
        # movement from the pre-correction golden is Stage B-1's depreciation charge
        if coe == "Single":
            implied = FLAT_PRE_CORRECTION_GOLDEN - got
            check(abs(implied - FLAT_STAGE_B1_CHARGE) < 1e-6,
                  f"{tag} FLAT CURVE: movement from pre-correction golden is "
                  f"{implied:.9f}, i.e. Stage B-1's charge alone "
                  f"({FLAT_STAGE_B1_CHARGE:.9f}); AEG correction contributes 0")

    print()
    if _fails:
        print(f"{len(_fails)} NEST CHECK(S) FAILED")
        return 1
    print("ALL NEST CHECKS PASSED — the two forms tie, the flat curve is unmoved by the "
          "correction, and the four-method tie holds")
    return 0


if __name__ == "__main__":
    sys.exit(main())
