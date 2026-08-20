#!/usr/bin/env python3
"""Unit tests for rate_feed.py against the contract fixtures. Covers the happy
path (parse + decomposition + NFO) and every fail-loud gate."""
import os, tempfile, shutil
import rate_feed as rf

FIX = os.path.join(os.path.dirname(__file__), "rate_fixtures")
_pass = _fail = 0


def ok(cond, msg):
    global _pass, _fail
    if cond:
        _pass += 1
        print(f"  PASS {msg}")
    else:
        _fail += 1
        print(f"  FAIL {msg}")


def expect_error(fn, needle, msg):
    global _pass, _fail
    try:
        fn()
        _fail += 1
        print(f"  FAIL {msg} (no error raised)")
    except rf.RateFeedError as e:
        if needle.lower() in str(e).lower():
            _pass += 1
            print(f"  PASS {msg}")
        else:
            _fail += 1
            print(f"  FAIL {msg} (wrong error: {e})")


print("== happy path ==")
feed = rf.load_all("AAPL", cash=30000.0, sti=25000.0, local_dir=FIX)
ok(feed["ticker"] == "AAPL", "ticker")
ok(len(feed["market_erp"]) == 30, "market_erp has 30 tenors")
ok(len(feed["real_cod"]) == 30, "real_cod has 30 tenors")
ok(0.03 < feed["market_erp"][0] < 0.06, f"market_erp t1 sane ({feed['market_erp'][0]})")
ok(feed["idiosyncratic"][0] > feed["idiosyncratic"][29], "idiosyncratic decays with tenor")
ok(feed["nfo_basis"] == "market", "nfo basis market")
# market NFO = MVD - cash - sti = 98650 - 30000 - 25000 = 43650
ok(abs(feed["market_nfo"] - 43650.0) < 1e-6, f"market_nfo = {feed['market_nfo']}")

print("== COE exact-additive decomposition holds (V2: rf+erp+idio) ==")
coe = rf.load_coe("AAPL", local_dir=FIX)
worst = max(abs(coe["real_rf"][i] + coe["market_erp"][i]
               + coe["idiosyncratic"][i] - coe["real_coe"][i]) for i in range(30))
ok(worst < 1e-9, f"decomposition ties to {worst:.2e}")

print("== bonded=False skips per-company debt files ==")
feed_b = rf.load_all("AAPL", cash=0, sti=0, local_dir=FIX, bonded=False)
ok("real_cod" not in feed_b and feed_b["nfo_basis"] == "book", "book fallback")

print("== live-contract details (AT&T): extra columns, measured/negative idio, abs-USD, BBB ==")
# extra trailing curve columns (nominal, nominal_fwd1y) are tolerated by the by-name reader
curve = rf.load_curve(local_dir=FIX)
ok(len(curve["real"]) == 30, "curve loads with extra nominal/nominal_fwd1y columns present")
t = rf.load_all("T", cash=0, sti=0, local_dir=FIX)
ok(t["cod_rating"] == "BBB", "dynamic real_cod_<rating> column (BBB) handled")
ok(min(t["idiosyncratic"]) < 0, f"measured idiosyncratic goes negative ({min(t['idiosyncratic']):.4f})")
ok(t["company"]["market_value_of_debt"] == 116047846974.0, "absolute-USD market_value_of_debt parsed")
# decomposition still exact with a negative idiosyncratic component
tc = rf.load_coe("T", local_dir=FIX)
worst_t = max(abs(tc["real_rf"][i] + tc["market_erp"][i]
                  + tc["idiosyncratic"][i] - tc["real_coe"][i]) for i in range(30))
ok(worst_t < 1e-9, f"AT&T decomposition ties with negative idio ({worst_t:.2e})")
# absolute-USD debt maps to engine (trillions) units via self-calibrating scale
import disclose as D
me, scale, _ = D._resolve_debt_scale(t["company"]["market_value_of_debt"], 0.137, None)
ok(abs(scale - 1e12) < 1 and 0.3 <= me / 0.137 <= 1.3, f"abs-USD debt -> engine units (scale {scale:g})")

