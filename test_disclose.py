#!/usr/bin/env python3
"""Tests for the Option A disclosure layer. Uses the pre-built ENGINE_A.xlsx
(re-pointed, idio hook installed at 0) + contract fixtures."""
import rate_feed as RF, disclose as D
from recalc_lo import recalc

_p = _f = 0
def ok(c, m):
    global _p, _f
    if c: _p += 1; print("  PASS", m)
    else: _f += 1; print("  FAIL", m)

feed = RF.load_all("AAPL", cash=0, sti=0, local_dir="rate_fixtures")
d = D.disclose("ENGINE_A.xlsx", feed, price=315.0, recalc=recalc)

print("== disclosure bridge integrity ==")
ok("PASS" in d["base_audit"], "base audit passes")
ok(d["base_tie"] < 1e-12, f"base tie machine-precision ({d['base_tie']:.1e})")
ok(d["sens_tie"] < 1e-12, f"sensitivity tie machine-precision ({d['sens_tie']:.1e})")
ok(d["idiosyncratic_haircut_ps"] > 0, "idiosyncratic haircut is a positive drag")
ok(0.3 <= d["market_debt_engine"] / d["book_debt"] <= 1.3, "market/book debt in sane band")
# bridge adds up exactly
recon = d["base_equity_ps"] + d["debt_capital_gain_ps"] - d["idiosyncratic_haircut_ps"]
ok(abs(recon - d["adjusted_equity_ps"]) < 1e-9, "bridge sums exactly to adjusted equity")

print("== fail-loud unit gate ==")
try:
    D.disclose("ENGINE_A.xlsx", feed, price=315.0, recalc=recalc, debt_scale=1.0)  # no scaling -> absurd
    ok(False, "bad debt_scale should abort")
except ValueError as e:
    ok("implausible" in str(e).lower(), "bad debt_scale aborts loud")

print(D.format_bridge(d))
print(f"\n{_p} passed, {_f} failed")
raise SystemExit(1 if _f else 0)
