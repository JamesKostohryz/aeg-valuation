#!/usr/bin/env python3
"""loader_core.py — deterministic ingestion + auto-derivation for the AEG model.

This is the engine the Colab notebook drives. It is a hardened superset of the
hand-typed setup_company.py:

  * parse_statement / norm / NOSCALE  -> reused verbatim (same parsing & unit rules)
  * populate_raw_tabs                 -> same label-match + unit-convert + blue font,
                                         plus a fail-loud gate on missing critical lines
                                         and on ambiguous (duplicated) labels
  * derive_inputs                     -> NEW: replaces the hand-typed CFG["inputs"] block;
                                         every scalar is computed from the filed statements,
                                         each carrying its source line for the report
  * apply_judgments                   -> overlays the handful of genuine judgment calls
  * snapshot_layer / diff_guard       -> same permitted-cell diff-guard

Nothing here recalculates or audits — that is done by recalc_lo.recalc and audit.py,
which the notebook calls after this module has written the workbook.
"""
import csv, re, copy
import openpyxl

# --- unit / label rules (identical to setup_company.py) ---
NOSCALE = re.compile(r"\b(EPS|PER SHARE|RATE|MARGIN|RATIO|YIELD)\b|%", re.I)


def norm(lbl):
    return re.sub(r"\s+", " ", str(lbl).strip()).lower()


def detect_fy_end_month(path):
    """Read the statement header and return the fiscal-year-end month if the year
    columns are full dates (e.g. '09/30/2024' -> 9, '2024-09-28' -> 9). Returns
    None when the headers are bare years (e.g. '2024'), so the caller can default."""
    with open(path, newline="") as fh:
        header = next(csv.reader(fh))
    for cell in header[1:]:
        c = str(cell).strip()
        if "ttm" in c.lower():
            continue
        m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", c)
        if m:
            return int(m.group(1))
        m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", c)
        if m:
            return int(m.group(2))
    return None


def _parsed_fy0(parsed, key, *labels):
    """FY0 (latest-year) value of the first matching label in a parsed statement.
    Used for lines the model's reported tabs don't carry (e.g. R&D). Returns None
    if no label matches or the FY0 cell is blank."""
    if not parsed or key not in parsed:
        return None
    years, rows = parsed[key]
    if not years:
        return None
    idx = years.index(max(years))
    normed = {norm(k): v for k, v in rows.items()}
    for lbl in labels:
        series = normed.get(norm(lbl))
        if series is not None and idx < len(series) and series[idx] is not None:
            return series[idx]
    return None


def parse_statement(path):
    """Parse a Yahoo-format CSV: label in col 1, fiscal years across the top.
    Drops any 'ttm' column. Returns (years:list[int], rows:dict[label->list])."""
    with open(path, newline="") as fh:
        rd = csv.reader(fh)
        header = next(rd)
        raw_years = header[1:]
        keep = [i for i, y in enumerate(raw_years) if "ttm" not in y.lower()]
        years = [int(re.search(r"(\d{4})", raw_years[i]).group(1)) for i in keep]
        rows = {}
        seen_norm = {}
        for rec in rd:
            if not rec or not rec[0].strip():
                continue
            label = rec[0].strip()
            n = norm(label)
            if n in seen_norm and seen_norm[n] != label:
                raise ValueError(
                    f"ambiguous labels normalize identically: "
                    f"'{seen_norm[n]}' and '{label}' in {path}")
            if n in seen_norm and seen_norm[n] == label:
                raise ValueError(f"duplicate label '{label}' appears twice in {path}")
            seen_norm[n] = label
            vals = []
            for i in keep:
                x = rec[i + 1].strip().replace(",", "") if i + 1 < len(rec) else ""
                vals.append(float(x) if x not in ("", "-", "--", "N/A") else None)
            rows[label] = vals
    return years, rows


# --- tab layout ---
TAB_OF = {"is_csv": "Income Statement", "bs_csv": "Balance Sheet", "cf_csv": "Cash Flow"}

