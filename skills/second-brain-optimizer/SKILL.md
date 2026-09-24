---
name: second-brain-optimizer
description: DigitalCLIQ Second Brain Optimizer. Audits and tunes a markdown second brain (Obsidian vault) with 5 consolidated passes; P1 Instruction Layer, P2 Mechanical Hygiene (scripted), P3 Link Graph, P4 Reflection, P5 Architecture and Discoverability. A bundled Python scanner does all deterministic work (em dashes, frontmatter, dead wikilinks, orphans, sizes, metrics) in one shot so agent tokens go only to judgment. Every finding ships a concrete fix; batched walk, terminal states, DigitalCLIQ-branded HTML dashboard. Built for vaults created by automotive-intelligence and for the DigitalCLIQ HQ vault; works on any markdown vault. TRIGGERS; second brain optimizer, optimize vault, vault audit, second brain audit, tidy vault, clean up vault, vault lint, /second-brain-optimizer. Run from vault root.
---

# DigitalCLIQ Second Brain Optimizer

**Built by [DigitalCLIQ](https://digitalcliq.com).** Audits every markdown file in the vault with 5 passes, walks the user through fixes in batches, applies approved fixes, and saves one branded HTML dashboard. Companion to the DigitalCLIQ `automotive-intelligence` skill: run it monthly on any vault that skill built.

## Operating laws

1. **Script first, judgment second.** `scripts/optimize.py` (next to this SKILL.md) does every deterministic check in one filesystem pass and emits JSON. The agent never greps for em dashes, never counts frontmatter, never builds the link graph by hand. Agent reads are reserved for P1, P4, and P5 judgment.
2. **One read per file, maximum.** When a file needs an agent read, apply every relevant check from every pass in that single read. Never iterate passes over the vault; iterate files once.
3. **Every finding ships a concrete fix.** No flag-only, no fix-later pile. Each finding ends in exactly one terminal state: `applied`, `saved_to_plan`, `declined`, or `failed` (with `failure_reason`). Unset status after Step 6 is a bug.
4. **Batched walk, not per-item interrogation.** One mode gate, then one review per finding category. Individual prompts fire only when the agent genuinely cannot pick a target (merge winner, ambiguous link target).
5. **Judgment findings carry case-specific reasoning.** A trigger surfaces a candidate; only a read confirms a finding. Reasoning that paraphrases the rule is a bug.
6. **Known layouts skip discovery.** Detect the vault flavor cheaply (Step 1). Full semantic role discovery runs only for unknown vaults, and its result persists so it never runs twice.
7. **Never destructive.** Archive instead of delete, back up before mechanical fixes, grep before any move or merge, verify zero new dead links after (re-run the scanner).
8. **No em dashes in anything this skill writes.** Periods, commas, colons, or restructure.

## Flow

| Step | What | Who |
|---|---|---|
| 1 | Verify vault, detect layout, load or build role map | agent (cheap) |
| 2 | `optimize.py scan` builds inventory, P2 + P3 triggers, metrics | script |
| 3 | Judgment passes P1, P4, P5 (single read per file in scope) | agent |
| 4 | Score + architectural read, show summary table | agent |
| 5 | Mode gate, then batched walk of every finding | agent + user |
| 6 | Apply fixes (script for mechanical, agent for semantic), re-scan | both |
| 7 | `optimize.py report` renders the dashboard, save, open, summarize | script |

Read `references/passes.md` once at Step 3 for the full check definitions, walk batches, and fix procedures. Do not paraphrase it from memory.

---

## Step 1: Verify and orient

Vault check: `CLAUDE.md` at cwd root, or any `.md` at depth 1. If neither, stop: "This does not look like a vault root. cd into your vault and re-run."

Detect layout, in order:

1. **Saved map**: `.claude/optimizer/roles.json` exists. Load it; re-classify only folders not in it.
2. **Automotive Intelligence vault**: `Context/gm-profile.md` or `Context/digitalcliq.md` exists. Roles are known: `Context/`=context, `Daily/`=daily, `Departments/`, `Projects/`, `Intelligence/decisions`=decisions, `Intelligence/competitors`, `Intelligence/archive`=archive, `Resources/`, `Tasks/`. Folder-index convention: README.md.
3. **DigitalCLIQ HQ vault**: root CLAUDE.md mentions DigitalCLIQ and `Projects/README.md` exists. Same role names plus `Team/`, `Skills/`, `Onboarding/`. Default scanner skips: `01_Inbox`, `outputs` (raw drops and staging are not the vault's fault) plus any GitHub skill-source folders at root (they follow repo conventions, not vault conventions). Tasks live in Notion, so never audit or create task markdown.
4. **Unknown vault**: lightweight discovery. Read top-level folder names plus each folder's index file if present; sample at most 2 files per ambiguous folder; assign each folder a role name, a layer (`curated`, `session`, `archive`, `meta`), and the folder-index convention (most common of README.md, index.md, Plot.md, CLAUDE.md). Ask the user only about folders you cannot classify after reading.

Persist the result to `.claude/optimizer/roles.json` (on DigitalCLIQ layouts include `"red_links_intentional": true`; red unresolved links are placeholders there, paged at 20+ references). Tell the user in one line which layout was detected and that the scan is starting. Then keep the user oriented with one short progress line per step (no task-widget dependency; this skill must run in plain Claude Code).

## Step 2: Scripted scan

```bash
python3 "{skill_dir}/scripts/optimize.py" scan --root . --state .claude/optimizer [--skip 01_Inbox --skip outputs]
```

Writes to `.claude/optimizer/`: `findings-scan.json` (P2 + P3 findings, each with path, line, excerpt, suggestion), `metrics-before.json` (per-role and total: files, tokens, em dashes, frontmatter coverage, dead links, orphans, oversize and stale candidates), `inventory.json` (per-file role, size, mtime, headers, links). Read only the summary the script prints plus `metrics-before.json`. Do not read the full findings file into context; query it with `jq`/`grep` as needed during the walk.

Show one compact discovery block: file count, folders, total size, per-pass candidate counts.

## Step 3: Judgment passes (P1, P4, P5)

Read `references/passes.md` now. Scope per pass:

- **P1 Instruction Layer**: every CLAUDE.md, SKILL.md, `.claude/rules/*`. Checks: size budget, vague rules, pruning test, position, filler compression, progressive disclosure, duplicated guidance.
- **P4 Reflection**: curated layer (context, projects, decisions, resources) plus the last 30 days of daily and meeting notes as evidence. Checks: contradictions, merge candidates, stale facts, emergent themes, promotions. Also adjudicate the scanner's stale-file and orphan candidates here.
- **P5 Architecture and Discoverability**: routing-table truth vs folder reality, folder-index presence and freshness, 3-hop reachability from root, misplaced files, folder overlap, reorg proposals, orientation quality.

**Incremental mode**: if `.claude/optimizer/last-run.json` exists, files unchanged since that run keep their prior P1 verdicts and are skipped for P1; P4 and P5 always run (they reason across files) but use the inventory, not fresh reads, wherever headers and links suffice. First run on a vault is always full.

Append judgment findings to `.claude/optimizer/findings-agent.json` (same schema as the scanner; see passes.md). Every finding: 1 to 2 sentences of case-specific reasoning plus a drafted fix.

## Step 4: Score and architectural read

The scanner computes the base score; confirm with:

```bash
python3 "{skill_dir}/scripts/optimize.py" score --state .claude/optimizer
```

Formula: per scored pass (P1, P2, P3), deduction = fails x 5 + warns x 1, capped at 25; score = 100 minus the sum. P4 and P5 are opportunity tiles, never scored. 90+ well-tuned, 70 to 89 visible drift, 50 to 69 bloat is hurting, below 50 vault rot.

Write the **architectural read**: 1 to 3 short paragraphs, the top structural observations, each grounded in this vault's own context files and citing the finding ids that surfaced it. Under 200 words. If the structure is sound, say so in one sentence with the numbers that prove it. Save to `.claude/optimizer/arch-read.md`. Show it in chat with one summary table (pass, files, findings, fail/warn counts).

## Step 5: Mode gate and batched walk

One AskUserQuestion: "{N} findings, every one has a proposed fix. Pick mode:"

1. **Apply everything** (default): mechanical and semantic fixes all apply; prompts fire only for genuine target choices. No saved_to_plan, no declined; the only non-applied state is a mechanical `failed`.
2. **Review by batch**: walk each category batch (per the table in passes.md); user answers per batch, item numbers to except.
3. **Plan only**: write every fix into the decisions folder as `{date}-optimizer-plan.md`, apply nothing.
4. **Cancel.**

In review mode, present each batch as one compact table (id, path, excerpt, proposed fix) and one question: apply all, apply all except listed numbers, save batch to plan, or decline batch. High-blast-radius categories (merges, moves, reorgs, any CLAUDE.md edit) always show drafted text before applying, whatever the mode.

## Step 6: Apply and verify

Order: mechanical first, then semantic, smallest blast radius first (exact order and procedures in passes.md).

- Mechanical (em dashes, duplicate H1): `optimize.py fix --emdash --h1 --state .claude/optimizer` (backs up every touched file to `.claude/optimizer/backups/{timestamp}/` first, protects code, URLs, wikilinks, frontmatter by construction).
- Semantic (frontmatter values, link repoints, rewrites, merges, moves, index generation, routing edits): agent applies the drafted, user-approved edits. CLAUDE.md edits are always per-item confirmed.
- After all fixes: `optimize.py scan --phase after`. Any new dead link or regression rolls back the responsible fix and marks it `failed`.
- Update `fix_status` on every finding. Verify applied + saved_to_plan + declined + failed = total. Write `.claude/optimizer/last-run.json`.

## Step 7: Report

```bash
python3 "{skill_dir}/scripts/optimize.py" report --state .claude/optimizer --out "{decisions}/{YYYY-MM-DD}-second-brain-audit.html"
```

The script renders the DigitalCLIQ-branded dashboard (Digital Blue #405FAB, Sky Blue #6B9DD4, Dosis + Roboto Slab) from the merged findings, before/after metrics, and the architectural read. It also copies the merged findings JSON next to the HTML. Save target: the decisions folder from the role map; fall back to `audits/` at root. Open with `open "{path}"`.

Final chat message, and nothing after it: report path, JSON path, score before to after with labels, files audited, fixes applied/failed (plus saved/declined in review mode), em dashes removed, frontmatter coverage delta, dead links resolved, tokens saved. No HTML dumped in chat.

## Never

- Never iterate the 5 passes as 5 sweeps over the vault; one read per file, all checks at once.
- Never do by hand what the scanner already did; never load `findings-scan.json` wholesale into context.
- Never edit a CLAUDE.md, delete anything, or leave a finding without a terminal state.
- Never apply substitutions inside code, URLs, wikilinks, frontmatter, or files in skip dirs.
- Never merge or move without redirecting inbound links and re-scanning for new dead links.
- Never propose a structural change without citing evidence from this vault's own files.
- Never write tasks to vault markdown on a DigitalCLIQ layout; tasks live in Notion.
- Never run silently; one progress line per step.
