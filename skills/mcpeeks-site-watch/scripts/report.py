#!/usr/bin/env python3
"""Assemble the run: merge findings + sitehealth + browser-phase results, diff
against the previous run, classify what changed and why, and emit

  DATA/report.json      the single input for build_workbook.py
  DATA/run_summary.md   a compact brief the model reads to write exec_summary.txt

It also updates STATE/snapshot.json and STATE/history/<date>.json so the next
run can diff. No deliverable is produced here; build_workbook.py does that.

Usage:
  python3 report.py --data DATA_DIR --state STATE_DIR
"""
import argparse, datetime, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_catalog import (CATALOG, AREA_ORDER, AREA_LEGAL, AREA_ACCURACY,
                           AREA_HEALTH, AREA_PHONE, area_for, clean_text)

VDP_RE = re.compile(r"/inventory/display/(new|used|certified)/(\d{4})/([^/]+)/([^/]+)/([A-Z0-9]{11,17})", re.I)


def key(f):
    return f"{f['check']}|{f.get('vin') or f.get('url')}"


def vehicle_from_url(url):
    m = VDP_RE.search(url or "")
    if not m:
        return {"condition": "", "year": "", "make": "", "model": "", "label": ""}
    cond, year, make, model, _vin = m.groups()
    make = make.replace("-", " ")
    model = model.replace("-", " ")
    cond = {"new": "New", "used": "Used", "certified": "Certified"}[cond.lower()]
    return {"condition": cond, "year": year, "make": make, "model": model,
            "label": f"{year} {make} {model}"}


