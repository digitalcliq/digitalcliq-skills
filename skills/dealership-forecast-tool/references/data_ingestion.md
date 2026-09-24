# Data Ingestion Reference

## E-Commerce Lead CSV Parsing

### Expected Columns
```
lead_provider, total_leads, total_invalid_leads, total_first_provider, total_dups, total_sales
```

### Month Identification Strategy

Lead CSV files are NOT labeled by month. The file names are typically system-generated timestamps (e.g., `E-Commerce_Summary_2026_02_27_19_33.csv`). To determine which file corresponds to which month:

1. **Primary Method — Campaign Date Codes**: Many lead providers include date-coded campaign names. Look for patterns like:
   - `_MMDD` at the end of provider names (e.g., `Golf24_BMW Championship_0820` → August 20)
   - `Southern24_StPeteBoatShow_0118` → January 18
   - `Tennis24_BNP Paribas Open_0304` → March 4
   
2. **Secondary Method — File Order**: Files uploaded in sequence usually correspond to Jan→Dec. The timestamp suffixes (`__1_`, `__2_`, etc.) indicate upload order.

3. **Validation**: After mapping, verify:
   - 12 files per year
   - No duplicate months
   - Lead volumes roughly match expected seasonal patterns (March/April peaks, July trough for most dealers)

### Month Mapping Code Pattern
```python
# Build mapping by examining dated providers in each file
for f in files:
    df = pd.read_csv(f)
    dated_providers = [p for p in df['lead_provider'] 
                       if any(c.isdigit() for c in str(p)[-4:])]
    # Extract MMDD codes and assign month
```

### CRITICAL: Always confirm mapping with the user before proceeding.

## Budget CSV Parsing

### Structure
Budget files use a personal finance template with these characteristics:
- Row 0: Headers (Categories, Jan, Feb, ... Dec, Total, Average)
- Category header rows: Column 0 has category name, Column 2 has "Monthly totals:"
- Vendor rows: Column 0 is empty, Column 2 has vendor name
- Dollar values: Formatted as `$X,XXX` strings
- Notes column (last): May contain useful context about vendor changes

### Relevant Categories
Only these categories contain marketing spend:
- **3rd Party Leads**: CarGurus, TrueCar, Costco, Edmunds, AutoTrader, CARFAX, Cars.com, LotLinx, etc.
- **Digital Media**: PPC, Social media, Conquest emails, Factory programs
- **Traditional Media**: Automotive Mastermind, Data Clover, Radio, TV
- **Misc**: Gubagoo, Call tracking, Website hosting, Epsilon mailers
- **Events**: Sponsorships, golf tournaments, galas

All other categories (Everyday, Gifts, Health, Home, Insurance, Pets, Technology, Transportation, Travel, Utilities) are empty template rows — skip them.

### Dollar Parsing
```python
def parse_dollar(s):
    if pd.isna(s) or str(s).strip() in ['', '$0', '?']:
        return 0
    return int(str(s).replace('$', '').replace(',', '').strip())
```

### Co-Op Reimbursements
Look for a "Co Op Reimbursements" row after the spend totals. This is money BMW reimburses the dealer — note it but analyze GROSS spend for ROI calculations (dealers make spending decisions based on gross, not net).

## Vendor Name Mapping

Budget vendor names and lead provider names won't match exactly. Use this fuzzy mapping approach:

| Budget Vendor | Lead Provider Matches |
|---|---|
| CarGurus | CarGurus, CarGurus Reengagement, CarGurus - Autolist, CarGurus - Digital Deal, CarGurus Pre-Qualified |
| TrueCar | Any provider containing "TrueCar" |
| Costco | Costco Auto Program |
| Edmunds | Edmunds, Edmunds CarCode |
| AutoTrader | Any provider containing "AutoTrader" |
| CARFAX/CarFax | Any provider containing "CARFAX" or "CarFax" |
| Cars.com | Cars.Com, Cars.com Phone |
| Gubagoo (Virtual Retailing) | Gubagoo - Virtual Retailing |
| Gubagoo (Chat) | Gubagoo - Chat |
| DealerInspire/Website | Any provider containing "Dealer Inspire" or "Dealer Website" |
| LotLinx | NO lead provider match — VIN-specific ads don't generate CRM leads |

For any dealership, build the mapping dynamically by searching for keyword matches between budget vendor names and lead provider names.
