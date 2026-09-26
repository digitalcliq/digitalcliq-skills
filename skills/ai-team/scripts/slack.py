#!/usr/bin/env python3
"""Slack voice for the DigitalCLIQ AI team. Standard library only.

One Slack app (scopes: chat:write, chat:write.customize, channels:history)
posts as each player (six voices) with its own name and jersey avatar.

Token lives OUTSIDE the vault: ~/.config/digitalcliq-ai-team/slack.env
  SLACK_BOT_TOKEN=xoxb-...

Commands:
  post --as kobe --text "..." [--thread TS] [--tag-drew]   prints the message ts
  post --as kobe --file PATH [--thread TS] [--tag-drew]    same, text read from a file (use it for any $ amount)
  read [--hours 24] [--thread TS]                          channel or thread history
  check                                                    token + channel membership test
  post-topics [--ledger PATH] [--thread TS] [--dry-run]    one Magic post per open topic with no slack_ts,
                                                           each ts written back to the ledger
  picks [--ledger PATH] [--apply]                          JSON of posted open topics Drew picked;
                                                           --apply marks them picked in the ledger
  reactions-check [--days 30] [--threads] [--record PATH]  do #ai-team messages carry "reactions"; --record keeps Magic's state
  selftest                                                 offline tests of the guards and the pick parser

PII law: #ai-team gets aggregates only. Any text that looks like it carries a
customer phone number or email address is refused, no override.

Dollar guard: in a double-quoted --text the shell expands "$6,497" to ",497" and
"$40/day" to "/day" before Python sees it. A --text post that shows that damage
is refused; write the text to a file and use --file (files are never checked).

Tap to pick (Drew's rule, 2026-09-23): Worthy's content topics live in
outputs/ai-team/topics.json. post-topics puts each open topic in #ai-team as its
own message; Drew picks one by reacting :white_check_mark: (or :heavy_check_mark:,
:+1:) or by replying "pick", "yes", or "go" in its thread. Nothing is drafted
until picks --apply has marked it picked. A topic posted inside a thread
(--thread) has no thread of its own, so a reply there must name it: "pick T8".
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

CHANNEL = "C0C2745RULV"  # #ai-team (public), see Context/connector-ids.md
DREW = "U0A18TB6F"
ENV_FILE = os.path.expanduser("~/.config/digitalcliq-ai-team/slack.env")
LEDGER = "outputs/ai-team/topics.json"  # relative to the vault root, where the shift runs

# Each player posts under its own name and icon. Standard Slack emoji work with
# no upload. Once the jersey PNGs in assets/avatars/ are added as custom emoji
# (magic32, kobe24, shaq34, worthy42, nick9, luka77), flip CUSTOM_EMOJI to True.
CUSTOM_EMOJI = False
PLAYERS = {
    "magic": ("Magic #32", ":magic_wand:", ":magic32:"),
    "kobe": ("Kobe #24", ":snake:", ":kobe24:"),
    "shaq": ("Shaq #34", ":truck:", ":shaq34:"),
    "worthy": ("Worthy #42", ":telescope:", ":worthy42:"),
    "nick": ("Nick Van Exel #9", ":dart:", ":nick9:"),
    "luka": ("Luka Doncic #77", ":flag-si:", ":luka77:"),
}

PHONE = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\d)")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# What zsh leaves of a dollar amount in a double-quoted --text. The left edge is
# the start of the text, whitespace, or opening punctuation, so "1.5x",
# "3,600 searches", "9/22", and "$40/day" itself never match.
_EDGE = r"(?:^|(?<=[\s(\[{'\"*_~+/-]))"
DOLLAR_DAMAGE = [
    re.compile(_EDGE + r"[.,]\d"),                                    # "$6,497" -> ",497", "$1.5M" -> ".5M"
    re.compile(_EDGE + r"/(?:day|mo|month|week|wk|yr|year)\b", re.I),  # "$40/day" -> "/day"
    re.compile(r"/bin/(?:z|ba)?sh(?![A-Za-z])"),                      # "$0.85" -> "/bin/zsh.85"
]

TOPIC_MAX_CHARS = 400  # short enough to read at a glance, long enough to keep the compliance verdict
TOPIC_FIELDS = ("id", "store", "title", "target_query", "compliance", "first_proposed")
PICK_REACTIONS = ("white_check_mark", "heavy_check_mark", "+1", "thumbsup")
PICK_WORDS = ("pick", "yes", "go")


def die(msg, code=1):
    print("ERROR: " + msg, file=sys.stderr)
    sys.exit(code)


def token():
    tok = os.environ.get("SLACK_BOT_TOKEN")
    if not tok and os.path.exists(ENV_FILE):
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line.startswith("SLACK_BOT_TOKEN="):
                    tok = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not tok:
        die("no Slack token. See references/setup.md step 1.")
    return tok


def call(method, params, post=True):
    url = "https://slack.com/api/" + method
    headers = {"Authorization": "Bearer " + token()}
    data = None
    if post:
        data = json.dumps(params).encode()
        headers["Content-Type"] = "application/json; charset=utf-8"
    else:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            res = json.load(r)
    except urllib.error.HTTPError as e:
        die("Slack HTTP %s" % e.code)
    if not res.get("ok"):
        die("Slack %s failed: %s" % (method, res.get("error")))
    return res


def to_mrkdwn(text):
    """Vault markdown to Slack mrkdwn: headings and **bold** become *bold*, wikilinks lose brackets."""
    text = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"(?m)^#{1,6}\s+(.+?)\s*$", r"*\1*", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)
    return text.replace("**", "*")


def clean(text):
    """What actually reaches Slack: em dashes stripped (Rule 14), then mrkdwn."""
    return to_mrkdwn(text.replace(chr(8212), ", "))


def pii_problem(text):
    if PHONE.search(text) or EMAIL.search(text):
        return ("refused: text looks like it holds a phone number or email address. "
                "#ai-team gets aggregates only, never customer-level data. Rewrite and resend.")
    return None


def dollar_damage(text):
    """The first fragment that looks like a shell-eaten dollar amount, or None."""
    for rx in DOLLAR_DAMAGE:
        m = rx.search(text)
        if m:
            end = text.find(" ", m.end())
            return text[m.start():end if end > 0 else len(text)].strip()
    return None


def send(who, text, thread=None, tag_drew=False):
    """Post already-guarded text as a player and return the message ts."""
    text = clean(text)
    if tag_drew:
        text = "<@%s> %s" % (DREW, text)
    name, std_emoji, custom_emoji = PLAYERS[who]
    emoji = custom_emoji if CUSTOM_EMOJI else std_emoji
    payload = {"channel": CHANNEL, "text": text, "username": name, "icon_emoji": emoji,
               "unfurl_links": False, "unfurl_media": False}
    if thread:
        payload["thread_ts"] = thread
    return call("chat.postMessage", payload)["ts"]


def cmd_post(args):
    who = args.as_player.lower()
    if who not in PLAYERS:
        die("unknown player %s. Known: %s" % (who, ", ".join(PLAYERS)))
    text = args.text
    if args.file:
        with open(args.file) as f:
            text = f.read()
    if not text or not text.strip():
        die("empty message")
    problem = pii_problem(text)
    if problem:
        die(problem, 2)
    if not args.file:
        bad = dollar_damage(text)
        if bad:
            die("refused: --text looks shell-mangled near %r. The shell eats $ amounts before Python "
                "sees them (\"$6,497\" arrives as \",497\", \"$40/day\" as \"/day\"). Write the text "
                "to a file in the shift folder and resend with --file PATH." % bad, 2)
    print(send(who, text, args.thread, args.tag_drew))


def cmd_read(args):
    if args.thread:
        res = call("conversations.replies", {"channel": CHANNEL, "ts": args.thread, "limit": 200}, post=False)
    else:
        oldest = "%.6f" % (time.time() - args.hours * 3600)
        res = call("conversations.history", {"channel": CHANNEL, "oldest": oldest, "limit": 200}, post=False)
    out = []
    for m in reversed(res.get("messages", [])) if not args.thread else res.get("messages", []):
        out.append({
            "ts": m.get("ts"),
            "from": m.get("username") or ("drew" if m.get("user") == DREW else m.get("user")),
            "is_drew": m.get("user") == DREW and not m.get("bot_id"),
            "thread_ts": m.get("thread_ts"),
            "replies": m.get("reply_count", 0),
            "files": [f.get("name") for f in m.get("files", [])] or None,
            "text": m.get("text"),
        })
    print(json.dumps(out, indent=1))


def cmd_check(_args):
    res = call("auth.test", {})
    print("token ok: bot %s in workspace %s" % (res.get("user"), res.get("team")))
    call("conversations.history", {"channel": CHANNEL, "limit": 1}, post=False)
    print("can read #ai-team: ok")


# ---- tap to pick: topic ledger ----

def load_ledger(path):
    try:
        with open(path) as f:
            data = json.load(f)
    except FileNotFoundError:
        die("no ledger at %s" % path)
    except ValueError as e:
        die("ledger %s is not valid JSON: %s" % (path, e))
    if not isinstance(data, dict) or not isinstance(data.get("topics"), list):
        die('ledger %s has no "topics" list' % path)
    return data


def save_ledger(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def _sentence(s):
    return s if s[-1:] in (".", "!", "?") else s + "."


def _shorten(s, n):
    """Cut s to about n characters at a word boundary, ending in '...'. A field already at or under
    the 16-character floor stays as is (a plain "Pass" must never read "Pass...")."""
    if len(s) <= max(n, 16):
        return s
    head = s[:max(n, 16) - 3]
    if " " in head:
        head = head.rsplit(" ", 1)[0]
    return head.rstrip(" ,;:.") + "..."


def topic_message(t):
    """(text, trimmed_fields, problem) for one ledger topic, as it will reach Slack."""
    f = {k: " ".join(str(t.get(k) or "").split()) for k in TOPIC_FIELDS}
    missing = [k for k in TOPIC_FIELDS if not f[k]]
    if missing:
        return None, [], "topic %s is missing %s" % (f["id"] or "?", ", ".join(missing))

    def render():
        return clean("Topic %s for %s: %s Target search: %s Compliance: %s Open since %s. "
                     "Tap :white_check_mark: or reply pick in its thread to choose it." % (
                         f["id"], f["store"], _sentence(f["title"]), _sentence(f["target_query"]),
                         _sentence(f["compliance"]), f["first_proposed"]))

    text, trimmed = render(), []
    for key in ("compliance", "target_query", "title"):  # the full compliance note stays in the ledger
        over = len(text) - TOPIC_MAX_CHARS
        if over <= 0:
            break
        cut = _shorten(f[key], len(f[key]) - over)
        if cut != f[key]:
            f[key] = cut
            trimmed.append(key)
            text = render()
    if len(text) > TOPIC_MAX_CHARS:
        return text, trimmed, "topic %s is %d characters even trimmed (limit %d)" % (f["id"], len(text), TOPIC_MAX_CHARS)
    return text, trimmed, None


def topic_problem(tid, text):
    if pii_problem(text):
        return "topic %s: text looks like it holds a phone number or email address" % tid
    bad = dollar_damage(text)
    if bad:
        return "topic %s: text looks shell-mangled near %r (a $ amount lost its digits); fix it in the ledger" % (tid, bad)
    return None


def cmd_post_topics(args):
    data = load_ledger(args.ledger)
    todo = [t for t in data["topics"] if t.get("status") == "open" and not t.get("slack_ts")]
    plan = []
    for t in todo:
        text, trimmed, problem = topic_message(t)
        problem = problem or topic_problem(t.get("id"), text)
        plan.append({"id": t.get("id"), "store": t.get("store"), "chars": len(text or ""),
                     "trimmed": trimmed or None, "problem": problem, "text": text})
    problems = [p["problem"] for p in plan if p["problem"]]
    if args.dry_run:
        print(json.dumps({"dry_run": True, "ledger": args.ledger, "thread": args.thread,
                          "would_post": plan, "note": "nothing posted, ledger unchanged"}, indent=1))
        if problems:
            sys.exit(2)
        return
    if problems:
        die("nothing posted, fix the ledger first:\n  " + "\n  ".join(problems), 2)
    posted = []
    for t, p in zip(todo, plan):
        ts = send("magic", p["text"], args.thread)
        t["slack_ts"] = ts
        t["slack_thread"] = args.thread
        save_ledger(args.ledger, data)  # after every post, so a crash never double-posts
        posted.append({"id": t.get("id"), "ts": ts})
    print(json.dumps({"ledger": args.ledger, "thread": args.thread, "posted": posted,
                      "note": None if posted else "no open topic without a slack_ts"}, indent=1))


def _is_drew(m):
    return m.get("user") == DREW and not m.get("bot_id")


def reaction_pick(msg):
    """Name of Drew's pick reaction on a message, or None."""
    for r in msg.get("reactions") or []:
        name = (r.get("name") or "").split("::")[0]  # "+1::skin-tone-2" -> "+1"
        if name in PICK_REACTIONS and DREW in (r.get("users") or []):
            return name
    return None


