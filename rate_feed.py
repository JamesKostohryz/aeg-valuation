#!/usr/bin/env python3
"""rate_feed.py — consume the rate-infrastructure chat's LOCKED CSV contract.

The rate-infrastructure pipeline (JamesKostohryz/real-yields) commits deterministic
rate CSVs to a public GitHub repo. Our valuation engine reads them the same way our
Sheet does: plain HTTPS GET on raw.githubusercontent, no auth, no service account.

This module is the single seam between their contract and our engine. It fetches,
parses, and *fail-loud* validates the series, then exposes them as clean structured
objects. Nothing here touches the sealed engine — re-pointing lives in a separate
step that consumes what this returns.

------------------------------------------------------------------ the contract
Base:  https://raw.githubusercontent.com/JamesKostohryz/real-yields/main/outputs/<FILE>

Two unit conventions, separated by filename suffix:
  *_latest.csv  -> continuously-compounded PERCENT   (2.11)
  *_annual.csv  -> annual-compounded DECIMAL fraction (0.0211), annual = exp(cc/100)-1
We consume the *_annual (decimal) variants everywhere — our engine works in annual
decimals — so there is zero conversion and zero convention risk on our side.

Global (market-wide) series, by tenor 1..30:
  curve_latest_annual.csv      cols: tenor, real, real_fwd1y, exp_inflation,
                                      exp_inflation_fwd1y, breakeven, breakeven_fwd1y
  erp_market_latest_annual.csv cols: tenor, market_erp

Per-company series (V2 feed), tenor grid 1..N (N may exceed 30; we slice 1..30):
  coe_v2_<TICKER>_latest_annual.csv
                           cols: tenor, real_rf, market_erp, idiosyncratic,
                                 company_erp, real_coe
                           exact-additive: real_rf+market_erp+idiosyncratic
                                           == real_coe  (annual-decimal)
                           (V2 drops the separate credit_relative term entirely;
                            leverage/credit stay inside the engine via MM re-lever.)
  cod_<TICKER>_annual.csv  cols: tenor, real_cod, spread, rating, offset,
                                 real_cod_<rating>   (real_cod consumed DIRECTLY)

Per-company scalars (field,value long file):
  company_<TICKER>.csv     fields incl: market_value_of_debt, portfolio_ytm,
                                        wavg_mod_duration, wavg_coupon, wavg_years,
                                        mvd_basis
      PROVENANCE — mvd_basis: the upstream feed publishes no per-bond amount
      outstanding, so market_value_of_debt may be BOOK-SCALED: the issuer's reported
      book total debt marked to the mean traded price of its own bond curve
      (mvd_basis="book-scaled"). That is an approximation, not issue-level truth, and
      it flows straight into the disclosed debt capital gain. Treat a book-scaled MVD
      as an estimate; upgrade path upstream is a real 10-K/XBRL debt schedule.

------------------------------------------------------------------ routing (V1-Plus)
COE:  base we feed engine = real_rf + market_erp  (per tenor, both from coe_annual).
      DROP credit_relative (our engine owns leverage via MM un/re-lever).
      ADD  idiosyncratic AFTER re-levering, as a disclosed firm-specific premium.
      IGNORE company_erp / real_coe (assembled totals; cross-check only).
COD:  consume real_cod directly (already real forward) — no nominal step.
NFO:  market NFO = market_value_of_debt - cash - ST investments, at period-0 anchor.
"""
import csv, io, math, urllib.request

BASE_URL = "https://raw.githubusercontent.com/JamesKostohryz/real-yields/main/outputs"
N_TENORS = 30

