#!/usr/bin/env python3
"""
AEG data puller — EODHD (+ SEC EDGAR pension) -> loader-ready CSVs.

Produces, per ticker, the six files the AEG Colab loader ingests:
  <T>_income.csv, <T>_balance.csv, <T>_cashflow.csv   (statements; NO Date header)
  <T>_prices.csv       (Date,Open,High,Low,Close,Adj Close,Volume)
  <T>_dividends.csv     (Date,Dividends)
  <T>_splits.csv        (Date,Stock Splits  -- header only / empty; closes are unadjusted)
Plus <T>_FULL_EODHD.xlsx with everything EODHD returns, for analysis.

Format rules are per INPUT_CONTRACT.md:
  * statements: col1 = label, then one column per fiscal year, OLD->NEW ascending
    (rightmost = FY0), header = period-end date; raw ACTUAL DOLLARS (loader /1e6);
    shares = raw count; EPS/rates unscaled.
  * signs: IS expenses positive; CF capex/dividends/repurchase NEGATIVE.
  * pension row label EXACT: 'Non Current Pension And Other Post-Retirement Benefit Plans'
  * CF capped to last 37 yrs, IS/BS to last 41, all sharing the same FY0 year.
"""

import csv, io, json, re

# ------------------------------------------------------------------ mappings
# model label -> EODHD Income_Statement field (or ('CALC', how))
INCOME_MAP = [
    ("Total Revenue",                       "totalRevenue"),
    ("Cost of Revenue",                     "costOfRevenue"),
    ("Gross Profit",                        "grossProfit"),
    ("Selling General and Administrative",  "sellingGeneralAdministrative"),
    ("Research & Development",              "researchDevelopment"),
    ("Operating Income",                    "operatingIncome"),
    ("Interest Expense",                    "interestExpense"),
    ("Pretax Income",                       "incomeBeforeTax"),
    ("Tax Provision",                       "incomeTaxExpense"),
    ("Net Income Common Stockholders",      "netIncomeApplicableToCommonShares"),
    ("Reconciled Depreciation",            "reconciledDepreciation"),
    ("EBITDA",                              "ebitda"),
    ("Tax Rate for Calcs",                 ("CALC", "taxrate")),   # incomeTaxExpense/incomeBeforeTax
    ("Diluted EPS",                         ("CALC", "eps")),      # NI common / shares (approx)
]
INCOME_POSITIVE = {"Cost of Revenue", "Selling General and Administrative",
                   "Research & Development", "Interest Expense"}

# model label -> EODHD Balance_Sheet field
BALANCE_MAP = [
    ("Total Assets",                        "totalAssets"),
    ("Cash And Cash Equivalents",           "cashAndEquivalents"),
    ("Other Short Term Investments",        "shortTermInvestments"),
    ("Net PPE",                             "propertyPlantAndEquipmentNet"),
    ("Gross PPE",                           "propertyPlantAndEquipmentGross"),
    ("Common Stock Equity",                 ["totalStockholderEquity", "commonStockTotalEquity"]),
    ("Minority Interest",                   "noncontrollingInterestInConsolidatedEntity"),
    ("Ordinary Shares Number",              "commonStockSharesOutstanding"),   # raw count
    ("Total Debt",                          "shortLongTermDebtTotal"),
    ("Total Liabilities Net Minority Interest", "totalLiab"),
    ("Retained Earnings",                   "retainedEarnings"),
    ("Gains Losses Not Affecting Retained Earnings", "accumulatedOtherComprehensiveIncome"),
    # pension row is injected from EDGAR (see build_balance)
]

# model label -> EODHD Cash_Flow field
CASHFLOW_MAP = [
    ("Operating Cash Flow",                 "totalCashFromOperatingActivities"),
    ("Investing Cash Flow",                 "totalCashflowsFromInvestingActivities"),
    ("Financing Cash Flow",                 "totalCashFromFinancingActivities"),
    ("Capital Expenditure",                 "capitalExpenditures"),        # force negative
    ("Common Stock Dividend Paid",          "dividendsPaid"),              # force negative
    ("Repurchase of Capital Stock",         "salePurchaseOfStock"),        # net-issuance proxy, negative
    ("Free Cash Flow",                      "freeCashFlow"),
]
CASHFLOW_NEGATIVE = {"Capital Expenditure", "Common Stock Dividend Paid",
                     "Repurchase of Capital Stock"}

