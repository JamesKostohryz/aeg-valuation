#!/usr/bin/env python3
"""
bond_coverage_probe.py — SELECTION ONLY. Counts bonds reachable per company in the
already-downloaded EODHD bond master list, and resolves issuer identity.
Computes NO yield, NO spread, NO pricing error, NO win rate. Session 7 pre-commitment
support only.

Resolution, in three stages:
  A. equity CUSIP6 -> all bonds whose Code is US<CUSIP6>...
  B. token-prefix name match of the company name against each NAMED bond
  C. issuer expansion: any CUSIP6 block reached in stage B, where a majority of that
     block's NAMED bonds match the company, is adopted whole. This is what recovers
     the 1,831 bonds whose Name field is an echo of the Code and therefore carries no
     issuer text, and it is what reaches financing subsidiaries with their own CUSIP6.
  D. a hand-written alias table for issuers whose debt is legally issued by a
     differently-named entity. Every alias is listed in the output and in the
     pre-commitment; none is chosen by looking at any outcome variable.

Inputs (all local, no API calls):
  outputs/2026-08-16-validation2/eodhd_bond_master.json
  outputs/.eodhd_fund_cache/<T>.general.json
  outputs/2026-08-17-r2-scope/r2_scope_prespec.csv  (the 210-name study universe)

Outputs:
  outputs/2026-08-17-bond-spread/bond_coverage.csv
  outputs/2026-08-17-bond-spread/bond_coverage_detail.csv
"""
import csv, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

def _arg(flag, default=None):
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default

D = os.path.join(ROOT, "data", "bond_spreads")
OUT = _arg("--outdir", D)
MASTER = _arg("--master", os.path.join(D, "eodhd_bond_master.json"))
INDEX = _arg("--issuer-index", os.path.join(D, "issuer_index.csv"))
UNIVERSE = _arg("--universe", os.path.join(ROOT, "outputs", "idio_universe_latest.csv"))
os.makedirs(OUT, exist_ok=True)

STOP = {"the", "of", "and", "inc", "incorporated", "corp", "corporation", "co",
        "company", "companies", "plc", "ltd", "limited", "lp", "llc", "holdings",
        "holding", "group", "sa", "nv", "ag", "class", "a", "b", "c", "cl"}

GENERIC_SINGLE = {"southern", "northern", "western", "eastern", "american", "national",
                  "general", "united", "first", "public", "standard", "global",
                  "pacific", "atlantic", "central", "consolidated", "premier",
                  "continental", "federal", "republic", "liberty", "summit"}