# ---- sane-value guardrails (annual decimals). Any series outside -> abort loud.
BOUNDS = {
    "real":                (-0.05, 0.10),
    "real_fwd1y":          (-0.05, 0.12),
    "exp_inflation":       (0.0, 0.15),
    "exp_inflation_fwd1y": (0.0, 0.15),
    "breakeven":           (0.0, 0.15),
    "breakeven_fwd1y":     (0.0, 0.15),
    # market_erp is VIX^2-based near the anchor; widen the ceiling to tolerate a genuine
    # volatility spike (~VIX 50) while still catching a percent-scale unit error (>>0.25).
    "market_erp":          (0.0, 0.25),
    "real_rf":             (-0.05, 0.10),
    "credit_relative":     (-0.02, 0.10),
    # idiosyncratic is now a MEASURED Martin-Wagner term ½·(stock var − avg stock var),
    # which is legitimately NEGATIVE for a lower-than-average-volatility name (e.g. AT&T),
    # so allow a modest negative floor. (Deferred obsolescence work may push the ceiling
    # past 0.15 at long horizons — the rate team will flag before publishing that.)
    "idiosyncratic":       (-0.05, 0.15),
    "company_erp":         (0.0, 0.30),
    "real_coe":            (-0.05, 0.35),
    "real_cod":            (-0.05, 0.20),
    "spread":              (0.0, 0.15),
    "offset":              (0.0, 5.0),
}
DECOMP_TOL = 1e-5  # additive COE decomposition tolerance. The rate team's _annual files
# publish at 6 decimals, so per-tenor rounding leaves a residual near 1e-6 on real data
# (verified on live AT&T); 1e-5 absorbs that comfortably while still catching a genuine
# decomposition break (which is orders of magnitude larger).


class RateFeedError(Exception):
    """Raised on any contract violation. Fail loud; never ship a silent bad rate."""


# ---------------------------------------------------------------- fetch layer
def _fetch_text(fname, *, base_url=BASE_URL, local_dir=None, timeout=30):
    """Return the raw text of one contract file.

    Production: HTTPS GET on raw.githubusercontent (no auth). Testing/offline:
    pass local_dir to read the file from disk instead. Exactly one source.
    """
    if local_dir is not None:
        import os
        path = os.path.join(local_dir, fname)
        if not os.path.exists(path):
            raise RateFeedError(f"[fetch] local fixture missing: {path}")
        with open(path, "r", newline="") as fh:
            return fh.read()
    url = f"{base_url}/{fname}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            if r.status != 200:
                raise RateFeedError(f"[fetch] {url} -> HTTP {r.status}")
            return r.read().decode("utf-8")
    except RateFeedError:
        raise
    except Exception as e:  # urllib.error.*, socket timeout, etc.
        raise RateFeedError(f"[fetch] {url} -> {type(e).__name__}: {e}")


# ---------------------------------------------------------------- parse helpers
def _read_rows(text, fname):
    rd = csv.DictReader(io.StringIO(text))
    if rd.fieldnames is None:
        raise RateFeedError(f"[{fname}] empty file / no header")
    rows = [{(k or "").strip(): (v or "").strip() for k, v in row.items()} for row in rd]
    if not rows:
        raise RateFeedError(f"[{fname}] header present but no data rows")
    return [c.strip() for c in rd.fieldnames], rows


def _require_cols(fields, need, fname):
    missing = [c for c in need if c not in fields]
    if missing:
        raise RateFeedError(f"[{fname}] missing columns {missing}; have {fields}")


def _fnum(s, fname, col, tenor=None):
    if s in ("", "null", "nan", "NaN", "NA", "N/A", "-"):
        where = f" tenor {tenor}" if tenor is not None else ""
        raise RateFeedError(f"[{fname}] blank/NaN in '{col}'{where}")
    try:
        v = float(s)
    except ValueError:
        raise RateFeedError(f"[{fname}] non-numeric '{s}' in '{col}'")
    if not math.isfinite(v):
        raise RateFeedError(f"[{fname}] non-finite in '{col}'")
    return v


def _check_bounds(v, col, fname, tenor=None):
    if col in BOUNDS:
        lo, hi = BOUNDS[col]
        if not (lo <= v <= hi):
            where = f" tenor {tenor}" if tenor is not None else ""
            raise RateFeedError(
                f"[{fname}] '{col}'{where} = {v:.6g} outside sane range [{lo},{hi}] "
                f"(is this really an annual-decimal *_annual file, not percent?)")
    return v


