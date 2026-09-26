# Excel Report Template

Built to `Resources/design-system/Design-System.md` (Excel section). Where this file and the design system disagree, the design system wins.

## General Rules

1. **Excel formulas for every derived figure.** Model outputs (monthly baselines, per-vendor spend, lead and sale counts) are the only numbers typed in; every total, ratio, tier, rating and scenario is a formula.
2. **TOTAL rows are `=SUM()` over their detail rows**, never typed numbers. Label them `TOTAL` or `{YEAR} TOTAL` in capitals. A grand total under the year TOTAL rows adds those TOTAL rows (`=B17+B30`), never a range that includes them. A non-additive column (seasonal prior, rates, shares) leaves its TOTAL cell blank or uses a ratio of the TOTAL cells.
3. **Executive Summary KPIs reference** the History TOTAL rows and the Scenario Planner, never literals.
4. **One baseline.** Scenario Planner Baseline Leads = the Forecast tab's baseline TOTAL. Executive Summary scenario columns and the Forecast tab's +25% / -15% columns read the Scenario Planner inputs.
5. **Recalc** with the installed xlsx skill's `scripts/recalc.py`, run from that skill's `scripts/` folder (the preflight prints the command). At most 3 attempts; then stop and report. 0 errors required.
6. **Numbers gate**: `verify_workbook.py check` must pass before post_flight.
7. **No em dashes** anywhere. Titles use ": ".
8. **Never** XLOOKUP, XMATCH, SORT, FILTER, UNIQUE or SEQUENCE (LibreOffice cannot evaluate them); sort and filter in Python.

## Openpyxl Style Definitions

```python
import os
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.styles.differential import DifferentialStyle
from openpyxl.formatting.rule import Rule
from openpyxl.drawing.image import Image as XLImage

# Palette: Design-System token table only
DIGITAL_BLUE = '405FAB'
SKY_BLUE     = '6B9DD4'
WARM_GREY    = '949592'
TILE_BLUE    = '2E4780'
CALLOUT_TINT = 'EDF2F9'   # alternating rows, callouts, input cells
CARD_WHITE   = 'FBFBFD'
BORDER_BLUE  = 'D8E1F0'
WHITE        = 'FFFFFF'
RICH_BLACK   = '000000'

H = 'Dosis'        # structure: titles, headers, labels, stats
B = 'Roboto Slab'  # reading: body cells, notes

title_font   = Font(name=H, bold=True, size=14, color=WHITE)     # masthead title
date_font    = Font(name=H, size=10, color=WHITE)
hdr_font     = Font(name=H, bold=True, size=10, color=WHITE)     # table header
hdr_fill     = PatternFill('solid', fgColor=DIGITAL_BLUE)
band_fill    = PatternFill('solid', fgColor=DIGITAL_BLUE)
total_fill   = PatternFill('solid', fgColor=TILE_BLUE)
total_font   = Font(name=H, bold=True, size=10, color=WHITE)
label_font   = Font(name=H, bold=True, size=10, color=RICH_BLACK)
body_font    = Font(name=B, size=10, color=RICH_BLACK)
note_font    = Font(name=B, italic=True, size=9, color=WARM_GREY)
stat_font    = Font(name=H, bold=True, size=16, color=SKY_BLUE)  # large KPI numbers
alt_fill     = PatternFill('solid', fgColor=CALLOUT_TINT)
callout_fill = PatternFill('solid', fgColor=CALLOUT_TINT)
input_font   = Font(name=B, bold=True, size=10, color=DIGITAL_BLUE)
input_fill   = PatternFill('solid', fgColor=CALLOUT_TINT)
thin   = Side(style='thin', color=BORDER_BLUE)
border = Border(left=thin, right=thin, top=thin, bottom=thin)
input_border = Border(*[Side(style='medium', color=DIGITAL_BLUE)] * 4)
ctr = Alignment(horizontal='center', vertical='center', wrap_text=True)

currency = '$#,##0'
currency2 = '$#,##0.00'
pct = '0.0%'
num = '#,##0'
signed_pct = '+0.0%;-0.0%'
```

### Masthead (every tab)

Rows 1-2: Digital Blue band across the used columns, the WHITE logo anchored at A1 (about 0.35in tall), the sheet title in white Dosis 14 bold, the report date on the right. The logo comes from the vault; a missing file stops the build.

