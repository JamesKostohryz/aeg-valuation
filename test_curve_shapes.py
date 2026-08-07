#!/usr/bin/env python3
"""test_curve_shapes.py — the property test the four-method tie could never provide.

WHY THIS FILE EXISTS

The four-method tie (AEG = ReOI = FCFE = FCFF) is an INTERNAL CONSISTENCY check. It proves
the five spokes on the DCF Reconciliation tab agree with each other. By construction it
cannot detect:

  (a) an error in a construction that is not one of those spokes — which is exactly what
      happened: the published headline is built on the Valuation tab, by a different
      formula, and nothing compared the two;
  (b) an error in an assumption SHARED by all the spokes, since a shared error moves them
      all together and the identity still closes;
  (c) anything computed outside the sealed sheet, in the Python overlays;
  (d) whether the inputs or the anchor are right in the first place.

The concrete failure: the abnormal-earnings-growth form discounted the forecast path at
the per-year cost-of-equity term structure but capitalised every AEG term at a single
long-run rate. That is exact on a flat curve and wrong on any slope. Throughout, the tie
read ~1e-15 and audit_status read "PASS — all identities tie" while the headline was up to
22.6% wrong. The oracle was green and the number was not.

WHAT THIS FILE ASSERTS

A property, over a family of inputs, rather than a memorised number for one input:

    for ANY shape of the cost-of-equity curve,
        Valuation!B52  ==  DCF Reconciliation!B45

The real cost-of-equity term structure (Market Data row 26, named range finrate_coe) is
overwritten with flat, rising, steep, INVERTED and humped shapes, and the engine is
rebuilt and recalculated for each. The inverted case matters most: the sign of the old
error REVERSES between rising and inverted curves, so the defect could never have been
corrected with a constant factor — and the live Apple curve only rises, so no live fixture
could ever have exposed it.

Measured on the uncorrected engine, for the record:
    flat 6.95%              0.00%
    live-like 5.03->6.95   -7.22%
    steep 3.0->10.0       -22.59%
    inverted 9.0->5.0     +18.11%     <- sign reversal
    humped 5->9->6         +1.12%
The corrected engine returns 0.00% on all five.

This is slower than the unit suites (five full recalculations) so it is not part of
--quick. Run it whenever the Valuation tab's capitalisation machinery, the rate plumbing,
or the continuing-value convention is touched.

Run:  python3 test_curve_shapes.py            (uses ./MODEL_TEMPLATE.xlsx)
      python3 test_curve_shapes.py <template>
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
WORK = os.path.join(_ROOT, "_curvework")
PRICE = 315.0
COE_ROW = 26             # Market Data!$B$26:$AE$26 == finrate_coe (REAL cost of equity)
NT = 30
XTAB_TOL = 1e-9          # $/share
TIE_TOL = 1e-9


def ramp(a, b, knee=30):
    return [a + (b - a) * min(t, knee) / knee for t in range(1, NT + 1)]


CURVES = [
    ("flat 6.95%",            [0.0695] * NT),
    ("live-like 5.03->6.95",  ramp(0.0503, 0.0695)),
    ("steep 3.0->10.0",       ramp(0.030, 0.100)),
    ("INVERTED 9.0->5.0",     ramp(0.090, 0.050)),
    ("humped 5->9->6",        [0.05 + 0.04 * min(t, 10) / 10 - 0.03 * max(0, min(t - 10, 20)) / 20
                               for t in range(1, NT + 1)]),
]

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
    base = os.path.join(WORK, "curve_base.xlsx")
    AE.build_model(_cfg(), TEMPLATE, base)

    print("== curve-shape property: the AEG form must equal the RI form on ANY curve ==")
    for clab, curve in CURVES:
        p = os.path.join(WORK, f"curve_{clab.split()[0]}.xlsx")
        shutil.copy(base, p)
        wb = openpyxl.load_workbook(p)
        MD = wb["Market Data"]
        for i, v in enumerate(curve):
            MD.cell(COE_ROW, 2 + i).value = float(v)
        wb.save(p)
        recalc(p)
        r = AE.read_results(p, price=PRICE)
        d = openpyxl.load_workbook(p, data_only=True)
        head = d["Valuation"]["B52"].value
        ri = d["DCF Reconciliation"]["B45"].value
        tie = r.get("max_identity_tie")
        audit = r.get("audit_status")

        if not (isinstance(head, (int, float)) and isinstance(ri, (int, float))):
            check(False, f"{clab:<22} unreadable (head={head!r}, RI={ri!r})")
            continue
        gap = head - ri
        pct = 100 * gap / ri if ri else float("nan")
        check(abs(gap) < XTAB_TOL,
              f"{clab:<22} cross-tab gap {gap:+.2e} ({pct:+.4f}%)  "
              f"AEG {head:.9f} / RI {ri:.9f}")
        check(isinstance(tie, (int, float)) and abs(tie) < TIE_TOL,
              f"{clab:<22} four-method tie {tie:.1e}")
        check(bool(audit) and str(audit).startswith("PASS"),
              f"{clab:<22} audit {audit!r}")

    print()
    if _fails:
        print(f"{len(_fails)} CURVE-SHAPE CHECK(S) FAILED")
        return 1
    print("ALL CURVE-SHAPE CHECKS PASSED — the AEG and RI forms agree on flat, rising, "
          "steep, inverted and humped curves")
    return 0


if __name__ == "__main__":
    sys.exit(main())
