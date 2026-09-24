# Excel Report Template

## General Rules

1. **Use Excel formulas** for ALL calculations — never hardcode Python-computed values
2. **Recalculate** using `python /mnt/skills/public/xlsx/scripts/recalc.py <file> 30` after saving
3. **Fix all errors** before delivering — 0 errors required
4. **DigitalCLIQ branding** on every sheet (see SKILL.md Brand Guide)
5. Font: Titillium Web everywhere (fallback: Arial)

## Openpyxl Style Definitions

```python
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

# Brand colors
DC_BLUE = '405FAB'
DC_SKY = '6B9DD4'
DC_BLACK = '000000'
DC_WHITE = 'FFFFFF'
DC_GREY = '949592'
DC_LIGHT_BG = 'E8EEF7'
DC_ACCENT = '2D4A8A'
DC_GREEN = '4CAF50'
DC_LIGHT_GREEN = 'D5F5E6'
DC_RED = 'E53935'
DC_LIGHT_RED = 'FADBD8'
DC_ORANGE = 'F57C00'
DC_LIGHT_ORANGE = 'FFF3E0'
DC_YELLOW = 'FFF9C4'

# Standard styles
hdr_font = Font(name='Titillium Web', bold=True, color=DC_WHITE, size=10)
hdr_fill = PatternFill('solid', fgColor=DC_BLUE)
data_font = Font(name='Titillium Web', size=10)
bold_font = Font(name='Titillium Web', bold=True, size=10)
title_font = Font(name='Titillium Web', bold=True, size=16, color=DC_BLUE)
alt_fill = PatternFill('solid', fgColor=DC_LIGHT_BG)
input_font = Font(name='Titillium Web', size=10, color='0000FF')
border = Border(
    left=Side(style='thin', color=DC_GREY),
    right=Side(style='thin', color=DC_GREY),
    top=Side(style='thin', color=DC_GREY),
    bottom=Side(style='thin', color=DC_GREY)
)
input_border = Border(
    left=Side(style='medium', color=DC_BLUE),
    right=Side(style='medium', color=DC_BLUE),
    top=Side(style='medium', color=DC_BLUE),
    bottom=Side(style='medium', color=DC_BLUE)
)
ctr = Alignment(horizontal='center', vertical='center')

# Number formats
currency = '$#,##0'
pct = '0.0%'
num = '#,##0'
```

## Sheet Specifications

### Tab 1: Executive Summary
- **Tab color**: DC_BLUE
- **Row 1-3**: Logo (if possible) + title + subtitle + "Prepared by DigitalCLIQ"
- **KPI Table**: Metric | Year 1 Actual | Year 2 Actual | Baseline Forecast | +25% Scenario | -15% Scenario
- **Metrics**: Total Spend, Total Leads, Total Sales, Close Rate, CPL, CPS, YoY Change
- **Key Finding**: Spend-to-lead correlation callout in red if not significant
- **Recommendation**: Brief reallocation recommendation in blue

### Tab 2: Monthly History
- **Tab color**: DC_SKY
- **Columns**: Month, Total Spend, Total Leads, Total Sales, Close Rate, Cost/Lead, Cost/Sale, Unique Leads, Duplicates, Dup Rate
- **Subtotal rows** for each year: styled with DC_ACCENT background, white text
- Close Rate, CPL, CPS must be FORMULAS (e.g., `=D{row}/C{row}`)
- Alternating row shading with DC_LIGHT_BG

### Tab 3: Vendor ROI
- **Tab color**: DC_GREEN
- **Title row**: "Vendor ROI Analysis — [Year] Spend vs Lead Performance"
- **Note row**: Call out any excluded artifacts (e.g., credit apps)
- **Columns**: Tier, Vendor, Annual Spend, Leads, Sales, Close Rate, CPL, CPS, Lead Share, Rating
- **Rating column**: Green fill for TIER 1, Red fill for TIER 4, Orange for UNMEASURED
- Sort by CPS ascending (best first)

