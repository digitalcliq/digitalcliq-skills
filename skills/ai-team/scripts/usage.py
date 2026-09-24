#!/usr/bin/env python3
"""Shift stats for the DigitalCLIQ AI team: minutes and tokens per player.

Reads the Claude Code transcript of the lead session plus its teammate transcripts
(~/.claude/projects/<project>/<session>.jsonl and <session>/subagents/*.jsonl) and
prints, per player, first and last activity, minutes, and token totals.
Standard library only. Tokens are what the API reported; no cost is computed here.

  python3 .claude/skills/ai-team/scripts/usage.py                 newest session touched today
  python3 .claude/skills/ai-team/scripts/usage.py --session ID    a specific lead session id
  python3 .claude/skills/ai-team/scripts/usage.py --since 08:50   only messages after HH:MM local today
  add --md to print a markdown block for the brief
  python3 .claude/skills/ai-team/scripts/usage.py --hung 5     hang watchdog: players with no API call for 5+ minutes
                                                              (exit 1 if any; a released player also shows, ignore those)
"""
import argparse, datetime as dt, glob, json, os, re, sys

PROJECT = os.path.expanduser("~/.claude/projects/-Users-drewmoon-Desktop-DigitalCLIQ-Brain-HQ")
PLAYERS = ["magic", "kobe", "shaq", "luka", "worthy", "nick"]

def player_of(path):
    m = re.search(r"agent-a?([A-Za-z]+)-[0-9a-f]+\.jsonl$", os.path.basename(path))
    if m and m.group(1).lower() in PLAYERS:
        return m.group(1).lower()
    return "magic" if "/subagents/" not in path else "other"

def parse_ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone()

def last_api_call(path):
    """Timestamp of the last assistant record (the last API call), or None."""
    last = None
    for line in open(path, encoding="utf-8", errors="replace"):
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("type") == "assistant" and d.get("timestamp"):
            last = parse_ts(d["timestamp"])
    return last

def hung_report(files, minutes):
    """Players whose last API call is older than `minutes`. A teammate waiting on a permission
    prompt, or otherwise stuck, keeps status `running` while making no API calls, so ListAgents
    cannot see it and this is the only tell (learned 2026-09-21)."""
    now = dt.datetime.now().astimezone()
    hung = []
    for f in files:
        p = player_of(f)
        if p in ("magic", "other"):
            continue
        last = last_api_call(f)
        if last is None:
            continue
        idle = (now - last).total_seconds() / 60
        if idle >= minutes:
            hung.append((p, last, idle))
    if not hung:
        print(f"no player idle {minutes}+ minutes")
        return 0
    for p, last, idle in hung:
        print(f"{p:7s} HUNG  last API call {last.strftime('%H:%M:%S')}, idle {idle:.1f} min")
    print("stop each hung player with TaskStop, then respawn it or take its lane (a released player also shows here; ignore those)")
    return 1

def scan(path, since):
    first = last = None
    tot = {"input": 0, "cache_read": 0, "cache_create": 0, "output": 0, "calls": 0}
    model = None
    for line in open(path, encoding="utf-8", errors="replace"):
        try:
            d = json.loads(line)
        except Exception:
            continue
        ts = d.get("timestamp")
        if not ts:
            continue
        t = parse_ts(ts)
        if since and t < since:
            continue
        m = d.get("message")
        if d.get("type") == "assistant" and isinstance(m, dict) and m.get("usage"):
            u = m["usage"]
            tot["input"] += u.get("input_tokens", 0)
            tot["cache_read"] += u.get("cache_read_input_tokens", 0)
            tot["cache_create"] += u.get("cache_creation_input_tokens", 0)
            tot["output"] += u.get("output_tokens", 0)
            tot["calls"] += 1
            model = m.get("model") or model
        first = t if first is None or t < first else first
        last = t if last is None or t > last else last
    return first, last, tot, model

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session")
    ap.add_argument("--since", help="HH:MM local, today")
    ap.add_argument("--md", action="store_true")
    ap.add_argument("--hung", type=float, metavar="MINUTES", help="watchdog: list players with no API call for MINUTES+")
    a = ap.parse_args()
    since = None
    if a.since:
        h, mnt = map(int, a.since.split(":"))
        since = dt.datetime.now().astimezone().replace(hour=h, minute=mnt, second=0, microsecond=0)
    if a.session:
        lead = os.path.join(PROJECT, a.session + ".jsonl")
    else:
        today = dt.date.today()
        cands = [p for p in glob.glob(os.path.join(PROJECT, "*.jsonl"))
                 if dt.date.fromtimestamp(os.path.getmtime(p)) == today]
        cands = [p for p in cands if os.path.isdir(p[:-6] + "/subagents")]
        if not cands:
            sys.exit("no lead session with teammates touched today; pass --session")
        lead = max(cands, key=os.path.getmtime)
    sid = os.path.basename(lead)[:-6]
    files = [lead] + sorted(glob.glob(os.path.join(PROJECT, sid, "subagents", "*.jsonl")))
    if a.hung is not None:
        sys.exit(hung_report(files, a.hung))
    rows = []
    for f in files:
        first, last, tot, model = scan(f, since)
        if first is None:
            continue
        rows.append((player_of(f), first, last, tot, model))
    rows.sort(key=lambda r: PLAYERS.index(r[0]) if r[0] in PLAYERS else 99)
    grand = {"input": 0, "cache_read": 0, "cache_create": 0, "output": 0, "calls": 0}
    lines = []
    for p, first, last, tot, model in rows:
        mins = round((last - first).total_seconds() / 60, 1)
        for k in grand:
            grand[k] += tot[k]
        total = tot["input"] + tot["cache_read"] + tot["cache_create"] + tot["output"]
        lines.append((p, model or "?", first.strftime("%H:%M"), last.strftime("%H:%M"), mins,
                      tot["input"] + tot["cache_create"], tot["cache_read"], tot["output"], total, tot["calls"]))
    if a.md:
        print("| Player | Model | On floor | Minutes | Fresh input | Cached input | Output | All tokens | API calls |")
        print("|---|---|---|---|---|---|---|---|---|")
        for p, model, s, e, mins, fresh, cached, out, total, calls in lines:
            print(f"| {p.title()} | {model} | {s} to {e} | {mins} | {fresh:,} | {cached:,} | {out:,} | {total:,} | {calls} |")
        gt = sum(grand.values()) - grand["calls"]
        print(f"| **Team** | | | | {grand['input'] + grand['cache_create']:,} | {grand['cache_read']:,} | {grand['output']:,} | {gt:,} | {grand['calls']} |")
        print("\nFresh input = tokens billed at the full input rate (new plus cache writes). Cached input = prompt-cache reads, billed at a fraction. Session " + sid + ".")
    else:
        print("session", sid)
        for p, model, s, e, mins, fresh, cached, out, total, calls in lines:
            print(f"{p:7s} {model:18s} {s}-{e} {mins:6.1f} min  fresh {fresh:>9,}  cached {cached:>10,}  out {out:>8,}  all {total:>11,}  calls {calls}")
        print(f"team    all tokens {sum(grand.values()) - grand['calls']:,}")

if __name__ == "__main__":
    main()
