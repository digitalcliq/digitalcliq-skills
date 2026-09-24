# Sterling BMW: Momentum CRM Runbook

status: SCOUTED 2026-07-21 (verified live pull: MTD totals 449 leads / 53 appts / 33 shows / 24 DMS sales)

- Entry URL: `http://sterlingbmwmom.udccrm.com/acrm/servlet/login`, with a live session this redirects straight to `general?cmd=home`. If a login FORM renders instead, return `{"available": false, "login_required": true, "note": "Momentum session expired"}`. NEVER touch the form.
- Session notes: Momentum (UDC) logs out aggressively. Expect a login wall often. The emailed "Momentum Executive New Car Snapshot" (see `../sources.md`) covers Sterling when the session is dead, note that in the merge so the store isn't double-reported.
- Load these tools via ToolSearch in ONE call: `tabs_context_mcp`, `tabs_create_mcp`, `navigate`, `computer`, `javascript_tool` (javascript_tool is REQUIRED, the report lives in an iframe that `get_page_text` and `read_page` cannot see).

## Target report

Reports menu → E-Commerce Reports → **E-Commerce Statistics Report**. Options dialog loads inside iframe `id="ifrm_reportIframe"` (`/acrm/servlet/report?cmd=ecommercestatisticsreport`). The Momentum home page ALSO shows a quick "Sales Statistics" MTD panel (appointments, prospects, calls) worth reading as bonus KPIs via screenshot.

## Click-path (deterministic, verified 2026-07-21)

1. Navigate to entry URL. Wait 5s. Screenshot to confirm home ("Drew Moon : Sterling BMW" in top-right = logged in).
2. Click **Reports** in the top menu bar (~x=848,y=44 at 1514px width), then click **E-Commerce Reports** (submenu opens on click/hover), then **E-Commerce Statistics Report**. Wait 5s for the options dialog.
3. Set **Report Type = HTML**: click the Report Type select (mid-dialog, ~(804,527)), then `type` "HTML". Native select, options never appear in screenshots; verify with a `zoom` on the dialog.
4. Set **Date Range**: click the Date Range select (~(804,551)), `type` the option name. Options include: Today, Yesterday, Month to Date, Week to Date, Last 30 Days, Last Month, Custom. Daily run does TWO pulls: first "Yesterday", then "Month to Date". From/To fields auto-fill.
5. **DO NOT click Run Report and DO NOT call `do_submit()`**: the form targets a popup window (`reportViewWindow`) that never joins the MCP tab group (popup-blocked → silently nothing happens). Instead, submit into the iframe itself via `javascript_tool`:

```js
const f = document.getElementById('ifrm_reportIframe').contentDocument.forms[0];
f.elements['action'].value = 'search';
f.target = '_self';
HTMLFormElement.prototype.submit.call(f);
```

6. Wait 8-10s, then read the rendered report:

```js
document.getElementById('ifrm_reportIframe').contentDocument.body.innerText
```

Slice in ~1200-char chunks if needed (report is ~5k chars). To run a second date range, re-open the dialog via the Reports menu (the iframe now holds the report, not the form) and repeat.

## Report format

Tab-separated rows per lead source ("First Provider Leads"):
`Source | Leads # | Contact Made # | % | Appointments # | % | Appt Shows # | % | Sales (DMS) # | %`
Final row: `Totals` (e.g. 2026-07-21 MTD: 449 / 333 / 74.2% / 53 / 11.8% / 33 / 62.3% / 24 / 5.3%). Header carries date range + "Generated" stamp, echo it into `period`.

## Quirks

- Report options form carries a per-render `ePage` session token, bare-URL re-navigation does NOT work; always drive the form.
- Defaults are correct: Employee Groups All, Showed Appts "Only verified", Sales Type "DMS Sales", all Lead Types checked. Leave them.
- Report Type also offers CSV/XLS but those download; HTML inline is the reliable read.
- This report is e-commerce/first-provider only (~449 MTD), the emailed Executive Snapshot counts ALL prospects incl. showroom (~623 MTD). Don't mix the two in one KPI row; label the source.

## Extraction contract

Return the dealer object in the shared CRM schema: `{available, period, kpis[], sources[], insights[], login_required?}`.