# Critical source lines: if a Yahoo CSV lacks any of these labels the model cannot
# be built correctly, so we abort loudly rather than silently blanking the row.
# (tab, exact model label).  Chosen because each feeds an anchor / reconciliation.
CRITICAL_LINES = [
    ("Income Statement", "Total Revenue"),
    ("Income Statement", "Cost of Revenue"),
    ("Income Statement", "Operating Income"),
    ("Income Statement", "Net Income Common Stockholders"),
    ("Income Statement", "Diluted EPS"),
    ("Income Statement", "Tax Rate for Calcs"),
    ("Income Statement", "Reconciled Depreciation"),
    ("Balance Sheet", "Total Assets"),
    ("Balance Sheet", "Cash And Cash Equivalents"),
    ("Balance Sheet", "Common Stock Equity"),
    ("Balance Sheet", "Ordinary Shares Number"),
    ("Balance Sheet", "Total Debt"),
    ("Balance Sheet", "Gross PPE"),
    ("Balance Sheet", "Net PPE"),
]


def _last_year_col(ws):
    for c in range(ws.max_column, 1, -1):
        if ws.cell(3, c).value is not None:
            return c
    return None


def populate_raw_tabs(wb, parsed):
    """Populate the three reported tabs from parsed CSVs.

    parsed: {"is_csv": (years, rows), "bs_csv": ..., "cf_csv": ...}
    Returns (permitted:set[(tab,coord)], match_report:dict, anchor_year:int).
    Raises ValueError (fail-loud) on missing critical line, ambiguous label,
    or mis-aligned fiscal years.
    """
    permitted = set()
    match_report = {}
    blue_font = copy.copy(wb["Income Statement"]["B4"].font)  # filed-input blue
    latest_years = {}

    for key, tab in TAB_OF.items():
        years, rows = parsed[key]
        ws = wb[tab]
        norm_csv = {}
        dup = set()
        for lbl, v in rows.items():
            k = norm(lbl)
            if k in norm_csv:
                dup.add(lbl)
            norm_csv[k] = v
        ncols = len(years)
        latest_years[tab] = years[-1]

        # ambiguity gate: a model row label that appears more than once in the CSV
        model_labels = [ws.cell(r, 1).value for r in range(4, ws.max_row + 1)
                        if ws.cell(r, 1).value is not None]
        ambiguous = sorted({lbl for lbl in model_labels if lbl in dup})
        if ambiguous:
            raise ValueError(
                f"[{tab}] ambiguous Yahoo labels (appear >once, cannot resolve): {ambiguous}")

        # year header row 3 -> STRINGS (model MATCHes against TEXT()); blank beyond span
        for j in range(41):  # cols B..AP
            cell = ws.cell(3, 2 + j)
            newv = str(years[j]) if j < ncols else None
            if cell.value != newv:
                cell.value = newv
                permitted.add((tab, cell.coordinate))

        matched = 0
        matched_norms = set()
        for r in range(4, ws.max_row + 1):
            lbl = ws.cell(r, 1).value
            if lbl is None:
                continue
            key_n = norm(lbl)
            scale = 1.0 if NOSCALE.search(str(lbl)) else 1e6
            series = norm_csv.get(key_n)
            for j in range(41):
                cell = ws.cell(r, 2 + j)
                newv = (round(series[j] / scale, 6)
                        if (series is not None and j < ncols and series[j] is not None)
                        else None)
                if cell.value != newv:
                    cell.value = newv
                    permitted.add((tab, cell.coordinate))
                    if newv is not None:
                        cell.font = copy.copy(blue_font)
            if series is not None:
                matched += 1
                matched_norms.add(key_n)
        match_report[tab] = {"matched": matched, "years": (years[0], years[-1]),
                             "n_years": ncols}

        # critical-line gate for this tab (compare on normalized labels)
        missing = [lbl for (t, lbl) in CRITICAL_LINES
                   if t == tab and norm(lbl) not in matched_norms]
        if missing:
            raise ValueError(
                f"[{tab}] missing critical line(s) not found in the CSV: {missing}")

    # --- derived fill: noncontrolling interest when the feed leaves it blank ---------
    # EODHD intermittently ships a blank 'Minority Interest' row (AT&T: 2008-09, 2023-25).
    # NCI then lands in neither CSE (excluded by the minority_include judgment) nor NFO
    # (design: MI+pension in NFO), so the per-year partition NOA-NFO-CSE breaks by exactly
    # the missing NCI. It is recoverable as the balance-sheet plug, and that plug
    # reproduces the reported NCI to the dollar in every year the feed does populate it.
    BSws = wb["Balance Sheet"]

    def _row_of(ws, label):
        for r in range(4, ws.max_row + 1):
            v = ws.cell(r, 1).value
            if v is not None and norm(v) == norm(label):
                return r
        return None

    r_mi = _row_of(BSws, "Minority Interest")
    r_ta = _row_of(BSws, "Total Assets")
    r_tl = _row_of(BSws, "Total Liabilities Net Minority Interest")
    r_te = _row_of(BSws, "Total Equity Gross Minority Interest")
    if all(x is not None for x in (r_mi, r_ta, r_tl, r_te)):
        filled = []
        for j in range(41):
            c_mi = BSws.cell(r_mi, 2 + j)
            # Fill when the feed leaves it blank, or files a hard 0 that does NOT close the
            # balance sheet (AT&T 2011: MI=0 filed, yet TA-(TL+TE)=263). A non-zero filed
            # value is always respected — we never override real reported NCI.
            if isinstance(c_mi.value, (int, float)) and c_mi.value != 0:
                continue
            ta = BSws.cell(r_ta, 2 + j).value
            tl = BSws.cell(r_tl, 2 + j).value
            te = BSws.cell(r_te, 2 + j).value
            if not all(isinstance(x, (int, float)) for x in (ta, tl, te)):
                continue                      # no full balance sheet that year -> leave blank
            plug = round(ta - (tl + te), 6)
            if abs(plug) < 1e-9:
                continue                      # genuinely zero NCI; leave blank as filed
            c_mi.value = plug
            c_mi.font = copy.copy(blue_font)
            permitted.add(("Balance Sheet", c_mi.coordinate))
            filled.append((BSws.cell(3, 2 + j).value, plug))
        if filled:
            print("  [loader] 'Minority Interest' blank in feed; derived as balance plug "
                  "TA-(TL+TE) for: " + ", ".join(f"{y}={v:,.0f}" for y, v in filled))

    # fiscal-year alignment gate: latest (FY0) year must agree across the three tabs
    yrs = set(latest_years.values())
    if len(yrs) != 1:
        raise ValueError(
            f"fiscal years do not align across statements (latest per tab): {latest_years}")
    anchor_year = latest_years["Income Statement"]
    return permitted, match_report, anchor_year