```python
LOGO = os.path.join(VAULT, 'Resources', 'brand-assets', 'digital-cliq-logo-solid-1000px-wide.png')
if not os.path.isfile(LOGO):
    raise SystemExit('STOP: white logo not found at ' + LOGO)   # the build stops here

def masthead(ws, title, ncols, report_date):
    for r in (1, 2):
        ws.row_dimensions[r].height = 22
        for c in range(1, ncols + 1):
            ws.cell(row=r, column=c).fill = band_fill
    img = XLImage(LOGO)
    img.height = 34
    img.width = int(34 * 500 / 154)        # keep the mark's aspect ratio
    ws.add_image(img, 'A1')
    ws.cell(row=1, column=3, value=title).font = title_font
    ws.cell(row=1, column=ncols, value=report_date).font = date_font
    ws.cell(row=1, column=ncols).alignment = Alignment(horizontal='right')
```
Row 3 is the note or subtitle row, row 4 the table header (frozen: `ws.freeze_panes = 'A5'`), data from row 5. Column widths are set to content; no `#####`.

### Tier treatment (conditional formatting, palette only)

```python
def tier_rules(ws, rng, tier_col, first_row):
    ref = '${}{}'.format(tier_col, first_row)
    styles = [
        ('"TIER 1"', PatternFill('solid', bgColor=SKY_BLUE), Font(color=WHITE, bold=True)),
        ('"TIER 2"', PatternFill('solid', bgColor=CALLOUT_TINT), Font(color=DIGITAL_BLUE, bold=True)),
        ('"TIER 4"', PatternFill('solid', bgColor=WARM_GREY), Font(color=WHITE, bold=True)),
    ]
    for val, fill, font in styles:
        rule = Rule(type='expression', dxf=DifferentialStyle(fill=fill, font=font))
        rule.formula = ['{}={}'.format(ref, val)]
        ws.conditional_formatting.add(rng, rule)
    muted = Rule(type='expression', dxf=DifferentialStyle(font=Font(color=WARM_GREY, italic=True)))
    muted.formula = ['OR({0}="UNMEASURED",{0}="NO SALES YET",{0}="NO SPEND")'.format(ref)]
    ws.conditional_formatting.add(rng, muted)
```
TIER 3 keeps the plain body style. The text label carries the meaning; the treatment only supports it.

## Sheet Specifications

### Tab 1: Executive Summary (page one)
- **Tab color**: Digital Blue
- **Masthead** title: "{Store}: Lead Forecast and Budget Scenarios"
- **Row 4-6**: subtitle ("{n}-Month Analysis ({Y1} to {Y2}) | {FY} Forecast | Budget Scenarios"), "Prepared by DigitalCLIQ | Digital Strategy & Development"
- **Row 7**: `Lead definition: <report> <column>; excludes <sources>; data <start> to <end>.` (from the facts `definitions` block, word for word)
- **KPI table** (header row 9): Metric | {Y1} Actual | {Y2} Actual | {FY} Baseline | {FY} +25% Budget | {FY} -15% Budget
  - Total Marketing Spend: actual columns `='{History}'!B{TOTAL}`; scenario columns `='Scenario Planner'!C15 / B15 / D15`
  - Total Leads: actual columns reference the History TOTAL row; scenario columns `='Scenario Planner'!C17 / B17 / D17`
  - Total Sales: actual columns reference the History TOTAL row; scenario columns `='Scenario Planner'!C19 / B19 / D19`
  - Close Rate (Sales / Good Leads): actual columns reference the History TOTAL close rate; scenario columns show the held rate `=$C$13` (label the row "Close Rate (forecast: held at {Y2} level)")
  - Cost per Lead `=IF(B11>0,B10/B11,"-")`, Cost per Sale `=IF(B12>0,B10/B12,"-")`
  - YoY Lead Change: `=C11/B11-1`, `=D11/C11-1`, `=E11/C11-1`, `=F11/C11-1`
  - Spend is gross. Add "(net)" to a label only when a co-op row exists and the figure is net of it.
- **Key finding** (callout: Callout Tint fill, Dosis label, Roboto Slab text): the elasticity statement with its label and statistics, e.g. "Spend elasticity 0.060 (Estimated, not statistically significant; p = 0.64, n = 24): budget changes show no reliable effect on lead volume."
- **Recommendation**: one or two lines on the reallocation.
- **Methodology line**: "Forecast: {models that ran}. Planning range, not a statistical interval. Tier cut-offs are a DigitalCLIQ planning assumption. Seasonal prior is a DigitalCLIQ estimate."

### Tab 2: Monthly History ("24-Month History" or "12-Month History")
- **Tab color**: Sky Blue
- **Columns** (header row 4): Month | Total Spend | Total Leads | Duplicates | Invalid | Good Leads | Total Sales | Close Rate | Cost/Lead | Cost/Sale | Dup Rate
- Good Leads `=C{r}-D{r}-E{r}`; Close Rate `=IF(F{r}>0,G{r}/F{r},"-")`; Cost/Lead `=IF(C{r}>0,B{r}/C{r},"-")`; Cost/Sale `=IF(G{r}>0,B{r}/G{r},"-")`; Dup Rate `=IF(C{r}>0,D{r}/C{r},"-")`. Every ratio reads its own row only.
- **{YEAR} TOTAL row** after each year: `=SUM()` of that year's rows for Spend, Leads, Duplicates, Invalid and Sales; Good Leads `=C{t}-D{t}-E{t}`; ratios from the TOTAL cells. Tile Blue fill, white Dosis.
- Alternating White / Callout Tint rows.