def reply_says_pick(text, topic_id, own_thread):
    """True when a reply reads as a pick: a bare pick word in the topic's own thread,
    or the word plus the topic id ("pick T8", "T8 yes") anywhere."""
    t = " ".join((text or "").lower().split()).strip(" .!")
    if own_thread and t in PICK_WORDS:
        return True
    tid = re.escape(str(topic_id).lower())
    words = "(?:%s)" % "|".join(PICK_WORDS)
    return bool(re.fullmatch(r"(?:%s[\s:,]+%s|%s[\s:,]+%s)" % (words, tid, tid, words), t))


def _thread(ts, oldest=None):
    """Every message in a thread (parent first), following cursors."""
    params = {"channel": CHANNEL, "ts": ts, "limit": 200}
    if oldest:
        params.update(oldest=oldest, inclusive="true")
    out = []
    while True:
        res = call("conversations.replies", params, post=False)
        out.extend(res.get("messages", []))
        cur = (res.get("response_metadata") or {}).get("next_cursor")
        if not (res.get("has_more") and cur):
            return out
        params["cursor"] = cur


def _day(ts):
    return time.strftime("%Y-%m-%d", time.localtime(float(ts)))


def cmd_picks(args):
    data = load_ledger(args.ledger)
    picked, still_open, missing = [], [], []
    threads = {}
    for t in data["topics"]:
        if t.get("status") != "open" or not t.get("slack_ts"):
            continue
        ts, parent = str(t["slack_ts"]), t.get("slack_thread")
        if parent and str(parent) != ts:
            # posted as a reply inside a thread: read it from that thread
            if parent not in threads:
                threads[parent] = _thread(parent)
            msgs = threads[parent]
            msg = next((m for m in msgs if m.get("ts") == ts), None)
            later = [m for m in msgs if float(m.get("ts", 0)) > float(ts)]
            own = False
        else:
            res = call("conversations.history", {"channel": CHANNEL, "latest": ts, "oldest": ts,
                                                 "inclusive": "true", "limit": 1}, post=False)
            msg = next((m for m in res.get("messages", []) if m.get("ts") == ts), None)
            later = [m for m in _thread(ts) if m.get("ts") != ts] if msg and msg.get("reply_count") else []
            own = True
        if msg is None:
            missing.append({"id": t.get("id"), "slack_ts": ts,
                            "why": "message not found (deleted, or posted in a thread with no slack_thread in the ledger)"})
            continue
        how, when = None, None
        name = reaction_pick(msg)
        if name:
            how, when = "reaction :%s:" % name, time.strftime("%Y-%m-%d")  # Slack does not date reactions
        else:
            for m in later:
                if _is_drew(m) and reply_says_pick(m.get("text"), t.get("id"), own):
                    how, when = "reply %r" % (m.get("text") or "").strip(), _day(m["ts"])
                    break
        if not how:
            still_open.append(t.get("id"))
            continue
        picked.append({"id": t.get("id"), "store": t.get("store"), "title": t.get("title"),
                       "slack_ts": ts, "how": how, "picked_at": when})
        if args.apply:
            t["status"] = "picked"
            t["picked_at"] = when
            t["picked_by"] = "Drew, in Slack (%s)" % how
    if args.apply and picked:
        save_ledger(args.ledger, data)
    print(json.dumps({"ledger": args.ledger, "applied": bool(args.apply and picked), "picked": picked,
                      "still_open": still_open, "missing": missing}, indent=1))