# --- Inputs auto-derivation --------------------------------------------------
# Each derived scalar carries (row, name, meaning, value, source, kind).
def _fy0(ws, label):
    """Return the FY0 (latest-year) value of a raw-tab row matched by label."""
    c = _last_year_col(ws)
    for r in range(4, ws.max_row + 1):
        if ws.cell(r, 1).value is not None and norm(ws.cell(r, 1).value) == norm(label):
            return ws.cell(r, c).value
    return None


def derive_inputs(wb, anchor_year, parsed=None):
    """Auto-derive every non-judgment Inputs scalar from the populated raw tabs.

    `parsed` (optional) is the {key:(years,rows)} dict from parse_statement; it is
    used to read lines the model's reported tabs don't carry (e.g. R&D, which the
    model keeps only as the Inputs scalar B45).

    Returns dict: row -> {"value","source","meaning","kind"} where kind is
    'auto' | 'derived' | 'judgment-default' (judgment rows are placeholders that
    apply_judgments will overwrite; they are surfaced with the filed number).
    """
    IS = wb["Income Statement"]; BS = wb["Balance Sheet"]; CF = wb["Cash Flow"]

    def g(ws, lbl):
        v = _fy0(ws, lbl)
        return v

    debt   = g(BS, "Total Debt")
    cash   = g(BS, "Cash And Cash Equivalents")
    sti    = g(BS, "Other Short Term Investments") or 0.0
    shares = g(BS, "Ordinary Shares Number")          # already /1e6 in the tab
    cse    = g(BS, "Common Stock Equity")
    mi     = g(BS, "Minority Interest") or 0.0
    intexp = g(IS, "Interest Expense") or 0.0
    oi     = g(IS, "Operating Income")
    unusual = g(IS, "Total Unusual Items")
    eps    = g(IS, "Diluted EPS")
    # R&D: the model keeps this only as an Inputs scalar (no reported-tab row), so
    # read it from the parsed CSV (raw dollars) and scale to $mm like the tabs do.
    rd_raw = _parsed_fy0(parsed, "is_csv", "Research And Development",
                         "Research & Development", "Research and Development")
    rd = round(rd_raw / 1e6, 6) if rd_raw is not None else 0.0

    # tax: prefer the filed effective-rate line ("Tax Rate for Calcs"); fall back
    # to provision / pretax.  Both are reported; we surface both for confirmation.
    tax_line = g(IS, "Tax Rate for Calcs")
    prov = g(IS, "Tax Provision"); pre = g(IS, "Pretax Income")
    tax_ratio = (prov / pre) if (prov is not None and pre not in (None, 0)) else None
    if tax_line is not None:
        tax = tax_line
        tax_src = f"IS 'Tax Rate for Calcs' = {tax_line}  (provision/pretax = {tax_ratio:.5f})" \
            if tax_ratio is not None else f"IS 'Tax Rate for Calcs' = {tax_line}"
    else:
        tax = tax_ratio
        tax_src = f"provision {prov} / pretax {pre} = {tax_ratio}"

    # dividends per share: use a filed per-share dividend line if present; else
    # derive from cash dividends paid (net of preferred) / shares.
    dps_line = None
    for cand in ("Dividends Per Share", "Common Stock Dividend Per Share",
                 "Trailing Dividend Rate", "Forward Dividend Rate"):
        v = g(IS, cand) or g(CF, cand)
        if v is not None:
            dps_line = v; dps_src = f"filed per-share line '{cand}' = {v}"; break
    if dps_line is not None:
        dps = dps_line
    else:
        divpaid = g(CF, "Common Stock Dividend Paid")
        if divpaid is None:
            divpaid = g(CF, "Cash Dividends Paid")
        pref = g(IS, "Preferred Stock Dividends") or 0.0
        if divpaid is not None and shares:
            dps = round((abs(divpaid) - abs(pref)) / shares, 6)
            dps_src = (f"|Cash Dividends Paid {divpaid}| - |Pref {pref}| / shares {shares} "
                       f"= {dps}  (no filed per-share line; CONFIRM)")
        else:
            dps = None
            dps_src = "no dividend data found"

    D = {}
    D[5]  = dict(name="in_debt",   meaning="Total debt incl. finance leases",
                 value=debt,   source="BS 'Total Debt'", kind="auto")
    D[6]  = dict(name="in_cash",   meaning="Cash & equivalents",
                 value=cash,   source="BS 'Cash And Cash Equivalents'", kind="auto")
    D[7]  = dict(name="in_sti",    meaning="Short-term investments",
                 value=sti,    source="BS 'Other Short Term Investments' (blank->0)", kind="auto")
    D[9]  = dict(name="anchor_shares0", meaning="Common shares outstanding (mm)",
                 value=shares, source="BS 'Ordinary Shares Number' (/1e6)", kind="auto")
    D[11] = dict(name="in_intexp0", meaning="Interest expense",
                 value=intexp, source="IS 'Interest Expense' (blank->0)", kind="auto")
    D[13] = dict(name="anchor_eps0", meaning="Diluted EPS",
                 value=eps,    source="IS 'Diluted EPS' (unscaled)", kind="auto")
    D[14] = dict(name="in_tax0",   meaning="Effective tax rate",
                 value=tax,    source=tax_src, kind="derived")
    D[15] = dict(name="anchor_dps0", meaning="Dividends per share (FY0)",
                 value=dps,    source=dps_src, kind="derived")
    D[45] = dict(name="in_rd_expense0", meaning="R&D expense (FY0)",
                 value=rd,     source="IS 'Research & Development' (blank->0)", kind="auto")
    D[66] = dict(name="in_anchor_year", meaning="Anchor / FY0 fiscal year",
                 value=anchor_year, source="latest full fiscal year in CSVs", kind="derived")

    # Judgment rows — surfaced WITH the filed number so the user confirms vs data.
    D[8]  = dict(name="in_finlease", meaning="Finance/capital-lease obligations",
                 value=None, kind="judgment",
                 source=f"filed BS 'Capital Lease Obligations' = {g(BS, 'Capital Lease Obligations')}"
                        f" (default 0 unless you include it)")
    D[10] = dict(name="anchor_cse0", meaning="Common stock equity (CSE)",
                 value=None, kind="judgment",
                 source=f"BS 'Common Stock Equity' = {cse}; 'Minority Interest' = {mi}"
                        f"  (Exclude MI -> {cse}; Include MI -> {(cse or 0)+mi})")
    D[12] = dict(name="in_oiadj0", meaning="Operating income, adjusted",
                 value=None, kind="judgment",
                 source=f"IS 'Operating Income' = {oi}; 'Total Unusual Items' = {unusual}"
                        f"  (default = Operating Income)")
    D[25] = dict(name="in_price", meaning="Current share price",
                 value=None, kind="judgment", source="today's market price (external)")
    D[43] = dict(name="in_rd_life", meaning="R&D amortization life (years)",
                 value=None, kind="judgment", source="0 = do not capitalize")

    # stash raw pieces the judgment layer needs
    D["_raw"] = dict(cse=cse, mi=mi, oi=oi, unusual=unusual, rd=rd)
    return D


