# SEMRUSH Playbook (for /blog-content)

SEMRUSH is connected over MCP and is the **preferred** source for keyword demand, difficulty,
intent, competitor gaps, and rank tracking. Use it to drive topic selection and the keyword
cluster. If the domain/market has no usable SEMRUSH data, fall back gracefully (see bottom) and
**flag in the plan** that estimates are research-based (`meta.semrush_used = false`).

> Vault note: the `reference_semrush-projects` memory lists DigitalCLIQ's existing SEMRUSH
> projects + domains (dealer clients). Position Tracking has been unreliable there, prefer
> organic/keyword reports for movers. Check whether the client already has a project before
> creating work.

## The workflow

Follow the SEMRUSH MCP server's own injected instructions (discovery tool → `get_report_schema` →
`execute_report`). The only blog-specific defaults: `database = "us"` unless the client's market is
elsewhere; `display_limit` 30-50 for exploratory pulls; always fetch real data, never recall metrics.

## Which tool for which question

| Need | Tool |
|---|---|
| Keyword volume, KD, intent, variations, questions, related terms | `keyword_research` |
| A domain's existing organic keywords + positions (the client AND competitors) | `organic_research` |
| Domain traffic / authority snapshot, top pages | `overview_research` |
| Backlink profile / authority (trust context for E-E-A-T) | `backlink_research` |
| Technical health that could cap ranking | `siteaudit_research` |
| Existing project data + position tracking | `projects_research`, `tracking_research` |
| Rising/seasonal demand for timing topics | `trends_research` |
| One specific URL's keywords (steal a competitor's winning page) | `url_research` |
| Generic / advanced report not covered above | `get_report_schema` then `execute_report` |

For any tool, if the args aren't obvious call `get_report_schema` first to see required params,
then `execute_report`. Combine multiple reports for one decision (e.g. keyword + organic gap).

## How to use the data for topic selection

1. **Seed.** From the brand research, list 10-20 seed topics/keywords the customer would search.
2. **`keyword_research`** each strong seed → capture volume, KD, intent, and the long-tail +
   question variants. These become the keyword **cluster** per piece.
3. **`organic_research` on 2-3 competitors** (incl. the hostile/competitor names from the facts
   ledger, e.g. LOGO Cargo for Atlas) → find keywords they rank for that the client does not.
   That delta is the **content gap** and a prime source of the 3 topics.
4. **`organic_research` on the client domain** → don't re-target a keyword they already win;
   find the near-misses (positions 5-20) a strong new piece could push onto page one.
5. **Score & pick:** prefer intent-matched, winnable (lower KD relative to the domain's
   authority), gap-filling topics. Spread the 3 pieces across funnel stages (TOFU/MOFU/BOFU).
6. **Record real numbers** in the SEO brief: every `primary_keyword` and `secondary_keyword`
   gets `{term, volume, kd, intent}` straight from SEMRUSH. Mark anything estimated.

## Optional: tracking after publish

If the client has (or you create) a SEMRUSH project, note the keyword set so Position Tracking
can monitor it. Don't block delivery on this; it's a measurement recommendation in the brief.

## Fallback when SEMRUSH has no data (small/new/local brand)

Common for a brand-new prospect or a hyper-local business. Do not fabricate metrics:
- Use **WebSearch** for the keyword, read **autocomplete**, **"People also ask"**, and
  **"related searches"** to infer real demand and question phrasing.
- Read the **top 3-5 ranking pages** (WebFetch / browser) to gauge intent, depth, and the gap.
- Provide **directional** estimates only, clearly labeled (e.g. "intent: commercial; volume: est.
  low-mid, no SEMRUSH data"). Set `meta.semrush_used = false` so the workbook says so honestly.
- The strategy quality does not depend on having paid metrics; intent + gap analysis still drives
  excellent topic selection.
