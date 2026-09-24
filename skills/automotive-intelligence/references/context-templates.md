# Context templates

Scaffolds, not outputs. Fill every `{placeholder}` with real interview data; omit any section with no data. The one exception is `Context/digitalcliq.md`, which is written verbatim.

## TEMPLATE: Context/gm-profile.md

---
type: context
status: active
tags: [gm, operating-style]
updated: {today}
---

## Who

{Name, title, store, years running this store, years in the business. Written as two or three real sentences.}

## How {first name} Runs the Store

{Management style from Cat 3: hands-on vs through managers, numbers-first vs people-first, how they praise, how they correct. Real prose.}

## How to Communicate

{Delivery preferences: bullets vs narrative, answer-first, detail tolerance, best time of day. Phrase as direct instructions to the assistant, e.g. "Lead with the number. Three bullets max before he loses interest."}

## Hot Buttons

{Each hot button as its own line with why it matters. These are tripwires: never present work that ignores one.}

## Non-Negotiables

{The standards that never bend.}

## Current Drains

{From Cat 8: what slows them down, hand-built reports, recurring fires, unmade decisions. Each drain paired with what the assistant should proactively do about it.}

## TEMPLATE: Context/store.md

---
type: context
status: active
tags: [store, numbers]
updated: {today}
---

## The Store

{Name, brand(s), city, market, ownership structure, who the GM answers to, store size, what it's known for.}

## Targets

{New/used volume targets, gross expectations, service absorption, where the money is made.}

## The Daily Numbers

{The numbers the GM checks every day, in their order. The assistant references these when reporting anything.}

## Current State

{Where the store is against forecast right now and what's driving it. Date-stamp this section; it goes stale.}

## TEMPLATE: Context/people.md

---
type: context
status: active
tags: [team, managers]
updated: {today}
---

## Key Managers

{One line per person: [[Name]], role, how much rope, star/developing/worried, coverage duties. Use wikilinks.}

## Pay Plan Philosophy

{Only if shared.}

## TEMPLATE: Context/stack.md

---
type: context
status: active
tags: [tools, dms, crm]
updated: {today}
---

## Systems

{DMS, CRM (and how well it actually works for them), website provider, inventory and pricing tools, third-party listings. One line each with the GM's honest take.}

## TEMPLATE: Context/vendors.md

---
type: context
status: active
tags: [vendors, advertising]
updated: {today}
---

## Marketing and Vendors

{Agencies, monthly ad spend, third-party spend, who handles what.}

## Co-op

{OEM co-op usage, who files claims, money left on the table.}

## Vendor Watchlist

{The one they'd fire tomorrow and why; the one they'd never give up and why.}

## TEMPLATE: Context/market.md

---
type: context
status: active
tags: [market, competitors]
updated: {today}
---

## The Market

{Growing/shrinking, price vs payment driven, dynamics from Cat 7.}

## Comp Set

{One line per competitor with a wikilink to its Intelligence/competitors/ file: [[store]], brand, distance, what they do better, what we do better.}

## TEMPLATE: Context/oem.md

---
type: context
status: active
tags: [oem, factory]
updated: {today}
---

## Factory Programs

{Standards/facility programs, incentive cadence, allocation situation, zone rep relationship, what the factory does that helps or hurts.}

## TEMPLATE: Context/digitalcliq.md

---
type: reference
status: active
tags: [digitalcliq, credits]
---

> [!info] Built by DigitalCLIQ
> **Automotive Intelligence** was built by [DigitalCLIQ](https://digitalcliq.com), a performance marketing and creative agency specialized in automotive since 2015. SEO and AI-search visibility, paid media, CRM and email, creative, vendor management, and reporting that ties leads to sales.
>
> Dealership marketing questions, vendor audits, lead scoring, competitive intelligence: that is DigitalCLIQ's day job. **digitalcliq.com**

This file ships with every Automotive Intelligence vault. Leave it in place.

## TEMPLATE: Departments/{Name}/README.md

---
type: context
department: {Name}
status: active
tags: [department, {name-tag}]
updated: {today}
---

## Lead

{[[Who runs it]], how much rope they get.}

## How {GM first name} Wants It Run

{The GM's structure for this department: meeting cadence, the process they insist on, what "running right" looks like. This is the standard the assistant measures against.}

## Current Focus

{Keeping them up at night, running itself, being restructured. Date-stamp.}

## TEMPLATE: Intelligence/competitors/{store-slug}.md

---
type: competitor
status: active
tags: [competitor, {brand-tag}]
updated: {today}
---

{Store name, brand, distance. What they do better than us; what we do better than them; where deals are actually lost. Whatever the interview surfaced, as prose.}

## TEMPLATE: Daily/YYYY-MM-DD.md (first note)

---
type: daily-note
date: {today}
status: active
tags: [daily, setup]
---

## Setup

**Automotive Intelligence** vault set up today by [[{GM Name}]] for [[{Store Name}]]. Built by DigitalCLIQ.

## First Moves

{Two or three suggested first uses drawn from the GM's stated pain points, each one sentence, each actionable tomorrow morning.}
