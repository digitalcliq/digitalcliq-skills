---
type: reference
status: active
tags: [skill, reporting, monthly, client-report]
---

Design notes for the [[monthly-client-report]] skill, built by [[Drew Moon]] 2026-06-30. Code lives in `.claude/skills/monthly-client-report/`; this is the in-vault reference.

## What it does

`/monthly-client-report <code|name|website> [--month YYYY-MM]` produces a branded, client-facing **2-3 page PDF** for the previous calendar month. One report per client. Designed to be lean: the main loop only orchestrates, and the heavy data-gathering runs in parallel **Sonnet** subagents.

## Data sources

- **Traffic**, GA4 (live, Chrome browser pattern reused from [[morning-coffee]]), full month + MoM, with **social referral broken out**.
- **Paid**, Drew's **attached** Google Ads / Meta CSV/PDF (no live Google Ads API; Meta is the only ads MCP). Parsed in the main loop.
- **SEO**, SEMRUSH live for dealers in the Semrush projects (see semrush projects); omitted for clients not in Semrush.
- **Leads**, Drew's **attached** CRM export, scored against NADA close rates by brand tier via the existing [[score-leads]] script.
- **Reputation**, Google + Yelp, fresh live every run, with MoM delta stored in `Projects/{CODE}/reporting/reputation-baseline.json`.
- **Regional**, NADA / state auto + economic data, keyed off the client's state (city→state logic; Anaheim→California, Las Vegas→Nevada). Non-auto clients get local small-business context instead.
- **Wins**, pulled from the vault: `Projects/{CODE}/` Running Context + Monthly Wins log + `visit-notes/` + the root `Daily/` journal. Rendered as "DigitalCLIQ & {client} wins this month".

## Guardrails

Loads [[Context/vault-facts|the facts ledger]] first. White logo on blue masthead only. gmail address hard-rejected by the generator. **Self-review loop** renders the PDF to images and judges it as Drew would (numbers reconcile, names correct, teammate voice, no placeholders, 2-3 pages) before `post_flight.py` validation. Final PDF is filed into `Projects/{CODE}/deliverables/`; nothing is sent to the client until Drew says so.

## Routing & registry

Client resolution is driven by `reference/client_registry.json` (CODE, aliases, domains → city, state, brand, brand_tier, GA4 property, Semrush project, CRM, owner). Add new clients there. Honors the ownership split.

## Scheduling

For automated 1st/2nd-of-month runs, use the [[schedule]] skill per client with model = Sonnet. Headless runs can't receive chat attachments, so the leads/paid sections need the CRM/ad export dropped to a known folder (e.g. `01_Inbox/`) first, or schedule a reminder instead.
