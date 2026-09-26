#!/usr/bin/env python3
"""Preflight for dealership-forecast-tool: stop early on a machine that cannot run it.

Standard library only. Never installs anything.

    python3 preflight.py --vault "<vault root>"

Exit codes
  0  ready: prints the recalc command to use
  2  wrong machine: Python older than 3.10 or no LibreOffice. Stop and run the
     skill in Cowork. Do not pip install here, do not improvise models, do not
     skip the recalc.
  3  capable machine with missing packages: prints the Cowork-only install line
  4  vault, white logo or outputs/ not reachable: a missing logo stops the build
  5  capable machine (Python 3.10+, LibreOffice) but the installed xlsx skill's
     scripts/recalc.py was not found: set XLSX_RECALC to its full path and re-run

recalc.py search order: $XLSX_RECALC, the sibling xlsx skill next to this one
(skills-plugin runtime), /mnt/skills/*/xlsx (Cowork mount; a fallback search,
not an instruction), then any */skills/xlsx two levels up.
"""

from __future__ import print_function

import argparse
import glob
import importlib
import os
import shutil
import sys

MODULES = ("pandas", "numpy", "scipy", "statsmodels", "prophet", "openpyxl")
PIP_LINE = ("pip install prophet statsmodels openpyxl pandas numpy scipy "
            "--break-system-packages   # Cowork only")
DEFAULT_VAULT = "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ"
WHITE_LOGO = os.path.join("Resources", "brand-assets", "digital-cliq-logo-solid-1000px-wide.png")
COWORK_MSG = ("STOP: this machine cannot run /dealership-forecast-tool. Run it in Cowork. "
              "Do not pip install here, do not improvise the models in plain Python, "
              "and do not skip the recalc.")
RECALC_MSG = ("STOP: Python and LibreOffice are fine here, but the installed xlsx skill's "
              "scripts/recalc.py was not found. Find it (it ships with the xlsx skill), then "
              "export XLSX_RECALC=\"/full/path/to/xlsx/scripts/recalc.py\" and re-run this "
              "preflight. Do not skip the recalc.")


def find_recalc(skill_dir):
    env = os.environ.get("XLSX_RECALC")
    cands = [env] if env else []
    cands.append(os.path.join(os.path.dirname(skill_dir), "xlsx", "scripts", "recalc.py"))
    cands += sorted(glob.glob("/mnt/skills/*/xlsx/scripts/recalc.py"))
    cands += sorted(glob.glob(os.path.join(os.path.dirname(os.path.dirname(skill_dir)), "*", "skills",
                                           "xlsx", "scripts", "recalc.py")))
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description="dealership-forecast-tool preflight")
    ap.add_argument("--vault", default=os.environ.get("DIGITALCLIQ_VAULT_ROOT", DEFAULT_VAULT))
    a = ap.parse_args(argv)
    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    wrong = []
    if sys.version_info < (3, 10):
        wrong.append("python3 is {}.{}; the models and the xlsx recalc need 3.10+".format(*sys.version_info[:2]))
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        wrong.append("LibreOffice (soffice) is not on PATH; the recalc and the render gate need it")
    recalc = find_recalc(skill_dir)
    if not recalc and wrong:
        wrong.append("the installed xlsx skill's scripts/recalc.py was not found")
    if os.environ.get("XLSX_RECALC") and not recalc:
        print("XLSX_RECALC is set but is not a file: " + os.environ["XLSX_RECALC"])
    missing = []
    for m in MODULES:
        try:
            importlib.import_module(m)
        except Exception:  # any import failure means the module is unusable here
            missing.append(m)

    print("python   {}".format(sys.version.split()[0]))
    print("soffice  {}".format(soffice or "MISSING"))
    print("recalc   {}".format(recalc or "MISSING"))
    print("modules  missing: {}".format(", ".join(missing) or "none"))

    if wrong:
        for w in wrong:
            print("  - " + w)
        print(COWORK_MSG)
        return 2
    if not recalc:
        print(RECALC_MSG)
        return 5
    if missing:
        print("Missing packages on a capable machine. Install, then re-run this preflight:")
        print("  " + PIP_LINE)
        return 3

    vault = a.vault
    logo = os.path.join(vault, WHITE_LOGO)
    problems = []
    if not os.path.isdir(vault):
        problems.append("vault root not found: " + vault)
    if not os.path.isfile(logo):
        problems.append("white logo not found: " + logo + " (a missing logo stops the build)")
    if not os.path.isdir(os.path.join(vault, "outputs")):
        problems.append("outputs/ staging folder not found under " + vault)
    if problems:
        for p in problems:
            print("  - " + p)
        print("STOP: fix the vault path (--vault) before building.")
        return 4

    print("READY. Recalc (at most 3 attempts), run from the xlsx skill's scripts folder:")
    print('  cd "{}" && python3 recalc.py "<workbook.xlsx>" 30'.format(os.path.dirname(recalc)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