# Stage D. Alias -> extra name prefixes to try. Written from knowledge of who issues
# the debt, BEFORE any spread exists. Listed in full in the pre-commitment.
ALIAS = {
    "NEE":  ["nextera energy capital", "florida power light"],
    "BK":   ["bank new york mellon", "bank of new york"],
    "MTB":  ["manufacturers traders", "m t bank"],
    "CHTR": ["cco holdings", "charter communications operating", "time warner cable"],
    "UAL":  ["united airlines"],
    "PPL":  ["ppl electric", "louisville gas", "kentucky utilities", "pennsylvania power"],
    "TEL":  ["tyco electronics", "te connectivity"],
    "TT":   ["trane technologies", "ingersoll rand"],
    "JCI":  ["johnson controls", "tyco fire"],
    "TDG":  ["transdigm"],
    "HCA":  ["hca healthcare", "hca inc"],
    "WTW":  ["willis north america", "willis towers", "willis group"],
    "CTSH": ["cognizant"],
    "ACN":  ["accenture"],
    "COR":  ["amerisourcebergen", "cencora"],
    "CB":   ["chubb", "ace ina", "ace inc"],
    "AON":  ["aon corp", "aon global", "aon north america"],
    "MRK":  ["merck"],
    "FDX":  ["fedex"],
    "CME":  ["cme group"],
    "IQV":  ["iqvia", "quintiles"],
    "PANW": ["palo alto"],
    "HLT":  ["hilton domestic", "hilton worldwide"],
    "TYL":  ["tyler technologies"],
    "J":    ["jacobs engineering", "jacobs solutions"],
    "PCAR": ["paccar"],
    "FAST": ["fastenal"],
    "AME":  ["ametek"],
    "ROK":  ["rockwell automation"],
    "NXPI": ["nxp bv", "nxp semiconductors", "nxp funding"],
    "SNPS": ["synopsys"],
    "CDNS": ["cadence design"],
    "ANET": ["arista"],
    "EXPD": ["expeditors"],
    "ODFL": ["old dominion"],
    "JBHT": ["hunt jb", "j b hunt"],
    "WST":  ["west pharmaceutical"],
    "STE":  ["steris"],
    "RMD":  ["resmed"],
    "IDXX": ["idexx"],
    "HOLX": ["hologic"],
    "DXCM": ["dexcom"],
    "MTD":  ["mettler toledo"],
    "WAT":  ["waters"],
    "COO":  ["cooper companies", "cooper cos"],
    "GRMN": ["garmin"],
    "ZBRA": ["zebra technologies"],
    "NTAP": ["netapp"],
    "PAYX": ["paychex"],
    "BRO":  ["brown brown"],
    "DPZ":  ["dominos", "domino s"],
    "CMG":  ["chipotle"],
    "WSM":  ["williams sonoma"],
    "WYNN": ["wynn las vegas", "wynn resorts"],
    "POOL": ["pool corp", "pool corporation"],
    "PTC":  ["ptc inc"],
    "HEI":  ["heico"],
    "EME":  ["emcor"],
    "CDW":  ["cdw llc", "cdw corp"],
    "ACM":  ["aecom"],
    "TSLA": ["tesla"],
    # Regulated utilities issue at the operating-company level. These are the legal
    # issuing subsidiaries, written from the corporate structure, not from any outcome.
    "SO":   ["alabama power", "georgia power", "mississippi power", "southern power",
             "southern co gas", "nicor gas", "atlanta gas light", "southern company"],
    "SRE":  ["sempra", "san diego gas", "southern calif gas", "southern california gas"],
    "ED":   ["consolidated edison"],
    "DUK":  ["duke energy", "progress energy", "piedmont natural gas"],
    "AEP":  ["appalachian power", "ohio power", "aep texas", "aep transmission",
             "indiana michigan power", "public service co oklahoma",
             "southwestern electric power", "american electric power"],
    "XEL":  ["northern sts pwr", "northern states power", "public service co colorado",
             "southwestern public service", "xcel energy"],
    "PEG":  ["public service electric", "pseg"],
    "DTE":  ["dte electric", "dte gas", "dte energy"],
    "WEC":  ["wisconsin electric", "wisconsin power", "wisconsin pub svc",
             "wisconsin public service", "wec energy"],
    "AEE":  ["ameren", "union electric"],
    "CMS":  ["consumers energy", "cms energy"],
    "FE":   ["firstenergy", "ohio edison", "cleveland electric", "jersey central",
             "met ed", "pennsylvania electric", "potomac edison", "west penn power",
             "toledo edison"],
    "AWK":  ["american water"],
    "ATO":  ["atmos energy"],
    "MMM":  ["3m co", "3m company"],
    "ETN":  ["eaton corp", "eaton capital"],
    "KO":   ["coca cola co", "coca-cola co"],
    # ---- ACQUIRED / PREDECESSOR ISSUERS, added 2026-08-20. The debt of a company this one
    # bought is this company's obligation, but it was issued under the acquired entity's own
    # name and CUSIP6, so neither the equity-CUSIP6 route nor a name-prefix match can reach it.
    # Verified against TradingView (ICE Data Services / FactSet), which lists the Activision
    # bonds on Microsoft's own bond page and shows FINRA has re-badged them MSFT58280xx.
    "MSFT": ["activision blizzard"],          # acquired October 2023
    "LIN":  ["praxair"],                      # Linde plc / Praxair merger, October 2018
}