def _tenor_series(rows, cols, fname, keep=N_TENORS):
    """Turn tenor-indexed rows into {col: [v_tenor1..v_tenor{keep}]}. Requires the
    contiguous 1..{keep} grid to be PRESENT (tenors beyond {keep} are ignored, so a
    longer V2 grid — e.g. 1..150 — is accepted and sliced) and per-cell bounds.
    String cols (rating) skipped."""
    by_tenor = {}
    for row in rows:
        t = int(_fnum(row["tenor"], fname, "tenor"))
        by_tenor[t] = row
    have = sorted(by_tenor)
    need_grid = list(range(1, keep + 1))
    missing = [t for t in need_grid if t not in by_tenor]
    if missing:
        raise RateFeedError(
            f"[{fname}] tenor grid must contain 1..{keep} contiguous; missing {missing} "
            f"(have {have[:3]}..{have[-2:] if len(have) > 3 else have})")
    out = {}
    for col in cols:
        if col == "tenor":
            continue
        series = []
        is_numeric = True
        for t in range(1, keep + 1):
            raw = by_tenor[t].get(col, "")
            try:
                v = _fnum(raw, fname, col, t)
            except RateFeedError:
                # tolerate genuinely non-numeric columns (e.g. 'rating') as strings
                if col in ("rating",):
                    is_numeric = False
                    series.append(raw)
                    continue
                raise
            _check_bounds(v, col, fname, t)
            series.append(v)
        out[col] = series
    return out


# ---------------------------------------------------------------- public loaders
def load_curve(*, base_url=BASE_URL, local_dir=None):
    """Global real-rate / inflation term structure (annual decimals, by tenor)."""
    fname = "curve_latest_annual.csv"
    need = ["tenor", "real", "real_fwd1y", "exp_inflation",
            "exp_inflation_fwd1y", "breakeven", "breakeven_fwd1y"]
    fields, rows = _read_rows(_fetch_text(fname, base_url=base_url, local_dir=local_dir), fname)
    _require_cols(fields, need, fname)
    return _tenor_series(rows, need, fname)


def load_market_erp(*, base_url=BASE_URL, local_dir=None):
    """Global market ERP term structure (annual decimal, by tenor)."""
    fname = "erp_market_latest_annual.csv"
    need = ["tenor", "market_erp"]
    fields, rows = _read_rows(_fetch_text(fname, base_url=base_url, local_dir=local_dir), fname)
    _require_cols(fields, need, fname)
    return _tenor_series(rows, need, fname)["market_erp"]


def load_coe(ticker, *, base_url=BASE_URL, local_dir=None):
    """Per-company COE components, V2 feed (annual decimals, by tenor). Reads the
    V2 file coe_v2_<TICKER>_latest_annual.csv, whose grid may run past tenor 30
    (sliced to 1..30 here). Verifies the exact-additive V2 decomposition
    rf + erp + idio == real_coe (no separate credit_relative term in V2)."""
    fname = f"coe_v2_{ticker.upper()}_latest_annual.csv"
    need = ["tenor", "real_rf", "market_erp",
            "idiosyncratic", "company_erp", "real_coe"]
    fields, rows = _read_rows(_fetch_text(fname, base_url=base_url, local_dir=local_dir), fname)
    _require_cols(fields, need, fname)
    ser = _tenor_series(rows, need, fname)
    for i in range(N_TENORS):
        parts = (ser["real_rf"][i] + ser["market_erp"][i]
                 + ser["idiosyncratic"][i])
        if abs(parts - ser["real_coe"][i]) > DECOMP_TOL:
            raise RateFeedError(
                f"[{fname}] tenor {i+1}: additive decomposition broken "
                f"(rf+erp+idio={parts:.8f} vs real_coe={ser['real_coe'][i]:.8f}, "
                f"diff={parts-ser['real_coe'][i]:.2e} > {DECOMP_TOL:.0e})")
    return ser


def load_cod(ticker, *, base_url=BASE_URL, local_dir=None):
    """Per-company REAL forward cost of debt (annual decimals, by tenor).
    real_cod is consumed directly — already the real forward COD the engine wants."""
    fname = f"cod_{ticker.upper()}_annual.csv"
    need = ["tenor", "real_cod", "spread", "rating", "offset"]
    fields, rows = _read_rows(_fetch_text(fname, base_url=base_url, local_dir=local_dir), fname)
    _require_cols(fields, need, fname)
    ser = _tenor_series(rows, need, fname)
    ser["rating_label"] = ser["rating"][0] if "rating" in ser else None
    return ser


