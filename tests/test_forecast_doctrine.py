#!/usr/bin/env python3
"""
tests/test_forecast_doctrine.py — the two rules a forecaster must not get wrong.

Written 2026-08-20 after both were got wrong in one session. Prose cannot be tested, but the
FACTS the prose describes can be, and if one of these ever changes silently the doctrine becomes
wrong without anyone noticing. See docs/DOCTRINE-How-This-Model-Thinks-2026-08-20.md.
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCTRINE = os.path.join(ROOT, "docs", "DOCTRINE-How-This-Model-Thinks-2026-08-20.md")


def test_the_doctrine_is_in_the_repository():
    """It lived only in the working folder, which is one PC and not a build input."""
    assert os.path.exists(DOCTRINE)
    # whitespace-insensitive: the quoted rule wraps across lines in the markdown
    s = re.sub(r"[\s>*]+", " ", open(DOCTRINE, encoding="utf-8").read())
    assert "AEG must be zero in the first year of the continuing period" in s
    assert "neutral value" in s.lower()


def test_the_truncation_gate_states_both_conditions_and_neither_has_a_default():
    """The rule is a LEVEL -- AEG zero at N+1 -- plus earnings at a normalized level. If the
    gate's own message ever stops saying BOTH, a forecaster reading only the error will infer a
    direction of travel and build a proxy for it, which is exactly what happened."""
    s = re.sub(r"\s+", " ", open(os.path.join(ROOT, "pipeline", "convergence.py"),
                                  encoding="utf-8").read())
    assert "Both conditions must hold" in s
    assert "normalized level" in s
    assert "abnormal earnings growth is spent" in s


def test_the_terminal_payout_has_no_default_and_says_so():
    """A default here would be a distribution policy nobody chose, silently applied to the
    continuing period of every company."""
    s = open(os.path.join(ROOT, "pipeline", "run_company.py"), encoding="utf-8").read()
    assert "NO TERMINAL DISTRIBUTION POLICY" in s
    assert "There is no default" in s


def test_the_reviewed_forecast_artifact_records_the_alternative_not_chosen():
    """More than one driver set satisfies the single constraint, and they mean different things
    about the company. Recording only the one that was picked hides that. Microsoft's file
    records both: 9.3% terminal asset growth (276.30) and 2.2% terminal revenue growth (262.10)
    both land AEG at zero."""
    import json
    p = os.path.join(ROOT, "companies", "MSFT.forecast.json")
    if not os.path.exists(p):
        return
    c = " ".join(json.load(open(p))["_comment"])
    assert "NOT CHOSEN" in c.upper(), "the artifact no longer records the road not taken"
    assert "262" in c and "276" in c


def test_microsofts_published_rate_is_its_own():
    """The point of the whole company-premium exercise. Two companies discounting at rates
    identical to fifteen significant figures is the state this system was in before 2026-08-20.
    """
    import csv
    got = {}
    for t in ("MSFT", "PEP"):
        p = os.path.join(ROOT, "outputs", "%s_summary.csv" % t)
        if not os.path.exists(p):
            return
        d = {r[0]: r[1] for r in csv.reader(open(p)) if len(r) >= 2}
        if "real_coe_longrun" in d:
            got[t] = float(d["real_coe_longrun"])
    if len(got) < 2:
        return
    a, b = got["MSFT"], got["PEP"]
    assert abs(a - b) > 1e-5, (
        "Microsoft and PepsiCo are discounting at the same rate (%.10f vs %.10f). The company "
        "premium has gone inert." % (a, b))


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