PENSION_LABEL = "Non Current Pension And Other Post-Retirement Benefit Plans"
EDGAR_PENSION_TAGS = [
    "PensionAndOtherPostretirementDefinedBenefitPlansLiabilitiesNoncurrent",
    "DefinedBenefitPensionPlanLiabilitiesNoncurrent",
    "OtherPostretirementDefinedBenefitPlanLiabilitiesNoncurrent",
]

IS_MAX_YEARS, BS_MAX_YEARS, CF_MAX_YEARS = 41, 41, 37


# ---- full-feed DISPLAY rows (readability; NOT consumed by the engine; native sign) ----
DISPLAY_INCOME = [
    ("Operating Revenue", "totalRevenue"),
    ("Operating Expense", "totalOperatingExpenses"),
    ("Other Operating Expenses", "otherOperatingExpenses"),
    ("Net Non Operating Interest Income Expense", "netInterestIncome"),
    ("Interest Income Non Operating", "interestIncome"),
    ("Interest Expense Non Operating", "interestExpense"),
    ("Other Income Expense", "totalOtherIncomeExpenseNet"),
    ("Special Income Charges", "nonRecurring"),
    ("Other Special Charges", "otherItems"),
    ("Other Non Operating Income Expenses", "nonOperatingIncomeNetOther"),
    ("Net Income", "netIncome"),
    ("Net Income Including Non-Controlling Interests", "netIncome"),
    ("Net Income Continuous Operations", "netIncomeFromContinuingOps"),
    ("Net Income Discontinuous Operations", "discontinuedOperations"),
    ("Otherunder Preferred Stock Dividend", "preferredStockAndOtherAdjustments"),
    ("Total Operating Income as Reported", "operatingIncome"),
    ("Total Expenses", "totalOperatingExpenses"),
    ("Net Income from Continuing & Discontinued Operation", "netIncome"),
    ("Interest Income", "interestIncome"),
    ("Net Interest Income", "netInterestIncome"),
    ("EBIT", "ebit"),
    ("Reconciled Cost of Revenue", "costOfRevenue"),
    ("Net Income from Continuing Operation Net Minority Interest", "netIncomeFromContinuingOps"),
]
DISPLAY_BALANCE = [
    ("Current Assets", "totalCurrentAssets"),
    ("Cash, Cash Equivalents & Short Term Investments", "cashAndShortTermInvestments"),
    ("Cash", "cash"),
    ("Receivables", "netReceivables"),
    ("Accounts receivable", "netReceivables"),
    ("Inventory", "inventory"),
    ("Other Current Assets", "otherCurrentAssets"),
    ("Total non-current assets", "nonCurrentAssetsTotal"),
    ("Accumulated Depreciation", "accumulatedDepreciation"),
    ("Goodwill", "goodWill"),
    ("Other Intangible Assets", "intangibleAssets"),
    ("Investments And Advances", "longTermInvestments"),
    ("Other Non Current Assets", "nonCurrrentAssetsOther"),
    ("Current Liabilities", "totalCurrentLiabilities"),
    ("Current Debt And Capital Lease Obligation", "shortTermDebt"),
    ("Current Debt", "shortTermDebt"),
    ("Current Capital Lease Obligation", "capitalLeaseObligations"),
    ("Other Current Liabilities", "otherCurrentLiab"),
    ("Total Non Current Liabilities Net Minority Interest", "nonCurrentLiabilitiesTotal"),
    ("Long Term Debt And Capital Lease Obligation", "longTermDebtTotal"),
    ("Long Term Debt", "longTermDebt"),
    ("Long Term Capital Lease Obligation", "capitalLeaseObligations"),
    ("Non Current Deferred Liabilities", "deferredLongTermLiab"),
    ("Other Non Current Liabilities", "nonCurrentLiabilitiesOther"),
    ("Total Equity Gross Minority Interest", "totalStockholderEquity"),
    ("Stockholders' Equity", "totalStockholderEquity"),
    ("Capital Stock", "capitalStock"),
    ("Preferred Stock", "preferredStockTotalEquity"),
    ("Common Stock", "commonStock"),
    ("Additional Paid in Capital", "additionalPaidInCapital"),
    ("Other Equity Adjustments", "otherStockholderEquity"),
    ("Capital Lease Obligations", "capitalLeaseObligations"),
    ("Net Tangible Assets", "netTangibleAssets"),
    ("Invested Capital", "netInvestedCapital"),
    ("Tangible Book Value", "netTangibleAssets"),
    ("Net Debt", "netDebt"),
    ("Share Issued", "commonStockSharesOutstanding"),
]
DISPLAY_CASHFLOW = [
    ("Cash Flow from Continuing Operating Activities", "totalCashFromOperatingActivities"),
    ("Net Income from Continuing Operations", "netIncome"),
    ("Depreciation Amortization Depletion", "depreciation"),
    ("Depreciation & amortization", "depreciation"),
    ("Other non-cash items", "otherNonCashItems"),
    ("Change in working capital", "changeInWorkingCapital"),
    ("Change in Receivables", "changeToAccountReceivables"),
    ("Changes in Account Receivables", "changeToAccountReceivables"),
    ("Change in Inventory", "changeToInventory"),
    ("Change in Payables And Accrued Expense", "changeToLiabilities"),
    ("Change in Other Current Liabilities", "changeToLiabilities"),
    ("Cash Flow from Continuing Investing Activities", "totalCashFlowsFromInvestingActivities"),
    ("Net PPE Purchase And Sale", "capitalExpenditures"),
    ("Purchase of PPE", "capitalExpenditures"),
    ("Net Investment Purchase And Sale", "investments"),
    ("Net Other Investing Changes", "otherCashflowsFromInvestingActivities"),
    ("Cash Flow from Continuing Financing Activities", "totalCashFromFinancingActivities"),
    ("Net Issuance Payments of Debt", "netBorrowings"),
    ("Net Common Stock Issuance", "salePurchaseOfStock"),
    ("Common Stock Issuance", "issuanceOfCapitalStock"),
    ("Cash Dividends Paid", "dividendsPaid"),
    ("Net Other Financing Charges", "otherCashflowsFromFinancingActivities"),
    ("End Cash Position", "endPeriodCashFlow"),
    ("Changes in Cash", "changeInCash"),
    ("Beginning Cash Position", "beginPeriodCashFlow"),
    ("Issuance of Capital Stock", "issuanceOfCapitalStock"),
    ("Issuance of Debt", "netBorrowings"),
]