### Tab 3: Vendor ROI
- **Tab color**: Sky Blue
- **Masthead** title: "Vendor ROI Analysis: {Year} Spend vs Lead Performance"
- **Row 3 note**: names every excluded source ("Excludes: Credit App (showroom credit applications), confirmed with Drew {date}.") and "Tier cut-offs are a DigitalCLIQ planning assumption."
- **Columns** (header row 4): Tier | Vendor | Annual Spend | Leads | Good Leads | Sales | Close Rate | Cost/Lead | Cost/Sale | Lead Share | Rating | Note
- Rows sorted by Cost/Sale ascending, rows without one last (order from `verify_workbook.py tiers`).
- Tier, Rating and Note are formulas (row r, data rows first..last):
```python
tier = ('=IF(AND(C{r}=0,COUNTIF($C${f}:$C${l},">0")>0),"NO SPEND",IF(C{r}=0,"",'
        'IF(D{r}=0,"UNMEASURED",IF(F{r}=0,IF(C{r}>=1500,"TIER 4","NO SALES YET"),'
        'IF(NOT(ISNUMBER(I{r})),"UNMEASURED",IF(I{r}<500,"TIER 1",IF(I{r}<1000,"TIER 2",'
        'IF(I{r}<1500,"TIER 3","TIER 4"))))))))')
rating = '=IF(A{r}="TIER 1","STAR",IF(A{r}="TIER 2","GOOD",IF(A{r}="TIER 3","AVG",IF(A{r}="TIER 4","REVIEW",A{r}))))'
note = ('=IF(AND(C{r}>0,D{r}=0),"No CRM leads",'
        'IF(AND(C{r}>=1500,D{r}>0,F{r}=0),"0 sales on "&TEXT(C{r},"$#,##0"),""))')
cps = '=IF(AND(C{r}>0,F{r}>0),C{r}/F{r},"-")'     # "-" for no sales and for NO SPEND rows
```
  A blank or "-" Cost/Sale never falls through to TIER 1: zero sales and non-numbers are caught before the cut-offs.
- Tier treatment via `tier_rules` on the Tier and Rating columns.

### Tab 4: Forecast ("{FY} Forecast")
- **Tab color**: Sky Blue
- **Masthead** title: "{FY} Lead Forecast: 3-Model Ensemble" only when all three models ran; otherwise name what ran ("2-Model Blend (Holt-Winters + Seasonal prior)").
- **Row 3 subtitle**: the models that ran with their weights and the data window, e.g. "Prophet 25% + Holt-Winters 40% + Seasonal prior (DigitalCLIQ estimate) 35% | 24 months training data (Jan 2024 to Dec 2025)". No confidence-interval wording and no NADA label.
- **Columns** (header row 4): Month | {Y1} Actual | {Y2} Actual | Baseline Forecast | Planning Low (-12%) | Planning High (+12%) | Seasonal prior (DigitalCLIQ estimate) | +25% Budget | -15% Budget
- Planning Low `=ROUND(D{r}*0.88,0)`, High `=ROUND(D{r}*1.12,0)`; +25% `=ROUND(D{r}*(1+'Scenario Planner'!$B$14*'Scenario Planner'!$B$9),0)`; -15% the same with `$D$14`.
- **TOTAL row**: `=SUM()` for the actual, baseline, planning and scenario columns; the seasonal prior column's TOTAL stays blank. Digital Blue styling.
- **vs {Y2} row**: `=D{t}/C{t}-1` and the same for the scenario columns.
- **Note under the table**: "Planning range, not a statistical interval." When the optional backtest ran: "{X} of the last 12 months fell inside."

### Tab 5: Scenario Planner
- **Tab color**: Digital Blue
- **Inputs** (rows 5-9), editable cells in Digital Blue bold on Callout Tint with a medium Digital Blue border:
  - B5 Baseline Spend ({Y2} actual) `='{History}'!B{TOTAL Y2}`
  - B6 Baseline Leads ({FY} forecast) `='{Forecast}'!D{TOTAL}`
  - B7 Baseline Sales `=ROUND(B6*B8,0)`
  - B8 Baseline sales per lead ({Y2} actual; assumed: close rate held at {Y2} level) `='{History}'!G{T}/'{History}'!C{T}`
  - B9 Lead Elasticity, label "Lead Elasticity (Estimated, not statistically significant; p = 0.64, n = 24)" or "(Estimated; p = ..., n = ...)"; value from `verify_workbook.py elasticity`
  - Row 10 note: "95% CI {low} to {high}. A range that crosses zero means the data cannot rule out no effect."
  - There is no sales elasticity input.
