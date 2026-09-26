# Data Ingestion Reference

## CRM Lead Reports

### Expected Columns
```
lead_provider, total_leads, total_invalid_leads, total_first_provider, total_dups, total_sales
```
Column names differ by CRM (VinSolutions, Momentum, Focus, Tekion, DealerSocket). Map each report's columns to these names once, show Drew the mapping, and record the CRM, the report name and the lead column in the facts file `definitions` block.

**Good Leads** = `total_leads - total_dups - total_invalid_leads`. Close rate is always Sales / Good Leads, the same definition score-leads uses, so one store never gets two close rates.

### Which month is each file?

Read the period start and end dates from each report's header (most CRM exports print "Date Range", "From / To" or a period line above the table). If a file has no period in its header, ask Drew for it. Never infer a month from campaign names inside provider names, and never from file names or upload order.

Validation after mapping:
- one file per month, no duplicate months, no gaps in the window;
- every file covers exactly one calendar month (a partial month is labelled partial and kept out of the forecast training data);
- the data window (first and last month) goes into `definitions.data_window` and prints on page one.

**Always confirm the month mapping with Drew before modeling.**

## Budget File Parsing

### Structure
Drew's budget sheets (SBMW, NCBMW) use a category layout:
- Row 0: headers (Categories, Jan ... Dec, Total, Average)
- Category header rows: column 0 has the category name, column 2 has "Monthly totals:"
- Vendor rows: column 0 empty, column 2 has the vendor name
- Dollar values as `$X,XXX` strings
- Notes column (last): may explain vendor changes; read it

### Which categories count
Keep marketing categories only, for example:
- **3rd Party Leads**: CarGurus, TrueCar, Costco, Edmunds, AutoTrader, CARFAX, Cars.com, LotLinx
- **Digital Media**: PPC, social, conquest email, factory programs
- **Traditional Media**: Automotive Mastermind, Data Clover, radio, TV
- **Misc**: Gubagoo, call tracking, website hosting, mailers
- **Events**: sponsorships

Ignore any category that is not marketing. Show Drew the categories kept and dropped.

### Dollar Parsing
```python
def parse_dollar(s):
    if pd.isna(s) or str(s).strip() in ['', '$0', '?']:
        return 0
    return int(str(s).replace('$', '').replace(',', '').strip())
```

### OEM Co-op Reimbursement
Look for a co-op reimbursement row below the spend totals. This is OEM co-op reimbursement: note it, and set `coop.present` in the facts file. Analyze GROSS spend for ROI (dealers decide on gross). Label spend "(net)" only when a co-op row exists and the figure really is net of it.

## Vendor Name Mapping

Budget vendor names and CRM provider names never match exactly. Match on keywords, case-insensitive, in this order:

| Budget Vendor | CRM Provider Matches |
|---|---|
| Credit App (own row, checked first) | Any provider containing "credit app" or "credit application" |
| CarGurus | CarGurus, CarGurus Reengagement, CarGurus - Autolist, CarGurus - Digital Deal, CarGurus Pre-Qualified |
| TrueCar | Any provider containing "TrueCar" |
| Costco | Costco Auto Program |
| Edmunds | Edmunds, Edmunds CarCode |
| AutoTrader | Any provider containing "AutoTrader" |
| CARFAX | Any provider containing "CARFAX" or "CarFax" |
| Cars.com | Cars.Com, Cars.com Phone |
| Gubagoo (Virtual Retailing) | Gubagoo - Virtual Retailing |
| Gubagoo (Chat) | Gubagoo - Chat |
| Website platform | Any provider containing "Dealer Inspire" or "Dealer Website" (after the credit-app row has taken its sources) |
| LotLinx | No CRM match: VIN-level ads do not create CRM leads (UNMEASURED) |

The "Credit App" row is matched before the website so credit applications never inflate the website vendor. It carries a neutral label because it prints on the GM's copy. The operational-source checkpoint (`roi_methodology.md`) then asks Drew whether to keep or exclude it.

For other stores, build the mapping the same way from keyword matches between budget vendor names and CRM provider names.

### Vendor Matching Loop (MATCHED / POSSIBLE / UNMATCHED)

After the rollup, classify every budget line against the CRM sources before any CPL or CPS is calculated:

- **MATCHED**: high-confidence match (keyword hit, more than 80% lead-volume overlap). Proceed.
- **POSSIBLE**: low-confidence match (partial name, under 50% overlap, or several candidates). Ask Drew: "I matched [budget line] to [CRM source]. Confidence: low. Confirm?"
- **UNMATCHED**: no CRM source found. Ask Drew: "No CRM data found for [budget line]. Map it to an existing source, or flag it as UNMEASURED?"

Loop until every budget line is MATCHED or UNMEASURED. A POSSIBLE match Drew does not confirm becomes UNMEASURED.

## Filing

The finished workbook, its `.facts.json` and its `.forecast.json` sidecar are staged in `outputs/` and filed to `Projects/{CODE}/deliverables/` (Rule 18). Input files stay where Drew dropped them.
