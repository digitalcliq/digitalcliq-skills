# Automotive Intelligence

**A second brain for dealership General Managers. Built by [DigitalCLIQ](https://digitalcliq.com).**

Automotive Intelligence is a [Claude Code](https://claude.com/claude-code) skill that sets up a personal knowledge vault for the person running a car store. It builds the structure, then interviews you the way a sharp incoming GSM would: your numbers, your departments, your people, your vendors, your comp set, and, most importantly, **how you run your store**: your management style, how you want information delivered, your hot buttons, your non-negotiables.

Everything Claude does afterward is tuned to those answers. You stop repeating yourself. Your assistant already knows you lead with the number, that unworked leads set you off, and that Saturday's manager meeting needs the agenda by Friday close.

## What you get

```
your-store-vault/
├── CLAUDE.md              ← the operating system: rules, routing, your communication contract
├── Context/               ← who you are, your store, your people, your stack, your market
│   └── gm-profile.md      ← the tuning file: your style, hot buttons, drains
├── Daily/                 ← your running journal, one note per day
├── Departments/           ← one folder per department, run the way YOU run it
├── Intelligence/          ← competitors, decisions, meeting formats
├── Projects/              ← active initiatives
├── Tasks/                 ← one simple task board
└── Resources/             ← reusable checklists and templates
```

The vault is plain markdown and doubles as an [Obsidian](https://obsidian.md) vault. Open the folder in Obsidian and you can browse, search, and link everything visually.

## Install

1. Install [Claude Code](https://claude.com/claude-code).
2. Copy this repository's folder into your skills directory:

```bash
git clone https://github.com/digitalcliq/automotive-intelligence.git ~/.claude/skills/automotive-intelligence
```

3. Create an empty folder for your vault, open a terminal there, and run `claude`.
4. Say: **"set up my dealership brain"** (or run `/automotive-intelligence`).

Block out 45 minutes for the interview. Dictating on your phone and pasting the transcript works great. The more real you are, the better this thing gets.

## What it asks

Eight topics in three rounds:

1. You and your store
2. The numbers that run your month
3. Management style and communication
4. Departments and how you structure them
5. Your people
6. Tech stack and vendors
7. Comp set, market, and OEM programs
8. Pain points and drains

Skip anything. Add more later; the vault updates in place.

## Who built this

[DigitalCLIQ](https://digitalcliq.com) is a performance marketing and creative agency specialized in automotive since 2015: SEO and AI-search visibility, paid media, CRM and email, creative, vendor management, and reporting that ties leads to sales. Most of our clients have been with us 10+ years.

We built Automotive Intelligence because the GMs we work with deserve the same AI leverage we use to run our own agency.

**Marketing questions? Vendor audits? Lead scoring?** That's our day job: [digitalcliq.com](https://digitalcliq.com)

---

*Single rooftop, single GM for now. A multi-store executive edition is on the roadmap.*
