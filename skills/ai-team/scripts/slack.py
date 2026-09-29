#!/usr/bin/env python3
"""Slack voice for the DigitalCLIQ AI team. Standard library only.

One Slack app (scopes: chat:write, chat:write.customize, channels:history)
posts as each player (six voices) with its own name and jersey avatar.

Token lives OUTSIDE the vault: ~/.config/digitalcliq-ai-team/slack.env
  SLACK_BOT_TOKEN=xoxb-...

Commands:
  post --as kobe --text "..." [--thread TS] [--tag-drew]   prints the message ts
  post --as kobe --file PATH [--thread TS] [--tag-drew]    same, text read from a file (use it for any $ amount)
  read [--hours 24] [--thread TS]                          channel or thread history, every page of the window
  check                                                    token + channel membership test
  post-topics [--ledger PATH] [--thread TS] [--dry-run]    one Magic post per open topic with no slack_ts,
                                                           each ts written back to the ledger
  picks [--ledger PATH] [--apply]                          JSON of posted open topics Drew picked;
                                                           --apply marks them picked in the ledger
  reactions-check [--days 30] [--threads] [--record PATH]  do #ai-team messages carry "reactions"; --record keeps Magic's state
  drew-sweep [--state PATH] [--days 14] [--out PATH]       every Drew message (threads too) and reaction in #ai-team
      [--no-advance] [--thread-days 3] [--all-threads]     newer than the watermark: one summary line, then JSON;
                                                           the watermark moves to the newest ts seen
  post-asks --ids A20,A27 [--ledger PATH] [--thread TS]    one Magic post per listed open ask with no slack_ts,
      [--dry-run]                                          each ts written back to that ask as slack_ts
  ask-answers [--ledger PATH] [--out PATH]                 read-only JSON list of Drew's call on each posted ask
                                                           (done, drop, park, note); ledgers.py asks apply-answers applies it
  post-brief --file outputs/ai-team/{date}/brief.md        the brief as Magic: parent = title, greeting, The three things,
      [--tag-drew] [--dry-run] [--max-head-words 350]      Needs your call; every other ### section a reply in its thread;
      [--max-id-mentions 1] [--receipt PATH] [--repost]    prints JSON with parent_ts and replies (the count)
  selftest                                                 offline tests: guards, picks, paging, sweep, asks, brief

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

Paging (2026-09-28): with only "oldest" set, Slack hands back the OLDEST page of
the window first, so the old single 200-message read returned the wrong end of a
busy window. Every history read now follows cursors to the end and sorts.

Answered once, never asked again (Drew, 2026-09-28): the tip-off read only 24 to
72 hours of top-level posts, so Drew's rulings aged out and Magic asked again.
drew-sweep reads the whole channel since its watermark
(outputs/ai-team/ledgers/drew-sweep.json), every thread with activity since then
included, and lists each Drew message and reaction it has not reported before,
with the ask (A12) and topic (T8) ids it touches. post-asks gives each open ask
its own message: Drew taps :white_check_mark: (go or done), :x: (drop it, ignore
from now on) or :zzz: (park 14 days), or replies in its thread ("done", "ignore",
"park"). ask-answers reads those taps and replies and never edits the ledger.

Brief in a thread (Drew, 2026-09-28): the brief was one wall of text. post-brief strips
the frontmatter and posts only Drew's part as the parent: the title line, the greeting,
"### The three things" and "### Needs your call". It refuses (exit 2, nothing posted)
when that head runs over --max-head-words (350), when Needs your call has more than five
bullets, or when an ask id (A20) is named more than --max-id-mentions (1) times in the
head. Every other ### section goes in the parent's thread, one reply each: a reply under
400 characters rides with its neighbor, a section over 3,500 is cut at paragraph breaks.
The PII and dollar guards run on every part before anything posts. A receipt next to the
brief (brief-slack.json) records each post, so a re-run resumes where it stopped and
never posts twice; a changed brief is refused unless --repost.
"""
import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

CHANNEL = "C0C2745RULV"  # #ai-team (public), see Context/connector-ids.md
DREW = "U0A18TB6F"
ENV_FILE = os.path.expanduser("~/.config/digitalcliq-ai-team/slack.env")
LEDGER = "outputs/ai-team/topics.json"  # relative to the vault root, where the shift runs
ASKS = "outputs/ai-team/ledgers/asks.json"
SWEEP_STATE = "outputs/ai-team/ledgers/drew-sweep.json"

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

# Asks: one tappable message each (post-asks), Drew's call read back (ask-answers).
ASK_MAX_CHARS = 449  # "under 450 characters"
ASK_FIELDS = ("id", "store", "label", "ask")
ASK_ANSWERABLE = ("open", "parked")  # ledgers.py applies done, drop and park to both
REACTION_DECISION = {"white_check_mark": "done", "heavy_check_mark": "done", "+1": "done", "thumbsup": "done",
                     "x": "drop", "negative_squared_cross_mark": "drop", "zzz": "park"}
REPLY_DECISION = {"done": "done", "yes": "done", "go": "done", "fixed": "done",
                  "ignore": "drop", "ignored": "drop", "drop": "drop", "dropped": "drop", "no": "drop",
                  "nope": "drop", "skip": "drop", "skipped": "drop",
                  "park": "park", "parked": "park", "later": "park"}
ASK_ID = re.compile(r"\bA\d+\b", re.I)    # "A12"; "GA4" is not ask A4
TOPIC_ID = re.compile(r"\bT\d+\b", re.I)  # "T8"
THREAD_PAUSE = 1.2  # seconds between thread reads; conversations.replies is Tier 3 (about 50 a minute)
NOISE_SUBTYPES = ("channel_join", "channel_leave", "channel_topic", "channel_purpose", "channel_name",
                  "channel_archive", "channel_unarchive")


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
    for attempt in range(4):
        req = urllib.request.Request(url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                res = json.load(r)
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 3:  # rate limited: Slack did nothing, so waiting and retrying is safe
                try:
                    wait = float((e.headers or {}).get("Retry-After") or 5)
                except (TypeError, ValueError):
                    wait = 5.0
                _pause(min(max(wait, 1.0), 60.0))
                continue
            die("Slack HTTP %s" % e.code)
    if not res.get("ok"):
        die("Slack %s failed: %s" % (method, res.get("error")))
    return res


def _pause(seconds):
    time.sleep(seconds)


_LAST_PACED = [0.0]


def _throttle(gap=THREAD_PAUSE):
    """Keep at least gap seconds between paced reads (thread reads in drew-sweep and ask-answers)."""
    wait = _LAST_PACED[0] + gap - time.time()
    if wait > 0:
        _pause(wait)
    _LAST_PACED[0] = time.time()


def _tsk(ts):
    """Sort key for a Slack ts ("1789841289.951349") that keeps every microsecond."""
    sec, _, frac = str(ts or "0").partition(".")
    try:
        return int(sec), int((frac + "000000")[:6])
    except ValueError:
        return 0, 0


def _history(oldest=None, latest=None, inclusive=False):
    """Every top-level message in the window, newest first, following cursors to the end.
    With only oldest set Slack returns the OLDEST page first, so every page is read, repeats
    are dropped, and the result is sorted."""
    params = {"channel": CHANNEL, "limit": 200}
    if oldest:
        params["oldest"] = oldest
    if latest:
        params["latest"] = latest
    if inclusive:
        params["inclusive"] = "true"
    seen = {}
    while True:
        res = call("conversations.history", params, post=False)
        for m in res.get("messages", []):
            seen.setdefault(m.get("ts"), m)
        cur = (res.get("response_metadata") or {}).get("next_cursor")
        if not (res.get("has_more") and cur):
            break
        params["cursor"] = cur
    return sorted(seen.values(), key=lambda m: _tsk(m.get("ts")), reverse=True)


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


def strip_frontmatter(text):
    """A vault file's YAML frontmatter (--- ... ---) is metadata, not message text: the 2026-09-28
    brief reached Drew opening with it. Drop it when the file starts with one."""
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if 0 < end < 2000:
            return text[end + 5:].lstrip("\n")
    return text


def cmd_post(args):
    who = args.as_player.lower()
    if who not in PLAYERS:
        die("unknown player %s. Known: %s" % (who, ", ".join(PLAYERS)))
    text = args.text
    if args.file:
        with open(args.file) as f:
            text = f.read()
        text = strip_frontmatter(text)
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
        msgs = _thread(args.thread)  # parent first, then replies, every page
    else:
        oldest = "%.6f" % (time.time() - args.hours * 3600)
        msgs = list(reversed(_history(oldest=oldest)))  # oldest first, the whole window
    out = []
    for m in msgs:
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


def save_ledger(path, data, indent=2):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)
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


def _thread(ts, oldest=None, paced=False):
    """Every message in a thread (parent first), following cursors. paced keeps THREAD_PAUSE
    seconds between calls (drew-sweep and ask-answers read many threads in a row)."""
    params = {"channel": CHANNEL, "ts": ts, "limit": 200}
    if oldest:
        params.update(oldest=oldest, inclusive="true")
    out = []
    while True:
        if paced:
            _throttle()
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
    msgs = _history(oldest="%.6f" % (time.time() - args.days * 86400))
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


# ---- drew-sweep: everything Drew said, since the watermark ----

def _iso(ts):
    return datetime.fromtimestamp(float(ts)).astimezone().isoformat(timespec="seconds")


def _when(ts):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(float(ts)))


def _flat(text, n=None):
    s = " ".join((text or "").split())
    return s[:n] if n else s


def _ids(text):
    """Ask ids (A12) and topic ids (T8) named in a text, in order, no repeats."""
    def find(rx):
        out = []
        for x in rx.findall(text or ""):
            x = x.upper()
            if x not in out:
                out.append(x)
        return out
    return {"asks": find(ASK_ID), "topics": find(TOPIC_ID)}