# ------------------------------------------------------------------ helpers
def _num(v):
    if v in (None, "", "None", "null"):
        return None
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None

def _year(datestr):
    m = re.match(r"\s*(\d{4})", str(datestr))
    return int(m.group(1)) if m else None

def _yearly(fund, statement):
    node = (((fund or {}).get("Financials") or {}).get(statement) or {}).get("yearly") or {}
    # dict keyed by date string -> {field: value}
    rows = []
    for datestr, obj in node.items():
        y = _year(obj.get("date", datestr))
        if y is not None:
            rows.append((y, str(obj.get("date", datestr))[:10], obj))
    # de-dup by year, keep latest date
    best = {}
    for y, d, obj in rows:
        if y not in best or d > best[y][0]:
            best[y] = (d, obj)
    return best  # {year:int -> (date_str, obj)}


def _fy0(*year_dicts):
    maxes = [max(d) for d in year_dicts if d]
    return min(maxes) if maxes else None


def build_statement(year_dict, mapping, fy0, cap, positive=None, negative=None,
                    calc_ctx=None, extra_rows=None):
    """Return (header_row, data_rows) for one statement CSV."""
    positive = positive or set()
    negative = negative or set()
    years = sorted(y for y in year_dict if y <= fy0)[-cap:]
    headers = ["name"] + [year_dict[y][0] for y in years]        # full period-end dates
    rows = []
    seen = set()
    for label, src in mapping:
        key = label.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        vals = []
        for y in years:
            obj = year_dict[y][1]
            if isinstance(src, tuple) and src and src[0] == "CALC":
                v = _calc(src[1], obj, calc_ctx, y)
            elif isinstance(src, list):            # fallback chain: first non-empty wins
                v = None
                for cand in src:
                    v = _num(obj.get(cand))
                    if v is not None:
                        break
            else:
                v = _num(obj.get(src))
            if v is not None:
                if label in positive:
                    v = abs(v)
                elif label in negative:
                    v = -abs(v)
            vals.append("" if v is None else _fmt(v, label))
        rows.append([label] + vals)
    if extra_rows:
        for label, series in extra_rows.items():   # {label: {year: value}}
            key = label.strip().lower()
            if key in seen:
                continue
            seen.add(key)
            rows.append([label] + ["" if series.get(y) is None else _fmt(series[y], label)
                                   for y in years])
    return headers, rows, years


