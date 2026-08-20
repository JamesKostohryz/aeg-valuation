#!/usr/bin/env python3
"""
test_workflow_deps.py — every workflow installs from requirements.txt, and requirements.txt
covers what the code actually imports.

WHY THIS EXISTS. requirements.txt opens by calling itself "the Python dependency source of truth
(all workflows: run_valuation.yml, valuation.yml, regression.yml)". On 2026-08-19 that sentence
was false: valuation.yml and valuation_request.yml ran `pip install openpyxl==3.1.5 pyyaml`, a
hand-kept list that had drifted, and idio_universe.yml installed pytest alone.

It cost two days across two separate incidents in one afternoon.

  * The market-data consolidation moved company prices onto a parquet panel. pyarrow never
    reached the runner, ModuleNotFoundError escaped eodhd_puller.pull_to_csvs(), and KO and PEP
    -- the only two companies with a reviewed forecast, the only two that could publish anything
    -- crashed on every fleet run, hidden behind fourteen intended refusals.
  * The regression harness gained a pytest suite and went red reporting "<no output>", because
    pytest was not in requirements.txt either.

Neither was a hard problem. Both were invisible, and a dependency list nothing reads is a
comment. This is a WIRING check in the same spirit as test_orphan_modules.py: it does not test
behaviour, it tests that the thing which is supposed to be connected is connected.

Deliberately dependency-free -- no yaml import, plain text scanning -- so it can never be the
test that fails for want of a package.
"""
import os
import re
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
WF_DIR = os.path.join(_ROOT, ".github", "workflows")
REQ = os.path.join(_ROOT, "requirements.txt")

_fail = 0


def check(cond, msg):
    global _fail
    print(f"  {'PASS' if cond else 'FAIL'}  {msg}")
    if not cond:
        _fail += 1


def requirements():
    names = set()
    for ln in open(REQ):
        ln = ln.split("#", 1)[0].strip()
        if ln:
            names.add(re.split(r"[=<>!\[; ]", ln, 1)[0].strip().lower())
    return names


def main():
    req = requirements()
    print(f"requirements.txt declares: {', '.join(sorted(req))}")

    # 1. THE WIRING. Any workflow that installs Python packages at all must install from the
    #    source of truth. A workflow may add packages on top (LibreOffice, a one-off tool); it
    #    may not install a hand-kept substitute for the list.
    for fn in sorted(os.listdir(WF_DIR)):
        if not fn.endswith((".yml", ".yaml")):
            continue
        text = open(os.path.join(WF_DIR, fn)).read()
        installs = [ln.strip() for ln in text.splitlines()
                    if re.search(r"^\s*(run:\s*)?pip install", ln)
                    and "--upgrade pip" not in ln]
        if not installs:
            continue
        from_req = [ln for ln in installs if "-r requirements.txt" in ln]
        hand = [ln for ln in installs if "-r requirements.txt" not in ln]
        check(bool(from_req),
              f"{fn} installs from requirements.txt")
        check(not hand,
              f"{fn} keeps no hand-written package list alongside it"
              + (f" (found: {hand})" if hand else ""))

    # 2. THE CONTENT. Every third-party package the repository imports at module scope has to be
    #    in the list. Scanned from the source rather than asserted, so a new import cannot be
    #    added without either declaring it or failing here.
    # `concurrent` (concurrent.futures) added 2026-08-20 with idio/bond_reprice.py. It is
    # standard library and always has been; the list was simply incomplete. Widening the list is
    # correct here -- the guard's job is to catch an UNDECLARED THIRD-PARTY import, and a false
    # positive on a stdlib module is how a guard trains people to ignore it.
    STDLIB_OK = {"os", "sys", "csv", "json", "math", "re", "gzip", "zlib", "shutil", "time",
                 "concurrent",
                 "datetime", "argparse", "subprocess", "itertools", "tempfile", "hashlib",
                 "urllib", "collections", "typing", "glob", "textwrap", "copy", "random",
                 "statistics", "functools", "dataclasses", "pathlib", "warnings", "traceback",
                 "unittest", "io", "base64", "decimal", "string", "importlib", "contextlib",
                 "zipfile", "socket", "ssl", "http", "pprint", "operator", "bisect", "enum",
                 "abc", "inspect", "logging", "platform", "signal", "struct", "uuid", "calendar",
                 "ast", "difflib", "fnmatch", "queue", "threading", "unicodedata", "getpass",
                 "secrets", "shlex", "sqlite3", "codecs", "locale", "numbers", "pickle"}
    ALIASES = {"yaml": "pyyaml", "pyarrow": "pyarrow", "dateutil": "python-dateutil",
               "PIL": "pillow", "sklearn": "scikit-learn"}
    LOCAL = {os.path.splitext(f)[0] for r, _, fs in os.walk(_ROOT) for f in fs
             if f.endswith(".py")} | {"normalization", "pipeline", "idio", "tests", "valuation"}

    # Parsed with `ast`, not scanned with a regular expression. Two reasons, and the second is
    # the one that matters: a regex reads the word "import" inside a docstring and reports the
    # next word as a package, and it only sees imports at the left margin. The import that
    # actually broke the pipeline -- `import pyarrow.parquet` -- sits INSIDE a function, twelve
    # spaces in, which is exactly where a lazily-imported optional dependency always lives.
    import ast
    missing = {}
    for root, dirs, files in os.walk(_ROOT):
        dirs[:] = [d for d in dirs if not d.startswith((".", "_")) and d != "archive"]
        for f in files:
            if not f.endswith(".py"):
                continue
            path = os.path.join(root, f)
            try:
                tree = ast.parse(open(path, errors="replace").read())
            except SyntaxError:
                continue
            mods = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    mods |= {a.name.split(".")[0] for a in node.names}
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    mods.add(node.module.split(".")[0])
            for mod in mods:
                if mod in STDLIB_OK or mod in LOCAL or mod.startswith("_"):
                    continue
                pkg = ALIASES.get(mod, mod).lower()
                if pkg not in req:
                    missing.setdefault(pkg, os.path.relpath(path, _ROOT))
    check(not missing,
          "every imported third-party package is declared in requirements.txt"
          + (f" — MISSING: {missing}" if missing else ""))

    print(f"\n{'test_workflow_deps: ALL PASS' if _fail == 0 else f'{_fail} FAILED'}")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
