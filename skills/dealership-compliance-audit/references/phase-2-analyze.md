## Phase 2: Analyze (One Deterministic Engine + One Focused Cloud Agent)

All deterministic compliance checks run locally with zero cloud API calls through a
single engine (`verify_loop.py` over `checks/registry.py`). Only genuine gray-area
items go to ONE focused cloud agent. **Run 2a and 2b first (both zero-token), then
2c.**

### Step 2a: AI-Review Payload Builder (zero tokens)

This does NOT compute findings. It reads the crawl and emits the small gray-area
payload (prominence/visual judgment, rebate stacking, sale substantiation,
financial-incentive gating, CARS-Act add-on presentation, visual brand rules) that
the cloud agent in 2c will evaluate. Keeping this payload tiny is what keeps token
cost down.

```bash
python3 /Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/dealership-compliance-audit/scripts/analyze_local.py \
  --crawl /tmp/{safe_client}_crawl_data.json \
  --brand {brand} \
  --brand-rules /Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/dealership-compliance-audit/brands/{brand}_guidelines.json
```

**Output:**
- `/tmp/{safe_client}_ai_review_needed.json`: filtered crawl excerpts for gray-area items only

### Step 2b: Codified Checks + Convergence Loop (zero tokens) ← the deterministic engine

This is THE engine. It executes every codified check (privacy, pricing, Reg M/Z,
CARS Act, brand identity, the 9 CA frameworks), and for any check that comes back
`unresolved` because its page was truncated, it re-fetches that page server-side and
re-asserts. This is what prevents truncation-driven false positives, including a
footer privacy link the browser cut off.

```bash
python3 /Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/dealership-compliance-audit/scripts/verify_loop.py \
  --crawl /tmp/{safe_client}_crawl_data.json \
  --brand {brand} \
  --brand-rules /Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/dealership-compliance-audit/brands/{brand}_guidelines.json
```

**Outputs:**
- `/tmp/{safe_client}_checks_findings.json`: ALL deterministic violations (status==fail only)
- `/tmp/{safe_client}_verification_report.json`: re-crawls, transitions, and the
  count of false positives averted. Surface this to the user before finalizing.

To eyeball the checks as a test report (PASS/FAIL/UNRESOLVED per framework) and
watch the re-verification happen, run:

```bash
python3 .../scripts/run_checks.py --crawl /tmp/{safe_client}_crawl_data.json --brand {brand} --verify
```

If the verification report still lists `still_unresolved` items after the loop
(fallback fetch failed, or a JS-rendered SPA), those stay `needs_human_review` and
must be presented as "could not verify", never as violations.

### Step 2c: Cloud Judgment Agent (one focused agent)

Launch ONE Task agent with `subagent_type: "general-purpose"`. This agent reads ONLY the AI review items file (much smaller than full crawl data) and evaluates gray-area items that require judgment.

```
Prompt:
You are a compliance analyst evaluating gray-area items that require professional judgment.

Read the AI review items file: /tmp/{safe_client}_ai_review_needed.json

Also read these reference files:
- /Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/dealership-compliance-audit/rules/ca_judgment_criteria.md (17 criteria)
- /Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/dealership-compliance-audit/brands/{brand}_guidelines.json

The deterministic engine (Step 2b) has already produced all rule-based findings; do not re-flag them.
Your job is to evaluate ONLY the items in the AI review file. Each item has:
- `review_type`: what kind of judgment is needed
- `judgment_criteria`: which criteria numbers to apply (from ca_judgment_criteria.md)
- `context`: what to evaluate
- Supporting data (disclaimers, text excerpts, prices, etc.)

For each item, evaluate using the specified judgment criteria and create findings where violations or concerns exist.

**Review types and what to evaluate:**

1. `clear_and_conspicuous` — Are disclaimers readable, prominent, and near the claims they qualify? Or are they buried in fine print, hidden behind click-to-expand, or in tiny font?

2. `rebate_stacking` — Are multiple rebates/incentives properly disclosed? Can a consumer qualify for all stacked rebates? Is it clear which are mutually exclusive?

3. `sale_savings` — Are sale/savings claims substantiated? Do they have valid date ranges? Are reference prices (MSRP, "was" price) legitimate?

4. `lease_due_at_signing` — Are lease due-at-signing amounts accurate and prominent? Do they include all required fees?

5. `vehicle_condition` — Are condition claims ("no accidents", "like new") substantiated with documentation references?

6. `financial_incentive` — Does the site gate pricing behind personal information collection? If so, is there a CCPA financial incentive disclosure?

7. `brand_visual_contextual` — Evaluate brand guideline rules that require visual/contextual judgment (logo placement, typography, color usage, photography, navigation layout, popup behavior, DAP compliance, etc.). Skip rules already covered by local analysis: FCA naming, Fiat branding, CPO page, brand in titles, model name order.

Each finding must use this exact schema:
{
  "page_url": "URL where the issue was found",
  "finding_type": "legal_violation" or "brand_violation",
  "rule_id": "CA-DISC-003" or "BMW-LOGO-001" etc.,
  "title": "Short description",
  "quote": "Exact text evidence",
  "severity": "critical|warning|advisory",
  "source": "legal_check" or "brand_check",
  "statute": "Applicable statute or empty string for brand rules",
  "recommendation": "What to fix",
  "confidence": "high|medium|low",
  "needs_human_review": true or false
}
