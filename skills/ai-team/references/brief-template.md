# Morning brief template (Magic fills this)

Written for a busy owner reading on a phone at 6am, in Magic's own voice: a teammate telling Drew what happened overnight, not a report generator. Every number carries its date range in words. GA4 counts for the target day are preliminary (the 1 AM pull runs before GA4 finishes counting): label them "preliminary, GA4 finalizes in 24 to 48 hours" wherever one is quoted, and remember traffic flags describe the day before, the last complete day (`flag_date` in `ga4_{STORE}.json`). Nothing unverified is stated as fact. No tables, no pipes, no lane listed when it has nothing to say. Never em dashes.

Head budget (Drew, 2026-09-28): the title, greeting, The three things and Needs your call together stay under 350 words, because `slack.py post-brief` posts only those as Drew's message and threads the rest (it refuses a longer head). Name each ask id once in the head: in Needs your call when it is Drew's decision, while The three things tells the story by store and number. Every Needs your call bullet carries an ask id so `post-asks` can make it tappable. A correction to an earlier brief is one sentence in the greeting, with the detail in its own `### Corrections` section in the thread. Repeat nothing that is on the settled list unless it changed; spot checks that found nothing new stay out of the brief.

```
## AI Team Brief, {weekday} {date}
Morning Drew. {One or two sentences: the night in a nutshell and the single thing that matters most.} We covered {target dates}, {dry run | shift}. On the floor: Magic, Kobe, Shaq, Luka, Worthy, Nick.

### The three things
1. **{Store}: {the headline in plain words}.** {The number and what it is being compared to, one sentence.} {What we would do about it.}
2. **…**
3. **…**

### Measurement health
- {Store}: {RED | AMBER | GREEN}. {Top issue in plain words, with its dates}. Broken {n} days.
(one line per store, straight from `data/health.md`; red numbers stay out of every claim below)

### Needs your call
- {The question in a sentence. Who raised it. What happens if you say go, and what happens if you do not.} ({Ax})

### What the team worked out together
- **{Players} on {store}:** {the question}. {What each side found, one sentence each.} {The answer, or "still open".} {The move.}

### Store by store
GA4 for {target date} is preliminary, GA4 finalizes in 24 to 48 hours; traffic flags below are for {flag date}, the last complete day.
**[[MCP]]** {Two to four sentences. Traffic, paid search, paid social, organic, CRM, but only what moved and why it matters.}
**[[NOI]]** …
**[[SBMW]]** …
**[[NCBMW]]** … Paid search is run by [[NabThat]] and [[Constellation]]; from Shaq's vendor section say only what moved: NabThat's implied spend (clicks x avg CPC) and pace against the cap, the credit split as an estimate with its range, a new Constellation month. A steady night gets no line.
**[[Atlas]]** …

### Organic and content (Worthy)
- {One or two sentences from the GA4 match: a ranking move GA4 confirms or contradicts, or a page Semrush expects traffic on that GA4 does not see.}
- Content: {"Worthy drafted {topic} for {store}, compliance {result}, path {outputs/ai-team/content/...}" | "{N} new topics are posted below for your checkmark" | "nothing picked, nothing drafted"}
- Radar (Mondays): {The idea in a sentence}, {store}. Evidence: {source, date}. {verified | unverified}
- Value line (first Monday of the month only): **[[{STORE}]]** {the store's two sentences from the "For the brief" block in `data/value_line.md`}, one line per store.

### Compliance gate
- {What was reviewed}: {pass | change needed, and what}. Checked federal, California, {OEM file}. Not checked: {…}
- CARS web watch, {STORE}: {n} flagged for review ({first run: listed, no Action items} | {n} NEW, see Action items) | no CARS web data for {STORE} since {date}
- Ad text: {high and review hits, flagged for review} | no ad text data for {accounts} (the export ran without its ad_text_7d tab)

### Missing tonight
- {Store}: no {source} since {date}.
- NCBMW NabThat dashboard: no read since {date}, {reason from `vendor_dash.py status`} (only when a read is missing or invalid)
- {STORE} dashboard: {RED | AMBER}, {first seen tonight | open n days}. {What the GM sees that is stale}. Fix: {the fix, e.g. "load the current Focus export into the NCBMW dashboard Sheet"}. (one line per flagged store, from `brief_lines` in `data/dashboards.json`; nothing when all three are GREEN)

### Action items
1. **{Owner}: {the action, in one sentence}.** Why: {the evidence}. If skipped: {what it costs}. {Needs your go | No approval needed | Waiting on {someone}}
2. …
(new or changed tonight only, each with its ask id, for example "(A19)"; carried-over asks live in Asks aging)

### Asks aging
- {id}, {label}, open {n} days, {owner}{, GM request due | , GM request drafted {date}: path}

### Closed tonight
- {id}, {label}: closed. {closure evidence}{ Win: {win}}
- {id}, {label}: withdrawn. {reason}

### What the players say
- **Kobe:** working: {…}. Not working: {…}. Suggestion: {…}. Source: {…}
- **Shaq:** …
- **Luka:** …
- **Worthy:** …
- **Nick:** …

### Tasks worth creating? (your call, nothing was created)
- {Task} for {client}: {why}

### Could not verify
- {Claim}, from {player}: {why it stayed out}

### Shift stats
{paste the table from `python3 .claude/skills/ai-team/scripts/usage.py --md`}

{One sign-off line in Magic's voice.} Shift started {start}; brief posted {time from `ledgers.py log --stamp-only`}, {n} huddles, {n} bounces.
```