def _author(m):
    if not m:
        return None
    if _is_drew(m):
        return "drew"
    return m.get("username") or (m.get("bot_profile") or {}).get("name") or m.get("user") or m.get("bot_id")


def _write_json(path, obj):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1)
        f.write("\n")
    os.replace(tmp, path)


def drew_sweep(state_path, days=14, advance=True, thread_days=3, all_threads=False, now=None):
    """(summary line, result) for every Drew message newer than the watermark in state_path, plus
    every Drew reaction not reported before. Parents are read back max(days, since the watermark),
    so a new reply under an older post is still found. A thread is read when it has a reply newer
    than the watermark (so no new reply can be missed), when it started in the last thread_days
    (Drew's reactions on replies carry no date), or with all_threads. The watermark then moves to
    the newest ts seen, never past the moment the sweep started."""
    now = time.time() if now is None else now
    state = {}
    if os.path.exists(state_path):
        try:
            with open(state_path) as f:
                state = json.load(f)
        except ValueError:
            print("WARNING: %s is not valid JSON; sweeping as a first run" % state_path, file=sys.stderr)
        if not isinstance(state, dict):
            state = {}
    first_run = not state.get("watermark")
    lookback = "%.6f" % (now - days * 86400)
    wm = str(state.get("watermark") or lookback)
    wmk = _tsk(wm)
    start = wm if wmk < _tsk(lookback) else lookback
    recent = _tsk("%.6f" % (now - thread_days * 86400))
    nowk = _tsk("%.6f" % now)  # a Drew message newer than the sweep's start is left for the next sweep

    top = _history(oldest=start)
    msgs = {m["ts"]: m for m in top if m.get("ts")}
    parents = [m for m in top if m.get("reply_count") and m.get("thread_ts", m.get("ts")) == m.get("ts")]
    thread_parent, threads_read, replies_read = {}, 0, 0
    for p in parents:
        lr = p.get("latest_reply")
        if not (all_threads or not lr or _tsk(lr) > wmk or _tsk(p["ts"]) >= recent):
            continue
        threads_read += 1
        for r in _thread(p["ts"], paced=True):
            if r.get("ts") and r["ts"] != p["ts"]:
                replies_read += 1
                msgs.setdefault(r["ts"], r)
                thread_parent[r["ts"]] = p

    seen_before = set(state.get("reactions_seen") or [])
    found, reacts, reacted = [], [], set()
    for ts in sorted(msgs, key=_tsk):
        m = msgs[ts]
        threaded = bool(m.get("thread_ts")) and m.get("thread_ts") != ts
        parent = (thread_parent.get(ts) or msgs.get(m.get("thread_ts"))) if threaded else None
        where = {"kind": "thread" if threaded else "top_level", "parent_ts": m.get("thread_ts") if threaded else None}
        if _is_drew(m) and m.get("subtype") not in NOISE_SUBTYPES and wmk < _tsk(ts) <= nowk:
            in_text = _ids(m.get("text"))
            in_parent = _ids((parent or {}).get("text")) if threaded else {"asks": [], "topics": []}
            found.append(dict(
                {"ts": ts, "iso": _iso(ts)}, **where,
                parent_author=_author(parent) if threaded else None,
                parent_first_200_chars=_flat((parent or {}).get("text"), 200) if parent else None,
                text=m.get("text") or "",
                files=[f.get("name") for f in m.get("files", [])] or None,
                ids={"asks": in_text["asks"] + [x for x in in_parent["asks"] if x not in in_text["asks"]],
                     "topics": in_text["topics"] + [x for x in in_parent["topics"] if x not in in_text["topics"]],
                     "in_text": in_text, "in_parent": in_parent}))
        for r in m.get("reactions") or []:
            if DREW not in (r.get("users") or []):
                continue
            name = (r.get("name") or "").split("::")[0]
            key = "%s %s" % (ts, name)
            if key in reacted:
                continue
            reacted.add(key)
            if key in seen_before:
                continue
            reacts.append(dict({"ts": ts, "emoji": name}, **where, author=_author(m),
                               first_200_chars=_flat(m.get("text"), 200), ids=_ids(m.get("text"))))

    newest = max(msgs, key=_tsk) if msgs else None
    new_wm = wm
    if newest and _tsk(newest) > wmk:
        cap = "%.6f" % now  # a message landing mid-sweep is read again next time, never skipped
        new_wm = newest if _tsk(newest) <= _tsk(cap) else cap
    keep_from = _tsk("%.6f" % (now - max(days, 60) * 86400))
    result = {
        "channel": CHANNEL, "state": state_path, "first_run": first_run,
        "since_ts": wm, "since": _iso(wm), "scanned_from": _iso(start),
        "scanned": {"top_level": len(top), "threads": len(parents), "threads_read": threads_read,
                    "thread_replies": replies_read},
        "messages": found, "reactions": reacts,
        "reactions_already_reported": len(reacted & seen_before),
        "watermark_before": wm, "watermark_after": new_wm if advance else wm,
        "advanced": bool(advance and new_wm != wm),
    }
    if advance:
        _write_json(state_path, {
            "_about": ("drew-sweep state (slack.py). watermark = newest #ai-team ts already swept; the next sweep "
                       "reports only Drew messages newer than it. reactions_seen = 'message_ts emoji' pairs of "
                       "Drew's reactions already reported (reactions carry no date)."),
            "watermark": new_wm, "watermark_iso": _iso(new_wm), "last_run": _iso(now),
            "last_found": {"messages": len(found), "reactions": len(reacts)},
            "reactions_seen": sorted((k for k in reacted | seen_before if _tsk(k.split(" ")[0]) >= keep_from),
                                     key=lambda k: (_tsk(k.split(" ")[0]), k)),
        })
    if not advance:
        tail = "watermark not advanced (--no-advance)"
    elif new_wm != wm:
        tail = "watermark moved to %s" % _when(new_wm)
    else:
        tail = "watermark unchanged"
    summary = "%d new Drew message%s since %s (%d new Drew reaction%s; read %d top-level, %d of %d threads, %d replies); %s" % (
        len(found), "" if len(found) == 1 else "s", _when(wm), len(reacts), "" if len(reacts) == 1 else "s",
        len(top), threads_read, len(parents), replies_read, tail)
    return summary, result


def cmd_drew_sweep(args):
    summary, result = drew_sweep(args.state, args.days, not args.no_advance, args.thread_days, args.all_threads)
    if args.out:
        _write_json(args.out, result)
    print(summary)
    print(json.dumps(result, indent=1))


# ---- asks: one tappable message each, and Drew's call read back ----

