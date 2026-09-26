# Facts File Schema (forecast-facts/1)

Every figure the workbook will show goes into one dict, written to `outputs/<deliverable>.facts.json` before the workbook is built. `verify_workbook.py facts` checks it; `verify_workbook.py check --facts` checks the workbook against it and writes the `<deliverable>.forecast.json` sidecar from it; the deliverable-reviewer uses its `manifest` list.

Months are `YYYY-MM`. Money is gross dollars. Counts are integers. The example values are the synthetic "Test Motors" fixture from `tests/build_sample.py`, not a real store; never copy a CRM, report name or figure from here into a client's facts.

```json
{
  "schema": "forecast-facts/1",
  "client": {"code": "TEST", "name": "Test Motors"},
  "definitions": {
    "crm": "VinSolutions",
    "report_name": "Lead Source ROI",
    "lead_definition_column": "total_leads",
    "close_rate_basis": "Sales / Good Leads (total_leads - total_dups - total_invalid_leads)",
    "excluded_sources": ["Dealer Website Credit Application"],
    "data_window": {"start": "2024-01", "end": "2025-12"}
  },
  "history": [
    {"month": "2024-01", "spend": 60777, "leads": 688, "sales": 43, "dups": 55, "invalid": 13, "unique": 633}
  ],
  "history_totals": {
    "2024": {"spend": 707968, "leads": 9462, "sales": 591, "dups": 751, "invalid": 182}
  },
  "subtotals": [
    {"label": "3rd Party Leads", "total": {"spend": 0}, "parts": [{"spend": 0}]}
  ],
  "sources": [
    {"name": "Dealer Website Credit Application", "vendor": "Credit App", "leads": 240, "sales": 66,
     "dups": 0, "invalid": 0, "included": false, "confirmed_by_drew": "exclude, 2026-09-26"}
  ],
  "vendors": [
    {"vendor": "Gubagoo Virtual Retailing", "spend": 13200, "leads": 1500, "sales": 45,
     "tier": "TIER 1", "rating": "STAR", "note": "", "sources": ["Gubagoo - Virtual Retailing"]}
  ],
  "models": {
    "ran": ["prophet", "holt_winters", "seasonal_prior"],
    "weights": {"prophet": 0.25, "holt_winters": 0.40, "seasonal_prior": 0.35},
    "monthly": {"prophet": [], "holt_winters": [], "seasonal_prior": []},
    "versions": {"prophet": "1.1.5", "statsmodels": "0.14.2", "python": "3.12.3"},
    "training_window": {"start": "2024-01", "end": "2025-12"}
  },
  "forecast": {
    "months": ["2026-01", "2026-02"],
    "baseline": [714, 738],
    "low": [628, 649],
    "high": [800, 827],
    "interval_method": "fixed +/-12% planning range",
    "backtest": {"inside": 11, "of": 12, "half_width": 0.12}
  },
  "elasticity": {
    "leads": {"slope": -0.130, "r": -0.202, "p": 0.343, "se": 0.134, "n": 24, "ci95": [-0.407, 0.148]},
    "label": "Estimated, not statistically significant"
  },
  "baseline": {"spend": 715500, "leads": 9593, "sales": 599, "close_rate_year": "2025"},
  "scenarios": {
    "executive_summary": {"baseline": {"leads": 9593, "sales": 599},
                          "+25%": {"leads": 9281, "sales": 579}, "-15%": {"leads": 9780, "sales": 610}},
    "scenario_planner":  {"baseline": {"leads": 9593, "sales": 599},
                          "+25%": {"leads": 9281, "sales": 579}, "-15%": {"leads": 9780, "sales": 610}}
  },
  "ads": {"monthly": [{"month": "2025-01", "clicks": 1200, "impressions": 48000, "cost": 5400}],
          "ctr": 0.025, "cpc": 4.5},
  "coop": {"present": false, "amount": 0},
  "labels": {"forecast_title": "2026 Lead Forecast: 3-Model Ensemble",
             "forecast_subtitle": "Prophet 25% + Holt-Winters 40% + Seasonal prior (DigitalCLIQ estimate) 35%",
             "net_used": false},
  "confirmations": {"sanity": "Drew: yes, the decline is expected (2026-09-26)", "divergence": ""},
  "manifest": [
    {"value": "9,593", "label": "Executive Summary, 2026 Baseline leads", "source": "ensemble forecast, facts.forecast.baseline"}
  ]
}
```

## What each check reads

| Check | Keys |
|---|---|
| Keys the sidecar saves are present | `client.code`, `client.name`, `definitions` (crm, report_name, lead_definition_column, close_rate_basis, excluded_sources, data_window start and end), `forecast.months` (one `YYYY-MM` per baseline month) |
| Subtotals equal the sum of their rows | `history`, `history_totals`, `subtotals` |
| Tier and Rating follow the rules; rows in cost-per-sale order | `vendors` (spend, leads, sales, tier, rating), in workbook order |
| Excluded sources never in included rows | `definitions.excluded_sources`, `sources[].included`, `vendors[].sources` |
| Operational-looking source over 20% close is confirmed or excluded | `sources[]` (name, leads, dups, invalid, sales, included, confirmed_by_drew) |
| CTR and CPC are pooled | `ads.monthly`, `ads.ctr`, `ads.cpc` (only when ads data is used) |
| '(net)' only with a co-op row | `labels.net_used`, `coop.present` |
| Models, weights, ensemble and title agree | `models`, `forecast.baseline`, `labels.forecast_title` |
| Planning range matches its stated method | `forecast.low`, `forecast.high`, `forecast.interval_method` |
| Elasticity and its label match the history | `elasticity`, `history` |
| One baseline; sales = leads x baseline sales per lead | `scenarios`, `baseline` |
| Drew confirmed the model audit | `confirmations.sanity`, `confirmations.divergence` |
| Reviewer manifest present | `manifest` |
| Workbook check (`check --facts`): each History `{YEAR} TOTAL` row equals its year | `history_totals` (spend, leads, sales, dups, invalid, unique where the tab has the column) |
| Workbook check (`check --facts`): the Budget Detail TOTAL equals that year's spend | `history_totals[year].spend` (year from the Budget Detail tab name) |

## The sidecar

`<deliverable>.forecast.json` is written only when the workbook check passes. It keeps: client code and name, CRM, report name, lead-definition column, close-rate basis, excluded sources, data window, forecast months with baseline, low and high, the interval method, elasticity slope, p, n and label, and the models that ran with their weights. It is filed with the workbook so a later scorecard or monthly report can be reconciled against the forecast's lead definition.
