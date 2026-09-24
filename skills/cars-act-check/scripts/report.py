#!/usr/bin/env python3
"""Merge findings from all agents, diff vs prior run, emit compact markdown.
The model adds only the executive summary on top; everything else is built here."""
import argparse, json, os, time

SEV_LABEL = {"C": "CRITICAL", "M": "MAJOR", "m": "minor"}
SEV_ORDER = {"C": 0, "M": 1, "m": 2}

def load(path):
    return json.load(open(path)) if os.path.exists(path) else None

def key(f):
    return (f.get("id"), f.get("url"), f.get("summary"))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--state", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--client", default="CLIENT")
    args = ap.parse_args()
    date = time.strftime("%Y-%m-%d")
    enforcement = date >= "2026-10-01"
    mode = "ENFORCEMENT" if enforcement else "READINESS (CARS Act operative 2026-10-01)"

    findings = []
    det = load(os.path.join(args.data, "findings.json"))
    if det:
        findings += det["findings"]
    for extra in ("browser_findings.json", "ad_findings.json"):
        blob = load(os.path.join(args.data, extra))
        if isinstance(blob, list):
            findings += blob
        elif isinstance(blob, dict) and blob.get("skipped"):
            findings.append({"id": extra, "point": 0, "severity": "m",
                "citation": "n/a", "url": "n/a",
                "summary": f"{extra} SKIPPED: {blob.get('reason','no reason given')}",
                "evidence": ""})

    prior_path = os.path.join(args.state, "prior_findings.json")
    prior = {tuple(k) for k in (load(prior_path) or [])}
    now = {key(f) for f in findings}
    for f in findings:
        f["status"] = "RECURRING" if key(f) in prior else "NEW"
    resolved = prior - now
    findings.sort(key=lambda f: (SEV_ORDER.get(f["severity"], 3), f.get("status") != "NEW"))

    lines = [f"# CARS Act Check: {args.client} ({date})", "",
             f"**Mode:** {mode}", "",
             "<!-- EXEC SUMMARY GOES HERE -->", "",
             f"**Totals:** {sum(1 for f in findings if f['severity']=='C')} CRITICAL, "
             f"{sum(1 for f in findings if f['severity']=='M')} MAJOR, "
             f"{sum(1 for f in findings if f['severity']=='m')} minor. "
             f"{sum(1 for f in findings if f['status']=='NEW')} new, {len(resolved)} resolved since last run.", ""]
    gap = "gap to close before Oct 1" if not enforcement else "violation exposure"
    for sev in ("C", "M", "m"):
        group = [f for f in findings if f["severity"] == sev]
        if not group:
            continue
        lines.append(f"## {SEV_LABEL[sev]} ({gap})" if sev != "m" else "## Minor / hygiene")
        for f in group:
            lines.append(f"- **[{f['status']}] Pt {f.get('point','?')} ({f.get('id','')})** "
                         f"{f['summary']}. Cite: {f.get('citation','')}. URL: {f.get('url','')}"
                         + (f". Evidence: {f['evidence']}" if f.get("evidence") else ""))
        lines.append("")
    if resolved:
        lines.append("## Resolved since last run")
        for rid, url, summ in sorted(resolved):
            lines.append(f"- {rid}: {summ} ({url})")
        lines.append("")
    lines.append("## Fix guidance")
    lines.append("Each finding above maps to a fix in references/inspection-points.md; "
                 "group MAJOR items by page template so one CMS/theme change clears many at once. "
                 "Frame all items as leadership discussion topics.")

    out_md = os.path.join(args.out, f"CARS_Act_Check_{args.client}_{date}.md")
    open(out_md, "w").write("\n".join(lines))
    json.dump([list(k) for k in now], open(prior_path, "w"))
    print(f"report: {out_md} | findings: {len(findings)} | resolved: {len(resolved)}")

if __name__ == "__main__":
    main()
