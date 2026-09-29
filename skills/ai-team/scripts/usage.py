#!/usr/bin/env python3
"""Shift stats for the DigitalCLIQ AI team: minutes and tokens per player.

Reads the Claude Code transcript of the lead session plus its teammate transcripts
(~/.claude/projects/<project>/<session>.jsonl and <session>/subagents/*.jsonl) and
prints, per player, first and last activity, minutes, and token totals.
Standard library only. Tokens are what the API reported; no cost is computed here.
A transcript writes one record per content block and repeats the API call's usage on each,
so usage is counted once per message id, and API calls = unique message ids.

  python3 .claude/skills/ai-team/scripts/usage.py                 newest shift session touched today
  python3 .claude/skills/ai-team/scripts/usage.py --session ID    a specific lead session id (a unique prefix works)
  python3 .claude/skills/ai-team/scripts/usage.py --since 08:50   only messages after HH:MM local today
  add --md to print a markdown block for the brief
  python3 .claude/skills/ai-team/scripts/usage.py --hung 5     hang watchdog: players whose last tool call has had no
                                                              result for 5+ minutes (exit 1 if any). Finished, released,
                                                              and stopped players print on info lines and never exit 1.
  python3 .claude/skills/ai-team/scripts/usage.py --tools      tools each teammate session loaded at spawn, with the
                                                              Semrush and Meta connector counts. Exit 0 when Worthy has
                                                              Semrush and Luka has Meta, 2 when either is missing.
"""
import argparse, datetime as dt, glob, json, os, re, sys

PROJECT = os.path.expanduser("~/.claude/projects/-Users-drewmoon-Desktop-DigitalCLIQ-Brain-HQ")
PLAYERS = ["magic", "kobe", "shaq", "luka", "worthy", "nick"]
TEAMMATES = PLAYERS[1:]
USAGE = [("input", "input_tokens"), ("cache_read", "cache_read_input_tokens"),
         ("cache_create", "cache_creation_input_tokens"), ("output", "output_tokens")]
SEMRUSH = ["mcp__claude_ai_Semrush__", "mcp__semrush__"]
META = ["mcp__meta-ads__", "mcp__claude_ai_Meta_Ads__"]
STUBS = ("authenticate", "complete_authentication")   # what a server lists before it is authorized: no data tools
DONE = ("end_turn", "stop_sequence")                  # stop reasons that end a turn

def player_of(path):
    m = re.search(r"agent-a?([A-Za-z]+)-[0-9a-f]+\.jsonl$", os.path.basename(path))
    if m and m.group(1).lower() in PLAYERS:
        return m.group(1).lower()
    return "magic" if "/subagents/" not in path else "other"

def parse_ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone()

def records(path):
    """Parsed transcript records, skipping lines that do not parse."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except Exception:
                continue
            if isinstance(d, dict):
                yield d

def blocks(d):
    """Content blocks of a record's message (empty for string content and non-message records)."""
    m = d.get("message")
    c = m.get("content") if isinstance(m, dict) else None
    return [b for b in c if isinstance(b, dict)] if isinstance(c, list) else []

def newest_by_player(files):
    """The newest transcript per teammate. A respawned player gets a new file and leaves the stopped one behind."""
    out = {}
    for f in files:
        p = player_of(f)
        if p in TEAMMATES and (p not in out or os.path.getmtime(f) > os.path.getmtime(out[p])):
            out[p] = f
    return out

def approves_shutdown(inp):
    """True when a SendMessage input approves a shutdown request (the teammate's process then exits)."""
    if not isinstance(inp, dict):
        return False
    m = inp.get("message") if isinstance(inp.get("message"), dict) else inp
    return m.get("type") == "shutdown_response" and m.get("approve") is True

def end_state(path):
    """How a teammate transcript ends, as (state, time, tools):
    hung      the last API call asked for tools and at least one never got a tool_result; time is that tool call
    released  the last API call approved a shutdown request
    finished  the last API call ended the turn and nothing arrived after it (idle or done)
    waiting   a tool returned or a message arrived and no API call has followed yet
    none      no API call yet; time is the spawn
    The caller applies the age threshold; `hung` younger than it is a tool still running."""
    msg = stop = None
    uses = {}          # tool_use id -> (tool name, time, input), for the last API call only
    answered = set()   # tool_use ids that got a tool_result
    first = last_call = last_in = None
    for d in records(path):
        if not d.get("timestamp"):
            continue
        t = parse_ts(d["timestamp"])
        first = first or t
        kind = d.get("type")
        if kind == "assistant" and isinstance(d.get("message"), dict):
            m = d["message"]
            key = m.get("id") or d.get("uuid")
            if key != msg:
                msg, stop, uses = key, None, {}
            stop = m.get("stop_reason") or stop
            last_call, last_in = t, None
            for b in blocks(d):
                if b.get("type") == "tool_use":
                    uses[b.get("id")] = (b.get("name") or "?", t, b.get("input"))
        elif kind == "user":
            for b in blocks(d):
                if b.get("type") == "tool_result":
                    answered.add(b.get("tool_use_id"))
            if not d.get("isMeta"):
                last_in = t
    if msg is None:
        return "none", first, ""
    orphans = [u for k, u in uses.items() if k not in answered]
    if orphans:
        return "hung", max(u[1] for u in orphans), ", ".join(sorted({u[0] for u in orphans}))
    if any(u[0] == "SendMessage" and approves_shutdown(u[2]) for u in uses.values()):
        return "released", last_call, ""
    if stop in DONE and not uses and last_in is None:
        return "finished", last_call, ""
    return "waiting", max(x for x in (last_call, last_in) if x), ""

