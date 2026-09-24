---
name: dealership-forecast-tool
description: "DigitalCLIQ's automotive dealership lead forecasting and budget optimization tool. Triggers whenever a user wants to: analyze dealership lead/CRM data, forecast future leads or sales, evaluate marketing ROI by vendor/provider, build budget reallocation strategies, or create marketing performance reports for car dealerships. Also trigger when the user mentions dealership analytics, lead provider analysis, cost-per-lead, cost-per-sale, marketing spend optimization, or automotive CRM reports. This skill handles the full pipeline: data ingestion, 3-model ensemble forecasting (Prophet + Holt-Winters + NADA seasonal), vendor ROI tiering, budget scenario planning, and branded Excel report generation. Use this even if the user just uploads dealership CSV files and asks for analysis."
---

# DigitalCLIQ Dealership Forecast Tool

A complete pipeline for ingesting dealership CRM lead data and marketing budgets, building forecasting models, and producing branded Excel reports with actionable reallocation strategies.

## When to Use This Skill

Use this skill when:
- User uploads dealership lead/CRM data (CSV files with lead providers, lead counts, sales)
- User asks for marketing ROI analysis for a dealership
- User wants lead or sales forecasting for a dealership
- User uploads marketing budget files and wants spend optimization
- User mentions "forecast", "leads", "providers", "cost per lead", "dealership" together
- User wants a branded report for a dealership client

## Required Inputs

The tool needs these files from the user. Always ask for what's missing before proceeding.

### 1. E-Commerce Lead Reports (CSV)
- Monthly CSV exports from the dealership's CRM/lead management system
- Expected columns: `lead_provider`, `total_leads`, `total_sales`, `total_first_provider`, `total_dups`, `total_invalid_leads`
- Need 12 files per year (one per month), ideally 24 months (2 years)
- Files are typically NOT labeled by month — use campaign date codes in provider names to identify months (e.g., `_0304` = March 4th → March file)

### 2. Marketing Budget (CSV)
- Spreadsheet export with vendor-level monthly spend
- Expected structure: Category rows with vendor sub-rows, columns for each month
- Dollar values formatted as `$X,XXX`
- Need budget for each year of lead data provided

