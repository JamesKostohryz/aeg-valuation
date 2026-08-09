#!/usr/bin/env python3
"""test_orphan_modules.py — the standing check for the failure mode that hid the convergence
period for weeks.

pipeline/convergence.py was written, tested, and reported PASS by the regression harness on
every single run — while being imported by nothing except its own test. It was absent from
every valuation, every output, every manifest and every report, and no check in this project
could see that, because a green unit test on an unused module looks exactly like a green unit
test on a wired one.

This test fails when any module in pipeline/ has no importer outside its own test file. It is
deliberately crude: it greps for `import <name>` and `from <name> import` across every .py in
the repository. A module that is genuinely standalone (an entry point, a one-off tool) is
declared in STANDALONE below with the reason, so the exemption is a written decision rather
than a silent gap.

Cheap to run, no LibreOffice, no fixtures.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPE = os.path.join(ROOT, "pipeline")

# Modules that legitimately have no importer. Each needs a reason, not just a name.
STANDALONE = {
    "run_company": "the per-company entry point; CI and the cockpit invoke it as a script",
    "onboard": "operator entry point for adding a ticker; invoked as a script",
    "diagnose_tie": "diagnostic tool run by hand when a tie residual needs investigating",
    "validate_load": "diagnostic tool run by hand against a built workbook",
    "run_scenarios": "imported lazily inside run_company's scenario branch (grep-visible there)",
}

# A statement-form import must start a line; a dynamic __import__("name") can appear anywhere
# (extract.py wires several feeds that way, inside lambdas), so it is matched unanchored.
IMPORT_RE = ("(^|\\n)\\s*(import\\s+{m}\\b|from\\s+{m}\\s+import\\b)"
             "|__import__\\(\\s*[\"']{m}[\"']\\s*\\)")


def _py_files():
    for base, dirs, names in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "outputs", "_work")]
        for n in names:
            if n.endswith(".py"):
                yield os.path.join(base, n)


def main():
    modules = sorted(n[:-3] for n in os.listdir(PIPE)
                     if n.endswith(".py") and not n.startswith("test_") and n != "__init__.py")
    sources = {}
    for path in _py_files():
        try:
            with open(path, encoding="utf-8") as fh:
                sources[path] = fh.read()
        except Exception:
            continue

    fails = 0
    for mod in modules:
        own = {os.path.join(PIPE, f"{mod}.py"), os.path.join(PIPE, f"test_{mod}.py"),
               os.path.join(ROOT, f"test_{mod}.py")}
        pat = re.compile(IMPORT_RE.format(m=re.escape(mod)))
        importers = sorted(os.path.relpath(p, ROOT) for p, src in sources.items()
                           if p not in own and pat.search(src))
        if importers:
            print(f"  PASS  {mod}: imported by {importers[0]}"
                  + (f" (+{len(importers) - 1} more)" if len(importers) > 1 else ""))
        elif mod in STANDALONE:
            print(f"  PASS  {mod}: declared standalone — {STANDALONE[mod]}")
        else:
            fails += 1
            print(f"  FAIL  {mod}: NO importer outside its own test. Either wire it into the "
                  f"pipeline or declare it in STANDALONE with a reason. A tested-but-unimported "
                  f"module is invisible to every check this project runs.")

    print(f"\n{'ALL MODULES WIRED OR DECLARED' if fails == 0 else f'{fails} ORPHANED MODULE(S)'}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