# Explicit rejections: entities whose name legitimately matches the company prefix but
# which are NOT the company's own credit. Written before any spread existed.
EXCLUDE = {
    "KO":   ["coca cola enterprises", "coca cola femsa", "coca cola consolidated",
             "coca cola bottling", "coca cola european"],
    "ETN":  ["eaton vance"],
    "WYNN": ["wynn macau", "wynmac"],
    "SO":   ["southern calif", "southern california", "southern copper",
             "southern natural gas"],
    "MS":   ["morgan stanley china"],
}


def toks(s):
    s = (s or "").lower()
    # DELETE apostrophes, do not split on them. EODHD writes the company name with a CURLY
    # apostrophe (U+2019): "McDonald’s Corporation" tokenised to ["mcdonald", "s"], which can
    # never be a prefix of ["mcdonalds", ...] as the bond master writes it. That one character
    # cost McDonald's 17 of its 20 bonds, and it costs every company whose name carries an
    # apostrophe -- Lowe's, Macy's, Moody's, Kellogg's, Dick's, Wendy's.
    s = s.replace("’", "").replace("ʼ", "").replace("'", "").replace("`", "")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return [t for t in s.split() if t and t not in STOP]


def is_prefix(key, name_toks):
    """key tokens must be a leading prefix of the bond name tokens."""
    if not key or len(name_toks) < len(key):
        return False
    return name_toks[:len(key)] == key