def apply_judgments(derived, *, price, minority_include, finlease, oi_adj_override,
                    rd_capitalize, rd_life, dps_override=None):
    """Fold the judgment-form values into the derived dict, filling the value of
    every judgment row.  Returns the same dict (mutated).

    dps_override: None -> keep the auto-derived DPS; a number -> use it (e.g. the
    filed per-share dividend, which a standard Yahoo cash-flow export lacks)."""
    raw = derived["_raw"]
    cse = raw["cse"] or 0.0
    mi = raw["mi"] or 0.0
    derived[8]["value"] = float(finlease)
    derived[8]["kind"] = "judgment"
    derived[10]["value"] = (cse + mi) if minority_include else cse
    derived[10]["kind"] = "judgment"
    derived[10]["source"] += f"  -> chose {'Include' if minority_include else 'Exclude'}"
    # oi_adj_override: None/blank -> use filed Operating Income; else use the override
    derived[12]["value"] = raw["oi"] if oi_adj_override in (None, "") else float(oi_adj_override)
    derived[25]["value"] = float(price)
    derived[43]["value"] = float(rd_life) if rd_capitalize else 0.0
    if dps_override is not None:
        derived[15]["value"] = float(dps_override)
        derived[15]["kind"] = "judgment"
        derived[15]["source"] += f"  -> OVERRIDDEN to {float(dps_override)}"
    return derived


def write_inputs(wb, derived):
    """Write every derived/judgment scalar into the Inputs tab. Returns permitted set."""
    inp = wb["Inputs"]
    permitted = set()
    for row, d in derived.items():
        if not isinstance(row, int):
            continue
        v = d["value"]
        if v is None:
            continue
        cell = inp.cell(row, 2)
        if cell.value != v:
            cell.value = v
            permitted.add(("Inputs", cell.coordinate))
    return permitted


# --- diff-guard --------------------------------------------------------------
def snapshot_layer(path):
    wb = openpyxl.load_workbook(path, data_only=False)
    snap = {}
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if c.value is not None:
                    snap[(ws.title, c.coordinate)] = c.value
    return snap


def diff_guard(before, after, permitted):
    """Return (changed, illegal). illegal must be empty or the caller must revert."""
    changed = [k for k in set(before) | set(after) if before.get(k) != after.get(k)]
    illegal = [k for k in changed if k not in permitted]
    return changed, illegal
