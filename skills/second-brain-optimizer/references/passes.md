# Pass definitions, walk batches, and fix procedures

Loaded once at Step 3. The scanner (`scripts/optimize.py`) owns P2 fully and P3 triggers; the agent owns P1, P4, P5 and all semantic fixes.

## Finding schema (both scanner and agent findings)

```json
{
  "id": "P4.1-007",
  "pass": "P4", "check": "P4.1",
  "path": "Context/stack.md", "line": 22,
  "severity": "fail | warn | info",
  "excerpt": "CRM is Elead",
  "reasoning": "Case-specific, 1 to 2 sentences. Why this is a real finding in this file's context.",
  "fix": {"kind": "rewrite | delete_line | repoint_link | add_frontmatter | merge | move | create | edit_claude_md | archive", "draft": "the exact proposed edit or steps"},
  "fix_status": null
}
```

`fix_status` terminal values: `applied`, `saved_to_plan`, `declined`, `failed` (with `failure_reason`). Scanner findings omit `reasoning` (mechanical checks need none).

---

## P1: Instruction Layer

Scope: every `CLAUDE.md`, every `SKILL.md`, `.claude/rules/*.md`. One read per file, apply all seven checks.

| Check | Look for | Fix |
|---|---|---|
| P1.1 size budget | Root CLAUDE.md over ~12KB auto-load weight; any folder CLAUDE.md over 8KB | Draft a split: keep rules and routing, move narrative to a routed note; show the cut list |
| P1.2 vague rules | "Be careful", "always be thorough", rules with no path, name, or number. Specific rules get followed; vague ones do not | Rewrite anchored to a concrete path, tool, or threshold, or delete |
| P1.3 pruning test | Rules that restate model defaults, duplicate another rule, or protect against a failure that cannot happen here | Delete, with one line of justification each |
| P1.4 position | Load-bearing rules buried below narrative; critical constraints not in the top third | Draft the reorder |
| P1.5 filler | Pleasantries, hedging, verbose connectors, "IMPORTANT" inflation in instruction files | Draft the compressed line; meaning must survive verbatim |
| P1.6 progressive disclosure | SKILL.md over 12KB, reference content inlined that loads every invocation, references nested more than one hop | Draft the layering: what stays, what moves to references/ |
| P1.7 duplicated guidance | Same rule living in two or more CLAUDE.md files | Pick the single home (closest to where it applies), replace others with a pointer |

Judgment notes: "just", "be careful", and `IMPORTANT:` are candidates, not verdicts; read the line in context. Never flag a rule as vague when it cites a file, code, or person. On DigitalCLIQ layouts, dated "Drew confirmed" rules are load-bearing history: compress wording if needed, never drop the date or the fact.

## P2: Mechanical Hygiene (scanner-owned)

The scanner detects and (in fix mode) repairs. Agent involvement: approve the batch, adjudicate P2.5.

- **P2.1 em dashes** (and en dashes): counted outside code fences, inline code, URLs, wikilinks, frontmatter, tables' delimiter rows. Fix: digit ranges get a hyphen; everything else gets `, ` with double-punctuation cleanup. Files are backed up first.
- **P2.2 duplicate H1**: first heading restates the filename. Fix: remove the line and its trailing blank.
- **P2.3 frontmatter incomplete**: missing block, missing `status:`, or fewer than 2 tags (convention from the automotive-intelligence templates; on unknown vaults only flag files whose siblings have frontmatter). Fix is semantic: the agent drafts real values from the file's content, batched per folder. Never invent `status: unknown` filler.
- **P2.4 oversize**: over 100KB fail; over 10KB warn for curated and instruction roles; over 50KB warn elsewhere. Fix: draft a split at H2 boundaries, or archive if superseded. Session-layer files (dailies, meetings, transcripts) are exempt from warns; they are records.
- **P2.5 stale candidates**: curated-layer files untouched for 180+ days. Not a finding by itself; the list feeds P4.3 where the agent checks whether the content is actually stale.

## P3: Link Graph (scanner triggers, agent targets)

- **P3.1 unresolved wikilinks**: one aggregated finding per unique target across the vault, with reference count, referring files, and closest-match suggestions. Likely renames (high-confidence suggestion) batch as repoints; targets with 20+ references get a page created; the rest are placeholders. On vaults where red links are intentional (set `red_links_intentional: true` in roles.json; default on DigitalCLIQ layouts) low-count placeholders are info, not warn.
- **P3.2 orphans**: curated-layer notes with zero inbound links and no folder-index mention. Dailies, meetings, READMEs, and index files are exempt. Agent picks per item: add a link from the folder index, weave a link from the most related note, or archive.
- **P3.3 missing cross-links**: while reading files for P1/P4/P5, entity names that exist as notes but appear unlinked. Draft the wikilink weave; batch per file. Do not force links into code, quotes, or frontmatter.

## P4: Reflection

Scope: read the curated layer (context, projects, decisions, resources roles) plus the last 30 days of daily and meeting notes as evidence. Use `inventory.json` headers to target reads; do not re-read files P1 already read, reuse what you learned.

