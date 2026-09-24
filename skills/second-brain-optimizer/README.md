# Second Brain Optimizer

**Keep your second brain sharp. Built by [DigitalCLIQ](https://digitalcliq.com).**

Second Brain Optimizer is a [Claude Code](https://claude.com/claude-code) skill that audits and tunes a markdown knowledge vault: the kind [Automotive Intelligence](https://github.com/digitalcliq/automotive-intelligence) builds for dealership General Managers, or any Obsidian-style vault you run your work from.

Vaults rot. Notes contradict each other, links die, facts go stale the week after you write them, and the instruction files that steer your AI quietly bloat until every session pays a token tax. This skill finds all of it and, unlike a linter, ships a concrete fix for every single finding. You approve fixes in batches, it applies them, and you get a branded before-and-after dashboard.

## The 5 passes

| Pass | What it catches |
|---|---|
| **P1 Instruction Layer** | Bloated or vague CLAUDE.md rules, buried constraints, filler, guidance duplicated across files |
| **P2 Mechanical Hygiene** | Em dashes, duplicate H1s, incomplete frontmatter, oversize files, stale candidates |
| **P3 Link Graph** | Dead wikilinks (with repoint suggestions), orphan notes, missing cross-links |
| **P4 Reflection** | Contradictions between notes, duplicate notes to merge, stale facts your recent dailies disprove, themes with no home, durable facts stuck in daily notes |
| **P5 Architecture** | Routing tables that lie, folders without indexes, files unreachable from the root, misplaced files, structural reorgs |

A bundled Python scanner does every deterministic check in one pass over the filesystem, so Claude's attention (and your token budget) goes only where judgment is needed. Mechanical fixes are applied by the script with automatic backups; anything semantic is drafted by Claude and approved by you.

## Install

1. Install [Claude Code](https://claude.com/claude-code).
2. Copy this repository into your skills directory:

```bash
git clone https://github.com/digitalcliq/second-brain-optimizer.git ~/.claude/skills/second-brain-optimizer
```

3. Open a terminal in your vault root and run `claude`.
4. Say: **"optimize my vault"** (or run `/second-brain-optimizer`).

Requires Python 3.8+ (standard library only, nothing to pip install).

## What a run looks like

1. Detects your vault layout (Automotive Intelligence vaults are recognized instantly; any other structure is discovered once and remembered).
2. Scans every markdown file in seconds and shows you the damage.
3. Reads the files that need judgment and writes a short architectural read of your vault.
4. Asks once how you want to proceed: apply everything, review by batch, or save it all to a plan.
5. Applies, verifies nothing broke (every merge and move is re-checked for new dead links), and saves a DigitalCLIQ-branded HTML dashboard with your health score, before and after.

Run it monthly. Watch the score climb.

## Who built this

[DigitalCLIQ](https://digitalcliq.com) is a performance marketing and creative agency specialized in automotive since 2015: SEO and AI-search visibility, paid media, CRM and email, creative, vendor management, and reporting that ties leads to sales.

We built Second Brain Optimizer because a second brain only compounds if somebody keeps it clean, and nobody has time to be that somebody.

**Marketing questions? Vendor audits? Lead scoring?** That's our day job: [digitalcliq.com](https://digitalcliq.com)

---

*Pairs with [Automotive Intelligence](https://github.com/digitalcliq/automotive-intelligence): that skill builds the vault, this one keeps it honest.*
