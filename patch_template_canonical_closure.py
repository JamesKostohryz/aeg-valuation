#!/usr/bin/env python3
"""patch_template_canonical_closure.py -- make the OPERATING closure canonical.

DECISION (James, 2026-08-10, signed off). The engine stops carrying two live forecast
closures. The operating closure becomes canonical: net operating assets and operating
income are driven, financing absorbs, and distributions are implied. The equity view
becomes PRESENTATION ONLY, via the existing Valuation READ toggle at Inputs!B34
(cfg_valread), which already computes both readings and carries an explicit agreement row.

WHY. The equity closure derives net operating assets as a residual of book equity
(NOA = CSE x (1 + FLEV)). Any equity transaction therefore moves operating assets: turning
share repurchases on collapsed Apple's net operating assets 43% in one forecast year and
broke the four-method tie at 1.98e+01 against a 1e-11 tolerance. It is a sound presentation
and an unsound forecasting closure -- in it, the income statement is forecast from revenue
and margins while the balance sheet that supposedly generates it is a financing residual,
so nothing requires the assets to be sufficient to produce the revenue. Full evidence in
AEG-Equity-Enterprise-RESOLUTION-2026-08-10.md.

WHAT THIS CHANGES. Inputs!B37 (cfg_mode, "Forecast-side") from "Equity" to "Enterprise".
Nine formula rows branch on it -- Forecast rows 20, 24, 25, 27, 29 and Valuation rows 7, 8,
10, 11 -- and all nine are already built for both sides. Nothing else in the workbook or the
Python pipeline sets it; no company YAML carries it; only apply_payload writes it, from the
submitted payload.

*** THIS MOVES VALUATION NUMBERS FOR EVERY COMPANY. IT IS NOT A NO-OP. ***
Under the operating closure, share repurchases become live and distributions become an
implied residual rather than a payout-ratio assumption. Every company must be re-run before
its number is quoted.

*** COMPANION REQUIREMENT ***
Because distributions are now implied, `payout_ratio` / `in_payout_seed` no longer sets
them in the canonical closure. Any forecast that expressed a distribution view through the
payout seed -- including PepsiCo Round 2's 0.84, defined as dividends plus net repurchases
-- must be re-expressed through the operating plan and financing structure. See the
two-of-three rule in the resolution document.

GATED, signed off 2026-08-10. Requires a green four-method tie and a full fleet re-run.

Idempotent. Run:  python3 patch_template_canonical_closure.py [path/to/MODEL_TEMPLATE.xlsx]
"""
import sys

import openpyxl

TEMPLATE = sys.argv[1] if len(sys.argv) > 1 else "MODEL_TEMPLATE.xlsx"
SHEET, CELL = "Inputs", "B37"
CANONICAL = "Enterprise"
EXPECT_OLD = "Equity"


def main():
    wb = openpyxl.load_workbook(TEMPLATE, data_only=False)
    if SHEET not in wb.sheetnames:
        sys.exit(f"FAIL: workbook has no '{SHEET}' tab")
    cur = wb[SHEET][CELL].value

    if cur == CANONICAL:
        print(f"[canonical-closure] already {CANONICAL!r} -- no change")
        return
    if cur != EXPECT_OLD:
        sys.exit(f"FAIL: {SHEET}!{CELL} is {cur!r}, expected {EXPECT_OLD!r} or "
                 f"{CANONICAL!r} -- refusing to write")

    wb[SHEET][CELL] = CANONICAL
    wb.save(TEMPLATE)
    print(f"[canonical-closure] {SHEET}!{CELL}: {cur!r} -> {CANONICAL!r}")
    print("[canonical-closure] the operating closure is now canonical; the equity view is "
          "presentation only (cfg_valread, Inputs!B34)")
    print("[canonical-closure] WARNING: moves valuation numbers -- re-run the whole fleet")
    print(f"[canonical-closure] wrote {TEMPLATE}")


if __name__ == "__main__":
    main()