print("== LIVE sample (real published AT&T bytes, 6-decimal) ==")
REAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rate_real_T")
if os.path.isdir(REAL):
    live = rf.load_all("T", cash=0.0, sti=0.0, local_dir=REAL, bonded=True)
    ok(live["cod_rating"] == "BBB" and len(live["real_cod"]) == 30, "live AT&T loads (BBB, 30 tenors)")
    lc = rf.load_coe("T", local_dir=REAL)
    worst_live = max(abs(lc["real_rf"][i] + lc["market_erp"][i]
                        + lc["idiosyncratic"][i] - lc["real_coe"][i]) for i in range(30))
    ok(worst_live <= rf.DECOMP_TOL, f"live decomposition within tol (residual {worst_live:.1e}, 6-dec publish)")
    ok(live["company"]["market_value_of_debt"] == 116047846974.0, "live absolute-USD MVD")
    lcv = rf.load_curve(local_dir=REAL)
    dss = max(abs(lc["real_rf"][i] - lcv["real_fwd1y"][i]) for i in range(30))
    # V2 single-sources real_rf from the same spot curve, but the coe_v2 file publishes it
    # at 9 dp while curve publishes real_fwd1y at 6 dp, so they agree to ~1e-6 (rounding),
    # not bit-exactly as the v1 matched sample did.
    ok(dss <= 1e-6, f"live single-source: coe.real_rf ~= curve.real_fwd1y (v2 6-dp vs 9-dp; max {dss:.1e})")
else:
    print("  (rate_real_T sample not present — skipping live check)")

print("== fail-loud gates ==")
tmp = tempfile.mkdtemp()
try:
    # missing file
    expect_error(lambda: rf.load_curve(local_dir=tmp), "fixture missing",
                 "missing file aborts")

    # percent (not decimal) values trip the bounds gate
    shutil.copytree(FIX, tmp + "/pct", dirs_exist_ok=True)
    p = tmp + "/pct/curve_latest_annual.csv"
    lines = open(p).read().splitlines()
    # blow up real column to a percent-scale number (2.05 instead of 0.0205)
    hdr = lines[0].split(","); ri = hdr.index("real")
    parts = lines[1].split(","); parts[ri] = "2.05"; lines[1] = ",".join(parts)
    open(p, "w").write("\n".join(lines) + "\n")
    expect_error(lambda: rf.load_curve(local_dir=tmp + "/pct"), "outside sane range",
                 "percent-scale value caught by bounds")

    # broken additive decomposition (perturb the V2 coe file the loader now reads)
    shutil.copytree(FIX, tmp + "/dec", dirs_exist_ok=True)
    p = tmp + "/dec/coe_v2_AAPL_latest_annual.csv"
    lines = open(p).read().splitlines()
    hdr = lines[0].split(","); ii = hdr.index("idiosyncratic")
    parts = lines[1].split(","); parts[ii] = str(float(parts[ii]) + 0.01)
    lines[1] = ",".join(parts); open(p, "w").write("\n".join(lines) + "\n")
    expect_error(lambda: rf.load_coe("AAPL", local_dir=tmp + "/dec"),
                 "decomposition broken", "broken decomposition caught")

    # missing tenor (drop tenor 15)
    shutil.copytree(FIX, tmp + "/ten", dirs_exist_ok=True)
    p = tmp + "/ten/curve_latest_annual.csv"
    lines = open(p).read().splitlines()
    lines = [lines[0]] + [ln for ln in lines[1:] if not ln.startswith("15,")]
    open(p, "w").write("\n".join(lines) + "\n")
    expect_error(lambda: rf.load_curve(local_dir=tmp + "/ten"), "contiguous",
                 "missing tenor caught")

    # blank cell
    shutil.copytree(FIX, tmp + "/blank", dirs_exist_ok=True)
    p = tmp + "/blank/curve_latest_annual.csv"
    lines = open(p).read().splitlines()
    hdr = lines[0].split(","); ri = hdr.index("real_fwd1y")
    parts = lines[3].split(","); parts[ri] = ""; lines[3] = ",".join(parts)
    open(p, "w").write("\n".join(lines) + "\n")
    expect_error(lambda: rf.load_curve(local_dir=tmp + "/blank"), "blank",
                 "blank cell caught")

    # non-positive market value of debt
    shutil.copytree(FIX, tmp + "/mvd", dirs_exist_ok=True)
    p = tmp + "/mvd/company_AAPL.csv"
    open(p, "w").write("field,value\nmarket_value_of_debt,0\n")
    expect_error(lambda: rf.load_company("AAPL", local_dir=tmp + "/mvd"),
                 "must be > 0", "non-positive MVD caught")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ---------------------------------------------------------------- freshness (2026-08-19)
