#!/usr/bin/env python3
"""Slack voice for the DigitalCLIQ AI team. Standard library only.

One Slack app (scopes: chat:write, chat:write.customize, channels:history)
posts as each player (six voices) with its own name and jersey avatar.

Token lives OUTSIDE the vault: ~/.config/digitalcliq-ai-team/slack.env
  SLACK_BOT_TOKEN=xoxb-...

Commands:
  post --as kobe --text "..." [--thread TS] [--tag-drew]   prints the message ts
  read [--hours 24] [--thread TS]                          channel or thread history
  check                                                    token + channel membership test

PII law: #ai-team gets aggregates only. Any text that looks like it carries a
customer phone number or email address is refused, no override.
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
    if PHONE.search(text) or EMAIL.search(text):
        die("refused: text looks like it holds a phone number or email address. "
            "#ai-team gets aggregates only, never customer-level data. Rewrite and resend.", 2)
    text = text.replace(chr(8212), ", ")  # Rule 14, strips em dashes
    text = to_mrkdwn(text)
    if args.tag_drew:
        text = "<@%s> %s" % (DREW, text)
    name, std_emoji, custom_emoji = PLAYERS[who]
    emoji = custom_emoji if CUSTOM_EMOJI else std_emoji
    payload = {"channel": CHANNEL, "text": text, "username": name, "icon_emoji": emoji,
               "unfurl_links": False, "unfurl_media": False}
    if args.thread:
        payload["thread_ts"] = args.thread
    res = call("chat.postMessage", payload)
    print(res["ts"])


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
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
