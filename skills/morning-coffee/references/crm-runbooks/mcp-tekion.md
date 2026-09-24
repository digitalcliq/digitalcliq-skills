# McPeek CDJR: Tekion Runbook

status: NEEDS SCOUTING (run `/morning-coffee scout` with Drew at the machine)

- Entry URL: `https://app.tekioncloud.com/` (Drew's bookmark lands on `/core/cpra/requests`, navigate to the CRM/sales area, not CPRA)
- Session notes: Tekion sessions are generally long-lived in Chrome. If a login appears, NEVER enter credentials, return `login_required: true` and skip.
- Vault context: the McPeek live dashboard has a Tekion-aware parser (`reference_mcpeek-dashboard`), so the Dashboard Cross-Check section may carry McPeek numbers when Tekion is unreachable. Drew is on-site at McPeek Tue/Thu.

## Target data (Lead Pulse + Funnel)

- Yesterday's new leads by source
- MTD: leads, appointments set/shown, sold, close %
- Unworked / aging leads count

## Click-path (fill in during scouting)

1. TODO: post-login landing
2. TODO: path to CRM lead source report (Tekion ARC "Sales > Reports" area)
3. TODO: date-range controls
4. TODO: extraction method notes

## Extraction contract

Return the dealer object in the shared CRM schema: `{available, period, kpis[], sources[], insights[], login_required?}`.