def load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--state", required=True)
    ap.add_argument("--date", default=datetime.date.today().isoformat(),
                    help="override run date (testing only)")
    args = ap.parse_args()
    today = args.date

    findings = load(os.path.join(args.data, "findings.json"), None)
    if not findings:
        print("FATAL: findings.json missing; run checks.py first", file=sys.stderr)
        sys.exit(1)
    F = list(findings["findings"])

    # browser-phase findings (C03 prominence, C12 photo spot-check, C16, C17)
    bp = os.path.join(args.data, "browser_findings.json")
    if os.path.exists(bp):
        F += load(bp, [])

    # site health: SSL, redirects, Lighthouse
    sh = load(os.path.join(args.data, "sitehealth.json"), {})
    for r in sh.get("ssl", []):
        if r.get("flag"):
            F.append({"check": "C18", "severity": "hygiene", "url": r["host"],
                      "summary": r["flag"], "vin": None})
    for r in sh.get("redirects", []):
        if r.get("flag"):
            F.append({"check": "C19", "severity": "hygiene", "url": r["domain"],
                      "summary": f"{r['flag']}. Chain: {' > '.join(r['chain'][-3:])}", "vin": None})

    prev = load(os.path.join(args.state, "snapshot.json"), {})
    prev_lh = {r["url"]: r for r in prev.get("lighthouse", [])}
    lighthouse_rows = []
    for r in sh.get("lighthouse", []):
        if "error" in r:
            lighthouse_rows.append({"url": r["url"], "error": r["error"]})
            continue
        pl = prev_lh.get(r["url"], {})
        row = {"url": r["url"]}
        for c in ("performance", "seo", "accessibility", "best-practices"):
            row[c] = r.get(c)
            row["prev_" + c] = pl.get(c)
        row["lcp_s"] = r.get("lcp_s")
        lighthouse_rows.append(row)
        drops = [f"{c} {pl[c]} to {r[c]}" for c in ("performance", "seo", "accessibility", "best-practices")
                 if c in r and c in pl and r[c] < pl[c] - 4]
        if r.get("performance", 100) < 50 or drops:
            F.append({"check": "C14", "severity": "hygiene", "url": r["url"], "vin": None,
                      "summary": f"Lighthouse performance {r.get('performance')}" +
                                 (f"; regressions: {', '.join(drops)}" if drops else "")})

    # ---- enrich every finding ----
    first_seen = load(os.path.join(args.state, "first_seen.json"), {})
    inv = load(os.path.join(args.data, "inventory.json"), {})
    current_vins = {v.get("vin") for v in inv.get("vehicles", []) if v.get("vin")}
    prev_keys = set(prev.get("finding_keys", []))
    baseline = not prev_keys
    cur_keys = {key(f) for f in F}
    new_keys, resolved_keys = cur_keys - prev_keys, prev_keys - cur_keys

    for f in F:
        f["summary"] = clean_text(f.get("summary"))
        f["detail"] = clean_text(f.get("detail")) if f.get("detail") else ""
        f["area"] = area_for(f)
        f["vehicle"] = vehicle_from_url(f.get("url"))
        k = key(f)
        if baseline:
            f["status"] = "BASELINE"; f["status_note"] = "First run; no prior run to compare"
        elif k in new_keys:
            f["status"] = "NEW"
            vin = f.get("vin")
            if vin and first_seen.get(vin) == today:
                f["status_note"] = "New arrival on the lot"
            elif vin:
                f["status_note"] = "New issue on a vehicle that was already listed"
            else:
                f["status_note"] = "New since last run"
        else:
            f["status"] = "PERSISTING"; f["status_note"] = "Also flagged last run"

    resolved = []
    for k in sorted(resolved_keys):
        chk, ref = k.split("|", 1)
        if re.fullmatch(r"[A-Z0-9]{11,17}", ref) and ref in first_seen:
            if ref in current_vins:
                reason = "Fixed on the page (vehicle still listed)"
            else:
                reason = "Vehicle no longer listed (sold or delisted)"
        else:
            reason = "No longer detected"
        resolved.append({"check": chk, "name": CATALOG.get(chk, {}).get("name", chk),
                         "ref": ref, "reason": reason})

    # ---- counts ----
    counts, prev_counts = {}, prev.get("counts", {})
    for f in F:
        counts[f["check"]] = counts.get(f["check"], 0) + 1
    area_counts = {a: 0 for a in AREA_ORDER}
    for f in F:
        area_counts[f["area"]] = area_counts.get(f["area"], 0) + 1
    new_by_reason, res_by_reason = {}, {}
    for f in F:
        if f["status"] == "NEW":
            new_by_reason[f["status_note"]] = new_by_reason.get(f["status_note"], 0) + 1
    for r in resolved:
        res_by_reason[r["reason"]] = res_by_reason.get(r["reason"], 0) + 1

    # ---- fix list: one row per check (plus the C08 hygiene split), GM-ranked ----
    groups = {}
    for f in F:
        groups.setdefault((f["check"], f["area"]), []).append(f)
    fix_list = []
    for (chk, area), items in groups.items():
        cat = CATALOG.get(chk)
        if not cat:
            continue
        # prior snapshots count per check, not per (check, area); use the check total for the trend
        prev_n = prev_counts.get(chk, 0) if len([g for g in groups if g[0] == chk]) == 1 else None
        n = len(items)
        if baseline:
            trend = "Baseline"
        elif prev_n is None:
            trend = "See Scorecard"
        elif prev_n == 0:
            trend = "New this run"
        elif n > prev_n:
            trend = f"Up from {prev_n}"
        elif n < prev_n:
            trend = f"Down from {prev_n}"
        else:
            trend = f"Unchanged ({prev_n})"
        ex = next((i for i in items if i.get("vin")), items[0])
        example = (f"{ex['vehicle']['label']} (VIN {ex['vin']})" if ex.get("vin") and ex["vehicle"]["label"]
                   else (ex.get("vin") or ex.get("url") or ""))
        fix_list.append({"check": chk, "name": cat["name"], "area": area, "count": n,
                         "prev_count": prev_n, "trend": trend, "why": cat["why"],
                         "owner": cat["owner"], "fix": cat["fix"], "what": cat["what"],
                         "example": example, "example_url": ex.get("url"),
                         "weight": cat["weight"], "new": sum(1 for i in items if i["status"] == "NEW")})
    fix_list.sort(key=lambda r: (AREA_ORDER.index(r["area"]), -r["weight"], -r["count"]))
    for i, r in enumerate(fix_list, 1):
        r["priority"] = i

    # ---- area status labels ----
    def area_status(area, n):
        if n == 0:
            return "CLEAR"
        if area == AREA_LEGAL:
            return "ACTION NEEDED"
        if area == AREA_ACCURACY:
            return "ACTION NEEDED" if n >= 20 else "WATCH"
        return "WATCH"
    area_status_rows = []
    for a in AREA_ORDER:
        n = area_counts.get(a, 0)
        checks = sorted({f["check"] for f in F if f["area"] == a})
        if a == AREA_PHONE:
            label = "MANUAL CHECK"
            meaning = (f"{len(findings.get('phones_sitewide', {}))} numbers listed on the site need a test call "
                       "(Phone Checklist tab).")
            if n:
                meaning = f"{n} page(s) show a generic or dummy number, plus the manual test calls."
        else:
            label = area_status(a, n)
            if n == 0:
                meaning = "Nothing flagged this run."
            else:
                names = [CATALOG[c]["name"] for c in checks if c in CATALOG][:3]
                meaning = f"{n} open item(s) across {len(checks)} check(s): " + "; ".join(names) + "."
        area_status_rows.append({"area": a, "status": label, "open": n, "meaning": meaning})

    # ---- phones (diffed run over run) ----
    phones = findings.get("phones_sitewide", {})
    prev_phones = prev.get("phones", {})
    phone_rows = []
    for num, pages in sorted(phones.items()):
        if prev_phones and num not in prev_phones:
            chg = "NEW number"
        elif prev_phones and sorted(prev_phones.get(num, [])) != sorted(pages):
            chg = "Pages changed"
        else:
            chg = "Same as last run" if prev_phones else "Baseline"
        phone_rows.append({"number": num, "pages": pages, "change": chg})
    for num in sorted(set(prev_phones) - set(phones)):
        phone_rows.append({"number": num, "pages": prev_phones[num], "change": "REMOVED since last run"})

    report = {
        "meta": {"date": today, "prev_date": prev.get("date"), "baseline": baseline,
                 "vehicle_count": findings.get("vehicle_count"),
                 "prev_vehicle_count": prev.get("vehicle_count"),
                 "total": len(F), "new": len(new_keys) if not baseline else len(F),
                 "resolved": len(resolved_keys), "new_by_reason": new_by_reason,
                 "resolved_by_reason": res_by_reason, "site": "www.mcpeeks.com"},
        "area_counts": area_counts, "area_status": area_status_rows,
        "counts": counts, "prev_counts": prev_counts,
        "fix_list": fix_list, "findings": F, "resolved": resolved,
        "lighthouse": lighthouse_rows, "phones": phone_rows,
        "sitehealth": {"ssl": sh.get("ssl", []), "redirects": sh.get("redirects", [])},
    }
    with open(os.path.join(args.data, "report.json"), "w") as f:
        json.dump(report, f, indent=1)

    # ---- compact brief for the model ----
    L = [f"# Run brief {today} (prev run: {prev.get('date') or 'none, baseline'})",
         f"VDPs crawled: {findings.get('vehicle_count')} (prev {prev.get('vehicle_count')}). "
         f"Findings: {len(F)} total, {report['meta']['new']} new, {len(resolved_keys)} resolved.",
         "", "## By area"]
    for r in area_status_rows:
        L.append(f"- {r['area']}: {r['open']} open, {r['status']}. {r['meaning']}")
    L += ["", "## Fix list (priority order)"]
    for r in fix_list:
        L.append(f"{r['priority']}. {r['check']} {r['name']}: {r['count']} ({r['trend']}), "
                 f"{r['new']} new. Owner: {r['owner']}. Example: {r['example']}")
    L += ["", "## Why findings are new / resolved"]
    for k, v in new_by_reason.items():
        L.append(f"- NEW, {k}: {v}")
    for k, v in res_by_reason.items():
        L.append(f"- RESOLVED, {k}: {v}")
    L += ["", "## Site-wide items (read these; they are few)"]
    for f in F:
        if not f.get("vin"):
            L.append(f"- {f['check']} [{f['status']}] {f['url']}: {f['summary'][:300]}")
    L += ["", "## Notable per-VIN examples (largest dollar exposure first)"]
    dollar = []
    for f in F:
        amts = [float(x.replace(",", "")) for x in re.findall(r"\$([\d,]+)", f.get("summary", ""))]
        if amts and f.get("vin"):
            dollar.append((max(amts), f))
    for _, f in sorted(dollar, key=lambda t: -t[0])[:8]:
        L.append(f"- {f['check']} {f['vehicle']['label']} VIN {f['vin']}: {f['summary'][:200]}")
    L += ["", "## Phones", *[f"- {p['number']} ({p['change']}): {', '.join(map(str, p['pages']))[:100]}" for p in phone_rows]]
    if not lighthouse_rows:
        L += ["", "NOTE: no Lighthouse data this run (sitehealth ran with --skip-lighthouse or Node missing)."]
    with open(os.path.join(args.data, "run_summary.md"), "w") as f:
        f.write("\n".join(L))

    # ---- persist state for next run ----
    snapshot = {"date": today, "finding_keys": sorted(cur_keys), "counts": counts,
                "lighthouse": sh.get("lighthouse", []), "vehicle_count": findings.get("vehicle_count"),
                "phones": phones, "vins": sorted(current_vins)}
    os.makedirs(os.path.join(args.state, "history"), exist_ok=True)
    with open(os.path.join(args.state, "snapshot.json"), "w") as f:
        json.dump(snapshot, f, indent=1)
    with open(os.path.join(args.state, "history", f"{today}.json"), "w") as f:
        json.dump(snapshot, f)

    print("\n".join(L[:12]))
    print(f"\nreport.json + run_summary.md written to {args.data}")


if __name__ == "__main__":
    main()