### Tab 4: Forecast
- **Tab color**: DC_SKY
- **Title**: "[Year] Lead Forecast — 3-Model Ensemble"
- **Subtitle**: Model weights and data window description
- **Columns**: Month, Year 1 Actual, Year 2 Actual, Baseline Forecast, Lower (80%), Upper (80%), NADA Index, +25% Budget, -15% Budget
- **Total row**: SUM formulas with DC_BLUE styling
- **YoY row**: Percentage change vs most recent actual year

### Tab 5: Scenario Planner
- **Tab color**: DC_RED
- **INPUT SECTION** (rows 4-9):
  - Labels: Baseline Spend, Baseline Leads, Baseline Sales, Lead Elasticity, Sales Elasticity
  - Values in BLUE font with YELLOW background and BLUE border (editable)
- **SCENARIO SECTION** (rows 12+):
  - Columns: Metric | +25% | Status Quo | -15% | Custom
  - Row 14: Budget Adjustment % (Custom cell is editable: blue font, yellow bg)
  - ALL calculations use formulas referencing the input cells
  - Metrics: Total Budget, Budget Change, Projected Leads, Lead Change, Projected Sales, CPL, CPS
- **Warning note**: Explain low elasticity and recommend reallocation over spend increases

### Tab 6: Budget Detail
- **Tab color**: DC_GREY
- **Columns**: Category, Vendor, Jan, Feb, ... Dec, Annual Total
- Annual Total = SUM formula across months
- Preserve monthly granularity from budget file

### Tab 7: All Providers
- **Tab color**: DC_ACCENT
- **Columns**: Lead Provider, Year 1 Leads, Year 2 Leads, Total Leads, Total Sales, Close Rate, YoY Change
- Sort by Total Leads descending
- Top 100 providers (or all if fewer)
- Close Rate and YoY Change as formulas

### Tab 8: Reallocation Strategy
- **Tab color**: DC_ORANGE
- **Section 1: Current Performance** — Adjusted vendor ROI table with tier colors
- **Section 2: Proposed Reallocation** — Action (CUT/INVEST/HOLD), Current, Proposed, Change, Rationale
  - CUT rows: red fill on spend cells
  - INVEST rows: green fill on spend cells
  - HOLD rows: grey text
  - Total row verifying budget neutrality
- **Section 3: Projected Impact** — Current vs After metrics with formulas
- **Section 4: Bottom Line** — Executive summary with key numbers
- **Methodology notes** at bottom explaining assumptions and exclusions

## Common Formula Patterns

### Close Rate
```python
ws.cell(row=r, column=5, value=f'=D{r}/C{r}').number_format = '0.0%'
```

### Cost per Lead
```python
ws.cell(row=r, column=6, value=f'=B{r}/C{r}').number_format = '$#,##0.00'
```

### Cost per Sale (with zero protection)
```python
ws.cell(row=r, column=7, value=f'=IF(D{r}>0,B{r}/D{r},"-")').number_format = '$#,##0'
```

### Year-over-Year Change
```python
ws.cell(row=r, column=7, value=f'=IF(B{r}>0,(C{r}/B{r})-1,"-")').number_format = '+0.0%;-0.0%'
```

### Scenario Planner Lead Projection
```python
# References input cells: B5=spend, B6=leads, B8=elasticity, B14=adjustment%
ws.cell(row=17, column=2, value='=ROUND($B$6*(1+B14*$B$8),0)')
```

## Pre-Delivery Checklist

1. [ ] All formulas use cell references, not hardcoded values
2. [ ] Recalc returns 0 errors
3. [ ] Every tab has DigitalCLIQ branding (colors, fonts)
4. [ ] Scenario Planner blue input cells are editable
5. [ ] Credit app / artifact exclusions are noted
6. [ ] Total rows use SUM formulas
7. [ ] Division formulas have zero-protection (IF or IFERROR)
8. [ ] Column widths are set for readability
9. [ ] Tab colors match the spec
10. [ ] "Prepared by DigitalCLIQ" appears on Executive Summary
