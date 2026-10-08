---
name: vault-archive
description: DigitalCLIQ vault archive. Moves old files out of the Obsidian vault into verified zips in ~/Desktop/DigitalCLIQ Vault Archive (outside the vault, backed up by Drive for desktop) and removes the originals only after the zip proves byte-for-byte good. Read-only plan first (size, .md count, inbound links, readers, recent edits), dry run by default, protected folders refused. Use when Drew says "archive the vault", "month-end vault archive", "vault cleanup", "move old files out of the vault", or /vault-archive. Never touches outputs/ai-team (month_close.py owns it).
---

# Vault archive

Drew wants a vault that stays small and flat: month-to-month information stays, day-and-time detail he rarely needs goes to an archive he can restore from. This skill is the one tool that takes files out of the vault. It never deletes anything until a zip of it has been written, re-opened and checked file by file.

Script: `scripts/vault_archive.py` (standard library only). From the vault root:

```
A=.claude/skills/vault-archive/scripts/vault_archive.py
python3 $A plan  --list LIST [--batch B] [--out REPORT.md] [--json-out FILE]
python3 $A apply --list LIST [--batch B] --name NAME --month YYYY-MM            # dry run, writes nothing
python3 $A apply --list LIST [--batch B] --name NAME --month YYYY-MM --apply    # archive, verify, remove
python3 $A selftest
```

Global flags go before the subcommand: `--root` (default: the vault the script is installed in), `--archive-root` (default: `$DIGITALCLIQ_ARCHIVE_ROOT`, else `~/Desktop/DigitalCLIQ Vault Archive`), `--include-denied` (see Read-denied paths).

A LIST is either plain text (one vault-relative path per line, `#` comments, and `path  dup: twin/path` for a proven duplicate) or a sweep JSON list of `{path, batch, category, reason, evidence, duplicate_of}` items, like `outputs/vault-archive/sweep-2026-10-07.json`. `apply` takes one batch at a time.

## Where the archive lives

```
~/Desktop/DigitalCLIQ Vault Archive/
  INDEX.md                         one section per zip: created, what, source paths, file count,
                                   bytes before and after, zip sha256, how to restore, what was removed
  2026-09/
    vault-sweep-2026-10-07-outputs-staging.zip
    vault-sweep-2026-10-07-outputs-staging.manifest.json   every file: path, size, mtime, sha256
```

