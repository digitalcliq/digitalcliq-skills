# Morning brief template (Magic fills this)

Written for a busy owner reading on a phone at 6am, in Magic's own voice: a teammate telling Drew what happened overnight, not a report generator. Every number carries its date range in words. Nothing unverified is stated as fact. No tables, no pipes, no lane listed when it has nothing to say. Never em dashes.

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
- {The question in a sentence. Who raised it. What happens if you say go, and what happens if you do not.}

### What the team worked out together
- **{Players} on {store}:** {the question}. {What each side found, one sentence each.} {The answer, or "still open".} {The move.}

### Store by store
**[[MCP]]** {Two to four sentences. Traffic, paid search, paid social, organic, CRM, but only what moved and why it matters.}
**[[NOI]]** …
**[[SBMW]]** …
**[[NCBMW]]** …
**[[Atlas]]** …

### Organic and content (Worthy)
- {One or two sentences from the GA4 match: a ranking move GA4 confirms or contradicts, or a page Semrush expects traffic on that GA4 does not see.}
- Content: {"Worthy drafted {topic} for {store}, compliance {result}, path {outputs/ai-team/content/...}" | "{N} new topics are posted below for your checkmark" | "nothing picked, nothing drafted"}
- Radar (Mondays): {The idea in a sentence}, {store}. Evidence: {source, date}. {verified | unverified}
- Value line (first Monday of the month only): **[[{STORE}]]** {the store's two sentences from the "For the brief" block in `data/value_line.md`}, one line per store.

### Compliance gate
- {What was reviewed}: {pass | change needed, and what}. Checked federal, California, {OEM file}. Not checked: {…}
- CARS web watch, {STORE}: {n} flagged for review ({first run: listed, no Action items} | {n} NEW, see Action items) | no CARS web data for {STORE} since {date}
- Ad text: {high and review hits, flagged for review} | no ad text data (v2 export not installed in {accounts})

### Missing tonight
- {Store}: no {source} since {date}.

**GM notes drafted for your edit (Fridays):** {paths, or "none this week" with the reason}. Nothing was sent.

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

{One sign-off line in Magic's voice.} Shift ran {start} to {end}, {minutes} minutes, {n} huddles, {n} bounces.
```
