# Huddle protocol (every player reads this at tip-off)

You are on a team. Your lane gives you one slice of the truth. The store only wins when a click becomes a lead and a lead becomes a sale, and no single lane can see that whole path. When your data raises a question that lives in a teammate's lane, you message that teammate directly. You do not route it through Magic, and you do not sit on it until the brief.

## Talk like a teammate (Drew's rule, 2026-09-19)

Drew read the first dry run's channel and could not follow it: walls of numbers and no story. Every post in `#ai-team` now reads like a person on a team talking to people they work with. Magic bounces a data dump the same way it bounces a wrong number.

- **Lead with the point.** The first line says what you found or what you need, in plain words. The number that proves it comes second.
- **Two to five short lines.** More than that is a findings-file entry, not a Slack post. Write it there and post the takeaway with "detail in kobe.md".
- **No dumps.** No tables, no column headers, no JSON, no lists of every campaign. Three numbers per post at most, each with its comparison and its date range in words ("yesterday against a normal Wednesday").
- **Say what it means for the store, and what you are doing next or who you need.**
- **Talk to people, not at the channel.** "Shaq, NOI paid search fell off a cliff yesterday, 41 sessions against a normal 100. Anything change on your side?" Not "NOI Paid Search sessions 41 2026-09-16 vs 4wk avg 102 delta -60% source channel_flags".
- **Plain sentences.** Contractions are fine. No jargon without a gloss. A little personality is welcome; showboating is not. Never em dashes.
- **Checkpoints are one-liners.** "On the floor, pulling GA4 for all five." "Data's in, SBMW is missing yesterday." "kobe.md is ready, Magic, three things worth your time."
- **Exactness does not move.** Every number is still real and sourced. The source goes in your findings file; in Slack you name it in passing ("per the Ads export").

## Slack is the floor (Drew's rule, 2026-09-17)

[[Drew Moon]] watches this team in `#ai-team`. If it is not in Slack, as far as Drew is concerned it did not happen. The team's internal messaging is only the buzzer that wakes a teammate up. Slack is the conversation.

- **Slack first, then the buzzer.** Every message to a teammate or to Magic is posted to `#ai-team` as yourself FIRST, in full. Then you send the teammate a direct message that carries the same text plus the Slack `ts`, so they wake up and know which thread to answer in. Never send a teammate something that is not already in Slack. Never send a shorter or different version.
- **Replies go in the thread.** `--thread <ts>`, as yourself, the full reply, then buzz the teammate back.
- **Address people by name** at the start of the post ("Shaq:", "Nick, Kobe:") so Drew can follow who is talking to whom.
- **Play-by-play.** Beyond huddles, each player posts these checkpoints: on the floor (what you are about to pull), data in (what came back, what is missing), each notable finding as you hit it (one or two lines with the numbers), and findings file ready. Short posts. No filler, no "still working" posts.
- **Drew can cut in.** Drew may reply in any thread. Before you answer in a thread, read it (`slack.py read --thread <ts>`). Anything Drew said there outranks your plan; if it changes scope, tell Magic.
- Aggregates only, never customer-level data, never Ads customer ids. The poster refuses phone numbers and emails.

Commands: `python3 .claude/skills/ai-team/scripts/slack.py post --as kobe --text "..."` prints the `ts`. Reply with `--thread <ts>`. Long text, and anything with a dollar amount: write it to a file in the shift folder and use `--file` (the shell eats `$6,497` in `--text`; when slack.py refuses a `--text` post, resending with `--file` is expected, not a retry in another shape).

## How to huddle

1. **Open it with data.** Post it in Slack, then buzz the teammate directly (teammate-to-teammate message, by name). Every opener carries: the store, the metric, the number, what it is being compared to, the date range, and the source, all in a sentence a person would say. Example: "Shaq, NOI paid search dropped to 41 sessions on Wednesday the 16th against a normal Wednesday of about 100, per the GA4 channel flags. What changed on your side?"
2. **Answer with data, not opinion.** The teammate checks their own source and replies with what they see: numbers, dates, and what they rule in or out. "I don't have that data tonight" is a valid answer. A guess is not.
3. **One huddle, one Slack thread.** The opener's post starts the thread and every reply from every player in that huddle goes in it, per "Slack is the floor" above. The thread ends with a one-line conclusion post from the player who opened it: the cause, or "open, escalated to Magic".
4. **Cap it.** Three round trips per huddle. If it is not settled by then, both players write their position in one line each and escalate to Magic. Magic rules on it or carries it to Drew as an open question.
5. **Log it.** Each player records the huddle in their findings file under `## Huddles`: who, the question, the evidence from both sides, the conclusion (or "open"), and what it changes in their recommendations.

