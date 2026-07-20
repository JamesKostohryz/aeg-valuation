#!/usr/bin/env python3
"""test_cost_boundary.py — the boundary-invariance test for the operating-cost decomposition.

Guards the AT&T "wedge" fix: the forecast opex decomposition (and the row-61 wedge, and the
valuation) must NOT depend on where the feed draws the Cost-of-Revenue / Operating-Expense
boundary. Self-contained (synthetic statements; no EODHD needed) so CI can't regress it.
"""
import sys, openpyxl
import loader_core as LC

_p = _f = 0
def ok(c, m):
    global _p, _f
    print(("  PASS " if c else "  FAIL ") + m); _f += 0 if c else 1; _p += 1 if c else 0

R_REV, R_COGS, R_SGA, R_OI, R_DA, R_YR = 4, 6, 9, 13, 54, 3
LBL = {R_REV: "Total Revenue", R_COGS: "Cost of Revenue", R_SGA: "SG&A",
       R_OI: "Operating Income", R_DA: "Reconciled Depreciation"}


def make_wb(rows_by_year):
    """rows_by_year: {year: {'rev','cogs','sga','oi','da'}}. Returns an IS-only workbook."""
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Income Statement"
    years = sorted(rows_by_year)
    for c, y in enumerate(years, 2):
        ws.cell(R_YR, c).value = str(y)
    for r, key in ((R_REV, "rev"), (R_COGS, "cogs"), (R_SGA, "sga"), (R_OI, "oi"), (R_DA, "da")):
        ws.cell(r, 1).value = LBL[r]
        for c, y in enumerate(years, 2):
            ws.cell(r, c).value = rows_by_year[y].get(key)
    return wb, ws


def wedge_core(ws):
    """(GP - SGA - D&A) - OI per year — the row-61 wedge before economic adjustments."""
    out = {}
    for c in range(2, ws.max_column + 1):
        y = ws.cell(R_YR, c).value
        v = {r: ws.cell(r, c).value for r in (R_REV, R_COGS, R_SGA, R_OI, R_DA)}
        if None in (v[R_REV], v[R_OI], v[R_DA]):
            continue
        gp = v[R_REV] - (v[R_COGS] or 0)
        out[y] = (gp - (v[R_SGA] or 0) - v[R_DA]) - v[R_OI]
    return out


# --- AT&T-like (REAL EODHD values): stable Revenue/OI/D&A, FABRICATED COGS/OpEx boundary.
#     Multiple reclassification years (2021, 2023, 2025) on a stable 2019-20 baseline — so a
#     single-year boundary move cannot make the recent window look clean.
att = {2019: dict(rev=181193, cogs=113900, sga=39422, oi=27955, da=28217),
       2020: dict(rev=171760, cogs=108436, sga=38039, oi=25717, da=28516),
       2021: dict(rev=134038, cogs=60407, sga=37944, oi=25897, da=33868),
       2022: dict(rev=120741, cogs=50848, sga=28961, oi=-4587, da=18021),
       2023: dict(rev=122428, cogs=68900, sga=28874, oi=24768, da=18777),
       2024: dict(rev=122336, cogs=69801, sga=28411, oi=24261, da=20580),
       2025: dict(rev=125648, cogs=25424, sga=28942, oi=24162, da=20886)}  # COGS collapses
# --- AAPL-like: genuine, stable gross margin
aapl = {2021: dict(rev=365817, cogs=212981, sga=21973, oi=108949, da=11284),
        2022: dict(rev=394328, cogs=223546, sga=25094, oi=119437, da=11104),
        2023: dict(rev=383285, cogs=214137, sga=24932, oi=114301, da=11519),
        2024: dict(rev=391035, cogs=210352, sga=26097, oi=123216, da=11445),
        2025: dict(rev=416161, cogs=220800, sga=26200, oi=133050, da=12100)}

print("== AT&T-like: fabricated boundary is detected and the wedge collapses ==")
wb, ws = make_wb(att)
pre = wedge_core(ws)
ok(max(abs(w) for w in pre.values()) > 1000, f"pre-fix wedge is large (worst {max(abs(w) for w in pre.values()):.0f})")
rep = LC.stabilize_cost_boundary(wb)
ok(rep["reconstructed"], f"detector fires (recent gross-margin swing {rep['max_gpm_swing']})")
post = wedge_core(ws)
ok(max(abs(w) for w in post.values()) < 1e-6, f"post-fix wedge ~0 every year (worst {max(abs(w) for w in post.values()):.1e})")

print("== BOUNDARY-INVARIANCE (the key test): move $45B COGS<->OpEx, value spine unchanged ==")
wb2, ws2 = make_wb(att)
ws2.cell(R_COGS, ws2.max_column).value += 45000     # shove $45B into latest Cost of Revenue
LC.stabilize_cost_boundary(wb2)
cogs_a = [ws.cell(R_COGS, c).value for c in range(2, ws.max_column + 1)]
cogs_b = [ws2.cell(R_COGS, c).value for c in range(2, ws2.max_column + 1)]
ok(max(abs(a - b) for a, b in zip(cogs_a, cogs_b)) < 1e-6,
   "reconstructed COGS identical after the $45B boundary move (INVARIANT)")
ok(max(abs(w) for w in wedge_core(ws2).values()) < 1e-6, "wedge still ~0 after the move")

print("== AAPL-like: genuine stable margin is left EXACTLY as filed ==")
wb3, ws3 = make_wb(aapl)
cogs_before = [ws3.cell(R_COGS, c).value for c in range(2, ws3.max_column + 1)]
rep3 = LC.stabilize_cost_boundary(wb3)
cogs_after = [ws3.cell(R_COGS, c).value for c in range(2, ws3.max_column + 1)]
ok(not rep3["reconstructed"], f"detector does NOT fire (recent swing {rep3['max_gpm_swing']})")
ok(cogs_before == cogs_after, "COGS untouched (preserved exactly)")

print(f"\n{_p} passed, {_f} failed")
sys.exit(1 if _f else 0)