def load_company(ticker, *, base_url=BASE_URL, local_dir=None):
    """Per-company scalar fields (field,value long file). Requires a positive
    market_value_of_debt. Bonus debt-analytics fields returned when present."""
    fname = f"company_{ticker.upper()}.csv"
    text = _fetch_text(fname, base_url=base_url, local_dir=local_dir)
    fields, rows = _read_rows(text, fname)
    _require_cols(fields, ["field", "value"], fname)
    d = {}
    for row in rows:
        d[row["field"]] = row["value"]
    if "market_value_of_debt" not in d:
        raise RateFeedError(f"[{fname}] missing market_value_of_debt")
    mvd = _fnum(d["market_value_of_debt"], fname, "market_value_of_debt")
    if mvd <= 0:
        raise RateFeedError(f"[{fname}] market_value_of_debt={mvd} must be > 0")
    out = {"market_value_of_debt": mvd}
    for k in ("portfolio_ytm", "wavg_mod_duration", "wavg_coupon", "wavg_years"):
        if k in d and d[k] not in ("", "null", "-"):
            try:
                out[k] = float(d[k])
            except ValueError:
                pass
    return out


def market_nfo(company, cash, sti):
    """market NFO = market_value_of_debt - cash - ST investments (period-0 anchor).
    cash and sti come from the loaded statements (Inputs in_cash / in_sti)."""
    return company["market_value_of_debt"] - float(cash) - float(sti)


# ---------------------------------------------------------------- one entry point
def load_all(ticker, cash, sti, *, base_url=BASE_URL, local_dir=None,
             bonded=True):
    """Load and validate the full feed for one company. Returns a dict of the
    series the engine re-pointer needs, plus the derived market NFO.

    bonded=False -> the issuer has no committed bond list, so per-company COD /
    MV-of-debt are unavailable; caller falls back to rating-curve COD + book NFO.
    """
    curve = load_curve(base_url=base_url, local_dir=local_dir)
    coe = load_coe(ticker, base_url=base_url, local_dir=local_dir)
    feed = {
        "ticker": ticker.upper(),
        "tenor": list(range(1, N_TENORS + 1)),
        # global curve
        "breakeven_spot":     curve["breakeven"],
        "breakeven_fwd1y":    curve["breakeven_fwd1y"],
        "real_rf_spot":       curve["real"],
        "real_rf_fwd1y":      curve["real_fwd1y"],
        "exp_inflation_spot": curve["exp_inflation"],
        "exp_inflation_fwd1y": curve["exp_inflation_fwd1y"],
        # per-company COE routing (V2: no credit_relative term)
        "market_erp":         coe["market_erp"],       # feed engine ERP row
        "idiosyncratic":      coe["idiosyncratic"],     # firm term (Martin-Wagner)
        "real_coe_published":  coe["real_coe"],         # = rf+erp+idio (cross-check / headline option)
    }
    if bonded:
        cod = load_cod(ticker, base_url=base_url, local_dir=local_dir)
        company = load_company(ticker, base_url=base_url, local_dir=local_dir)
        feed["real_cod"] = cod["real_cod"]
        feed["cod_rating"] = cod.get("rating_label")
        feed["company"] = company
        feed["market_nfo"] = market_nfo(company, cash, sti)
        feed["nfo_basis"] = "market"
    else:
        feed["nfo_basis"] = "book"  # caller supplies book NFO + rating-curve COD
    return feed


if __name__ == "__main__":
    import sys
    tk = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    ld = sys.argv[2] if len(sys.argv) > 2 else None
    f = load_all(tk, cash=0.0, sti=0.0, local_dir=ld)
    print(f"loaded feed for {f['ticker']} (nfo_basis={f['nfo_basis']})")
    for k in ("real_rf_fwd1y", "market_erp", "idiosyncratic", "real_cod"):
        if k in f:
            s = f[k]
            print(f"  {k:20s} t1={s[0]:.4f}  t10={s[9]:.4f}  t30={s[29]:.4f}")
    if "market_nfo" in f:
        print(f"  market_nfo = {f['market_nfo']:.1f}")