# The guard that answers "how old is this discount rate?", which nothing asked until now. The
# four-method tie ties just as well on a frozen curve, so age is invisible to every other check
# in this repository. These tests prove the guard DISCRIMINATES: it lets a fresh feed through,
# flags a stale one, refuses an expired one, and reports an absent stamp as unknown rather than
# treating it as either fresh or expired.
import datetime as _dt2
import tempfile as _tf


def _stamp_dir(days_old, ticker="AAPL"):
    d = _tf.mkdtemp()
    shutil.copytree(FIX, d + "/f", dirs_exist_ok=True)
    when = _dt2.datetime.now(_dt2.timezone.utc) - _dt2.timedelta(days=days_old)
    open(d + f"/f/run_stamp_{ticker}.csv", "w").write(
        "field,value\nticker,%s\ngenerated_iso,%s\ngit_sha,deadbee\nrun_id,1\n"
        % (ticker, when.strftime("%Y-%m-%dT%H:%M:%SZ")))
    return d + "/f"


_d = _stamp_dir(3)
_st = rf.load_run_stamp("AAPL", local_dir=_d)
ok(_st is not None and _st["age_days"] in (2, 3) and not _st["stale"] and not _st["expired"],
   "a 3-day-old rate side reads fresh")
ok("days old" in rf.check_freshness("AAPL", _st) and "STALE" not in rf.check_freshness("AAPL", _st),
   "a fresh feed reports its age and is not flagged")

_d = _stamp_dir(45)
_st = rf.load_run_stamp("AAPL", local_dir=_d)
ok(_st["stale"] and not _st["expired"], "a 45-day-old rate side WARNS but still values")
ok("STALE" in rf.check_freshness("AAPL", _st), "the warning is visible in the status string")
_f = rf.load_all("AAPL", cash=0, sti=0, local_dir=_d)
ok(_f["rate_asof_stale"] is True and _f["rate_age_days"] >= 44,
   "load_all carries the age through to the caller instead of swallowing it")

_d = _stamp_dir(200)
_st = rf.load_run_stamp("AAPL", local_dir=_d)
ok(_st["expired"], "a 200-day-old rate side is expired")
expect_error(lambda: rf.load_all("AAPL", cash=0, sti=0, local_dir=_d),
             "past the", "an expired rate side REFUSES the valuation")

ok(rf.load_run_stamp("AAPL", local_dir=FIX) is None,
   "a missing run_stamp reads as absent, not as fresh")
ok("unknown" in rf.check_freshness("AAPL", None),
   "an absent stamp is reported as unknown — a different thing from an old one")
_f = rf.load_all("AAPL", cash=0, sti=0, local_dir=FIX)
ok(_f["rate_age_days"] is None and _f["rate_asof_stale"] is False,
   "a company with no published stamp still values, and says the age is unknown")

print(f"\n{_pass} passed, {_fail} failed")
raise SystemExit(1 if _fail else 0)
