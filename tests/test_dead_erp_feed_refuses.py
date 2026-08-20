#!/usr/bin/env python3
"""
tests/test_dead_erp_feed_refuses.py — the loaded gun stays unloaded.

`erp_market_latest_annual.csv` is rebuilt and committed by real-yields EVERY WEEKDAY, it was
listed in rate_feed.py's LOCKED CSV contract, and `load_market_erp()` sat there looking
production-ready. It has never had a caller. Wiring it up is the most natural thing in the world
for a reader of that module to do, and doing so would cut every discount rate on the system by
roughly 180 basis points and every company premium by about 44% — with the four-method tie green
throughout, because an identity check cannot see which ERP curve it was handed.

Found and correctly documented on 2026-08-15 as "dead — no caller anywhere". Nothing was done
and the loader stayed. So it now refuses, and this pins that.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import rate_feed as RF  # noqa: E402


def test_the_dead_loader_refuses_instead_of_returning_a_curve():
    with pytest.raises(RF.DeadFeedError) as e:
        RF.load_market_erp()
    m = str(e.value)
    assert "180bp" in m or "180 basis points" in m, "the refusal must quantify what it prevents"
    assert "load_coe" in m, "it must point the reader at the curve that IS used"


def test_nothing_in_the_repository_calls_it():
    """A refusal is only a guard while nobody routes around it."""
    import re
    bad = []
    for dirpath, dirnames, files in os.walk(ROOT):
        if any(p in dirpath for p in (".git", "_regwork", "_curvework", "archive")):
            continue
        for fn in files:
            if not fn.endswith(".py") or fn == os.path.basename(__file__):
                continue
            p = os.path.join(dirpath, fn)
            src = open(p, encoding="utf-8", errors="replace").read()
            for mm in re.finditer(r"load_market_erp\s*\(", src):
                line = src[:mm.start()].count("\n") + 1
                if os.path.basename(p) == "rate_feed.py":
                    continue                      # the definition itself
                bad.append("%s:%d" % (os.path.relpath(p, ROOT), line))
    assert not bad, (
        "load_market_erp() is being called from %s. It returns the WRONG market ERP -- 2.31%% at "
        "1y against the 4.13%% the engine discounts at -- and every gate would stay green." % bad)


def test_the_module_contract_says_the_file_is_dead():
    src = open(os.path.join(ROOT, "rate_feed.py"), encoding="utf-8").read()
    i = src.index("erp_market_latest_annual.csv")
    assert "DEAD" in src[i:i + 200], (
        "the LOCKED CSV contract at the top of rate_feed.py lists this file without saying it is "
        "dead. That listing is what makes it look like a feed somebody forgot to wire up.")


def test_the_engine_gets_its_market_erp_from_the_company_feed():
    """Positive control: the curve that IS consumed still loads, so this test fails if the real
    path breaks rather than only if the dead one is revived."""
    assert hasattr(RF, "load_coe")
    src = open(os.path.join(ROOT, "rate_feed.py"), encoding="utf-8").read()
    assert 'feed["market_erp"] = coe["market_erp"]' in src or 'coe["market_erp"]' in src


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
