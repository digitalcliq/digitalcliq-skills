# New Century BMW: Focus (Reynolds & Reynolds) Runbook

status: SCOUTED 2026-07-21 (verified live pull: MTD totals 689 prospects / 86 appts sched 12.48% / 54 sold 7.84% / $152,721 gross)

- Entry URL: `https://focus.dealer.reyrey.net/?bg=130445`, Drew keeps a parked FOCUS tab; PREFER the existing FOCUS tab in the group over navigating fresh (fresh loads can bounce through Reynolds SSO). If a Reynolds login/SSO page renders, return `{"available": false, "login_required": true, "note": "Focus session expired"}`. NEVER touch the form.
- Header must read "Moon, Drew / New Century Autos" = logged in.
- The NCBMW live dashboard (Dashboard Cross-Check section) is fed by Prospect ROI + CallRevu pastes and can cover NCBMW when Focus is unreachable.

## Target report

Top nav **Reports** button (pie-chart icon, 2nd icon after home; a11y name "Reports") → REPORTING HOME tab → Standard Reports → **Prospect Source Report**.
Also available: My Reports → "Sales & Source" (Drew's saved Sales Tracking Report), client-level detail, 700+ rows; use only when a per-lead drill-down is asked for, not for the daily pull.

## Click-path (deterministic, verified 2026-07-21)

1. Use the parked FOCUS tab (find via `tabs_context_mcp`, title "FOCUS"). Screenshot to confirm logged-in header.
2. Click the **Reports** nav button (use `read_page filter:interactive` → button "Reports", click by ref). Wait 8s. The REPORTING HOME tab lists all reports.
3. Click **Prospect Source Report**. Wait 8s. Defaults are already correct: Report By **Source**, Category **Sales**, Date Range **Current Month**, Report View **Summary**. For a yesterday-only pull, change Date Range via its dropdown (options include Today, Yesterday, Current Month...).
4. Click **VIEW** (right end of the filter bar, ~(1471,276)). Wait 10s.
5. Read with **`get_page_text`**: the grid dumps clean: per-source rows with columns `Source | Source Type | Business Unit | Prorated Cost | Per Lead Cost | Duplicate Leads | Total Prospects | Appts Scheduled | % | Appts Confirmed | % | Appts Kept | Appt No Shows | Avg Cost/Prospect | New Sold | Used Sold | Total Sold | Closing Ratio | Total Gross | Avg Cost/Sale | Total Net`, ending with `Average` and `Total` rows.

## Quirks

- NEVER click the green save icon in the report toolbar, it overwrites saved report settings. RESET/VIEW only.
- The grid virtualizes: `get_page_text` returns the Totals row plus only the loaded subset of the 70+ source rows. Totals are always present; for full source detail, `scroll` the grid down and re-read, or sort by Total Prospects descending (click the column header) so the big sources load first.
- Clicking hamburger-menu → Reports → Dashboard just reloads home in a NEW tab (old tab dies), don't use it; use the top-nav Reports button.
- Numbers here (689 MTD prospects) run wider than the NCBMW live dashboard (539 "leads"), different filters. Label the period/source; don't reconcile in the report.
- Focus sessions can force re-auth daily; treat any login page as login_required and move on.

## Extraction contract

Return the dealer object in the shared CRM schema: `{available, period, kpis[], sources[], insights[], login_required?}`.