NOSCALE = re.compile(r"\b(EPS|PER SHARE|RATE|MARGIN|RATIO|YIELD)\b|%", re.I)
def _fmt(v, label):
    # integers stay integers (raw dollars / share counts); rates/eps keep decimals
    if NOSCALE.search(label):
        return repr(round(v, 6))
    return repr(int(round(v)))

def _calc(kind, obj, ctx, year):
    if kind == "taxrate":
        pre = _num(obj.get("incomeBeforeTax")); tax = _num(obj.get("incomeTaxExpense"))
        if pre and pre > 0 and tax is not None:
            return tax / pre
        return None
    if kind == "eps":
        # Diluted EPS denominator = WEIGHTED-AVERAGE DILUTED shares (ASC 260 / IAS 33),
        # NOT period-end. Prefer a reported/weighted-avg field if EODHD exposes one;
        # only fall back to period-end shares (flagged) when nothing better exists.
        ni = _num(obj.get("netIncomeApplicableToCommonShares")) or _num(obj.get("netIncome"))
        wavg = (_num(obj.get("weightedAverageShsOutDil"))
                or _num(obj.get("weightedAverageSharesDiluted"))
                or _num(obj.get("weightedAverageShsOut"))
                or _num(obj.get("weightedAverageSharesOutstanding")))
        reported = _num(obj.get("epsdiluted")) or _num(obj.get("dilutedEPS"))
        if reported is not None:
            return reported
        if ni is not None and wavg:
            return ni / wavg
        sh = (ctx or {}).get("shares", {}).get(year)          # period-end fallback (flagged)
        if ni is not None and sh:
            (ctx or {}).setdefault("_eps_fallback", []).append(year)
            return ni / sh
        return None
    return None


# ------------------------------------------------------------------ builders
def build_income(fund):
    inc = _yearly(fund, "Income_Statement")
    bal = _yearly(fund, "Balance_Sheet")
    cf  = _yearly(fund, "Cash_Flow")
    fy0 = _fy0(inc, bal, cf)
    shares = {y: _num(o[1].get("commonStockSharesOutstanding")) for y, o in bal.items()}
    h, r, yrs = build_statement(inc, INCOME_MAP + DISPLAY_INCOME, fy0, IS_MAX_YEARS,
                                positive=INCOME_POSITIVE, calc_ctx={"shares": shares})
    return h, r, fy0

def build_balance(fund, pension_by_year):
    bal = _yearly(fund, "Balance_Sheet")
    inc = _yearly(fund, "Income_Statement")
    cf  = _yearly(fund, "Cash_Flow")
    fy0 = _fy0(inc, bal, cf)
    extra = {PENSION_LABEL: {y: pension_by_year.get(y) for y in bal}} if pension_by_year else \
            {PENSION_LABEL: {}}   # keep the row present, blank
    h, r, yrs = build_statement(bal, BALANCE_MAP + DISPLAY_BALANCE, fy0, BS_MAX_YEARS, extra_rows=extra)
    return h, r, fy0

