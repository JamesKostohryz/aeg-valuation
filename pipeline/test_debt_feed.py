"""Offline tests for the debt-feed guard. No network, no fixtures, deterministic.

The guard's job is to tell three things apart: the feeds agree; the feeds
disagree and it is the known lease break; and we cannot tell. The third is the
one worth testing hardest, because a guard that claims a finding it cannot
support is worse than no guard.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import debt_feed as DF

FAIL = []


def check(name, got, want):
    if got != want:
        FAIL.append(f"{name}: got {got!r}, want {want!r}")
        print(f"  FAIL {name}: got {got!r}, want {want!r}")
    else:
        print(f"  ok   {name}")


def row(y, end, borrow, lease=None, op=None, fin=None, op_nc=None, fin_nc=None):
    return {"fiscal_year": y, "period_end": end, "borrowings_musd": borrow,
            "borrowings_basis": "components", "routes": {"components": borrow},
            "lease_liabilities_musd": lease, "operating_lease_musd": op,
            "finance_lease_musd": fin, "operating_lease_noncurrent_musd": op_nc,
            "finance_lease_noncurrent_musd": fin_nc}


# --------------------------------------------------------------- fiscal labels
print("\nfiscal_year_label")
check("september year end", DF.fiscal_year_label("2025-09-27"), 2025)
check("calendar year end", DF.fiscal_year_label("2025-12-31"), 2025)
check("retailer ending late January", DF.fiscal_year_label("2025-01-31"), 2025)
check("retailer ending early February", DF.fiscal_year_label("2025-02-02"), 2025)
# The fifty-two/fifty-three week correction: a year ending 3 January 2021 is
# fiscal 2020, not fiscal 2021.
check("fifty-three week year ending in early January",
      DF.fiscal_year_label("2021-01-03"), 2020)
check("June year end", DF.fiscal_year_label("2025-06-30"), 2025)


# ------------------------------------------------------------- the Apple shape
# Agreement through fiscal 2021, then the noncurrent finance leases, then every
# capitalized lease. Figures are the real ones, verified against data.sec.gov.
print("\nthe Apple shape -> AMBER")
apple_primary = [
    row(2019, "2019-09-28", 108047.0, lease=0.0, op=0.0, fin=0.0),
    row(2020, "2020-09-26", 112436.0, lease=9842.0, op=9126.0, fin=716.0, fin_nc=637.0),
    row(2021, "2021-09-25", 124719.0, lease=11803.0, op=10955.0, fin=848.0, fin_nc=769.0),
    row(2022, "2022-09-24", 120069.0, lease=12411.0, op=11470.0, fin=941.0, fin_nc=812.0),
    row(2023, "2023-09-30", 111088.0, lease=12842.0, op=11818.0, fin=1024.0, fin_nc=859.0),
    row(2024, "2024-09-28", 106629.0, lease=12430.0, op=11534.0, fin=896.0, fin_nc=752.0),
    row(2025, "2025-09-27", 98657.0, lease=13720.0, op=12490.0, fin=1230.0, fin_nc=692.0),
]
apple_vendor = {2019: 108047.0, 2020: 112436.0, 2021: 124719.0, 2022: 120881.0,
                2023: 111947.0, 2024: 119059.0, 2025: 112377.0}
ok, detail = DF.corroboration(apple_vendor, apple_primary)
check("corroborated", ok, True)
check("clean break", detail["clean_break"], True)
check("last agreeing year", detail["last_agreeing_year"], 2021)
check("first disagreeing year", detail["first_disagreeing_year"], 2022)

dis = DF.debt_feed_disagreements(apple_vendor, apple_primary)
check("four disagreeing years", [d["fiscal_year"] for d in dis], [2022, 2023, 2024, 2025])
check("every gap lease-explained", all(d["explained_by_leases"] for d in dis), True)
check("fiscal 2022 gap is noncurrent finance leases",
      dis[0]["gap_equals"], "noncurrent finance leases")
check("fiscal 2025 gap is every capitalized lease",
      dis[3]["gap_equals"], "all capitalized leases")
check("fiscal 2025 gap size", round(dis[3]["gap_musd"], 6), 13720.0)


# ----------------------------------------------------------------- agreement
print("\nfeeds agree everywhere -> GREEN")
agree_primary = [row(y, f"{y}-12-31", 1000.0 + y) for y in range(2015, 2026)]
agree_vendor = {y: 1000.0 + y for y in range(2015, 2026)}
ok, _ = DF.corroboration(agree_vendor, agree_primary)
check("corroborated", ok, True)
check("no disagreements", DF.debt_feed_disagreements(agree_vendor, agree_primary), [])


# ------------------------------------------------- disagreement that is NOT leases
print("\nclean break that is not leases -> the RED case")
red_primary = [row(y, f"{y}-12-31", 1000.0) for y in range(2015, 2020)]
red_primary += [row(y, f"{y}-12-31", 1000.0, lease=50.0, op=50.0)
                for y in range(2020, 2026)]
red_vendor = {y: 1000.0 for y in range(2015, 2020)}
red_vendor.update({y: 1400.0 for y in range(2020, 2026)})   # +400, not the 50 of leases
ok, _ = DF.corroboration(red_vendor, red_primary)
check("corroborated", ok, True)
red = DF.debt_feed_disagreements(red_vendor, red_primary)
check("six disagreeing years", len(red), 6)
check("none lease-explained", any(d["explained_by_leases"] for d in red), False)


# ------------------------------------------------------- the refusals to claim
print("\nrefusals — the cases where the guard must NOT claim a finding")

# Too few corroborating years: our construction is probably incomplete.
few_primary = [row(2024, "2024-12-31", 900.0), row(2025, "2025-12-31", 950.0)]
ok, detail = DF.corroboration({2024: 1000.0, 2025: 1100.0}, few_primary)
check("two overlapping years, both disagreeing -> refuse", ok, False)
check("refusal names the reason", "construction" in detail["why_not"], True)

# Intermittent disagreement: agrees, disagrees, agrees again. Not a break.
noisy_primary = [row(y, f"{y}-12-31", 1000.0) for y in range(2015, 2026)]
noisy_vendor = {y: 1000.0 for y in range(2015, 2026)}
noisy_vendor[2017] = 1300.0      # an early disagreement...
noisy_vendor[2025] = 1300.0      # ...and a late one, with agreement in between
ok, detail = DF.corroboration(noisy_vendor, noisy_primary)
check("intermittent disagreement -> refuse", ok, False)
check("refusal names alternating years", "alternating" in detail["why_not"], True)

# A break inferred across a hole in our own coverage. This is the AT&T case:
# corroboration in 2008-2011, nothing until 2019, then persistent divergence.
holey_primary = [row(y, f"{y}-12-31", 1000.0) for y in (2008, 2009, 2010, 2011)]
holey_primary += [row(y, f"{y}-12-31", 1000.0, lease=300.0, op=300.0)
                  for y in range(2019, 2026)]
holey_vendor = {y: 1000.0 for y in (2008, 2009, 2010, 2011)}
holey_vendor.update({y: 1300.0 for y in range(2019, 2026)})
ok, detail = DF.corroboration(holey_vendor, holey_primary)
check("break across an eight-year hole -> refuse", ok, False)
check("refusal names the hole", "hole" in detail["why_not"], True)

# The same shape with the hole closed IS claimable, which proves the rule above
# is about the hole and not about the lease amount.
closed = list(holey_primary)
closed.insert(4, row(2012, "2012-12-31", 1000.0))
closed_vendor = dict(holey_vendor)
closed_vendor[2012] = 1000.0
for y in range(2013, 2019):
    closed.insert(0, row(y, f"{y}-12-31", 1000.0))
    closed_vendor[y] = 1000.0
closed.sort(key=lambda r: r["fiscal_year"])
ok, _ = DF.corroboration(closed_vendor, closed)
check("same shape with continuous coverage -> claimable", ok, True)


# ------------------------------------------------------------------ tolerance
print("\ntolerance")
tol_primary = [row(y, f"{y}-12-31", 100000.0) for y in range(2015, 2026)]
tol_vendor = {y: 100000.0 for y in range(2015, 2026)}
tol_vendor[2025] = 100050.0       # 0.05 percent — inside the tolerance
check("rounding-scale difference is not a disagreement",
      DF.debt_feed_disagreements(tol_vendor, tol_primary), [])
tol_vendor[2025] = 100200.0       # 0.2 percent — outside it
check("two tenths of a percent is a disagreement",
      len(DF.debt_feed_disagreements(tol_vendor, tol_primary)), 1)


# ------------------------------------------------------------ scale inference
print("\nvendor unit-scale inference")
# The golden fixtures are millions divided by a million again (a known register
# item), so the guard must establish the vendor row's units rather than assume
# them, or every fixture run reports a spurious hundred-percent disagreement.
tiny_vendor = {y: v * 1e-6 for y, v in apple_vendor.items()}
factor, hits = DF.infer_vendor_scale(tiny_vendor, apple_primary)
check("millionth-scale row recovered", factor, 1e6)
check("recovered scale agrees in the pre-break years", hits, 3)
check("already-correct row keeps factor one",
      DF.infer_vendor_scale(apple_vendor, apple_primary)[0], 1.0)
# And the inference must not manufacture agreement where there is none.
check("unrelated series does not acquire a scale",
      DF.infer_vendor_scale({2024: 7.0, 2025: 9.0}, apple_primary)[1], 0)


# ---------------------------------------------------- offline behaviour + I/O
print("\noffline behaviour and report writing")
with tempfile.TemporaryDirectory() as d:
    bs = os.path.join(d, "XYZ_reported_bs.csv")
    with open(bs, "w") as f:
        f.write("Line item,2023,2024,2025\n")
        f.write("Total Assets,10,11,12\n")
        f.write("Total Debt,100,110,120\n")
    check("vendor row parsed", DF.vendor_total_debt(bs),
          {2023: 100.0, 2024: 110.0, 2025: 120.0})
    # Offline with an unknown ticker: no identifier, no network, no claim, no raise.
    rep = DF.audit_debt_feed("XYZ", bs, anchor_year=2025, cache_dir=d,
                             allow_network=False)
    check("offline verdict is UNVERIFIED", rep["verdict"], "UNVERIFIED")
    check("offline reports the vendor anchor anyway", rep["anchor_vendor_musd"], 120.0)
    out = DF.write_report(rep, os.path.join(d, "XYZ_debt_feed.csv"))
    check("report written", os.path.exists(out), True)
    lines = open(out).read().strip().split("\n")
    check("report has a header and one verdict row", len(lines), 2)

    # A missing Total Debt row is a nothing-to-check, not a crash.
    bs2 = os.path.join(d, "NOD_reported_bs.csv")
    with open(bs2, "w") as f:
        f.write("Line item,2024,2025\nTotal Assets,1,2\n")
    check("absent Total Debt row returns empty", DF.vendor_total_debt(bs2), {})


print("\n" + ("=" * 60))
if FAIL:
    print(f"FAILED {len(FAIL)}")
    for f in FAIL:
        print("  " + f)
    sys.exit(1)
print("test_debt_feed: ALL PASS")