### Key Data Mapping Challenge
The lead CSVs don't come labeled by month. Use this process to assign months:
1. Look for providers with campaign date codes (e.g., `Golf24_BMW Championship_0820` → August)
2. Sort files by filename timestamp order (they're typically uploaded chronologically)
3. Verify by checking lead volume patterns against known seasonality
4. Always confirm the mapping with the user before proceeding

## Pipeline Steps

Follow these steps IN ORDER. Do not skip steps.

### Step 1: Data Ingestion & Validation
```
Read references/data_ingestion.md for detailed parsing logic
```
- Parse all uploaded CSV files
- Map each file to a month using campaign date codes
- Combine into a unified dataset
- Parse budget files (handle `$X,XXX` format, category/subcategory structure)
- Validate: check for missing months, zero-lead months, column mismatches
- Print summary for user confirmation before proceeding

### Step 2: Exploratory Analysis
- Monthly lead/sales/close rate trends
- Provider concentration (Pareto analysis — how many providers = 80% of leads)
- Duplicate rate trends
- Year-over-year comparisons (if 2 years available)
- Spend-to-lead correlation (Pearson + elasticity)

### Step 3: Vendor ROI Analysis
```
Read references/roi_methodology.md for tiering logic and exclusion rules
```
- Map budget vendors to lead providers (names won't match exactly — use fuzzy matching)
- Calculate: Cost per Lead (CPL), Cost per Sale (CPS), Close Rate by vendor
- **CRITICAL**: Ask the user if any high-close-rate sources are operational artifacts (e.g., credit apps for showroom walk-ins). Exclude these from marketing ROI.
- Assign efficiency tiers:
  - TIER 1 (★★★ STAR): CPS < $500
  - TIER 2 (★★ GOOD): CPS $500–$999
  - TIER 3 (★ AVG): CPS $1,000–$1,499
  - TIER 4 (⚠ REVIEW): CPS ≥ $1,500

### Step 4: Forecasting
```
Read references/forecasting.md for model configuration details
```
Build a 3-model ensemble:
1. **Prophet** — yearly seasonality, multiplicative mode, conservative changepoints
2. **Holt-Winters** — additive trend, multiplicative seasonality, damped
3. **NADA Seasonal** — industry benchmark indices for luxury/import dealers

Ensemble weights depend on data available:
- 24+ months: Prophet 25%, Holt-Winters 40%, NADA 35%
- 12 months only: Prophet 15%, Holt-Winters 25%, NADA 60%

Generate forecasts for:
- Baseline (status quo spend)
- +25% budget scenario
- -15% budget scenario

### Step 5: Reallocation Strategy
- Identify underperformers (Tier 4) and unmeasured spend
- Propose specific dollar moves from underperformers to Tier 1/2
- Project impact using vendor-specific CPL and close rates
- Ensure proposal is BUDGET NEUTRAL (total spend unchanged)

### Step 6: Build Branded Excel Report
```
Read references/excel_template.md for exact sheet specs and formatting
```
Generate the workbook with these tabs:
1. Executive Summary
2. 24-Month History (or 12-Month if only 1 year)
3. Vendor ROI
4. Forecast
5. Scenario Planner (live formulas)
6. Budget Detail
7. All Providers
8. Reallocation Strategy

Use DigitalCLIQ branding (see Brand Guide below). Use Excel FORMULAS, not hardcoded Python calculations.

After saving, ALWAYS run the recalc script:
```bash
python /mnt/skills/public/xlsx/scripts/recalc.py <output_file> 30
```
Fix any errors and recalc again until status is "success" with 0 errors.

## DigitalCLIQ Brand Guide

### Colors
| Name | Hex | RGB | Usage |
|------|-----|-----|-------|
| Digital Blue | #405FAB | 64, 95, 171 | Primary headers, titles, tab colors |
| Sky Blue | #6B9DD4 | 107, 157, 212 | Secondary headers, accents |
| Rich Black | #000000 | 0, 0, 0 | Body text |
| Privilege White | #FFFFFF | 255, 255, 255 | Backgrounds, header text |
| Warm Grey | #949592 | 148, 149, 146 | Borders, subtle text, notes |

### Derived Colors for Excel
| Usage | Hex |
|-------|-----|
| Alternating row fill | #E8EEF7 (light blue tint) |
| Dark accent (subtotals) | #2D4A8A |
| Green (positive/Tier 1) | #4CAF50 / light: #D5F5E6 |
| Red (negative/Tier 4) | #E53935 / light: #FADBD8 |
| Orange (warnings) | #F57C00 / light: #FFF3E0 |
| Yellow (input cells) | #FFF9C4 |

### Fonts
- Primary: Titillium Web (all Excel content)
- Fallback: Arial
- Serif (if needed): Roboto Slab

### Formatting Rules
- Company name: "DigitalCLIQ" (one word, CLIQ capitalized)
- Tagline: "Digital Strategy & Development"
- Include "Prepared by DigitalCLIQ" on Executive Summary
- All headers use Digital Blue (#405FAB) background with white text
- Input cells (user-editable) use blue font + yellow background + blue border
- Alternating row shading using #E8EEF7

### Logo
The DigitalCLIQ logo is available at: `assets/digitalcliq-logo.png`
Attempt to insert it on the Executive Summary tab. If image insertion fails, continue without it.

## Dependencies

Install before running:
```bash
pip install prophet statsmodels scikit-learn openpyxl pandas numpy scipy --break-system-packages
```

## Important Notes

- ALWAYS ask the user to confirm month-to-file mapping before building models
- ALWAYS ask about operational artifacts (credit apps, showroom walk-ins) before calculating ROI
- Use Excel formulas for all calculations in the workbook — never hardcode Python-computed values
- The Scenario Planner tab must have LIVE formulas so users can change inputs
- Run recalc and fix all errors before delivering
- If only 12 months of data, recommend the user provide a second year and explain why (seasonality detection, trend reliability)
- LotLinx and similar VIN-specific ad platforms typically have NO trackable leads in CRM — flag as UNMEASURED
- Co-Op reimbursements should be noted but don't affect the spend analysis (analyze gross spend)
