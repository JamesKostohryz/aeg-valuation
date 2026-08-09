#!/usr/bin/env python3
"""test_lease_ruling.py — the lease ruling's decision logic, pinned.

THE RULING (James, 2026-08-09): feed the debt row from primary-source BORROWINGS only, in
every year, so one company's series stops carrying two different lease treatments.

THE CONSTRAINT (measured the same day): the reconstruction does not generalize. Of fourteen
names, four corroborate at the anchor, eight disagree between routes, two return no usable
primary row. So the ruling is applied ONLY where two independent routes agree --
primary-source borrowings from the filer's XBRL tags, against vendor total debt minus tagged
capitalized leases. James's decision: apply it where corroborated, disclose it where not, no
new refusals.

WHAT THIS FILE GUARDS. Three things that were got wrong once each and would be silent if
they regressed:

1. ORDER OF TESTS. "Is the vendor row already borrowings-only?" must be asked BEFORE "does
   vendor minus leases equal borrowings?". A company can carry capitalized leases on its
   balance sheet in a year when the vendor has not yet folded them into this row -- Apple for
   fiscal 2020 to 2023 exactly. Subtracting there would corrupt four correct years. The first
   implementation had the tests in the wrong order and reported those years as disagreeing.

2. NO SILENT SUBSTITUTION. A year that cannot be corroborated keeps the vendor figure and is
   reported with a reason. It is never quietly replaced.

3. SCALE. The vendor tabs are in the engine's inferred per-ticker scale -- trillions for
   Apple, millions for AT&T -- while the feed is in millions of dollars. Replacements come
   back in the VENDOR'S OWN units. A first attempt converted through an inferred scale factor
   and wrote a figure one million times too large; the four-method tie caught it at 1.4e-2.

No network. The primary-source feed is stubbed, so the assertions are about the decision
logic and nothing else.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
for _p_ in (_ROOT, os.path.join(_ROOT, "pipeline")):
    if _p_ not in sys.path:
        sys.path.insert(0, _p_)

import debt_feed as DF  # noqa: E402

_p = _f = 0


def ok(cond, msg):
    global _p, _f
    if cond:
        _p += 1
        print("  PASS", msg)
    else:
        _f += 1
        print("  FAIL", msg)


def stub(rows):
    """Replace the network-facing calls with a fixed primary-source series."""
    DF.resolve_cik = lambda t, c=None, n=True: "0000000000"
    DF.build_primary_series = lambda cik, c=None, n=True: rows
    return rows


def row(year, borrowings, leases):
    return {"fiscal_year": year, "period_end": f"{year}-09-30",
            "borrowings_musd": borrowings, "borrowings_basis": "components",
            "routes": {}, "lease_liabilities_musd": leases,
            "operating_lease_musd": leases, "finance_lease_musd": None,
            "operating_lease_noncurrent_musd": None, "finance_lease_noncurrent_musd": None}


# ---------------------------------------------------------------- the Apple shape
# Vendor row is borrowings-only through 2023 even though leases are tagged from 2020, then
# folds them in from 2024. Values in $mm; the vendor series is given at scale 1.0 here.
stub([
    row(2019, 108_047, None),
    row(2020, 112_436, 10_600),
    row(2021, 124_719, 11_100),
    row(2022, 120_069, 11_600),
    row(2023, 111_088, 12_000),
    row(2024, 106_629, 12_430),
    row(2025, 98_657, 13_720),
])
vendor = {2019: 108_047.0, 2020: 112_436.0, 2021: 124_719.0, 2022: 120_069.0,
          2023: 111_088.0, 2024: 119_059.0, 2025: 112_377.0}

repl, rep = DF.corroborated_debt_series("AAPL", vendor, allow_network=False)

print("== the Apple shape: leases tagged from 2020, folded into the vendor row from 2024 ==")
ok(sorted(repl) == [2024, 2025], f"only the folded-in years are replaced (got {sorted(repl)})")
ok(abs(repl.get(2025, 0) - 98_657) < 1e-6, "fiscal 2025 becomes borrowings-only, 98,657")
ok(abs(repl.get(2024, 0) - 106_629) < 1e-6, "fiscal 2024 becomes borrowings-only, 106,629")
for y in (2020, 2021, 2022, 2023):
    ok(y not in repl and rep["kept"].get(y) == "already borrowings-only",
       f"fiscal {y}: leases tagged but NOT in the vendor row — left alone, not subtracted")
ok(rep["kept"].get(2019) == "already borrowings-only",
   "fiscal 2019 predates the lease standard — left alone")
ok(rep["years_replaced"] == 2 and rep["years_total"] == 7,
   "the report counts what it changed and what it saw")

# THE ORDERING GUARD, stated as the failure it prevents.
ok(2022 not in repl,
   "ORDERING: a year already on borrowings does not get its leases subtracted a second time")


# ---------------------------------------------------------------- no silent substitution
print("\n== a year that cannot be corroborated is kept and reported ==")
stub([row(2025, 50_000, 3_000)])
repl2, rep2 = DF.corroborated_debt_series("XXX", {2025: 60_000.0}, allow_network=False)
ok(repl2 == {}, "routes disagree, so nothing is replaced")
ok("disagree" in rep2["kept"].get(2025, ""), f"and the reason is recorded ({rep2['kept'].get(2025)})")

stub([row(2025, None, 3_000)])
repl3, rep3 = DF.corroborated_debt_series("XXX", {2025: 60_000.0}, allow_network=False)
ok(repl3 == {} and rep3["kept"].get(2025) == "no borrowings route",
   "no borrowings route resolved: kept, with the reason")

stub([])
repl4, rep4 = DF.corroborated_debt_series("XXX", {2025: 60_000.0}, allow_network=False)
ok(repl4 == {} and rep4["error"], "no primary rows at all: nothing replaced, error recorded")


# ---------------------------------------------------------------- scale
print("\n== replacements come back in the VENDOR'S own units ==")
stub([row(2024, 106_629, 12_430), row(2025, 98_657, 13_720),
      row(2023, 111_088, 12_000), row(2022, 120_069, 11_600)])
# Apple's engine scale: the vendor tab reads 0.112377 for $112,377m -> factor 1e6.
vendor_t = {2022: 0.120069, 2023: 0.111088, 2024: 0.119059, 2025: 0.112377}
repl5, rep5 = DF.corroborated_debt_series("AAPL", vendor_t, allow_network=False)
ok(abs(rep5["scale"] - 1e6) < 1, f"the vendor scale is inferred, not assumed (got {rep5['scale']:g})")
ok(2025 in repl5 and abs(repl5[2025] - 0.098657) < 1e-9,
   f"fiscal 2025 comes back as 0.098657, not 98,657 (got {repl5.get(2025)!r})")
ok(all(v < 1.0 for v in repl5.values()),
   "every replacement is in the vendor's units — the error the tie caught cannot recur")


# ---------------------------------------------------------------- the workbook writer
print("\n== the writer targets the Balance Sheet row the whole build derives from ==")


class _Cell:
    def __init__(self, v=None):
        self.value = v


class _Sheet:
    def __init__(self):
        self.max_row, self.max_column = 5, 4
        self._c = {(3, 2): _Cell(2024), (3, 3): _Cell(2025), (3, 4): _Cell("n/a"),
                   (4, 1): _Cell("Total Assets"), (5, 1): _Cell("Total Debt"),
                   (5, 2): _Cell(0.119059), (5, 3): _Cell(0.112377), (5, 4): _Cell(None)}

    def cell(self, r, c):
        return self._c.setdefault((r, c), _Cell())


sheet = _Sheet()
n = DF.write_debt_series_to_workbook({"Balance Sheet": sheet}, {2024: 0.106629, 2025: 0.098657})
ok(n == 2, f"two cells written (got {n})")
ok(abs(sheet.cell(5, 3).value - 0.098657) < 1e-12, "fiscal 2025 cell carries the new figure")
ok(abs(sheet.cell(5, 2).value - 0.106629) < 1e-12, "fiscal 2024 cell carries the new figure")
ok(sheet.cell(4, 1).value == "Total Assets", "no other row was touched")

if _f:
    print(f"\nFAIL  test_lease_ruling.py  ({_p} passed, {_f} failed)")
    sys.exit(1)
print(f"\n{_p} passed, 0 failed")
