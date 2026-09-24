#!/usr/bin/env python3
"""
DigitalCLIQ — Shared Post-Flight Self-Validation Module

Validates a finished report deliverable BEFORE success may be reported:
  1. Output location — file must live in the vault outputs/ folder, never Desktop.
  2. Branding — the DigitalCLIQ logo must actually be embedded in the file
     (image objects in the PDF pages / xl/media in the Excel zip).
  3. Page count — PDF page count or Excel sheet count within expected range.
  4. Placeholder scan — no template tokens, lorem ipsum, or unfilled fields.

Design rule: NO silent failure. Every check either passes or is reported as a
loud failure with the reason. Unexpected exceptions inside a check are recorded
as failures with the full message — never swallowed. Exit code 0 = all passed,
1 = at least one failure.

CLI:
    python3 post_flight.py <file> [--min-pages N] [--max-pages N]
        [--min-sheets N] [--no-logo-every-page] [--json]

Import from a skill:
    sys.path.insert(0, "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills")
    from post_flight import validate_report
    result = validate_report(path, min_pages=5)
    if not result["passed"]:
        raise RuntimeError(result["summary"])
"""

import os
import re
import sys
import json
import zipfile

VAULT_OUTPUTS = "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/outputs"
CANONICAL_LOGO = ("/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Resources/brand-assets/"
                  "digital-cliq-logo-solid-1000px-wide.png")

# Tokens that should never appear in a finished client deliverable.
PLACEHOLDER_LITERALS = [
    "placeholder", "lorem ipsum", "[insert", "<insert", "your text here",
    "sample data", "tktk", "todo:", "fixme", "xxxxx",
    "dealer name here", "client name here",
]
# Unfilled template tokens like {dealer_name}, {{date}}, YYYY-MM-DD left literal
PLACEHOLDER_PATTERNS = [
    re.compile(r"\{\{?[a-z_]+\}?\}", re.IGNORECASE),
    re.compile(r"\bYYYY-MM-DD\b"),
    re.compile(r"\bMM/DD/YYYY\b"),
]


# ---------------------------------------------------------------------------
# File-type readers
# ---------------------------------------------------------------------------
def _read_pdf(path):
    """Return (page_count, images_per_page, full_text). Loud on parse failure."""
    import logging
    import warnings
    import pdfplumber
    # pdfminer is chatty about cosmetic color-space quirks; those are not failures
    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    pages_text = []
    images_per_page = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                images_per_page.append(len(page.images))
                pages_text.append(page.extract_text() or "")
    return len(images_per_page), images_per_page, "\n".join(pages_text)


def _read_xlsx(path):
    """Return (sheet_count, embedded_media, full_text)."""
    import openpyxl
    with zipfile.ZipFile(path) as z:
        media = [n for n in z.namelist() if n.startswith("xl/media/")]
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    texts = []
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            for v in row:
                if isinstance(v, str):
                    texts.append(v)
    return len(wb.sheetnames), media, "\n".join(texts)


# ---------------------------------------------------------------------------
# Individual checks — each returns (passed: bool, detail: str)
# ---------------------------------------------------------------------------
def check_output_location(path):
    resolved = os.path.realpath(path)
    outputs = os.path.realpath(VAULT_OUTPUTS)
    if resolved.startswith(outputs + os.sep):
        return True, f"Saved to vault outputs/: {resolved}"
    hint = ""
    desktop = os.path.realpath(os.path.expanduser("~/Desktop"))
    if resolved.startswith(desktop) and "DigitalCLIQ" not in resolved:
        hint = " — file landed on the Desktop, the exact failure mode this check exists for"
    return False, (f"File is NOT in the vault outputs folder.{hint}\n"
                   f"  actual:   {resolved}\n"
                   f"  expected: under {outputs}/")


def check_branding_pdf(page_count, images_per_page, require_every_page=True):
    if page_count == 0:
        return False, "PDF has zero pages"
    if images_per_page[0] == 0:
        return False, ("Page 1 has NO embedded images — the DigitalCLIQ logo did not "
                       "render. Check the logo path and remove any try/except hiding "
                       f"the failure. Canonical logo: {CANONICAL_LOGO}")
    if require_every_page:
        bare = [i + 1 for i, n in enumerate(images_per_page) if n == 0]
        if bare:
            return False, (f"Pages missing the header logo image: {bare}. "
                           "Every page of a DigitalCLIQ report carries the logo.")
    return True, f"Logo image present on all {page_count} pages"


def check_branding_xlsx(media):
    images = [m for m in media if m.lower().endswith((".png", ".jpg", ".jpeg", ".gif"))]
    if not images:
        return False, ("No embedded images in the workbook — the DigitalCLIQ logo "
                       "is missing. A black tile without the logo is NOT compliant. "
                       f"Canonical logo: {CANONICAL_LOGO}")
    return True, f"Embedded brand image(s): {', '.join(images)}"