def build_cashflow(fund):
    bal = _yearly(fund, "Balance_Sheet")
    inc = _yearly(fund, "Income_Statement")
    cf  = _yearly(fund, "Cash_Flow")
    fy0 = _fy0(inc, bal, cf)
    h, r, yrs = build_statement(cf, CASHFLOW_MAP + DISPLAY_CASHFLOW, fy0, CF_MAX_YEARS,
                                negative=CASHFLOW_NEGATIVE)
    return h, r, fy0


def csv_text(header, rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    for row in rows:
        w.writerow(row)
    return buf.getvalue()


def build_prices_csv(eod_list):
    """eod_list: list of {date,open,high,low,close,adjusted_close,volume}. Unadjusted close."""
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"])
    for d in eod_list:
        w.writerow([d.get("date"), d.get("open"), d.get("high"), d.get("low"),
                    d.get("close"), d.get("adjusted_close"), d.get("volume")])
    return buf.getvalue()

def build_dividends_csv(div_list):
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["Date", "Dividends"])
    for d in div_list:
        amt = d.get("unadjustedValue")
        if amt in (None, ""):
            amt = d.get("value")
        w.writerow([d.get("date"), amt])
    return buf.getvalue()

def build_empty_splits_csv():
    return "Date,Stock Splits\r\n"


# ------------------------------------------------------------------ EDGAR
def pension_from_edgar(companyfacts):
    """companyfacts: dict from data.sec.gov/api/xbrl/companyfacts. Return {fy_year:int -> value}."""
    facts = (companyfacts or {}).get("facts", {}).get("us-gaap", {})
    for tag in EDGAR_PENSION_TAGS:
        node = facts.get(tag)
        if not node:
            continue
        usd = (node.get("units") or {}).get("USD") or []
        out = {}
        for e in usd:
            if e.get("form", "").startswith("10-K") and e.get("end"):
                y = _year(e["end"])
                # keep the latest-filed value per fiscal year end
                if y is not None:
                    out[y] = float(e["val"])
        if out:
            return out
    return {}