def cmd_reactions_check(args):
    """Read-only: page through #ai-team history and report whether messages carry "reactions"."""
    params = {"channel": CHANNEL, "oldest": "%.6f" % (time.time() - args.days * 86400), "limit": 200}
    msgs = []
    while True:
        res = call("conversations.history", params, post=False)
        msgs.extend(res.get("messages", []))
        cur = (res.get("response_metadata") or {}).get("next_cursor")
        if not (res.get("has_more") and cur):
            break
        params["cursor"] = cur
    replies = []
    parents = [m["ts"] for m in msgs if m.get("reply_count")]
    if args.threads:
        for ts in parents:
            replies.extend(m for m in _thread(ts) if m.get("ts") != ts)
            time.sleep(1.2)  # conversations.replies is tier 3
    seen = [m for m in msgs + replies if "reactions" in m]
    drew = [m for m in seen if any(DREW in (r.get("users") or []) for r in m["reactions"])]
    examples = [{"ts": m.get("ts"), "from": m.get("username") or m.get("user"),
                 "reactions": ["%s x%s" % (r.get("name"), r.get("count")) for r in m["reactions"]]} for m in seen[:5]]
    if seen:
        verdict = ("conversations.history returns a reactions field under the current scopes; "
                   "picks can see Drew's checkmark taps.")
    else:
        verdict = ("No message in the last %g days carries a reactions field, so it cannot be confirmed until "
                   "Drew taps a reaction on one #ai-team message and this check is re-run. The reply fallback "
                   "(Drew replies \"pick\" in the topic's thread) works now with channels:history. If Drew has "
                   "tapped one and with_drew_reaction is still 0, Slack is hiding reactions from this token: add "
                   "the reactions:read bot scope and reinstall the app." % args.days)
    out = {"days": args.days, "top_level_messages": len(msgs), "threads": len(parents),
           "thread_replies_scanned": len(replies) if args.threads else None,
           "with_reactions": len(seen), "with_drew_reaction": len(drew),
           "examples": examples, "verdict": verdict}
    if args.record:
        out["state"] = record_reactions_state(args.record, len(seen), len(drew), args.topics)
    print(json.dumps(out, indent=1))