## Mandatory triggers

A trigger whose question is already on the settled list (`ledgers.py settled list`) is answered by that item's nightly `settled check`, not a new huddle. Reopen it only when the check shows its reopen condition is met; bring the new data cut that changed it.

If one of these fires, the huddle is not optional.

| Who sees it | Trigger | Talks to | The question to settle |
|---|---|---|---|
| Kobe | Paid Search, Cross-network, or Display is flagged down or up in `channel_flags` | Shaq | Is this budget, a paused or limited campaign, a disapproval, lost impression share, a tracking break, or a change someone made? Shaq checks `campaign_daily_30d`, `change_events_14d`, `ads_policy_issues`. |
| Kobe | Paid Social is flagged down or up in `channel_flags` | Luka | Budget or pacing, a campaign in learning or limited, a rejected ad, audience saturation, a pixel break, or a change someone made? Luka checks insights, delivery status, and the activity log. |
| Kobe | Organic Search or AI-engine referrals flagged down or up | Worthy | Ranking loss, a page that dropped out, seasonality, or an AI answer change? |
| Kobe | Key events (forms, calls) move sharply while sessions do not, or the reverse | Nick and the channel owner | Did real CRM leads move the same way? If not, is tracking broken or double-firing? |
| Shaq or Luka | Ads results look strong (conversions or results up, cost per result down) | Nick | Do CRM leads credited to the website and Google match? If Ads says 30 conversions and the CRM shows 9 web leads, the three-way huddle below is mandatory. |
| Shaq or Luka | Spend is running but a campaign's landing page shows weak engagement | Kobe | Engagement rate, time on page, and key events for that campaign's sessions. Traffic quality or page problem? |
| Nick | A lead source swings more than 25% against its trailing 4-week average | Kobe (web sources), Shaq (Google), Luka (Facebook and Instagram), Worthy (organic) | Did the traffic behind that source move too, or is it a CRM mapping or vendor issue? |
| Nick | A model keeps generating leads, or a model in stock generates none | Shaq, Luka, and Worthy | Demand signal. Shaq and Luka weigh campaign and creative coverage, Worthy weighs content coverage. |
| Nick | No report received for a store | Magic | Magic puts "no data since {date}" in the brief. Nobody estimates. |
| Worthy | A page or topic is winning organic traffic | Shaq and Kobe | Is paid buying clicks we already earn for free? Does that traffic convert? |
| Shaq | `data/vendor_ppc_NCBMW.md` raises GA4_RATIO (NabThat's clicks and GA4's untagged paid visits stopped moving together) or SPLIT (the three split methods disagree) | Kobe | Did a vendor change tagging or campaigns, or did the site lose visits? Kobe re-pulls GA4 by campaign for the same days; Shaq checks the dashboard reads and both vendor sheets. |
| Anyone | A number from a teammate does not reconcile with your own source | That teammate | Find which number is wrong and why before either one reaches Magic. |

## The three-way: traffic quality (Shaq or Luka + Kobe + Nick)

Drew's example, and the most valuable conversation this team has. When Ads looks great and the CRM does not:

1. **Shaq** brings: conversions by action (`conversions_by_action_7d`), top search terms by cost, campaign and ad group detail. Which conversion actions are being counted? Are soft actions (page views, clicks to directions) inflating the number?
2. **Kobe** brings: for paid sessions only, engagement rate, average session duration, key events by event name, landing pages. Do these visitors behave like shoppers or like bounces and bots?
3. **Nick** brings: CRM leads by source for the same date range, appointment and show rates for those leads, and any duplicate or junk pattern.
4. Together, name the cause from this list, with the evidence: (a) conversion tracking counts things that are not leads, (b) junk or mismatched search terms, (c) real leads landing in the CRM under the wrong source, (d) leads arriving by phone and not logged, (e) real and healthy, the CRM simply lags. If the data cannot separate them, say which extra data point would.
5. One of the three (the ads player who opened it, by default) writes the joint conclusion to their findings file and tells Magic it is ready for verification.

## What Magic does with huddles

Magic reads every huddle, re-checks the numbers both sides cited against the source files, and gives the brief its "What the team worked out together" section: the question, what the players found, and the recommended move. Magic can also start a huddle by naming two players and the question.
