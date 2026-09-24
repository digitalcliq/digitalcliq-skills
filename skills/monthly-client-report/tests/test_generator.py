#!/usr/bin/env python3
"""Smoke tests for the monthly report generator: graceful omission + email
guard + HTML pipeline (canonical cover page, no reportlab)."""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
GEN = os.path.join(HERE, "..", "generate_monthly_report.py")
LOGO = "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Resources/brand-assets/digital-cliq-logo-solid-1000px-wide.png"


def run(data, out):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        path = f.name
    r = subprocess.run([sys.executable, GEN, path, out, LOGO],
                       capture_output=True, text=True)
    os.unlink(path)
    return r


def test_minimal_omission():
    """A sparse client (only metadata + wins) must still render, no crash."""
    data = {
        "metadata": {"client_name": "Kasama Coffee Collective", "client_code": "KCC",
                     "month_label": "May 2026", "city": "", "state": "California", "brand": ""},
        "exec_summary": "Quiet but steady month for the cafe.",
        "wins": {"items": ["Refreshed the seasonal menu landing page."], "challenges": []},
    }
    out = os.path.join(tempfile.gettempdir(), "mcr_test_minimal.pdf")
    r = run(data, out)
    assert r.returncode == 0, f"minimal render failed: {r.stderr}"
    assert os.path.exists(out), "no PDF produced"
    # HTML pipeline: dark cover page + at least one interior page.
    import fitz
    doc = fitz.open(out)
    assert doc.page_count >= 2, f"expected cover + interior, got {doc.page_count} page(s)"
    doc.close()
    print("PASS: graceful omission (sparse client renders, cover + interior)")
    os.unlink(out)


def test_no_reportlab():
    """The generator must use the design-system HTML pipeline, never reportlab."""
    import re
    with open(GEN) as f:
        src = f.read()
    assert not re.search(r"^\s*(?:import|from)\s+reportlab", src, re.MULTILINE), \
        "generator still imports reportlab"
    assert "render_pdf" in src and "--print-to-pdf" in src, \
        "HTML render pipeline (WeasyPrint/Chrome) not found in generator"
    print("PASS: generator is reportlab-free (HTML + WeasyPrint/Chrome pipeline)")


def test_email_guard():
    """gmail address anywhere must hard-fail the render."""
    data = {
        "metadata": {"client_name": "X", "month_label": "May 2026"},
        "exec_summary": "Contact digitalcliq@gmail.com for details.",
    }
    out = os.path.join(tempfile.gettempdir(), "mcr_test_guard.pdf")
    r = run(data, out)
    assert r.returncode != 0, "email guard did NOT fire on gmail address"
    assert "gmail" in r.stderr.lower()
    print("PASS: email guard rejects gmail")


def test_missing_metadata():
    data = {"exec_summary": "no metadata"}
    out = os.path.join(tempfile.gettempdir(), "mcr_test_nometa.pdf")
    r = run(data, out)
    assert r.returncode != 0, "missing-metadata did not fail"
    print("PASS: missing metadata fails loudly")


if __name__ == "__main__":
    test_minimal_omission()
    test_email_guard()
    test_missing_metadata()
    test_no_reportlab()
    print("\nAll generator smoke tests passed.")