def record_reactions_state(path, with_reactions, with_drew, topics_path):
    """Magic's automatic reactions check (Drew, 2026-09-23: no manual step). Sticky once confirmed.
    status: confirmed (a reactions field came back, so taps are visible), or unconfirmed. When topics
    have been on Slack 2+ days and nothing is visible yet, tell_drew is true: the brief gets one line."""
    today = time.strftime("%Y-%m-%d")
    state = {}
    if os.path.exists(path):
        try:
            with open(path) as f:
                state = json.load(f)
        except ValueError:
            state = {}
    if state.get("status") != "confirmed":
        if with_reactions:
            state.update({"status": "confirmed", "confirmed_on": today,
                          "how": "Drew's reaction seen" if with_drew else "a reactions field came back"})
        else:
            state["status"] = "unconfirmed"
    first_post = None
    try:
        with open(topics_path) as f:
            ts = [float(t["slack_ts"]) for t in json.load(f).get("topics", []) if t.get("slack_ts")]
        if ts:
            first_post = time.strftime("%Y-%m-%d", time.localtime(min(ts)))
    except (OSError, ValueError, KeyError, TypeError):
        pass
    state["first_topic_posted"] = first_post
    state["last_checked"] = today
    days_out = None
    if first_post:
        days_out = (time.mktime(time.strptime(today, "%Y-%m-%d")) -
                    time.mktime(time.strptime(first_post, "%Y-%m-%d"))) / 86400
    state["tell_drew"] = bool(state["status"] == "unconfirmed" and days_out is not None and days_out >= 2
                              and not state.get("told_drew_on"))
    state["line_for_brief"] = ("I can't see any checkmark reactions in #ai-team yet. If you've tapped one on a topic, "
                               "reply \"pick\" under it instead and I'll take it from there.") if state["tell_drew"] else None
    if state["tell_drew"]:
        state["told_drew_on"] = today  # said once, not every night
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w") as f:
        json.dump(state, f, indent=2)
    return state