def stops(lead):
    """Teammates the lead stopped with TaskStop, as {player: time of the last successful stop}. The task id is
    usually the player's name; for an internal id, the result's command (the spawn prompt) names the player."""
    asked, done = {}, {}
    for d in records(lead):
        for b in blocks(d):
            if b.get("type") == "tool_use" and b.get("name") == "TaskStop" and d.get("timestamp"):
                inp = b.get("input") if isinstance(b.get("input"), dict) else {}
                who = str(inp.get("task_id", "")).split("@")[0].lower()
                asked[b.get("id")] = (who if who in TEAMMATES else None, parse_ts(d["timestamp"]))
            elif b.get("type") == "tool_result" and b.get("tool_use_id") in asked:
                c = b.get("content")
                text = c if isinstance(c, str) else json.dumps(c)
                if "Successfully stopped" not in text:
                    continue
                who, t = asked[b["tool_use_id"]]
                if who is None and "in_process_teammate" in text:
                    m = re.search(r"command\W+([^\n]{0,60})", text)
                    who = next((w.lower() for w in re.findall(r"[A-Za-z]+", m.group(1) if m else "")
                                if w.lower() in TEAMMATES), None)
                if who:
                    done[who] = max(t, done.get(who, t))
    return done

def hung_report(files, minutes, lead):
    """Players stuck on a tool call: the last API call asked for a tool and its tool_result has not come back
    for `minutes` or more. A teammate waiting on a permission prompt keeps status `running` while making no
    API calls, so ListAgents cannot see it and this is the only tell (learned 2026-09-21). A player whose last
    API call ended its turn is idle or finished, not hung (flagging those was the 2026-09-23 false alarm)."""
    now = dt.datetime.now().astimezone()
    stopped = stops(lead)
    hung = []
    info = {"idle/finished": [], "released": [], "stopped by lead": [], "quiet": [], "no API call yet": []}
    for p, f in sorted(newest_by_player(files).items(), key=lambda kv: PLAYERS.index(kv[0])):
        state, t, tools = end_state(f)
        if t is None:
            continue
        age = (now - t).total_seconds() / 60
        when = f"{p} {t.strftime('%H:%M')} ({age:.1f} min ago)"
        if p in stopped and stopped[p] >= t:
            info["stopped by lead"].append(f"{p} at {stopped[p].strftime('%H:%M')}")
        elif state == "hung" and age >= minutes:
            hung.append((p, t, age, tools))
        elif state == "finished":
            info["idle/finished"].append(when)
        elif state == "released":
            info["released"].append(when)
        elif state == "waiting" and age >= minutes:
            info["quiet"].append(when)
        elif state == "none" and age >= minutes:
            info["no API call yet"].append(f"{p} spawned {t.strftime('%H:%M')} ({age:.1f} min ago)")
    if hung:
        for p, t, age, tools in hung:
            calls = "calls" if "," in tools else "call"
            print(f"{p:7s} HUNG  {tools} {calls} at {t.strftime('%H:%M:%S')} still without a result after {age:.1f} min "
                  "(a permission prompt nobody can answer, or a command that never returned)")
        print("stop each hung player with TaskStop, then respawn it or take its lane")
    else:
        print(f"no player hung: no player idle {minutes:g}+ minutes on an unanswered tool call")
    notes = {"idle/finished": "idle/finished (info, not hung; last API call ended its turn)",
             "released": "released (info; approved a shutdown request)",
             "stopped by lead": "stopped by lead (info; TaskStop after its last activity)",
             "quiet": f"quiet {minutes:g}+ min (info, not a permission hang; its last tool returned and no API call followed, check again next round)",
             "no API call yet": "no API call yet (info; check again next round)"}
    for k, v in info.items():
        if v:
            print(f"{notes[k]}: {', '.join(v)}")
    return 1 if hung else 0

