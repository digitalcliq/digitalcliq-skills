---
type: instructions
status: active
tags: [claude, instructions]
---

This folder is the vault-level catalog of Drew's custom Claude Code skills. **The runtime source-of-truth lives at `.claude/skills/{name}/SKILL.md`** at the vault root, which is where Claude Code auto-discovers them.

## Two kinds of content live here

1. **Catalog & docs** at `Skills/README.md` and per-skill `Skills/{name}/notes.md`. Vault-readable documentation, change logs, and references that don't belong inside the runtime `.claude/skills/{name}/` folder.

2. **Skill-adjacent vault content** like input templates, reference data, or sample outputs that the skill points back at via `[[wikilinks]]`. The skill's runtime code stays under `.claude/skills/`; its vault-side knowledge lives here.

## When to put a file here vs in `.claude/skills/{name}/`

| File type | Lives at |
|---|---|
| `SKILL.md` (entry point + YAML frontmatter) | `.claude/skills/{name}/SKILL.md` |
| Skill scripts (`*.py`, `*.sh`, etc.) | `.claude/skills/{name}/` |
| Skill references that the skill reads at runtime | `.claude/skills/{name}/references/` |
| Skill output samples, examples for humans | `Skills/{name}/examples/` |
| Skill change log, design notes, evolution notes | `Skills/{name}/notes.md` |
| Skill-specific input data (compliance PDFs, templates) | `Resources/` (cross-link from the skill) |

## Per-skill notes convention

Per-skill change logs and design notes live at `Skills/{skill-name}/notes.md`. The generic filename is deliberate: the parent folder disambiguates, and existing wikilinks (e.g. `[[Skills/social-media-manager/notes|design notes]]`) depend on the path. Do not rename these to `design-notes.md` or similar; always link them with the full folder path.

## Don't duplicate

If a skill needs OEM brand guidelines, it reads them from [[Resources/automotive-guidelines/README|Automotive Guidelines]] via wikilink reference. Do not re-package those guidelines inside the skill folder. Single source of truth.

## Current skill catalog

See [[Skills/README|Skills catalog]] for the full list with descriptions, trigger phrases, and arguments.

## Naming convention

Slug-case, no caps, no spaces. The folder name in `.claude/skills/{name}/` becomes the invocation handle (`/{name}`).