def cmd_selftest(_args):
    """Offline: no token, no network."""
    fails, n = [], [0]

    def check(label, got, want):
        n[0] += 1
        if got != want:
            fails.append("%s: got %r, want %r" % (label, got, want))

    damaged = [",497 in spend", "Meta spend hit ,497 last month", "CPL ran .50 on Meta", "budget is .5M",
               "raise it to /day", "/mo on Semrush", "that is /month", "about /week", "call it /wk",
               "about /yr", "or /year", "(,200 total)", "- ,497", "line one\n,497 on line two",
               "CPL /bin/zsh.85", "\"/day\" cap"]
    clean_text = ["1.5x lift", "3,600 searches", "9/22", "9/22 brief", "$6,497 spend", "$40/day", "40/day cap",
                  "0.5% CTR", "Sept 22, 2026", "v2.1 of the brief", "#ai-team", "per day", "3,600/mo",
                  "https://example.com/day", "10 /days", "/daylight", "wait... 5 leads", "a, b, c",
                  "e.g. 15 leads", "T5, 3,600/mo", "search volume 9,900/mo at position 7", ".com", "shift/day"]
    for s in damaged:
        check("dollar guard should refuse %r" % s, dollar_damage(s) is not None, True)
    for s in clean_text:
        check("dollar guard should pass %r" % s, dollar_damage(s), None)

    base = {"id": "T9", "store": "MCP", "title": "Jeep Wagoneer S is back", "target_query": "jeep wagoneer s",
            "compliance": "Pass", "first_proposed": "2026-09-22", "status": "open"}
    text, trimmed, problem = topic_message(base)
    check("topic text", text, "Topic T9 for MCP: Jeep Wagoneer S is back. Target search: jeep wagoneer s. "
                             "Compliance: Pass. Open since 2026-09-22. Tap :white_check_mark: or reply pick in its thread to choose it.")
    check("topic trimmed", (trimmed, problem), ([], None))
    long_one = dict(base, compliance="Pass with conditions: " + "no on-sale date, price, or availability implied; " * 12)
    text, trimmed, problem = topic_message(long_one)
    check("long topic fits", len(text) <= TOPIC_MAX_CHARS and problem is None, True)
    check("long topic trims compliance only", trimmed, ["compliance"])
    check("long topic keeps its ending", text.endswith("Open since 2026-09-22. Tap :white_check_mark: or reply pick in its thread to choose it."), True)
    check("missing field", topic_message(dict(base, title=""))[2], "topic T9 is missing title")
    long_title = dict(base, title="Why the store keeps showing up in local searches across " + "Alhambra, Pasadena, San Gabriel, " * 3,
                      target_query="dealer near me / service in the store service area / " * 2)
    text, trimmed, problem = topic_message(long_title)
    check("short compliance never gets an ellipsis", ("Compliance: Pass." in text, "Pass..." in text, problem), (True, False, None))
    check("short compliance not reported as trimmed", "compliance" in trimmed, False)
    check("short field unchanged by _shorten", _shorten("Pass", -46), "Pass")

    check("reaction white_check_mark", reaction_pick({"reactions": [{"name": "white_check_mark", "users": [DREW]}]}), "white_check_mark")
    check("reaction +1 skin tone", reaction_pick({"reactions": [{"name": "+1::skin-tone-2", "users": [DREW]}]}), "+1")
    check("reaction heavy_check_mark", reaction_pick({"reactions": [{"name": "heavy_check_mark", "users": ["U1", DREW]}]}), "heavy_check_mark")
    check("reaction by someone else", reaction_pick({"reactions": [{"name": "white_check_mark", "users": ["U999"]}]}), None)
    check("reaction not a check", reaction_pick({"reactions": [{"name": "eyes", "users": [DREW]}]}), None)
    check("no reactions", reaction_pick({}), None)
    for s, own, want in [("pick", True, True), ("Pick", True, True), ("yes.", True, True), ("GO!", True, True),
                         (" yes ", True, True), ("pick", False, False), ("pick T9", False, True), ("T9 yes", False, True),
                         ("go: t9", False, True), ("pick T19", False, False), ("pick T8", True, False),
                         ("maybe", True, False), ("yes but later", True, False), ("", True, False)]:
        check("reply %r own_thread=%s" % (s, own), reply_says_pick(s, "T9", own), want)
    check("drew", _is_drew({"user": DREW}), True)
    check("bot posting with drew's id", _is_drew({"user": DREW, "bot_id": "B1"}), False)

    if fails:
        print("selftest FAILED, %d of %d checks:" % (len(fails), n[0]))
        for f in fails:
            print("  " + f)
        sys.exit(1)
    print("selftest ok: %d checks (%d damaged and %d clean texts for the dollar guard, topic text, picks)"
          % (n[0], len(damaged), len(clean_text)))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("post")
    s.add_argument("--as", dest="as_player", required=True)
    s.add_argument("--text", default="")
    s.add_argument("--file", help="read message text from a file instead of --text")
    s.add_argument("--thread")
    s.add_argument("--tag-drew", action="store_true")
    s.set_defaults(fn=cmd_post)
    s = sub.add_parser("read")
    s.add_argument("--hours", type=float, default=24)
    s.add_argument("--thread")
    s.set_defaults(fn=cmd_read)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    s = sub.add_parser("post-topics", help="post each open topic with no slack_ts as Magic")
    s.add_argument("--ledger", default=LEDGER)
    s.add_argument("--thread", help="post the topics as replies in this thread")
    s.add_argument("--dry-run", action="store_true", help="print what would post, change nothing")
    s.set_defaults(fn=cmd_post_topics)
    s = sub.add_parser("picks", help="which posted open topics Drew picked")
    s.add_argument("--ledger", default=LEDGER)
    s.add_argument("--apply", action="store_true", help="mark them picked in the ledger")
    s.set_defaults(fn=cmd_picks)
    s = sub.add_parser("reactions-check", help="read-only: do #ai-team messages carry a reactions field")
    s.add_argument("--days", type=float, default=30)
    s.add_argument("--threads", action="store_true", help="also read every thread's replies (slower)")
    s.add_argument("--record", help="state file Magic keeps (outputs/ai-team/ledgers/slack-reactions.json)")
    s.add_argument("--topics", default="outputs/ai-team/topics.json", help="topic ledger, to date the first topic post")
    s.set_defaults(fn=cmd_reactions_check)
    sub.add_parser("selftest", help="offline tests of the guards and the pick parser").set_defaults(fn=cmd_selftest)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