def load_asks(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        die("no asks ledger at %s" % path)
    except ValueError as e:
        die("asks ledger %s is not valid JSON: %s" % (path, e))
    if not isinstance(data, dict) or not isinstance(data.get("asks"), list):
        die('asks ledger %s has no "asks" list' % path)
    return data


def ask_message(a, in_thread=False):
    """(text, trimmed_fields, problem) for one ask, as it will reach Slack. In a thread the ask has no
    thread of its own, so a reply there has to start with its id."""
    f = {k: " ".join(str(a.get(k) or "").split()) for k in ASK_FIELDS}
    missing = [k for k in ASK_FIELDS if not f[k]]
    if missing:
        return None, [], "ask %s is missing %s" % (f["id"] or "?", ", ".join(missing))
    store = "all stores" if f["store"].upper() == "ALL" else f["store"]
    tail = ("Tap :white_check_mark: = go or done, :x: = drop it (ignore from now on), :zzz: = park 14 days, or "
            + ("reply here starting with %s." % f["id"] if in_thread else "reply in this thread."))

    def render():
        return clean("%s for %s: %s %s %s" % (f["id"], store, _sentence(f["label"]), _sentence(f["ask"]), tail))

    text, trimmed = render(), []
    for key in ("ask", "label"):  # the full ask stays in the ledger
        over = len(text) - ASK_MAX_CHARS
        if over <= 0:
            break
        cut = _shorten(f[key], len(f[key]) - over)
        if cut != f[key]:
            f[key] = cut
            trimmed.append(key)
            text = render()
    if len(text) > ASK_MAX_CHARS:
        return text, trimmed, "ask %s is %d characters even trimmed (limit %d)" % (f["id"], len(text), ASK_MAX_CHARS)
    return text, trimmed, None


def ask_problem(aid, text):
    if pii_problem(text):
        return "ask %s: text looks like it holds a phone number or email address" % aid
    bad = dollar_damage(text)
    if bad:
        return "ask %s: text looks shell-mangled near %r (a $ amount lost its digits); fix it in the ledger" % (aid, bad)
    return None


def _id_list(s):
    out = []
    for x in re.split(r"[\s,]+", s or ""):
        x = x.strip().upper()
        if x and x not in out:
            out.append(x)
    return out


def _find_ask(data, aid):
    return next((a for a in data["asks"] if str(a.get("id") or "").upper() == aid), None)


def cmd_post_asks(args):
    ids = _id_list(args.ids)
    if not ids:
        die("--ids is empty: name the asks to post, e.g. --ids A20,A27")
    data = load_asks(args.ledger)
    plan, skipped, problems = [], [], []
    for aid in ids:
        a = _find_ask(data, aid)
        if a is None:
            problems.append("no ask %s in %s" % (aid, args.ledger))
            continue
        if a.get("status") != "open":
            skipped.append({"id": aid, "why": "status is %s, only open asks are posted" % a.get("status")})
            continue
        if a.get("slack_ts"):
            skipped.append({"id": aid, "why": "already in Slack, slack_ts %s" % a["slack_ts"]})
            continue
        text, trimmed, problem = ask_message(a, bool(args.thread))
        problem = problem or ask_problem(aid, text)
        if problem:
            problems.append(problem)
        plan.append({"id": aid, "store": a.get("store"), "chars": len(text or ""), "trimmed": trimmed or None,
                     "problem": problem, "text": text})
    if args.dry_run:
        print(json.dumps({"dry_run": True, "ledger": args.ledger, "thread": args.thread, "would_post": plan,
                          "skipped": skipped, "problems": problems or None,
                          "note": "nothing posted, ledger unchanged"}, indent=1))
        if problems:
            sys.exit(2)
        return
    if problems:
        die("nothing posted, fix these first:\n  " + "\n  ".join(problems), 2)
    posted = []
    for p in plan:
        fresh = load_asks(args.ledger)  # re-read each time: ledgers.py may have written since
        a = _find_ask(fresh, p["id"])
        if a is None or a.get("status") != "open" or a.get("slack_ts"):
            skipped.append({"id": p["id"], "why": "changed in the ledger before posting (gone, not open, or already posted)"})
            continue
        ts = send("magic", p["text"], args.thread)
        a["slack_ts"] = ts
        if args.thread:
            a["slack_thread"] = args.thread
        save_ledger(args.ledger, fresh, indent=1)  # after every post, so a crash never double-posts
        posted.append({"id": p["id"], "ts": ts})
    print(json.dumps({"ledger": args.ledger, "thread": args.thread, "posted": posted, "skipped": skipped,
                      "note": None if posted else "no listed ask is open without a slack_ts"}, indent=1))


_TOKEN = re.compile(r":[a-z0-9_+'-]+:|[a-z0-9']+")


def _word_decision(w):
    if not w:
        return None
    if len(w) > 2 and w[0] == ":" and w[-1] == ":":
        return REACTION_DECISION.get(w.strip(":").split("::")[0])
    return REPLY_DECISION.get(w)


BARE_NO = ("no", "nope")  # drop only as a bare answer: "no", "no thanks", "nope", "A20 no, A21 done"


def _decide(toks, j):
    """The decision word at toks[j]. "no" and "nope" drop only when nothing, "thanks", an ask id or another
    drop word follows; "no rush, after Oct 1" and "no idea" are notes, never a drop and a standing ruling."""
    w = toks[j] if j is not None and 0 <= j < len(toks) else None
    d = _word_decision(w)
    if d == "drop" and w in BARE_NO:
        nxt = toks[j + 1] if j + 1 < len(toks) else None
        if not (nxt is None or nxt in ("thanks", "thank", "thx") or re.fullmatch(r"a\d+", nxt)
                or _word_decision(nxt) == "drop"):
            return None
    return d


def reply_decision(text, ask_id, own_thread):
    """Drew's call on ask_id in one reply: "done", "drop", "park" or "note", or None when the reply is
    not about this ask. In the ask's own thread a reply that names no ask counts on its first word
    ("done", "Ignore them, the page is stale", "park it"); a reply that names asks counts only for the
    ones it names, each taking the word after it, or before it at the end ("A20 done, A21 drop",
    "A20 and A21 park", "drop A20"). Outside its own thread the reply must name the ask."""
    toks = _TOKEN.findall(re.sub(r"<[^>]*>", " ", text or "").lower())  # mentions and links out
    aid = str(ask_id).lower()

    def is_id(w):
        return re.fullmatch(r"a\d+", w) is not None

    named = [w for w in toks if is_id(w)]
    if not named:
        if not own_thread:
            return None
        return _decide(toks, 0) or "note"
    if aid not in named:
        return None
    i = toks.index(aid)
    skip = ("and", "plus", "also", "on")
    after = next((j for j in range(i + 1, len(toks)) if not is_id(toks[j]) and toks[j] not in skip), None)
    if after is not None:
        return _decide(toks, after) or "note"
    before = next((j for j in range(i - 1, -1, -1) if not is_id(toks[j]) and toks[j] not in skip), None)
    return _decide(toks, before) or "note"


def reaction_decisions(msg):
    """[(decision, emoji)] for Drew's decision reactions on a message."""
    out = []
    for r in msg.get("reactions") or []:
        if DREW not in (r.get("users") or []):
            continue
        name = (r.get("name") or "").split("::")[0]
        if name in REACTION_DECISION:
            out.append((REACTION_DECISION[name], name))
    return out


def ask_answers(ledger_path, today=None):
    """([answer], [waiting ids], [missing]) for every open or parked ask with a slack_ts. A decisive
    reply (the latest one) outranks a reaction, since reactions carry no date; a reaction outranks a
    plain note. Every other signal is listed in other_signals."""
    today = today or time.strftime("%Y-%m-%d")
    data = load_asks(ledger_path)
    answers, waiting, missing, threads = [], [], [], {}
    for a in data["asks"]:
        if a.get("status") not in ASK_ANSWERABLE or not a.get("slack_ts"):
            continue
        aid, ts, parent = str(a.get("id")), str(a["slack_ts"]), a.get("slack_thread")
        if parent and str(parent) != ts:
            parent = str(parent)
            if parent not in threads:
                threads[parent] = _thread(parent, paced=True)
            msg = next((m for m in threads[parent] if m.get("ts") == ts), None)
            later = [m for m in threads[parent] if _tsk(m.get("ts")) > _tsk(ts)]
            own = False
        else:
            _throttle()
            res = call("conversations.history", {"channel": CHANNEL, "latest": ts, "oldest": ts,
                                                 "inclusive": "true", "limit": 1}, post=False)
            msg = next((m for m in res.get("messages", []) if m.get("ts") == ts), None)
            later = [m for m in _thread(ts, paced=True) if m.get("ts") != ts] if msg and msg.get("reply_count") else []
            own = True
        if msg is None:
            missing.append({"id": aid, "slack_ts": ts, "why": "message not found (deleted, or posted in a thread "
                                                               "with no slack_thread in the ledger)"})
            continue
        reacts = reaction_decisions(msg)
        replies = []
        for m in later:
            if _is_drew(m):
                d = reply_decision(m.get("text"), aid, own)
                if d:
                    replies.append((d, m))
        decisive = [x for x in replies if x[0] != "note"]
        notes = [x for x in replies if x[0] == "note"]
        signals = ["reaction :%s: (%s)" % (e, d) for d, e in reacts] + \
                  ["reply %s (%s): %s" % (m["ts"], d, _flat(m.get("text"), 120)) for d, m in replies]
        if decisive:
            d, m = decisive[-1]
            pick = {"decision": d, "source": "reply", "ts": m["ts"], "text": _flat(m.get("text")), "date": _day(m["ts"])}
            used = "reply %s (%s): %s" % (m["ts"], d, _flat(m.get("text"), 120))
        elif reacts:
            kinds = sorted({d for d, _ in reacts})
            names = " ".join(":%s:" % e for _, e in reacts)
            if len(kinds) == 1:
                pick = {"decision": kinds[0], "source": "reaction", "ts": ts, "text": None, "reaction": names,
                        "date": today}  # Slack does not date reactions: the day it was seen
            else:
                pick = {"decision": "note", "source": "reaction", "ts": ts, "reaction": names, "date": today,
                        "text": "Conflicting reactions on %s: %s. Ask Drew which one stands." % (aid, names)}
            used = None
        elif notes:
            d, m = notes[-1]
            pick = {"decision": "note", "source": "reply", "ts": m["ts"], "text": _flat(m.get("text")), "date": _day(m["ts"])}
            used = "reply %s (%s): %s" % (m["ts"], d, _flat(m.get("text"), 120))
        else:
            waiting.append(aid)
            continue
        other = [s for s in signals if s != used and not (used is None and s.startswith("reaction "))]
        answers.append(dict({"id": aid}, **pick, store=a.get("store"), label=a.get("label"), slack_ts=ts,
                            other_signals=other))
    return answers, waiting, missing


def cmd_ask_answers(args):
    answers, waiting, missing = ask_answers(args.ledger)
    if args.out:
        _write_json(args.out, answers)
    print(json.dumps(answers, indent=1))
    said = ", ".join("%s %s" % (x["id"], x["decision"]) for x in answers) or "none"
    print("ask-answers: %d answered (%s); %d posted with no answer yet%s; %d missing%s. Ledger untouched."
          % (len(answers), said, len(waiting), " (%s)" % ", ".join(waiting) if waiting else "", len(missing),
             " (%s)" % ", ".join(x["id"] for x in missing) if missing else ""), file=sys.stderr)


# ---- post-brief: Drew's decisions up top, everything else in the thread ----

BRIEF_HEAD = ("the three things", "needs your call")  # the only ### sections that ride in the parent
BRIEF_MAX_HEAD_WORDS = 350
BRIEF_MAX_CALLS = 5         # Needs your call: Drew's decisions, five bullets at most
BRIEF_MAX_ID_MENTIONS = 1   # each ask id is named once in the head, never repeated
REPLY_MAX_CHARS = 3500      # a thread reply longer than this is split at paragraph breaks
SLACK_MAX_CHARS = 40000     # Slack's hard limit on one message
TINY_REPLY_CHARS = 400      # a reply this short rides with its neighbor while the pair fits REPLY_MAX_CHARS
POST_PAUSE = 1.1            # seconds between posts; chat.postMessage allows about one a second per channel
BRIEF_RECEIPT = "brief-slack.json"  # written next to brief.md, so a re-run resumes or posts nothing
HEAD_ASK_ID = re.compile(r"\bA\d+\b")  # case-sensitive, as the ledger writes them; "GA4" is not A4
LIST_ITEM = re.compile(r"^(?:[-*+]|\d+[.)])\s+")
_SPLIT_AT = (("\n\n", re.compile(r"\n(?:[ \t]*\n)+")), ("\n", re.compile(r"\n")), (" ", re.compile(r"[ \t]+")))


def _heading_name(line):
    return re.sub(r"\*+", "", line.lstrip("#").strip()).strip()


def brief_parts(text):
    """(title, preamble, [(name, block)]) of a brief: frontmatter dropped, split at '### ' headings.
    title is the first line when it is a heading other than '### ' ("## AI Team Brief, ..."), preamble
    is everything between it and the first '### ' heading (the greeting). Each block keeps its heading."""
    lines = strip_frontmatter(text.replace("\r\n", "\n")).split("\n")
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    title = ""
    if i < len(lines) and re.match(r"#{1,6}\s", lines[i]) and not lines[i].startswith("### "):
        title, i = lines[i].strip(), i + 1
    pre, sections = [], []
    for line in lines[i:]:
        if line.startswith("### "):
            sections.append([_heading_name(line), [line.rstrip()]])
        elif sections:
            sections[-1][1].append(line)
        else:
            pre.append(line)
    return title, "\n".join(pre).strip(), [(n, "\n".join(b).strip()) for n, b in sections]


def _word_count(text):
    """Words as Drew reads them: heading marks and list markers are not words."""
    n = 0
    for line in text.split("\n"):
        line = LIST_ITEM.sub("", re.sub(r"^\s*#{1,6}\s+", "", line).lstrip())
        n += sum(1 for w in line.split() if re.search(r"[A-Za-z0-9]", w))
    return n


def _pack(pieces, limit, sep):
    out = []
    for p in pieces:
        if out and len(out[-1]) + len(sep) + len(p) <= limit:
            out[-1] += sep + p
        else:
            out.append(p)
    return out


def split_text(text, limit, level=0):
    """text in pieces of at most limit characters: cut at paragraph breaks first, then at line breaks,
    then between words, and mid-word only for a single word longer than limit."""
    if not text.strip():
        return []
    if len(text) <= limit:
        return [text]
    if level == len(_SPLIT_AT):
        return [text[i:i + limit] for i in range(0, len(text), limit)]
    sep, rx = _SPLIT_AT[level]
    small = []
    for p in rx.split(text):
        small.extend(split_text(p, limit, level + 1))
    return _pack(small, limit, sep)


def brief_thread(sections, limit=REPLY_MAX_CHARS, tiny=TINY_REPLY_CHARS):
    """[{"sections", "text"}] thread replies as Slack will show them: one per section, a section over
    limit cut at paragraph breaks (each later piece headed "*Name (continued)*"), and a reply under
    tiny characters merged with its neighbor while the pair still fits in limit."""
    pieces = []
    for name, block in sections:
        label = clean("*%s (continued)*" % name) + "\n"
        for k, p in enumerate(split_text(clean(block), limit - len(label))):
            pieces.append(([name], p) if k == 0 else (["%s (continued)" % name], label + p))
    replies = []
    for names, text in pieces:
        last = replies[-1] if replies else None
        if last and (len(last["text"]) < tiny or len(text) < tiny) and len(last["text"]) + 2 + len(text) <= limit:
            last["text"] += "\n\n" + text
            last["sections"] += names
        else:
            replies.append({"sections": list(names), "text": text})
    return replies


def _ordered_ids(text):
    out = []
    for x in HEAD_ASK_ID.findall(text or ""):
        if x not in out:
            out.append(x)
    return out


def brief_plan(text, max_words=BRIEF_MAX_HEAD_WORDS, max_mentions=BRIEF_MAX_ID_MENTIONS,
               max_calls=BRIEF_MAX_CALLS):
    """What post-brief would send, with every reason to refuse it. The parent (head) is the title, the
    greeting, The three things and Needs your call; every other ### section goes in its thread."""
    title, pre, sections = brief_parts(text)
    in_head = lambda n: n.lower().startswith(BRIEF_HEAD)
    head_secs = [(n, b) for n, b in sections if in_head(n)]
    head = clean("\n\n".join(x for x in [title, pre] + [b for _, b in head_secs] if x))
    words = _word_count(head)
    calls = [line for n, b in head_secs if n.lower().startswith("needs your call")
             for line in b.split("\n") if LIST_ITEM.match(line)]
    mentions = {}
    for x in HEAD_ASK_ID.findall(head):
        mentions[x] = mentions.get(x, 0) + 1
    repeated = [x for x in _ordered_ids(head) if mentions[x] > max_mentions]
    thread = brief_thread([(n, b) for n, b in sections if not in_head(n)])

    problems, warnings = [], []
    if words > max_words:
        problems.append("head is %d words (limit %d). The parent carries only the title, the greeting, The three "
                        "things and Needs your call: cut those to %d words and let the detail live in the other "
                        "sections, which go in the thread." % (words, max_words, max_words))
    if len(calls) > max_calls:
        problems.append("Needs your call has %d bullets (limit %d): keep Drew's %d biggest decisions there and move "
                        "the rest to Action items." % (len(calls), max_calls, max_calls))
    for x in repeated:
        problems.append("%s is named %d times in the head (limit %d): say each ask once, in The three things or in "
                        "Needs your call, not both." % (x, mentions[x], max_mentions))
    parts = [("head", head)] + [("reply %d (%s)" % (i, ", ".join(r["sections"])), r["text"])
                                for i, r in enumerate(thread, 1)]
    for label, t in parts:
        if pii_problem(t):
            problems.append("%s: text looks like it holds a phone number or email address; #ai-team gets "
                            "aggregates only" % label)
        bad = dollar_damage(t)
        if bad:
            problems.append("%s: text looks shell-mangled near %r (a $ amount lost its digits); fix brief.md" % (label, bad))
        if len(t) > SLACK_MAX_CHARS:
            problems.append("%s is %d characters, over Slack's %d limit" % (label, len(t), SLACK_MAX_CHARS))
    for want in ("The three things", "Needs your call"):
        if not any(n.lower().startswith(want.lower()) for n, _ in head_secs):
            warnings.append("no '### %s' section, so the parent carries less than it should" % want)
    for k, line in enumerate(calls, 1):
        if not HEAD_ASK_ID.search(line):
            warnings.append("Needs your call bullet %d names no ask id (%s): post-asks cannot make it a message "
                            "Drew can tap" % (k, _flat(LIST_ITEM.sub("", clean(line)), 60)))
    if not sections:
        warnings.append("no '### ' sections at all: nothing goes in the thread")
    return {
        "head": {"words": words, "max_words": max_words, "chars": len(head),
                 "sections": [n for n, _ in head_secs], "needs_call_bullets": len(calls), "max_calls": max_calls,
                 "needs_call_ids": _ordered_ids("\n".join(calls)), "ask_id_mentions": mentions,
                 "repeated_ids": repeated, "text": head},
        "thread": [dict(r, n=i, chars=len(r["text"])) for i, r in enumerate(thread, 1)],
        "problems": problems, "warnings": warnings,
    }


def _receipt_state(path, sha, repost=False):
    """(state, receipt): none, posted (all of this exact file is in Slack), partial (this file, not every
    reply yet), or changed (a different version of the brief already has a parent in Slack)."""
    if repost or not os.path.exists(path):
        return "none", None
    try:
        with open(path, encoding="utf-8") as f:
            rec = json.load(f)
    except ValueError:
        return "none", None
    if not isinstance(rec, dict) or not rec.get("parent_ts"):
        return "none", None
    if rec.get("sha256") != sha:
        return "changed", rec
    done = len(rec.get("replies") or []) >= int(rec.get("parts") or 0)
    return ("posted" if done else "partial"), rec


def cmd_post_brief(args):
    try:
        with open(args.file, encoding="utf-8") as f:
            raw = f.read()
    except OSError as e:
        die("cannot read %s: %s" % (args.file, e))
    if not strip_frontmatter(raw).strip():
        die("empty brief: %s" % args.file)
    plan = brief_plan(raw, args.max_head_words, args.max_id_mentions)
    head, thread = plan["head"], plan["thread"]
    receipt = args.receipt or os.path.join(os.path.dirname(args.file), BRIEF_RECEIPT)
    sha = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    state, rec = _receipt_state(receipt, sha, args.repost)
    problems = list(plan["problems"])
    if state == "changed":
        problems.append("this brief already has a parent in #ai-team (ts %s, receipt %s) and the file changed since. "
                        "Post the correction in that thread (slack.py post --as magic --file PATH --thread %s), or "
                        "add --repost to post the whole brief again as a new message." % (rec["parent_ts"], receipt,
                                                                                          rec["parent_ts"]))
    if args.dry_run:
        refused = bool(problems)
        print(json.dumps({
            "dry_run": True, "file": args.file, "refused": refused, "problems": problems or None,
            "warnings": plan["warnings"] or None, "tag_drew": bool(args.tag_drew),
            "head": head, "replies": len(thread),
            "thread": [{"n": r["n"], "chars": r["chars"], "sections": r["sections"],
                        "preview": _flat(r["text"], 100)} for r in thread],
            "receipt": {"path": receipt, "state": state, "parent_ts": (rec or {}).get("parent_ts")},
            "note": "nothing posted, nothing written" + ("; a real run would refuse" if refused else "")}, indent=1))
        if refused:
            sys.exit(2)
        return
    if problems:
        die("nothing posted, fix these first:\n  " + "\n  ".join(problems), 2)
    if state == "posted":
        out = {"file": args.file, "already_posted": True, "parent_ts": rec["parent_ts"],
               "replies": len(rec["replies"]), "reply_ts": [r["ts"] for r in rec["replies"]], "posted_now": 0,
               "receipt": receipt, "note": "this exact brief is already in #ai-team; nothing posted"}
        print(json.dumps(out, indent=1))
        print("post-brief: already posted, parent ts %s, %d replies; nothing posted" % (rec["parent_ts"], len(rec["replies"])),
              file=sys.stderr)
        return
    if state != "partial":
        rec = {"_about": ("post-brief receipt (slack.py): what of this brief is already in #ai-team. A re-run of the same "
                          "file resumes or posts nothing; a changed file is refused unless --repost."),
               "file": args.file, "sha256": sha, "channel": CHANNEL, "parent_ts": None, "tag_drew": bool(args.tag_drew),
               "parts": len(thread), "replies": [], "started": _iso(time.time()), "finished": None}
    done = {int(r["n"]) for r in rec["replies"]}
    posted_now = 0
    if not rec.get("parent_ts"):
        rec["parent_ts"] = send("magic", head["text"], None, args.tag_drew)
        _LAST_PACED[0] = time.time()
        posted_now += 1
        _write_json(receipt, rec)  # after every post, so a crash never double-posts
    for r in thread:
        if r["n"] in done:
            continue
        _throttle(POST_PAUSE)
        ts = send("magic", r["text"], rec["parent_ts"])
        posted_now += 1
        rec["replies"].append({"n": r["n"], "ts": ts, "sections": r["sections"]})
        _write_json(receipt, rec)
    rec["finished"] = _iso(time.time())
    _write_json(receipt, rec)
    out = {"file": args.file, "already_posted": False, "parent_ts": rec["parent_ts"], "replies": len(rec["replies"]),
           "reply_ts": [r["ts"] for r in rec["replies"]], "posted_now": posted_now, "head_words": head["words"],
           "needs_call_ids": head["needs_call_ids"], "warnings": plan["warnings"] or None, "receipt": receipt}
    print(json.dumps(out, indent=1))
    print("post-brief: parent ts %s, %d replies in its thread (%d posted now); receipt %s"
          % (rec["parent_ts"], len(rec["replies"]), posted_now, receipt), file=sys.stderr)


# ---- offline tests ----

class _FakeSlack:
    """Enough of the Slack Web API for offline tests. Like the real API, history with only oldest set
    returns the OLDEST page first (each page newest first); pages are `page` messages long."""

    def __init__(self, top=(), threads=None, page=2):
        self.top = [dict(m) for m in top]
        self.threads = {k: [dict(m) for m in v] for k, v in (threads or {}).items()}
        self.page, self.calls, self.posted = page, [], []

    def __call__(self, method, params, post=True):
        self.calls.append((method, dict(params)))
        if method == "conversations.history":
            lo, hi, inc = params.get("oldest"), params.get("latest"), params.get("inclusive") == "true"

            def inside(m):
                k = _tsk(m["ts"])
                if lo and (k < _tsk(lo) or (k == _tsk(lo) and not inc)):
                    return False
                return not (hi and (k > _tsk(hi) or (k == _tsk(hi) and not inc)))
            ms = sorted((m for m in self.top if inside(m)), key=lambda m: _tsk(m["ts"]), reverse=not (lo and not hi))
            return self._page(ms, params, True)
        if method == "conversations.replies":
            parent = next((m for m in self.top if m["ts"] == params["ts"]), {"ts": params["ts"]})
            ms = [parent] + sorted(self.threads.get(params["ts"], []), key=lambda m: _tsk(m["ts"]))
            return self._page(ms, params, False)
        if method == "chat.postMessage":
            ts = "1790000000.%06d" % (len(self.posted) + 1)
            self.posted.append(dict(params, ts=ts))
            return {"ok": True, "ts": ts}
        raise AssertionError("unexpected Slack call " + method)

    def _page(self, ms, params, newest_first):
        size = min(int(params.get("limit") or 200), self.page)
        at = int(params.get("cursor") or 0)
        chunk = ms[at:at + size]
        if newest_first:
            chunk = sorted(chunk, key=lambda m: _tsk(m["ts"]), reverse=True)
        more = at + size < len(ms)
        return {"ok": True, "messages": [dict(m) for m in chunk], "has_more": more,
                "response_metadata": {"next_cursor": str(at + size) if more else ""}}

    def count(self, method):
        return sum(1 for c in self.calls if c[0] == method)


def _run(fn, args):
    """Run a command offline: (exit code, stdout, stderr)."""
    out, err, code = io.StringIO(), io.StringIO(), 0
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            fn(argparse.Namespace(**args))
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
    return code, out.getvalue(), err.getvalue()


def _selftest_slack(check):
    """Paging, drew-sweep, post-asks and ask-answers against a fake Slack. No token, no network."""
    g = globals()
    real_call, real_pause, real_urlopen = g["call"], g["_pause"], urllib.request.urlopen
    tmp = tempfile.mkdtemp(prefix="slack-selftest-")
    now = time.time()

    def T(hours):
        return "%.6f" % (now - hours * 3600)

    def use(fake):
        g["call"] = fake
        return fake

    try:
        g["_pause"] = lambda s: None

        # 429: one rate-limit answer, then the call goes through.
        hits = []

        class _Resp(io.BytesIO):
            pass

        def fake_urlopen(req, timeout=30):
            hits.append(req.full_url)
            if len(hits) == 1:
                raise urllib.error.HTTPError(req.full_url, 429, "ratelimited", {"Retry-After": "1"}, None)
            return _Resp(b'{"ok": true, "messages": []}')
        old_tok = os.environ.get("SLACK_BOT_TOKEN")
        os.environ["SLACK_BOT_TOKEN"] = "xoxb-selftest-not-real"
        urllib.request.urlopen = fake_urlopen
        try:
            res = real_call("conversations.history", {"channel": CHANNEL}, post=False)
        finally:
            urllib.request.urlopen = real_urlopen
            if old_tok is None:
                os.environ.pop("SLACK_BOT_TOKEN", None)
            else:
                os.environ["SLACK_BOT_TOKEN"] = old_tok
        check("429 retried once, then ok", (len(hits), res.get("ok")), (2, True))

        # Paging: 7 posts in the window, 2 per page, oldest page first (as Slack does).
        bot = {"bot_id": "B1", "username": "Kobe #24"}
        seven = [dict(bot, ts=T(20 - i), text="post %d" % i) for i in range(7)]
        f = use(_FakeSlack(seven + [dict(bot, ts=T(30), text="outside the window")], page=2))
        got = _history(oldest=T(24))
        check("history pages to the end", [m["text"] for m in got], ["post %d" % i for i in range(6, -1, -1)])
        check("history used every page", f.count("conversations.history"), 4)
        check("cursor passed on", [c[1].get("cursor") for c in f.calls], [None, "2", "4", "6"])
        f = use(_FakeSlack(seven, page=2))
        code, out, _ = _run(cmd_read, {"hours": 24, "thread": None})
        rows = json.loads(out)
        check("read --hours: every post, oldest first", [r["text"] for r in rows], ["post %d" % i for i in range(7)])
        check("read --hours: same keys as before", sorted(rows[0]),
              sorted(["ts", "from", "is_drew", "thread_ts", "replies", "files", "text"]))
        p = dict(bot, ts=T(10), text="parent", reply_count=5, thread_ts=T(10))
        f = use(_FakeSlack([p], {p["ts"]: [dict(bot, ts=T(9 - i), thread_ts=p["ts"], text="r%d" % i) for i in range(5)]}, page=2))
        code, out, _ = _run(cmd_read, {"hours": 24, "thread": p["ts"]})
        check("read --thread: parent then every reply", [r["text"] for r in json.loads(out)],
              ["parent", "r0", "r1", "r2", "r3", "r4"])
        check("read --thread paged", f.count("conversations.replies"), 3)

        # drew-sweep: watermark, threads, reactions, ids.
        magic, worthy = {"bot_id": "B1", "username": "Magic #32"}, {"bot_id": "B1", "username": "Worthy #42"}
        drew = {"user": DREW}
        d1 = dict(drew, ts=T(120), text="Nick, A2 is dead: ignore Auto Credit Express. GA4 is fine.")
        p1 = dict(magic, ts=T(48), thread_ts=T(48), reply_count=2, latest_reply=T(24), text="Topic T8 for MCP: Wagoneer S.",
                  reactions=[{"name": "white_check_mark", "users": [DREW], "count": 1}])
        p1r = [dict(magic, ts=T(47.9), thread_ts=p1["ts"], text="more on T8"),
               dict(drew, ts=T(24), thread_ts=p1["ts"], text="pick")]
        p2 = dict(worthy, ts=T(240), thread_ts=T(240), reply_count=1, latest_reply=T(239), text="A5 NCBMW tracking, first look")
        p2r = [dict(worthy, ts=T(239), thread_ts=p2["ts"], text="details",
                    reactions=[{"name": "zzz", "users": [DREW], "count": 1}])]
        top = [d1, p1, p2,
               dict(drew, ts=T(500), text="older than the window"),
               dict(drew, bot_id="B9", username="Magic #32", ts=T(100), text="a bot posting with Drew's id"),
               dict(drew, ts=T(90), subtype="channel_join", text="<@%s> has joined the channel" % DREW),
               dict(magic, ts=T(12), text="brief")]
        state = os.path.join(tmp, "sweep.json")
        use(_FakeSlack(top, {p1["ts"]: p1r, p2["ts"]: p2r}, page=2))
        summary, r = drew_sweep(state, days=14, now=now)
        check("sweep first run summary", summary.startswith("2 new Drew messages since "), True)
        check("sweep first run messages", [(m["text"], m["kind"]) for m in r["messages"]],
              [(d1["text"], "top_level"), ("pick", "thread")])
        check("sweep ids: A2 found, GA4 is not A4", r["messages"][0]["ids"]["asks"], ["A2"])
        check("sweep thread reply carries its parent", {k: r["messages"][1][k] for k in ("parent_ts", "parent_author")},
              {"parent_ts": p1["ts"], "parent_author": "Magic #32"})
        check("sweep ids from the parent", (r["messages"][1]["ids"]["topics"], r["messages"][1]["ids"]["in_text"]),
              (["T8"], {"asks": [], "topics": []}))
        check("sweep parent first 200 chars", r["messages"][1]["parent_first_200_chars"], p1["text"])
        check("sweep reactions anywhere", sorted((x["emoji"], x["kind"]) for x in r["reactions"]),
              [("white_check_mark", "top_level"), ("zzz", "thread")])
        check("sweep first run reads every thread", r["scanned"]["threads_read"], 2)
        with open(state) as fh:
            st = json.load(fh)
        check("sweep watermark = newest ts seen", (st["watermark"], r["watermark_after"], r["advanced"]),
              (T(12), T(12), True))
        summary, r = drew_sweep(state, days=14, now=now)
        check("sweep second run finds nothing new", (len(r["messages"]), len(r["reactions"]), r["reactions_already_reported"]),
              (0, 0, 1))  # the quiet 10-day-old thread is not re-read, so only the top-level checkmark is seen again
        check("sweep second run skips a quiet old thread", r["scanned"]["threads_read"], 1)
        check("sweep second run summary", summary.startswith("0 new Drew messages since "), True)
        new_reply = dict(drew, ts=T(1), thread_ts=p2["ts"], text="A5 done, fixed the tag")
        p2b = dict(p2, reply_count=2, latest_reply=new_reply["ts"])
        use(_FakeSlack([d1, p1, p2b, top[-1]], {p1["ts"]: p1r, p2["ts"]: p2r + [new_reply]}, page=2))
        with open(state, "rb") as fh:
            before = fh.read()
        summary, r = drew_sweep(state, days=14, advance=False, now=now)
        with open(state, "rb") as fh:
            check("sweep --no-advance leaves the state alone", fh.read(), before)
        check("sweep late reply under an old post is found", [(m["text"], m["parent_author"], m["ids"]["asks"]) for m in r["messages"]],
              [("A5 done, fixed the tag", "Worthy #42", ["A5"])])
        check("sweep --no-advance summary", summary.endswith("watermark not advanced (--no-advance)"), True)
        check("sweep keeps old reactions as reported", (r["reactions"], r["reactions_already_reported"]), ([], 2))
        summary, r = drew_sweep(state, days=14, advance=False, now=now)
        check("sweep --no-advance twice finds it again", len(r["messages"]), 1)
        drew_sweep(state, days=14, now=now)
        summary, r = drew_sweep(state, days=14, now=now)
        check("sweep after advancing finds it no more", len(r["messages"]), 0)
        summary, r = drew_sweep(state, days=14, all_threads=True, now=now)
        check("sweep --all-threads reads every thread", r["scanned"]["threads_read"], 2)
        mid = os.path.join(tmp, "mid.json")  # a Drew post landing mid-sweep is reported once, by the next sweep
        late = [dict(drew, ts=T(2), text="before"), dict(drew, ts="%.6f" % (now + 5), text="during the sweep")]
        use(_FakeSlack(late))
        _, r1 = drew_sweep(mid, days=14, now=now)
        use(_FakeSlack(late))
        _, r2 = drew_sweep(mid, days=14, now=now + 3600)
        check("sweep: a post landing mid-sweep is reported once, next time",
              ([m["text"] for m in r1["messages"]], [m["text"] for m in r2["messages"]]), (["before"], ["during the sweep"]))
        use(_FakeSlack([], {}))
        summary, r = drew_sweep(os.path.join(tmp, "empty.json"), days=10, advance=False, now=now)
        check("sweep of an empty window", (len(r["messages"]), r["advanced"], summary.startswith("0 new")), (0, False, True))

        # post-asks: message text, trimming, guards, ledger write-back.
        base = {"id": "A1", "store": "MCP", "label": "MCP auto-apply", "status": "open",
                "ask": "Check whether Google Ads auto-apply is still on"}
        text, trimmed, problem = ask_message(base)
        check("ask text", text, "A1 for MCP: MCP auto-apply. Check whether Google Ads auto-apply is still on. "
                                "Tap :white_check_mark: = go or done, :x: = drop it (ignore from now on), "
                                ":zzz: = park 14 days, or reply in this thread.")
        check("ask not trimmed", (trimmed, problem), ([], None))
        check("ask for ALL reads all stores", ask_message(dict(base, store="ALL"))[0].startswith("A1 for all stores: "), True)
        check("ask in a thread names its id", ask_message(base, True)[0].endswith("or reply here starting with A1."), True)
        long_ask = dict(base, ask="Confirm with the store whether Auto Credit Express and TrueCar are live vendors, " * 8)
        text, trimmed, problem = ask_message(long_ask)
        check("long ask fits under 450", (len(text) < 450, problem), (True, None))
        check("long ask trims the ask only", trimmed, ["ask"])
        check("long ask keeps its ending", text.endswith("or reply in this thread.") and "... Tap " in text, True)
        long_both = dict(long_ask, label="A label that runs on and on " * 12)
        text, trimmed, problem = ask_message(long_both)
        check("long label trimmed too", (len(text) < 450, trimmed, problem), (True, ["ask", "label"], None))
        check("ask missing field", ask_message(dict(base, ask=""))[2], "ask A1 is missing ask")
        check("ask phone refused", "phone number" in (ask_problem("A1", ask_message(dict(base, ask="Call (714) 555-0100"))[0]) or ""), True)
        check("ask dollar damage refused", "shell-mangled" in (ask_problem("A1", ask_message(dict(base, ask="Spend was ,497"))[0]) or ""), True)
        check("ask ids parsed", _id_list("a20, A27,A20  a3"), ["A20", "A27", "A3"])

        ledger = os.path.join(tmp, "asks.json")
        asks = {"_about": "test", "asks": [
            base, dict(base, id="A2", slack_ts="1789999999.000100"), dict(base, id="A3", status="closed"),
            dict(base, id="A4", store="ALL", label="GA4 link"), dict(base, id="A5", label="In a thread")]}
        save_ledger(ledger, asks, indent=1)
        with open(ledger, "rb") as fh:
            before = fh.read()
        f = use(_FakeSlack())
        code, out, _ = _run(cmd_post_asks, {"ledger": ledger, "ids": "a1,A2,A3,A4", "thread": None, "dry_run": True})
        o = json.loads(out)
        check("post-asks dry run plan", (code, [p["id"] for p in o["would_post"]], [s["id"] for s in o["skipped"]]),
              (0, ["A1", "A4"], ["A2", "A3"]))
        with open(ledger, "rb") as fh:
            check("post-asks dry run: ledger unchanged, nothing posted", (fh.read() == before, len(f.posted)), (True, 0))
        code, out, err = _run(cmd_post_asks, {"ledger": ledger, "ids": "A1,A99", "thread": None, "dry_run": False})
        check("post-asks unknown id: exit 2, nothing posted", (code, len(f.posted), "A99" in err), (2, 0, True))
        code, out, _ = _run(cmd_post_asks, {"ledger": ledger, "ids": "A1,A2,A4", "thread": None, "dry_run": False})
        o = json.loads(out)
        check("post-asks posted as Magic", [(x["username"], x["text"][:12]) for x in f.posted],
              [("Magic #32", "A1 for MCP: "), ("Magic #32", "A4 for all s")])
        check("post-asks posted text = ask text", f.posted[0]["text"], ask_message(base)[0])
        with open(ledger, encoding="utf-8") as fh:
            saved = {a["id"]: a for a in json.load(fh)["asks"]}
        check("post-asks ts written back", (saved["A1"]["slack_ts"], saved["A4"]["slack_ts"], "slack_thread" in saved["A1"]),
              (o["posted"][0]["ts"], o["posted"][1]["ts"], False))
        check("post-asks leaves the rest", (saved["A2"]["slack_ts"], saved["A3"].get("slack_ts"), saved["A5"].get("slack_ts")),
              ("1789999999.000100", None, None))
        code, out, _ = _run(cmd_post_asks, {"ledger": ledger, "ids": "A1,A4", "thread": None, "dry_run": False})
        check("post-asks never posts twice", (len(f.posted), json.loads(out)["posted"]), (2, []))
        code, out, _ = _run(cmd_post_asks, {"ledger": ledger, "ids": "A5", "thread": "1789000000.000001", "dry_run": False})
        with open(ledger, encoding="utf-8") as fh:
            a5 = _find_ask(json.load(fh), "A5")
        check("post-asks --thread", (f.posted[-1]["thread_ts"], a5["slack_thread"], f.posted[-1]["text"].endswith("starting with A5.")),
              ("1789000000.000001", "1789000000.000001", True))

        # ask-answers: the reply parser, then end to end.
        for s, aid, own, want in [
                ("done", "A1", True, "done"), ("Yes, go ahead", "A1", True, "done"), ("fixed it Friday", "A1", True, "done"),
                ("go", "A1", True, "done"), ("Ignore them, the VinSolutions cost page is stale", "A1", True, "drop"),
                ("no", "A1", True, "drop"), ("skip.", "A1", True, "drop"), ("park it", "A1", True, "park"),
                ("Later", "A1", True, "park"), ("latest numbers?", "A1", True, "note"), ("don't know", "A1", True, "note"),
                ("GA4 is fine", "A1", True, "note"), ("", "A1", True, "note"), ("done", "A1", False, None),
                ("A1 done", "A1", False, "done"), ("done A1", "A1", False, "done"), ("A2 done", "A1", False, None),
                ("A2 done", "A1", True, None), ("A1 and A2 drop", "A1", False, "drop"), ("A1 and A2 drop", "A2", False, "drop"),
                ("A1 done, A2 drop", "A1", False, "done"), ("A1 done, A2 drop", "A2", False, "drop"),
                ("<@U0A18TB6F> A1: park", "A1", False, "park"), (":white_check_mark:", "A1", True, "done"),
                (":x: stale", "A1", True, "drop"), ("A1 what is this?", "A1", False, "note"), ("A10 done", "A1", False, None),
                ("no thanks", "A1", True, "drop"), ("nope", "A1", True, "drop"), ("note", "A1", True, "note"),
                ("no rush, after Oct 1", "A1", True, "note"), ("No idea, ask Ron", "A1", True, "note"),
                ("A1 no, A2 done", "A1", False, "drop"), ("A1 no rush", "A1", False, "note"), ("no no", "A1", True, "drop")]:
            check("reply %r for %s own_thread=%s" % (s, aid, own), reply_decision(s, aid, own), want)
        check("reaction decisions", reaction_decisions({"reactions": [
            {"name": "+1::skin-tone-3", "users": [DREW]}, {"name": "x", "users": ["U9"]}, {"name": "eyes", "users": [DREW]}]}),
            [("done", "+1")])

        P = "1789900000.000100"
        X = {i: "17899%05d.000100" % i for i in range(1, 10)}
        rx = lambda *names: [{"name": n, "users": [DREW], "count": 1} for n in names]
        top = [dict(magic, ts=X[1], text="A1 ...", reactions=rx("white_check_mark")),
               dict(magic, ts=X[2], text="A2 ...", reply_count=1, thread_ts=X[2]),
               dict(magic, ts=P, text="brief", reply_count=3, thread_ts=P),
               dict(magic, ts=X[4], text="A4 ...", reply_count=1, thread_ts=X[4]),
               dict(magic, ts=X[5], text="A5 ...", reactions=[{"name": "white_check_mark", "users": ["U9"]}]),
               dict(magic, ts=X[6], text="A6 ...", reply_count=1, thread_ts=X[6], reactions=rx("zzz")),
               dict(magic, ts=X[9], text="A9 ...", reactions=rx("x", "white_check_mark"))]
        threads = {X[2]: [dict(drew, ts="1789950000.000002", thread_ts=X[2], text="Ignore them, the VinSolutions cost page is stale")],
                   P: [dict(magic, ts=X[3], thread_ts=P, text="A3 ..."),
                       dict(drew, ts="1789950000.000003", thread_ts=P, text="A9 done"),
                       dict(drew, ts="1789950000.000004", thread_ts=P, text="A3 park")],
                   X[4]: [dict(drew, ts="1789950000.000005", thread_ts=X[4], text="why is this still open?")],
                   X[6]: [dict(drew, ts="1789950000.000006", thread_ts=X[6], text="done, fixed Friday")]}
        sa = lambda i, **kw: dict(base, id="A%d" % i, slack_ts=X[i], **kw)
        save_ledger(ledger, {"_about": "test", "asks": [
            sa(1), sa(2), sa(3, slack_thread=P), sa(4), sa(5), sa(6), sa(7, status="parked"), sa(8, status="closed"),
            sa(9), dict(base, id="A10")]}, indent=1)
        with open(ledger, "rb") as fh:
            before = fh.read()
        f = use(_FakeSlack(top, threads))
        code, out, err = _run(cmd_ask_answers, {"ledger": ledger, "out": os.path.join(tmp, "answers.json")})
        ans = {x["id"]: x for x in json.loads(out)}
        check("ask-answers decisions", {k: (v["decision"], v["source"]) for k, v in ans.items()},
              {"A1": ("done", "reaction"), "A2": ("drop", "reply"), "A3": ("park", "reply"), "A4": ("note", "reply"),
               "A6": ("done", "reply"), "A9": ("note", "reaction")})
        check("ask-answers list shape", sorted(k for k in ("id", "decision", "source", "ts", "text") if k in ans["A2"]),
              ["decision", "id", "source", "text", "ts"])
        check("ask-answers reply ts and text", (ans["A2"]["ts"], ans["A2"]["text"]),
              ("1789950000.000002", "Ignore them, the VinSolutions cost page is stale"))
        check("ask-answers reaction ts is the ask's", (ans["A1"]["ts"], ans["A1"]["text"], ans["A1"]["reaction"]),
              (X[1], None, ":white_check_mark:"))
        check("ask-answers reply beats reaction, reaction kept", ans["A6"]["other_signals"], ["reaction :zzz: (park)"])
        check("ask-answers shared-thread reply for another ask ignored", "A9 done" in json.dumps(ans["A3"]), False)
        check("ask-answers summary on stderr", ("6 answered" in err, "1 posted with no answer yet (A5)" in err,
                                                "1 missing (A7)" in err), (True, True, True))
        with open(ledger, "rb") as fh:
            check("ask-answers never edits the ledger", fh.read(), before)
        with open(os.path.join(tmp, "answers.json")) as fh:
            check("ask-answers --out = stdout", json.load(fh), json.loads(out))
    finally:
        g["call"], g["_pause"] = real_call, real_pause
        urllib.request.urlopen = real_urlopen
        shutil.rmtree(tmp, ignore_errors=True)


def _selftest_brief(check):
    """post-brief against a fake Slack: head and thread split, refusals, guards, receipt. No token, no network."""
    g = globals()
    real_call, real_pause = g["call"], g["_pause"]
    tmp = tempfile.mkdtemp(prefix="slack-brief-selftest-")
    para = lambda k: ("Store paragraph %d. " % k) + " ".join(["word"] * 280)

    def brief(three=None, calls=None, store=None, closed="- Nothing closed tonight."):
        three = three or ["1. **NOI: the pre-qualified ad is still live.** It ran all Monday.",
                          "2. **MCP: Performance Max recovered.** 212 clicks Monday against 19 Sunday, GA4 up 4.2%, preliminary.",
                          "3. **SBMW: quiet night.** Nothing moved."]
        calls = calls or ["- **NOI pre-qualified line (A20):** change it or keep it.",
                          "- **MCP auto-apply (A1):** turn it off?", "- **Atlas site audit:** your go."]
        store = store or "\n\n".join(para(k) for k in (1, 2, 3))
        return "\n".join([
            "---", "type: ai-team-brief", "date: 2026-09-29", "---", "",
            "## AI Team Brief, Tuesday 2026-09-29",
            "Morning Drew. Short night" + chr(8212) + " nothing on fire. We covered Monday 9/28.", "",
            "### The three things"] + three + ["", "### Measurement health", "- SBMW: AMBER. Service page views. Broken 11 days.", "",
            "### Needs your call"] + calls + ["", "### Store by store", store, "", "### Closed tonight", closed, "",
            "### Could not verify", "- One line from Nick, no saved file.", "", "### Shift stats", "Shift ran 01:00 to 01:14.", ""])

    def write(name, text):
        path = os.path.join(tmp, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def args(path, **kw):
        a = {"file": path, "tag_drew": False, "dry_run": False, "max_head_words": BRIEF_MAX_HEAD_WORDS,
             "max_id_mentions": BRIEF_MAX_ID_MENTIONS, "receipt": None, "repost": False}
        a.update(kw)
        return a

    class _Dies(_FakeSlack):
        """Slack that fails on post number `at`, the way call() dies on an error."""
        def __init__(self, at):
            _FakeSlack.__init__(self)
            self.at = at

        def __call__(self, method, params, post=True):
            if method == "chat.postMessage" and len(self.posted) + 1 == self.at:
                raise SystemExit(1)
            return _FakeSlack.__call__(self, method, params, post)

    try:
        g["_pause"] = lambda s: None
        # Pieces: parse, word count, splitting.
        title, pre, secs = brief_parts(brief())
        check("brief title and greeting", (title, pre.startswith("Morning Drew.")), ("## AI Team Brief, Tuesday 2026-09-29", True))
        check("brief sections in order", [n for n, _ in secs], ["The three things", "Measurement health", "Needs your call",
                                                              "Store by store", "Closed tonight", "Could not verify", "Shift stats"])
        check("brief with no title or frontmatter", brief_parts("Morning.\n\n### Needs your call (2)\n- x")[:2], ("", "Morning."))
        check("heading with a count still counts", brief_plan("### Needs your call (2)\n- a\n- b")["head"]["needs_call_bullets"], 2)
        check("word count skips heading marks and list markers",
              _word_count("*The three things*\n1. *NOI: up 5%.* Next.\n- $8,277 - so"), 9)
        long_line = " ".join("w%d" % i for i in range(2000))
        cut = split_text(long_line, 3500)
        check("one long line splits between words", (len(cut) > 1, max(map(len, cut)) <= 3500, " ".join(cut) == long_line),
              (True, True, True))
        bullets = "\n".join("- bullet %03d " % i + "x" * 50 for i in range(100))
        cut = split_text(bullets, 3500)
        check("a bullet list splits at line breaks", (len(cut), max(map(len, cut)) <= 3500, "\n".join(cut) == bullets),
              (2, True, True))
        cut = split_text("y" * 8000, 3500)
        check("one giant word is hard-cut", ([len(c) for c in cut], "".join(cut)), ([3500, 3500, 1000], "y" * 8000))

        # The plan: head, thread, warnings.
        plan = brief_plan(brief())
        head = plan["head"]
        check("head starts with the title, frontmatter gone", head["text"].startswith("*AI Team Brief, Tuesday 2026-09-29*\nMorning Drew."), True)
        check("head holds the three things and the calls only",
              (head["sections"], "*Measurement health*" in head["text"], "Store paragraph" in head["text"]),
              (["The three things", "Needs your call"], False, False))
        check("head loses its em dash", chr(8212) in head["text"], False)
        check("head counts", (head["needs_call_bullets"], head["needs_call_ids"], head["repeated_ids"], plan["problems"]),
              (3, ["A20", "A1"], [], []))
        check("GA4 is not ask A4", "A4" in head["ask_id_mentions"], False)
        check("bullet with no ask id warned", any("bullet 3 names no ask id" in w for w in plan["warnings"]), True)
        th = plan["thread"]
        check("thread sections, tiny ones merged, long one split",
              [r["sections"] for r in th],
              [["Measurement health", "Store by store"],
               ["Store by store (continued)", "Closed tonight", "Could not verify", "Shift stats"]])
        check("every reply within 3,500", all(r["chars"] <= REPLY_MAX_CHARS and r["chars"] == len(r["text"]) for r in th), True)
        check("the split lands on a paragraph break",
              (th[0]["text"].endswith(para(2)), th[1]["text"].startswith("*Store by store (continued)*\n" + para(3))), (True, True))
        w = head["words"]
        check("word limit is exact", (brief_plan(brief(), max_words=w)["problems"],
                                      [x[:8] for x in brief_plan(brief(), max_words=w - 1)["problems"]]), ([], ["head is "]))
        whole = "\n".join([head["text"]] + [r["text"] for r in th])
        check("nothing lost", all(x in whole for x in ["Store paragraph 1", "Store paragraph 2", "Store paragraph 3",
                                                      "Nothing closed tonight", "One line from Nick", "Shift ran 01:00"]), True)

        # Refusals: dry run exits 2, a real run posts nothing at all.
        path = write("long.md", brief())
        f = _FakeSlack()
        g["call"] = f
        code, out, _ = _run(cmd_post_brief, args(path, dry_run=True, max_head_words=20))
        o = json.loads(out)
        check("too long: dry run refuses", (code, o["refused"], "words (limit 20)" in " ".join(o["problems"] or [])), (2, True, True))
        six = ["- **Call %d (A%d):** yes or no." % (i, 30 + i) for i in range(6)]
        code, out, _ = _run(cmd_post_brief, args(write("six.md", brief(calls=six)), dry_run=True))
        check("six calls refused", (code, any("6 bullets (limit 5)" in p for p in json.loads(out)["problems"] or [])), (2, True))
        rep = ["1. **NOI: pre-qualified ad still live (A20).** Three days to 10/1.", "2. **MCP: fine.** Nothing new."]
        code, out, _ = _run(cmd_post_brief, args(write("rep.md", brief(three=rep)), dry_run=True))
        o = json.loads(out)
        check("repeated ask id refused", (code, o["head"]["repeated_ids"], any(p.startswith("A20 is named 2 times") for p in o["problems"] or [])),
              (2, ["A20"], True))
        code, out, _ = _run(cmd_post_brief, args(write("rep2.md", brief(three=rep)), dry_run=True, max_id_mentions=2))
        check("--max-id-mentions 2 lets a pair through", code, 0)
        code, _, err = _run(cmd_post_brief, args(write("pii.md", brief(store="Call the customer at (714) 555-0100 today.")), tag_drew=True))
        check("phone in a thread section: refused, nothing posted", (code, len(f.posted), "reply 1" in err), (2, 0, True))
        code, _, err = _run(cmd_post_brief, args(write("usd.md", brief(closed="- Spend was ,497 last week."))))
        check("shell-eaten dollar amount: refused, nothing posted", (code, len(f.posted), "shell-mangled" in err), (2, 0, True))
        check("no Slack call on any refusal or dry run", f.calls, [])
        check("dry run and refusals write no receipt", sorted(x for x in os.listdir(tmp) if x.endswith(".json")), [])

        # A real run: parent as Magic with the tag, replies in its thread, receipt, never twice.
        path = write("brief.md", brief())
        plan = brief_plan(brief())
        code, out, err = _run(cmd_post_brief, args(path, tag_drew=True))
        o = json.loads(out)
        parent = f.posted[0]
        check("post-brief posts parent plus replies", (code, len(f.posted), o["replies"], o["posted_now"]), (0, 3, 2, 3))
        check("parent as Magic, tagged, no thread", (parent["username"], parent["text"].startswith("<@%s> *AI Team Brief" % DREW),
                                                     "thread_ts" in parent), ("Magic #32", True, False))
        check("parent text = planned head", parent["text"], "<@%s> %s" % (DREW, plan["head"]["text"]))
        check("replies in the parent's thread", [p.get("thread_ts") for p in f.posted[1:]], [o["parent_ts"]] * 2)
        check("reply text = planned text", [p["text"] for p in f.posted[1:]], [r["text"] for r in plan["thread"]])
        check("output keys", sorted(o), sorted(["file", "already_posted", "parent_ts", "replies", "reply_ts", "posted_now",
                                                 "head_words", "needs_call_ids", "warnings", "receipt"]))
        check("summary on stderr", err.startswith("post-brief: parent ts %s, 2 replies" % o["parent_ts"]), True)
        with open(os.path.join(tmp, BRIEF_RECEIPT), encoding="utf-8") as fh:
            rec = json.load(fh)
        check("receipt written", (rec["parent_ts"], [r["n"] for r in rec["replies"]], bool(rec["finished"])), (o["parent_ts"], [1, 2], True))
        code, out, _ = _run(cmd_post_brief, args(path, tag_drew=True))
        check("same brief again: nothing posted", (code, len(f.posted), json.loads(out)["already_posted"]), (0, 3, True))
        code, out, _ = _run(cmd_post_brief, args(path, dry_run=True))
        check("dry run sees the receipt", json.loads(out)["receipt"]["state"], "posted")
        write("brief.md", brief() + "\nOne late line.\n")
        code, _, err = _run(cmd_post_brief, args(path))
        check("changed brief refused", (code, len(f.posted), "--repost" in err), (2, 3, True))
        code, out, _ = _run(cmd_post_brief, args(path, repost=True))
        check("--repost posts a new parent", (code, len(f.posted), json.loads(out)["parent_ts"] != o["parent_ts"]), (0, 6, True))

        # A crash after the first reply: the re-run finishes in the same thread.
        os.makedirs(os.path.join(tmp, "crash"))
        path = write(os.path.join("crash", "brief.md"), brief())
        g["call"] = _Dies(3)
        code, _, _ = _run(cmd_post_brief, args(path))
        dead = g["call"]
        check("crash on the second reply", (code, len(dead.posted)), (1, 2))
        f2 = _FakeSlack()
        g["call"] = f2
        code, out, _ = _run(cmd_post_brief, args(path))
        o2 = json.loads(out)
        check("re-run resumes: one post, same thread",
              (code, len(f2.posted), f2.posted[0].get("thread_ts"), o2["parent_ts"], o2["replies"], o2["posted_now"]),
              (0, 1, dead.posted[0]["ts"], dead.posted[0]["ts"], 2, 1))
        os.makedirs(os.path.join(tmp, "crash2"))
        path = write(os.path.join("crash2", "brief.md"), brief())
        g["call"] = _Dies(2)  # dies on the first reply: the parent alone is on record
        code, _, _ = _run(cmd_post_brief, args(path))
        dead = g["call"]
        f3 = _FakeSlack()
        g["call"] = f3
        code2, out, _ = _run(cmd_post_brief, args(path))
        check("crash right after the parent: re-run never posts a second parent",
              (code, len(dead.posted), code2, [p.get("thread_ts") for p in f3.posted], json.loads(out)["parent_ts"]),
              (1, 1, 0, [dead.posted[0]["ts"]] * 2, dead.posted[0]["ts"]))
    finally:
        g["call"], g["_pause"] = real_call, real_pause
        shutil.rmtree(tmp, ignore_errors=True)


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
    check("ts key keeps microseconds", _tsk("1789841289.951349") < _tsk("1789841289.951350"), True)
    check("ts key short fraction", _tsk("1789841289.5"), (1789841289, 500000))

    n_before = n[0]
    _selftest_slack(check)
    n_slack = n[0] - n_before
    n_before = n[0]
    _selftest_brief(check)
    n_brief = n[0] - n_before

    if fails:
        print("selftest FAILED, %d of %d checks:" % (len(fails), n[0]))
        for f in fails:
            print("  " + f)
        sys.exit(1)
    print("selftest ok: %d checks (%d damaged and %d clean texts for the dollar guard, topic text, picks; "
          "%d offline Slack checks: paging, drew-sweep, post-asks, ask-answers; %d post-brief checks)"
          % (n[0], len(damaged), len(clean_text), n_slack, n_brief))


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
    s = sub.add_parser("drew-sweep", help="every Drew message and reaction in #ai-team since the watermark")
    s.add_argument("--state", default=SWEEP_STATE, help="watermark file (default %s)" % SWEEP_STATE)
    s.add_argument("--days", type=float, default=14,
                   help="first run looks back this far; every run re-reads parents this far back for late replies")
    s.add_argument("--out", help="also write the JSON here")
    s.add_argument("--no-advance", action="store_true", help="report only; leave the watermark where it is")
    s.add_argument("--thread-days", type=float, default=3,
                   help="also re-read threads started in the last N days, for Drew's reactions on replies")
    s.add_argument("--all-threads", action="store_true", help="read every thread in the window (slow: 1.2 s each)")
    s.set_defaults(fn=cmd_drew_sweep)
    s = sub.add_parser("post-asks", help="post each listed open ask with no slack_ts as Magic")
    s.add_argument("--ledger", default=ASKS)
    s.add_argument("--ids", required=True, help="asks to post, e.g. A20,A27")
    s.add_argument("--thread", help="post the asks as replies in this thread (a reply then has to start with the id)")
    s.add_argument("--dry-run", action="store_true", help="print what would post, change nothing")
    s.set_defaults(fn=cmd_post_asks)
    s = sub.add_parser("ask-answers", help="read-only: Drew's call on each posted open or parked ask")
    s.add_argument("--ledger", default=ASKS)
    s.add_argument("--out", help="also write the JSON list here (for ledgers.py asks apply-answers)")
    s.set_defaults(fn=cmd_ask_answers)
    s = sub.add_parser("post-brief", help="the brief as Magic: Drew's part as the parent, every other section in its thread")
    s.add_argument("--file", required=True, help="outputs/ai-team/{date}/brief.md")
    s.add_argument("--tag-drew", action="store_true", help="tag Drew on the parent")
    s.add_argument("--dry-run", action="store_true", help="print the plan and every refusal, post and write nothing")
    s.add_argument("--max-head-words", type=int, default=BRIEF_MAX_HEAD_WORDS,
                   help="refuse when the parent runs longer (default %d)" % BRIEF_MAX_HEAD_WORDS)
    s.add_argument("--max-id-mentions", type=int, default=BRIEF_MAX_ID_MENTIONS,
                   help="refuse when one ask id is named more often than this in the parent (default %d)" % BRIEF_MAX_ID_MENTIONS)
    s.add_argument("--receipt", help="post record (default: brief-slack.json next to the brief)")
    s.add_argument("--repost", action="store_true", help="ignore an earlier receipt and post the brief again as a new message")
    s.set_defaults(fn=cmd_post_brief)
    sub.add_parser("selftest", help="offline tests: guards, picks, paging, sweep, asks, brief").set_defaults(fn=cmd_selftest)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