- The folder sits next to the vault, never inside it, and never under `~/Library/CloudStorage` (the script refuses both).
- Google Drive for desktop backs up `~/Desktop`, so the zips reach Drive with no extra step. Drive mirrors deletions too: never delete a zip. There is no Time Machine, so a zip is the only copy of what it holds.
- `--month` is the month the batch closes out (the 10/7 sweep is September's close, so every sweep batch uses `2026-09`). Zip names say what and when: `vault-sweep-{date}-{batch}`.
- Zip members are vault-relative paths, so a restore puts files back exactly where they were.

## The safe removal protocol (apply --apply)

1. Collect regular files only. Symlinks are skipped and reported, never followed. Nothing outside the listed paths is touched.
2. Record sha256, size and mtime of every file. A file that changes while it is being hashed stops the run.
3. Write `{name}.zip.partial` in `{archive}/{YYYY-MM}/`, close it, rename it to `{name}.zip`. An existing zip is never overwritten: the name becomes `{name}-2.zip`, `-3`, and so on.
4. Re-open the zip: `testzip()` must find nothing, every file must be in it exactly once, and the sha256 of every decompressed member must match step 2. A zip that fails is renamed `.zip.failed` and nothing is removed.
5. Write `{name}.manifest.json` (with the zip's own sha256) and append the section to `INDEX.md`.
6. Only then remove the originals, one at a time, re-checking size and mtime first. A file that changed since hashing stays and is reported. A `.fuse_hidden` file still open in another process stays. A proven duplicate stays if its twin is gone. Then remove the folders inside listed folders that are now empty, bottom-up. A non-empty folder is never removed, and a parent of a listed path is never touched.
7. Print the summary and add the removal line to `INDEX.md`.

Any failure before step 6 leaves every original where it was.

## Protected (refused, whatever the list says)

`Context/`, `.obsidian/`, every `CLAUDE.md`, a folder's `README.md` index (it may leave only together with the folder it indexes; copies of either inside `.claude/optimizer/backups/` and `runs/` are backups, not live files), `Projects/*/context-log*.md` and `*.bak-0926` (September entries pending restore), `Projects/*/cars-act-state/` (legal retention), `Projects/*/deliverables/` (client record; only a proven byte-identical duplicate may leave, named with `dup:` or `duplicate_of` and re-hashed at plan and apply time), `outputs/ai-team/` (month_close.py owns it), `outputs/context-log-redesign/`, `outputs/KrystalKlear/`, `outputs/*dashboard*` and `outputs/sbmw-dashboard-backend/`, `outputs/_qa/`, `outputs/ncbmw-dropfolder-ingest/`, `outputs/bmw-digest-generator/`, `Second Brain Optimizer Skill/`, `Automotive Intelligence Skill/`, `Resources/brand-assets/`, `Resources/automotive-guidelines/`, `.claude/skills/`, `.claude/agents/`, `.claude/settings*.json`, `Daily/*.md`, `Team/`, any `.git` folder, and every file or folder at the vault root.

## Read-denied paths

`.claude/settings.json` denies Claude reads of `Intelligence/archive/**`, `.claude/optimizer/backups/**`, `Daily/attachments/**`, `Projects/**` images, and `*.mp3`, `*.mp4`, `*.zip`, fonts. The script honors those rules: `plan` never walks a denied folder and `apply` refuses a denied path. Those batches are Drew's to run from Terminal with `--include-denied` (a global flag, before the subcommand). A Claude session never passes `--include-denied`.

## How Claude runs it

1. Build the list from the monthly policy below. Re-verify each candidate now: sha256 for duplicates, readers in skills and scheduled tasks, inbound links.
2. Run `plan` and show Drew the totals per batch: files, bytes, .md files leaving Obsidian, links that would go dead, anything edited in the last 7 days.
3. Repoint or fix any link that would go dead before the run, never after.
4. With Drew's go, run `apply` for one batch as a dry run, then with `--apply`. One batch per zip.
5. Log one line in today's Daily note: zip names, files and bytes moved, anything kept and why.

## Restore

- Everything in one zip: `unzip -o "$HOME/Desktop/DigitalCLIQ Vault Archive/2026-09/{name}.zip" -d "$HOME/Desktop/DigitalCLIQ Brain HQ"` (INDEX.md holds the exact line for every zip)
- One file: add its vault-relative path after the zip name: `unzip -o "{zip}" "Projects/MCP/some-file.json" -d "{vault}"`
- Keep newer copies already in the vault: use `unzip -n` instead of `-o`.
- See what a zip holds: `unzip -l "{zip}"`. Check a restored file: `shasum -a 256 {file}` against the manifest.

## Monthly policy, by producer

| Producer and pile | Where it writes | Month-end rule | Who acts | State |
|---|---|---|---|---|
| AI night shift (launchd, Mon to Sat 01:00), plus semrush-prepull, vendor-dash-read, cars-watch-sbmw-browser | `outputs/ai-team/YYYY-MM-DD/`, `vendor-dash/`, `cars-sbmw/`, `gm-notes/` | `month_close.py` on the first shift on or after the 15th of M+1: final month pack and summary note `outputs/ai-team/monthly/YYYY-MM.md`, then every day folder dated in M goes off-vault (Semrush raw files in their own zip pending Drew's ToS 3.3 ruling). This tool never touches `outputs/ai-team/`. | ai-team skill, final whistle (SKILL.md step 7) | staged with this skill |
| Daily notes (Nightly notes 21:00, ari-evening-wrapup, AI team brief append, auto-trends line) | `Daily/YYYY-MM-DD.md` | monthly-daily-rollup cloud routine on the 1st writes `Daily/YYYY-MM.md`, then today hard-deletes the dailies of month M-2. Recommended: zip month M-2 with this tool instead of deleting, and grant the routine `Context/` and `Team/` so it can repoint mileage-ledger and contact links. | monthly-daily-rollup (trig_01FLizgJjKDXVni31mp9jJqJ) | needs Drew: cloud prompt and folder grants |
| Client context logs (Nightly notes, cars-act-check, monthly-client-report, NCBMW Semrush refresh) | `Projects/{CODE}/context-log.md`, `context-log-YYYY-MM.md` | Owned by the pending context-log redesign (`outputs/context-log-redesign/`). Never compacted or archived here; monthly-client-report reads the month files. | redesign, when Drew approves it | protected |
| `outputs/` staging (inventory-pulse, site watch, compliance audit, reputation, score-leads, auto-trends, manual builds) | `outputs/*` | After the 1st: proven byte-identical duplicates of Projects deliverables leave; prior-month dated sidecars (`*.facts.json`, `*.manifest.json`, `manifest_*.json`, `*_blog.html`, `*.source.html`), one-off `build_*.py` and run scratch go to the archive; the allowlist (protected list above plus `outputs/README.md` and `build_ncbmw_crossshop.py`) is never touched; current-month files stay; anything unfiled goes to Drew, not the archive. | Claude with this tool, on Drew's go | first run: sweep 2026-10-07 |
| second-brain-optimizer (manual, every 2 to 3 weeks) | `.claude/optimizer/backups/{stamp}/`, `.claude/optimizer/runs/{date}/` | `optimize.py` reads only the root state; backups serve a same-run rollback. Keep the root state plus the newest two runs' backup sets and run snapshot; older ones go to the archive. `backups/` is Read-denied, so Drew runs that batch. | Claude (runs), Drew (backups) | |
| second-brain-optimizer audit sidecars | `Intelligence/decisions/{date}-*-audit*.json` | Nothing reads an old sidecar. Keep the newest two runs' JSON (the latest is cited by the plan file) and every HTML dashboard (they hold the scores); older JSON goes to the archive. | Claude | |
| One-off moves and cleanups | `Intelligence/archive/{date}-*/` | Off-vault: zip whole subfolders once their inbound links are repointed; keep `JS/` and the `*-merged/` folders. Read-denied, so Drew runs it. | Drew with this tool | |
| Cowork FUSE mount | `**/.fuse_hidden*` | Archive each month, never delete blind (some are older context-log versions). lsof must show them closed. Inside `Projects/*/deliverables/` they stay until Drew rules. | Claude | |
| Agents editing the vendor register | `Resources/Vendor-Contacts.backup-*.xlsx` | Keep the newest backup; older ones go to the archive. | Claude | |
| inventory-pulse (5th and 20th), mcpeeks-site-watch | `Projects/{CODE}/inventory-pulse-state/snapshots/`, `Projects/MCP/site-watch-state/history/` | Keep `registry.json`, the current month's snapshots and the previous month's newest anchor (`pick_compare_run` reads exactly one); keep `snapshot.json`, `first_seen.json` and the newest two history files. Older ones go to the archive. | Claude | |
| auto-trends-monthly (5th) | `Intelligence/market/auto-trends/YYYY-MM.json`, `Market-Read.md` | Already one file per month. Its staging copies follow the `outputs/` rule. | nobody | working |
| Weekly work summary | `Intelligence/weekly-reviews/YYYY-Www.md` | Keep all: small and already a rollup. The producer has been broken since W38. | Drew (folder grants) | needs Drew |

## Laws

- Never an em dash or en dash in anything this writes.
- Never delete before the zip verifies; never follow a symlink; never write inside the vault from `apply` (the archive root must be outside it).
- Never archive a file a skill reads, a file edited in the last 7 days (unless it is a proven duplicate), or anything protected.
- Never run `ledgers.py month` or anything else that rebuilds from files this tool has moved off-vault.