- **Scenarios** (header row 13): Metric | +25% Budget | Status Quo | -15% Budget | Custom
  - Row 14 Budget Adjustment %: 0.25 | 0 | -0.15 | (Custom editable)
  - Row 15 Total Budget `=$B$5*(1+B14)`; row 16 Budget Change `=B15-$B$5`
  - Row 17 Projected Leads `=ROUND($B$6*(1+B14*$B$9),0)`; row 18 Lead Change `=B17/$B$6-1`
  - Row 19 Projected Sales `=ROUND(B17*$B$8,0)`, labelled "Projected Sales (assumed: close rate held at {Y2} level)"
  - Row 20 Cost per Lead `=IF(B17>0,B15/B17,"-")`; row 21 Cost per Sale `=IF(B19>0,B15/B19,"-")`
- **Note**: explain what the elasticity label means for budget changes and point to the Reallocation tab.

### Tab 6: Budget Detail ("{Year} Budget Detail")
- **Tab color**: Warm Grey
- **Columns** (header row 4): Category | Vendor | Jan ... Dec | Annual Total
- Annual Total `=SUM(C{r}:N{r})`; a **TOTAL** row with `=SUM()` for every month and the annual column. The TOTAL equals the History spend TOTAL for that year.
- A co-op reimbursement row, when the budget has one, sits below the TOTAL row and is labelled as OEM co-op reimbursement.

### Tab 7: All Providers
- **Tab color**: Tile Blue
- **Columns** (header row 4): Lead Provider | {Y1} Leads | {Y2} Leads | Total Leads | Good Leads | Total Sales | Close Rate | YoY Change | Status
- Sorted by Total Leads descending, top 100 (or all). Close Rate `=IF(E{r}>0,F{r}/E{r},"-")`, YoY `=IF(B{r}>0,C{r}/B{r}-1,"-")`. Status reads "Included" or "Excluded" so excluded sources stay visible here without entering the ROI math.

### Tab 8: Reallocation Strategy
- **Tab color**: Tile Blue
- **Section 1: Current performance**: the Vendor ROI rows with tier treatment.
- **Section 2: Proposed reallocation** (header row with exactly "Current" and "Proposed"): Action (CUT / INVEST / HOLD) | Vendor | Tier | Current | Proposed | Change | Rationale
  - CUT rows in the order `verify_workbook.py tiers` prints (paid lines with leads and 0 sales first); Warm Grey fill with white text on the spend cells
  - INVEST rows: Callout Tint fill, Digital Blue bold text on the spend cells
  - HOLD rows: Warm Grey text
  - Change `=E{r}-D{r}`; a **TOTAL** row with `=SUM()` for Current and Proposed, which must be equal (budget neutral)
- **Section 3: Projected impact**: current vs after, formulas from each vendor's CPL and close rate
- **Section 4: Bottom line**: the key numbers in two or three lines
- **Methodology notes**: exclusions, tier cut-offs (DigitalCLIQ planning assumption), projection method

## Common Formula Patterns

```python
ws.cell(row=r, column=8, value=f'=IF(F{r}>0,G{r}/F{r},"-")').number_format = pct          # close rate on Good Leads
ws.cell(row=r, column=9, value=f'=IF(C{r}>0,B{r}/C{r},"-")').number_format = currency2    # cost per lead
ws.cell(row=r, column=10, value=f'=IF(G{r}>0,B{r}/G{r},"-")').number_format = currency    # cost per sale
ws.cell(row=r, column=8, value=f'=IF(B{r}>0,C{r}/B{r}-1,"-")').number_format = signed_pct # YoY
ws.cell(row=t, column=2, value=f'=SUM(B{first}:B{last})').number_format = currency        # TOTAL row
```

## Pre-Delivery Checklist

1. [ ] Every derived cell is a formula; TOTAL rows are `=SUM()`; Executive Summary reads History and Scenario Planner
2. [ ] Recalc: 0 errors, within 3 attempts
3. [ ] `verify_workbook.py check --facts ... --write-sidecar` passed and wrote the `.forecast.json`
4. [ ] Every tab: Digital Blue masthead with the white logo; Dosis and Roboto Slab only; palette colors only
5. [ ] Page one carries the Lead definition line
6. [ ] Tier column present, Tier and Rating formulas, rows in cost-per-sale order
7. [ ] Excluded sources named on Vendor ROI and marked Excluded on All Providers
8. [ ] Planning range labelled as such; elasticity labelled Estimated with p and n; seasonal prior labelled DigitalCLIQ estimate
9. [ ] No em dashes; no "(net)" without a co-op row
10. [ ] Column widths fit; header rows frozen; "Prepared by DigitalCLIQ" on the Executive Summary
