#!/usr/bin/env python3
"""diagnose_T_tie.py — pinpoint which identity breaks the AT&T (T) build and why.
Run AFTER a build+recalc, against the built engine workbook (pipeline/_work/T_engine.xlsx)."""
import sys, openpyxl

path = sys.argv[1] if len(sys.argv) > 1 else "T_engine.xlsx"
wb = openpyxl.load_workbook(path, data_only=True)
A = wb["Audit"]

def nm(name):
    dn = wb.defined_names.get(name)
    if not dn:
        return None
    try:
        ref = str(dn.value).replace("$", "").replace("'", "")
        sh, cell = ref.split("!")
        if ":" in cell:
            tot = 0.0
            for row in wb[sh][cell]:
                for c in row:
                    if isinstance(c.value, (int, float)):
                        tot += abs(c.value)
            return tot
        return wb[sh][cell].value
    except Exception as e:
        return f"<err {e}>"

def cell(coord):
    return A[coord].value

print("="*72)
print("AT&T identity diagnosis —", path)
print("="*72)
print(f"Audit status B6 = {cell('B6')!r}   (B5 max = {cell('B5')}, tol in_tie_tol = {nm('in_tie_tol')})")

TARGET = 51021.0
def flag(v):
    try:
        return "   <<== ~51,021 (THE CULPRIT)" if abs(abs(float(v)) - TARGET) <= max(50.0, 0.02*TARGET) else ""
    except (TypeError, ValueError):
        return ""

groups = [
    ("BASE TIES  B22:B25", [
        (22, "NOA = CSE + NFO           (in_noa0 - anchor_cse0 - anchor_nfo0)"),
        (23, "FLEV*CSE = NFO"),
        (24, "BPS*shares = CSE"),
        (25, "NFO/sh*shares = NFO"),
    ]),
    ("RECONCILIATION  B35:B42 (chosen input vs reported)", [
        (35, "in_debt - rep_debt"), (36, "in_cash - rep_cash"),
        (37, "anchor_cse0 - rep_cse   <-- minority/equity mis-pick shows HERE"),
        (38, "shares - rep_shares"), (39, "eps - rep_eps"),
        (40, "intexp - rep_intexp"), (41, "oiadj - rep_oi"), (42, "tax - rep_tax"),
    ]),
    ("REFORMULATION TIES  B47:B49", [
        (47, "S|partition tie NOA-NFO-CSE (nominal)|"),
        (48, "S|real tie NOA-NFO-CSE|"),
        (49, "Cap Engine anchor vs per-year"),
    ]),
    ("FORECAST TIES  B55:B57", [
        (55, "S|NOA-NFO-CSE|"), (56, "S|EPS*sh - NI|"), (57, "S|FCFE - distribution|"),
    ]),
    ("DCF RECON  B61:B62", [(61, "V(FCFE)-V(RI)"), (62, "Equity(FCFF)-V(RI)")]),
]
for title, rows in groups:
    print(f"\n-- {title}")
    for r, lbl in rows:
        v = cell(f"B{r}")
        vs = f"{v:,.1f}" if isinstance(v, (int, float)) else str(v)
        print(f"   B{r}: {vs:>16}   {lbl}{flag(v)}")

print("\n-- ANCHOR / INPUT VALUES (engine units = $millions)")
for n in ["in_noa0","anchor_cse0","anchor_nfo0","in_debt","in_cash","in_sti","in_finlease",
          "rep_cse_fy0","rep_debt_fy0","rep_cash_fy0","in_flev0","in_bps0","anchor_shares0",
          "in_oiadj0","rep_oi_fy0","in_anchor_year"]:
    v = nm(n)
    vs = f"{v:,.3f}" if isinstance(v, (int, float)) else str(v)
    print(f"   {n:18} = {vs}")

cse = nm("anchor_cse0"); rep = nm("rep_cse_fy0"); noa = nm("in_noa0"); nfo = nm("anchor_nfo0")
print("\n-- AUTO-DIAGNOSIS")
if isinstance(cse,(int,float)) and isinstance(rep,(int,float)):
    d = cse - rep
    print(f"   anchor_cse0 - rep_cse_fy0 = {d:,.1f}  ({'MATCH' if abs(d)<1 else 'MISMATCH — CSE is not the reported equity'})")
if all(isinstance(x,(int,float)) for x in (noa,cse,nfo)):
    print(f"   in_noa0 - anchor_cse0 - anchor_nfo0 = {noa-cse-nfo:,.1f}  (should be ~0)")
print("   -> the flagged residual names the broken identity; compare anchor_cse0 vs rep_cse_fy0")
print("      and in_finlease to map it to a T.yaml knob.")
