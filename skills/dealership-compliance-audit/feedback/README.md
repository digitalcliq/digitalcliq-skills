# feedback/: audit override log (Loop 2 in LEGAL_WATCH.md)

`overrides.jsonl` accumulates one JSON line per overridden finding so the checks get
smarter from real use. Append a line whenever a finding is corrected:

```json
{"date":"YYYY-MM-DD","rule_id":"CA-DISC-004","page":"vdp","verdict":"false_positive|missed|wrong_severity","reason":"why","url":"..."}
```

- `false_positive`: the check fired but it was not actually a violation.
- `missed`: a real violation the checks did not catch.
- `wrong_severity`: fired at the wrong severity.

Periodically review and fold recurring patterns into `checks/registry.py`
(gating/regex for false positives, new checks for misses). See LEGAL_WATCH.md.