def first_tools(path):
    """Tool names in the first deferred_tools_delta attachment (what the session loaded at spawn), or None."""
    for d in records(path):
        a = d.get("attachment")
        if isinstance(a, dict) and a.get("type") == "deferred_tools_delta":
            return [n for n in a.get("addedNames") or [] if isinstance(n, str)]
    return None

def server_count(names, prefix):
    """Tools from one MCP server prefix, not counting its authenticate stubs."""
    return sum(1 for n in names if n.startswith(prefix) and n[len(prefix):] not in STUBS)

def tools_report(files):
    """Per teammate: tools loaded at spawn and the Semrush / Meta connector counts, then the verdict.
    Teammates get the tool list from the start of the lead's current turn, so a spawn in turn 1 (before MCP
    finished loading) gives them no connector tools (root cause found 2026-09-23)."""
    newest = newest_by_player(files)
    have = {}
    for p in TEAMMATES:
        names = first_tools(newest[p]) if p in newest else None
        if names is None:
            print(f"{p:7s} not spawned yet")
            continue
        counts = [(pre, server_count(names, pre)) for pre in SEMRUSH + META]
        have[p] = (sum(n for pre, n in counts if pre in SEMRUSH), sum(n for pre, n in counts if pre in META))
        print(f"{p:7s} tools {len(names):4d}  " + "  ".join(f"{pre[5:-2]} {n}" for pre, n in counts))
    semrush = have.get("worthy", (0, 0))[0] > 0
    meta = have.get("luka", (0, 0))[1] > 0
    print(f"SEMRUSH worthy: {'yes' if semrush else 'no'}")
    print(f"META luka: {'yes' if meta else 'no'}")
    if not (semrush and meta):
        print("missing connector tools: respawn once (SKILL.md step 2: TaskStop all five, background sleep, end turn, --turn-check); pull fallbacks only if the second spawn also shows 0")
    return 0 if semrush and meta else 2

def scan(path, since):
    """First and last activity, token totals, and model of one transcript. Each API call counts once:
    the transcript repeats message.usage on every content block, and output_tokens only reaches its final
    count on the last block, so each usage field keeps its max per message id."""
    first = last = None
    calls = {}
    model = None
    for d in records(path):
        ts = d.get("timestamp")
        if not ts:
            continue
        t = parse_ts(ts)
        if since and t < since:
            continue
        m = d.get("message")
        if d.get("type") == "assistant" and isinstance(m, dict) and m.get("usage") and m.get("model") != "<synthetic>":
            u = m["usage"]
            got = [u.get(field) or 0 for _, field in USAGE]
            key = m.get("id") or d.get("requestId") or d.get("uuid")
            calls[key] = [max(a, b) for a, b in zip(calls[key], got)] if key in calls else got
            model = m.get("model") or model
        first = t if first is None or t < first else first
        last = t if last is None or t > last else last
    tot = {k: sum(c[i] for c in calls.values()) for i, (k, _) in enumerate(USAGE)}
    tot["calls"] = len(calls)
    return first, last, tot, model

def find_lead(session):
    """Lead transcript for --session (an id, a unique prefix, or a .jsonl path), else the newest session
    touched today that has teammate transcripts, preferring one with named players (the shift)."""
    if session:
        sid = os.path.basename(session)
        sid = sid[:-6] if sid.endswith(".jsonl") else sid
        exact = os.path.join(PROJECT, sid + ".jsonl")
        if os.path.exists(exact):
            return exact
        hits = glob.glob(os.path.join(PROJECT, sid + "*.jsonl"))
        if len(hits) == 1:
            return hits[0]
        sys.exit(f"session {session}: {'ambiguous prefix' if hits else 'no transcript'} in {PROJECT}")
    today = dt.date.today()
    cands = [p for p in glob.glob(os.path.join(PROJECT, "*.jsonl"))
             if dt.date.fromtimestamp(os.path.getmtime(p)) == today]
    cands = [p for p in cands if os.path.isdir(p[:-6] + "/subagents")]
    shift = [p for p in cands if any(player_of(f) in TEAMMATES for f in glob.glob(p[:-6] + "/subagents/*.jsonl"))]
    if not cands:
        sys.exit("no lead session with teammates touched today; pass --session")
    return max(shift or cands, key=os.path.getmtime)

def find_current_lead(session):
    """The running shift lead, before any teammate exists: --session if given, else the newest
    transcript touched in the last 15 minutes that holds the /ai-team command."""
    if session:
        return find_lead(session)
    now = dt.datetime.now().timestamp()
    cands = sorted((p for p in glob.glob(os.path.join(PROJECT, "*.jsonl"))
                    if now - os.path.getmtime(p) < 900), key=os.path.getmtime, reverse=True)
    for p in cands:
        with open(p, encoding="utf-8", errors="replace") as fh:
            head = fh.read(200000)
        if "<command-name>/ai-team</command-name>" in head:
            return p
    sys.exit("no running /ai-team session found in the last 15 minutes; pass --session")