def main():
    master = json.load(open(MASTER))
    by_c6, named = {}, []
    for b in master:
        code = b.get("Code") or ""
        nm = b.get("Name") or ""
        c6 = code[2:8] if code.startswith("US") and len(code) >= 8 else ""
        b["_c6"] = c6
        b["_echo"] = int(nm == code or not nm)
        if c6:
            by_c6.setdefault(c6, []).append(b)
        if not b["_echo"]:
            b["_toks"] = toks(nm)
            named.append(b)
    sys.stderr.write(f"master {len(master)} bonds, {len(by_c6)} CUSIP6 blocks, "
                     f"{len(master)-len(named)} echo-named\n")

    uni = [(r["ticker"], r.get("sample") or "universe")
           for r in csv.DictReader(open(UNIVERSE))]
    IDX = {r["ticker"]: r for r in csv.DictReader(open(INDEX))}
    rows, detail = [], []
    for tkr, sample in uni:
        g = IDX.get(tkr) or {}
        cusip = g.get("cusip") or ""
        cname = g.get("company") or ""
        c6 = cusip[:6] if cusip else ""
        keys = [toks(cname)] + [toks(a) for a in ALIAS.get(tkr, [])]
        keys = [k for k in keys if k]
        # a company key of three or more tokens is also tried truncated to two, because
        # bond issuer entities routinely shorten ("T-Mobile US" -> "T-MOBILE USA INC").
        # Two tokens is the shortest safe truncation: "American Express" and "American
        # Electric Power" still separate, "United Parcel" and "United Airlines" still
        # separate. One-token keys are matched whole.
        # A key that reduces to ONE token is only usable if that token is long and not
        # a geographic/generic word. "The Southern Company" -> ["southern"] would
        # otherwise swallow Southern California Edison, Southern California Gas and
        # Southern Copper. Verified: it did, on the first draft of this tool.
        keys = [k for k in keys
                if len(k) > 1 or (len(k[0]) >= 5 and k[0] not in GENERIC_SINGLE)]

        bad = [toks(x) for x in EXCLUDE.get(tkr, [])]
        def rejected(b):
            return any(is_prefix(x, b["_toks"]) for x in bad)

        # stage B: name-prefix hits
        name_hits = [b for b in named
                     if any(is_prefix(k, b["_toks"]) for k in keys) and not rejected(b)]
        # stage B2: many EODHD bond names lead with the EQUITY TICKER rather than the
        # company name ("UNP 2.891 06-APR-36", "NXPI 2.65 15-FEB-32"). Free extra route.
        if len(tkr) >= 3:
            tk = [tkr.lower()]
            name_hits += [b for b in named if b not in name_hits
                          and is_prefix(tk, b["_toks"]) and not rejected(b)]

        # stage C: adopt a CUSIP6 block when a majority of its NAMED bonds match
        blocks = {c6} if c6 else set()
        cand = {}
        for b in name_hits:
            if b["_c6"]:
                cand.setdefault(b["_c6"], 0)
                cand[b["_c6"]] += 1
        adopted_via_name = []
        for cb, hit in cand.items():
            blk = by_c6.get(cb, [])
            nmd = [x for x in blk if not x["_echo"]]
            # 100%, not a majority. A majority rule let Edison International's block in
            # under Southern Company. A CUSIP6 block belongs to exactly one issuer, so
            # if any named bond in it is somebody else, the match is wrong.
            if nmd and hit == len(nmd):
                if cb not in blocks:
                    adopted_via_name.append(cb)
                blocks.add(cb)

        got = {}
        for cb in blocks:
            for b in by_c6.get(cb, []):
                got[b["Code"]] = ("cusip6" if cb == c6 else "name_block", b)
        for b in name_hits:
            got.setdefault(b["Code"], ("name_only", b))

        n_c6 = len(by_c6.get(c6, [])) if c6 else 0
        rows.append({
            "ticker": tkr, "sample": sample, "company": cname,
            "equity_cusip6": c6,
            "n_equity_cusip6_block": n_c6,
            "n_name_prefix_hits": len(name_hits),
            "extra_cusip6_blocks": ";".join(sorted(adopted_via_name)),
            "used_alias": int(bool(ALIAS.get(tkr))),
            "n_bonds_total": len(got),
            "n_bonds_echo_named": sum(1 for _, (_, b) in got.items() if b["_echo"]),
        })
        for code, (route, b) in sorted(got.items()):
            detail.append({"ticker": tkr, "sample": sample, "bond_code": code,
                           "route": route, "cusip6": b["_c6"],
                           "bond_name": b.get("Name"), "echo_named": b["_echo"]})

    with open(os.path.join(OUT, "bond_coverage.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    with open(os.path.join(OUT, "bond_coverage_detail.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ticker", "sample", "bond_code", "route",
                                          "cusip6", "bond_name", "echo_named"])
        w.writeheader(); w.writerows(detail)

    n = len(rows)
    m_c = sum(1 for r in rows if r["n_equity_cusip6_block"] > 0)
    m_n = sum(1 for r in rows if r["n_name_prefix_hits"] > 0)
    m_e = sum(1 for r in rows if r["n_bonds_total"] > 0)
    tot = sum(r["n_bonds_total"] for r in rows)
    cnts = sorted(r["n_bonds_total"] for r in rows if r["n_bonds_total"] > 0)
    print(f"universe                 {n}")
    print(f"  equity CUSIP6 alone    {m_c}")
    print(f"  name prefix alone      {m_n}")
    print(f"  ANY route              {m_e}")
    print(f"  bonds reachable        {tot}  (echo-named "
          f"{sum(r['n_bonds_echo_named'] for r in rows)})")
    print(f"  per company: median {cnts[len(cnts)//2]}  p90 {cnts[int(.9*len(cnts))]}  max {max(cnts)}")
    for s in ("sample1", "sample2"):
        ss = [r for r in rows if r["sample"] == s]
        print(f"  {s}: {sum(1 for r in ss if r['n_bonds_total']>0)} of {len(ss)} matched, "
              f"{sum(r['n_bonds_total'] for r in ss)} bonds")
    miss = [r["ticker"] for r in rows if r["n_bonds_total"] == 0]
    print(f"  UNMATCHED ({len(miss)}): {' '.join(miss)}")
    one = [r["ticker"] for r in rows if r["n_bonds_total"] == 1]
    print(f"  SINGLE BOND ({len(one)}): {' '.join(one)}")


if __name__ == "__main__":
    main()