def check_page_count(count, unit, min_count=None, max_count=None):
    if min_count is not None and count < min_count:
        return False, (f"Only {count} {unit} — expected at least {min_count}. "
                       "The report is likely truncated or a section silently failed.")
    if max_count is not None and count > max_count:
        return False, f"{count} {unit} — expected at most {max_count}."
    return True, f"{count} {unit} (within expected range)"


def check_no_placeholders(full_text):
    findings = []
    lowered = full_text.lower()
    for token in PLACEHOLDER_LITERALS:
        idx = lowered.find(token)
        if idx != -1:
            context = full_text[max(0, idx - 30):idx + len(token) + 30].replace("\n", " ")
            findings.append(f"literal '{token}' near: …{context}…")
    for pat in PLACEHOLDER_PATTERNS:
        m = pat.search(full_text)
        if m:
            start = max(0, m.start() - 30)
            context = full_text[start:m.end() + 30].replace("\n", " ")
            findings.append(f"pattern '{m.group(0)}' near: …{context}…")
    if findings:
        return False, "Placeholder data remains in the deliverable:\n  - " + "\n  - ".join(findings)
    return True, "No placeholder tokens found"


# ---------------------------------------------------------------------------
# Master validator
# ---------------------------------------------------------------------------
def validate_report(path, min_pages=None, max_pages=None, min_sheets=None,
                    logo_every_page=True):
    """
    Run all post-flight checks on a finished deliverable.

    Returns dict: {passed, file, kind, checks: [{name, passed, detail}], summary}
    """
    checks = []

    def run(name, fn, *args, **kwargs):
        try:
            passed, detail = fn(*args, **kwargs)
        except Exception as e:
            passed, detail = False, f"check crashed: {type(e).__name__}: {e}"
        checks.append({"name": name, "passed": passed, "detail": detail})
        return passed

    if not os.path.isfile(path):
        checks.append({"name": "file_exists", "passed": False,
                       "detail": f"File does not exist: {path}"})
        return _finish(path, "missing", checks)

    ext = os.path.splitext(path)[1].lower()
    run("output_location", check_output_location, path)

    if ext == ".pdf":
        try:
            page_count, images_per_page, full_text = _read_pdf(path)
        except Exception as e:
            checks.append({"name": "readable", "passed": False,
                           "detail": f"Could not parse PDF: {type(e).__name__}: {e}"})
            return _finish(path, "pdf", checks)
        run("branding_logo", check_branding_pdf, page_count, images_per_page,
            require_every_page=logo_every_page)
        run("page_count", check_page_count, page_count, "pages", min_pages, max_pages)
        run("no_placeholders", check_no_placeholders, full_text)
        return _finish(path, "pdf", checks)

    if ext in (".xlsx", ".xlsm"):
        try:
            sheet_count, media, full_text = _read_xlsx(path)
        except Exception as e:
            checks.append({"name": "readable", "passed": False,
                           "detail": f"Could not parse workbook: {type(e).__name__}: {e}"})
            return _finish(path, "xlsx", checks)
        run("branding_logo", check_branding_xlsx, media)
        run("sheet_count", check_page_count, sheet_count, "sheets", min_sheets, None)
        run("no_placeholders", check_no_placeholders, full_text)
        return _finish(path, "xlsx", checks)

    checks.append({"name": "file_type", "passed": False,
                   "detail": f"Unsupported deliverable type '{ext}' — expected .pdf or .xlsx"})
    return _finish(path, ext, checks)


def _finish(path, kind, checks):
    passed = all(c["passed"] for c in checks)
    failures = [c for c in checks if not c["passed"]]
    if passed:
        summary = f"POST-FLIGHT PASSED — {os.path.basename(path)} ({len(checks)} checks)"
    else:
        lines = [f"POST-FLIGHT FAILED — {os.path.basename(path)} "
                 f"({len(failures)}/{len(checks)} checks failed)"]
        for c in failures:
            lines.append(f"  ❌ {c['name']}: {c['detail']}")
        summary = "\n".join(lines)
    return {"passed": passed, "file": path, "kind": kind,
            "checks": checks, "summary": summary}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def main(argv):
    import argparse
    p = argparse.ArgumentParser(description="DigitalCLIQ post-flight report validation")
    p.add_argument("file", help="Finished deliverable (.pdf or .xlsx)")
    p.add_argument("--min-pages", type=int, default=None)
    p.add_argument("--max-pages", type=int, default=None)
    p.add_argument("--min-sheets", type=int, default=None)
    p.add_argument("--no-logo-every-page", action="store_true",
                   help="Only require the logo on page 1 (PDF)")
    p.add_argument("--json", action="store_true", help="Emit full JSON report")
    args = p.parse_args(argv)

    result = validate_report(
        args.file,
        min_pages=args.min_pages,
        max_pages=args.max_pages,
        min_sheets=args.min_sheets,
        logo_every_page=not args.no_logo_every_page,
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for c in result["checks"]:
            mark = "✅" if c["passed"] else "❌"
            print(f"{mark} {c['name']}: {c['detail']}")
        print()
        print(result["summary"])

    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
