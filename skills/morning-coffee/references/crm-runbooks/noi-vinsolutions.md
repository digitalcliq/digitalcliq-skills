# Nissan of Irvine: VinSolutions (Cox) Runbook

status: NEEDS SCOUTING (run `/morning-coffee scout` with Drew at the machine)

- Entry URL: `https://vinsolutions.app.coxautoinc.com/vinconnect/`
- Session notes: Cox Bridge ID SSO usually keeps a long-lived session in Drew's Chrome. If the Bridge ID login appears, NEVER enter credentials, return `login_required: true` and skip.
- VinConnect is an SPA; after navigation give it 10-15s before reading, and prefer `read_page` over `get_page_text` for its grids.

## Target data (Lead Pulse + Funnel)

- Yesterday's new internet leads by source
- MTD: leads, appointments set/shown, sold, close %
- Unworked / aging leads count

## Click-path (fill in during scouting)

1. TODO: post-login landing (CarDashboard)
2. TODO: Reports menu path to the internet lead source performance report
3. TODO: date-range controls
4. TODO: extraction method notes

## Extraction contract

Return the dealer object in the shared CRM schema: `{available, period, kpis[], sources[], insights[], login_required?}`.