| Check | Look for | Fix |
|---|---|---|
| P4.1 contradictions | Two curated files asserting incompatible facts | User picks the winner; loser line becomes `See [[Winner]]` or is deleted |
| P4.2 merge candidates | Two or more notes covering the same subject | User picks the canonical file; unique sections merge in, sources archive, inbound links repoint |
| P4.3 stale facts | Curated claims contradicted by recent dailies or meetings (vendor switched, person left, number changed) | Rewrite to current state; move superseded wording to a `## History` line when it carries decision context |
| P4.4 emergent themes | A topic recurring across 3+ session notes with no curated home | Create the note in the context or resources role, frontmatter complete, wikilinks back to sources |
| P4.5 promotions | Durable facts living only in a daily or meeting note | Append to the right curated file; leave `See [[Target]]` at the source |

Verification bar: every P4 finding cites at least two files. One file saying something odd is not a contradiction.

## P5: Architecture and Discoverability

Walk the path a fresh Claude session takes: root CLAUDE.md, routing table, folder index, file.

| Check | Look for | Fix |
|---|---|---|
| P5.1 routing truth | Routing entries pointing at folders that do not exist, are empty, or hold something else; real folders missing from routing | Draft the corrected routing lines (CLAUDE.md edit: always per-item confirmed) |
| P5.2 folder indexes | Non-trivial folders missing the vault's index convention, or index children lists that no longer match reality | Generate or refresh the index; under 8KB, purpose line plus one line per child |
| P5.3 reachability | Files not reachable in 3 hops from root via routing and indexes | Add to index, add routing entry, move, or archive; user picks |
| P5.4 misplaced files | File content contradicting its folder's stated purpose | Move (with link redirect) or broaden the index's purpose line; user picks |
| P5.5 folder overlap | Two folders holding the same kind of content | Merge one into the other, or sharpen both purpose lines; user picks |
| P5.6 reorg proposal | Structural change touching 10+ files | Full migration checklist (moves, redirects, routing updates), default save_to_plan |
| P5.7 orientation | Root CLAUDE.md failing to orient a fresh agent in this user's world (who, what, where things live) | Draft the orientation edit; per-item confirmed |

Evidence bar: every P5 proposal must cite this vault's own files (a purpose line, a context note, an observed overlap). Convention preference alone is never justification.

---

## Walk batches (Step 5, review mode)

| Batch | Findings | Question shape |
|---|---|---|
| 1 Mechanical | P2.1, P2.2 | Apply all / except numbers / decline |
| 2 Frontmatter | P2.3 drafted values, per folder | Apply folder batch / edit values / decline |
| 3 Links | P3.1 confident repoints, then ambiguous per item; P3.2 per item; P3.3 per file | Per batch, then per item where ambiguous |
| 4 Instruction layer | P1.x drafted edits | Per file: show draft, apply / edit / save to plan / decline (CLAUDE.md always shows full draft) |
| 5 Reflection | P4.1 to P4.5 | Per item for winners and targets; per batch otherwise |
| 6 Architecture | P5.1 to P5.7, smallest blast radius first | Per item; P5.6 defaults to save_to_plan |

Apply-everything mode collapses batches 1 to 3 and 5 to automatic, prompts only for winner/target/destination choices, and still shows CLAUDE.md drafts before landing them.

## Fix procedures and safety (Step 6)

Order: P2 mechanical (script), P2.3 frontmatter, P3 links, P1 instruction edits, P4 smallest to largest (contradictions, stale, merges, themes, promotions), P5 smallest to largest (routing lines, indexes, single moves, folder merges, reorgs).

- **Backups**: script backs up before mechanical fixes. Before agent rewrites or merges, copy the file into `.claude/optimizer/backups/{timestamp}/` preserving the relative path.
- **Merges (P4.2, P5.5)**: concatenate unique sections into the canonical target; if the result exceeds 10KB, abort and mark `failed`. Grep the vault for every `[[Source]]` and `[[Source|alias]]`, repoint to the canonical name. Move sources to the archive role under `{date}-merged/`. Never delete.
- **Moves (P3.2, P5.3, P5.4)**: `mv`, update both folder indexes, repoint inbound links.
- **CLAUDE.md edits (P1.x, P5.1, P5.7)**: only with the exact drafted text confirmed by the user for that item. Never batch, never via the generic runner.
- **After everything**: `optimize.py scan --phase after`. New dead links or a regressed metric identify the responsible fix; roll it back from backup and mark `failed` with the reason. Re-run the after scan once more after any rollback.

## Plan file (save_to_plan target)

Append to `{decisions}/{YYYY-MM-DD}-optimizer-plan.md`, frontmatter `status: pending`, `type: reorg-plan`, `tags: [optimizer, plan]`. One checkbox per saved fix with its steps and reasoning. On DigitalCLIQ HQ layouts, pending plans also get a Notion task per the vault's own rules; on other layouts the plan file is the record. The plan file is itself audited next run.
