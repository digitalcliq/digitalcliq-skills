---
type: instructions
status: active
tags: [claude, instructions]
---

Vault-side catalog and notes for Drew's custom skills. Runtime code lives at `.claude/skills/{name}/` (auto-discovered); this folder holds the human-readable side.

| Path | Holds |
|---|---|
| `README.md` | Catalog: every skill, trigger phrases, arguments |
| `{name}/notes.md` | Change log and design notes (keep this exact filename; wikilinks depend on the path) |
| `{name}/examples/` | Sample outputs for humans |

Placement: `SKILL.md`, scripts, and runtime references go in `.claude/skills/{name}/`; OEM guideline inputs stay in `Resources/automotive-guidelines/` and are wikilinked, never copied. Names are slug-case; the folder name is the `/{name}` handle.