# ------------------------------------------------------------------ self-test
if __name__ == "__main__":
    # synthetic EODHD-shaped payload: 2 fiscal years
    fund = {"Financials": {
        "Income_Statement": {"yearly": {
            "2023-12-31": {"date": "2023-12-31", "totalRevenue": "300000000000",
                "costOfRevenue": "120000000000", "grossProfit":"180000000000",
                "sellingGeneralAdministrative": "30000000000",
                "researchDevelopment": "40000000000", "operatingIncome": "90000000000",
                "interestExpense": "1000000000", "incomeBeforeTax": "95000000000",
                "incomeTaxExpense": "15000000000",
                "netIncomeApplicableToCommonShares": "76000000000",
                "reconciledDepreciation": "12000000000", "ebitda": "102000000000"},
            "2024-12-31": {"date": "2024-12-31", "totalRevenue": "350000000000",
                "costOfRevenue": "140000000000", "grossProfit":"210000000000",
                "sellingGeneralAdministrative": "34000000000",
                "researchDevelopment": "45000000000", "operatingIncome": "110000000000",
                "interestExpense": "1200000000", "incomeBeforeTax": "119000000000",
                "incomeTaxExpense": "19000000000",
                "netIncomeApplicableToCommonShares": "100000000000",
                "reconciledDepreciation": "15000000000", "ebitda": "135000000000"}}},
        "Balance_Sheet": {"yearly": {
            "2023-12-31": {"date": "2023-12-31", "totalAssets": "402000000000",
                "cashAndEquivalents": "24000000000", "shortTermInvestments": "86000000000",
                "propertyPlantAndEquipmentNet": "148000000000",
                "propertyPlantAndEquipmentGross": "215000000000",
                "commonStockTotalEquity": "283000000000",
                "noncontrollingInterestInConsolidatedEntity": "0",
                "commonStockSharesOutstanding": "12460000000",
                "shortLongTermDebtTotal": "27000000000", "totalLiab": "119000000000",
                "retainedEarnings": "211000000000",
                "accumulatedOtherComprehensiveIncome": "-4400000000"},
            "2024-12-31": {"date": "2024-12-31", "totalAssets": "450000000000",
                "cashAndEquivalents": "23000000000", "shortTermInvestments": "72000000000",
                "propertyPlantAndEquipmentNet": "184000000000",
                "propertyPlantAndEquipmentGross": "264000000000",
                "commonStockTotalEquity": "325000000000",
                "noncontrollingInterestInConsolidatedEntity": "0",
                "commonStockSharesOutstanding": "12211000000",
                "shortLongTermDebtTotal": "22000000000", "totalLiab": "125000000000",
                "retainedEarnings": "245000000000",
                "accumulatedOtherComprehensiveIncome": "-4800000000"}}},
        "Cash_Flow": {"yearly": {
            "2023-12-31": {"date": "2023-12-31", "totalCashFromOperatingActivities":"101000000000",
                "depreciation":"12000000000", "totalCashFlowsFromInvestingActivities":"-27000000000",
                "totalCashFromFinancingActivities":"-72000000000",
                "capitalExpenditures":"-32000000000", "dividendsPaid":"0",
                "salePurchaseOfStock":"-61000000000", "freeCashFlow":"69000000000"},
            "2024-12-31": {"date": "2024-12-31", "totalCashFromOperatingActivities":"125000000000",
                "depreciation":"15000000000", "totalCashFlowsFromInvestingActivities":"-45000000000",
                "totalCashFromFinancingActivities":"-79000000000",
                "capitalExpenditures":"-52000000000", "dividendsPaid":"-7363000000",
                "salePurchaseOfStock":"-62000000000", "freeCashFlow":"72000000000"}}},
    }}
    edgar = {"facts": {"us-gaap": {
        "PensionAndOtherPostretirementDefinedBenefitPlansLiabilitiesNoncurrent": {
            "units": {"USD": [
                {"form": "10-K", "end": "2023-12-31", "val": 8000000000},
                {"form": "10-K", "end": "2024-12-31", "val": 8478000000}]}}}}}

    pen = pension_from_edgar(edgar)
    ih, ir, ify = build_income(fund)
    bh, br, bfy = build_balance(fund, pen)
    ch, cr, cfy = build_cashflow(fund)

    def show(name, h, r):
        print(f"\n### {name}  FY0-header={h[-1]}")
        print(csv_text(h, r).replace("\r\n", "\n").strip())

    show("INCOME", ih, ir); show("BALANCE", bh, br); show("CASHFLOW", ch, cr)

    # ---- assertions against the contract ----
    def rowdict(rows): return {r[0]: r[1:] for r in rows}
    ai, ab, ac = rowdict(ir), rowdict(br), rowdict(cr)
    ok = True
    def chk(cond, msg):
        global ok
        print(("PASS" if cond else "FAIL"), msg); ok = ok and cond

    chk("Date" not in ih and "Date" not in bh and "Date" not in ch, "statements have NO 'Date' header")
    chk(ai["Total Revenue"][-1] == "350000000000", "revenue raw dollars, FY0 rightmost")
    chk(ai["Cost of Revenue"][-1] == "140000000000", "cost positive, raw")
    chk(abs(float(ai["Tax Rate for Calcs"][-1]) - 19000/119000) < 1e-6, "tax rate = tax/pretax fraction")
    chk("." in ai["Diluted EPS"][-1], "diluted EPS is a per-share decimal (unscaled)")
    chk(ab["Ordinary Shares Number"][-1] == "12211000000", "shares = raw count")
    chk(PENSION_LABEL in ab, "pension row present with exact label")
    chk(ab[PENSION_LABEL][-1] == "8478000000", "pension FY0 from EDGAR, raw dollars, positive")
    chk(ac["Capital Expenditure"][-1].startswith("-"), "capex negative")
    chk(ac["Common Stock Dividend Paid"][-1].startswith("-"), "dividends negative")
    chk(ac["Repurchase of Capital Stock"][-1].startswith("-"), "repurchase negative")
    chk(ify == bfy == cfy, "all three share same FY0 year")
    chk(build_empty_splits_csv().strip() == "Date,Stock Splits", "splits file is header-only")
    print("\nALL GOOD" if ok else "\nSOME CHECKS FAILED")