def turn_check(lead, upto=None):
    """Is the lead's CURRENT turn a fresh one that began after MCP connectors loaded?
    Teammates get the tool list from the start of the lead's current turn (root cause 2026-09-23;
    9/28 failed because a background job's notification arrived mid-turn and the lead spawned
    without ending turn 1). Exit 0 = safe to spawn, 3 = end your turn first."""
    mcp_first = last_end = last_start = None
    for i, d in enumerate(records(lead)):
        if upto is not None and i > upto:
            break
        a = d.get("attachment")
        if (mcp_first is None and isinstance(a, dict) and a.get("type", "").startswith("deferred_tools")
                and any(str(n).startswith("mcp__") for n in (a.get("addedNames") or []))):
            mcp_first = i
        m = d.get("message") if isinstance(d.get("message"), dict) else {}
        if d.get("type") == "assistant" and m.get("stop_reason") == "end_turn":
            last_end = i
        if d.get("type") == "user":
            c = m.get("content")
            if isinstance(c, str) or any(b.get("type") == "text" for b in blocks(d)):
                last_start = i
    ok = (mcp_first is not None and last_end is not None and last_start is not None
          and mcp_first < last_start and last_end < last_start)
    if ok:
        print("OK to spawn: this turn began after an end of turn and after the connectors loaded "
              "(connectors at record %d, turn ended at %d, new turn at %d)." % (mcp_first, last_end, last_start))
        return 0
    why = []
    if mcp_first is None:
        why.append("no MCP connectors have loaded in this session yet")
    if last_end is None:
        why.append("you have not ended a turn yet in this session")
    elif last_start is None or last_start < last_end:
        why.append("you are still inside the turn that ended at record %d's successor" % last_end)
    elif mcp_first is not None and last_start < mcp_first:
        why.append("this turn began before the connectors loaded")
    print("NOT SAFE TO SPAWN: " + "; ".join(why or ["this is still the turn that began with /ai-team"]) +
          ". Start one background python3 sleep, end your turn now with one line, and spawn only on the turn "
          "its notification starts. A notification that arrives while you are still working is not the wake.")
    return 3

def main():
    ap = argparse.ArgumentParser(description="AI team shift stats, hang watchdog, and teammate tool check.")
    ap.add_argument("--session", help="lead session id or unique prefix (default: newest shift session touched today)")
    ap.add_argument("--since", help="HH:MM local, today")
    ap.add_argument("--md", action="store_true")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--hung", type=float, metavar="MINUTES",
                      help="watchdog: players whose last tool call has had no result for MINUTES+ (exit 1 if any)")
    mode.add_argument("--tools", action="store_true",
                      help="tools each teammate loaded at spawn; exit 2 if Worthy lacks Semrush or Luka lacks Meta")
    mode.add_argument("--turn-check", action="store_true",
                      help="run right before spawning: exit 0 if this turn is fresh (after an end of turn and after connectors loaded), 3 if not")
    ap.add_argument("--upto", type=int, help=argparse.SUPPRESS)  # tests: evaluate the transcript as of record N
    a = ap.parse_args()
    if a.turn_check:
        lead = find_current_lead(a.session)
        print("session", os.path.basename(lead)[:-6])
        sys.exit(turn_check(lead, a.upto))
    since = None
    if a.since:
        h, mnt = map(int, a.since.split(":"))
        since = dt.datetime.now().astimezone().replace(hour=h, minute=mnt, second=0, microsecond=0)
    lead = find_lead(a.session)
    sid = os.path.basename(lead)[:-6]
    files = [lead] + sorted(glob.glob(os.path.join(PROJECT, sid, "subagents", "*.jsonl")))
    if a.hung is not None:
        print("session", sid)
        sys.exit(hung_report(files, a.hung, lead))
    if a.tools:
        print("session", sid)
        sys.exit(tools_report(files))
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
        print("\nFresh input = tokens billed at the full input rate (new plus cache writes). Cached input = prompt-cache reads, billed at a fraction. "
              "Each API call is counted once (deduplicated by message id). Session " + sid + ".")
    else:
        print("session", sid)
        for p, model, s, e, mins, fresh, cached, out, total, calls in lines:
            print(f"{p:7s} {model:18s} {s}-{e} {mins:6.1f} min  fresh {fresh:>9,}  cached {cached:>10,}  out {out:>8,}  all {total:>11,}  calls {calls}")
        print(f"team    all tokens {sum(grand.values()) - grand['calls']:,}")

if __name__ == "__main__":
    main()
