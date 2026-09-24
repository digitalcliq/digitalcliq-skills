# Legal Watch: keeping the compliance audit current and self-improving

This skill enforces real, moving law. Two loops keep it from going stale and make it
smarter over time. Jurisdiction focus: **California** (almost all DigitalCLIQ dealer
clients); federal rules are secondary context.

## Loop 1: Monthly legal-currency watch (stays current)

Run by a scheduled agent once a month. Steps:

1. **What's due?**
   ```bash
   python3 scripts/legal_watch.py --due 30
   ```
   Lists frameworks in `rules/legal_watch.json` not re-verified in 30+ days.

2. **Research them** (web). Use the prompt template in
   `Resources/automotive-guidelines/` style: for each due framework verify (a) current
   status, (b) correct citation + effective/operative date, (c) any 2025-2026 change,
   (d) 1-2 authoritative sources (oag.ca.gov, dmv.ca.gov, leginfo, cppa.ca.gov, courts,
   and for CARS-CA the current CNCDA Compliance Guide on CNCDA Comply, which CNCDA
   updates continuously through October 2026; diff it against
   `Resources/automotive-guidelines/cncda-cars-act-guidance.md`).
   Write the result as JSON keyed by framework id:
   ```json
   { "CCPA-CPRA": { "status": "...", "effective_date": "2026-01-01", "sources": ["..."] } }
   ```

3. **Diff against the baseline:**
   ```bash
   python3 scripts/legal_watch.py --diff /tmp/legal_findings.json
   ```
   Prints every material change (status moved, new operative date, rule reinstated).

4. **On a material change:** write a dated note to the vault
   (`Intelligence/` compliance log), and open a task (Notion `💼 TASKS`, Assignee
   [[Drew Moon]]) to update the affected check in `checks/registry.py` and/or the
   statute/severity. Do NOT silently edit checks, a human approves legal changes.

5. **Stamp it verified:**
   ```bash
   python3 scripts/legal_watch.py --update /tmp/legal_findings.json
   ```
   Bumps `last_verified` and records the new status + sources.

The audit report can cite `legal_watch.json`'s `last_full_review` as the "legal basis
last verified" date, so a dealer/ANSIRA dispute sees the audit is current.

### Schedule it
Use the `schedule` skill (cron cloud agent) to run this monthly, e.g. the 1st of each
month. The agent runs steps 1-5 and DMs Drew a one-paragraph "what changed in the law
this month" summary. Nothing in `registry.py` changes without Drew's approval.

## Loop 2: Audit feedback (gets smarter from use)

Every time a finding is overridden: you mark it a false positive, the cloud judgment
agent downgrades it, or a dealer disputes it and is right, append one line to
`feedback/overrides.jsonl`:

```json
{"date":"2026-06-28","rule_id":"CA-DISC-004","page":"vdp","verdict":"false_positive","reason":"'excludes ... documentary fee' is a state-required notice here, not a price exclusion","url":"https://..."}
```

These accumulate into a tuning signal. Periodically (or on `/compliance-audit --tune`)
review `overrides.jsonl` and fold recurring false positives into the check's gating or
regex in `registry.py`, and recurring misses into new/tightened checks. This is how the
check set converges on the real world instead of drifting on assumptions.

Rules of the loop:
- A check is only as good as its last verification. Stale = suspect.
- Never auto-apply a legal change; a human signs off on what the law is.
- Every override is a free lesson: log it, don't lose it.
