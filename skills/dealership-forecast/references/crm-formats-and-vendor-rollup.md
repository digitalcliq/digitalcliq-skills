# CRM Formats & Vendor Rollup Reference

Read by the dealership-forecast skill. Detect the CRM from the file headers using the
Detection column below, then read ONLY that CRM's row plus the rollup sections.

## Contents

1. [CRM Format Comparison Table](#crm-format-comparison-table)
2. [Adding New CRMs (eLeads, etc.)](#adding-new-crms-eleads-etc)
3. [Vendor Rollup Rules](#vendor-rollup-rules) (matching loop, rollup mapping, artifact detection)

## CRM Format Comparison Table

The Python script auto-detects CRM format from column headers. Supported CRMs:

| CRM | Detection | Structure | Good Leads | Sales | Cost / Profit | Contact & Appointments | Number formats | Caveats |
|---|---|---|---|---|---|---|---|---|
| MomentumCRM | First column is `lead_provider` and has `total_leads` column | Flat, one row per source. Columns: `lead_provider`, `total_leads`, `total_invalid_leads`, `total_first_provider`, `total_dups`, `total_sales` | `total_leads - total_invalid_leads - total_dups` | `total_sales` | Not available | Not available | Plain integers | Sub-sources heavy: AutoTrader has 7+ variants, TrueCar has 18+ variants |
| VinSolutions | Has `Lead Source Group` column and `Sold from Leads` column | Flat, one row per source, 40 columns | `Good Leads` column directly | `Sold from Leads` (preferred over `Sold in Timeframe`) | Cost: `Total Cost` column (when dealer has entered it). Profit: `Total Gross`, `Avg Gross`, `Profit` columns | Contact funnel: `Internet Attempted Contact`, `Internet Actual Contact`. Appts: `Appts Set`, `Appts Scheduled`, `Appts Confirmed`, `Appts Shown` | `$1,539.26`; `($3,385.22)` for negatives; `27.42%` | Row 2 may be a totals row (blank source name): skip it |
| Tekion | Has `Source Type (Consolidated)` column | Flat with 3-level hierarchy: `Source Type`, `Lead Source Group`, `Source Name` | `Total Good Leads` column | `Sold In Time Period` (only metric available; note caveat in output) | Not available | Contact: `Internet/OEM Leads Engaged %` (percentage only, no count). Appts: `Appointments Scheduled %`, `Appointments Scheduled Shown %` (percentages only) | `17,438` with commas; `74.95 %` with space before % | Rollup: use `Lead Source Group` level for vendor ROI, `Source Name` for the All Providers detail tab. Row 2 may be a totals row: skip it |
| DealerSocket | Has `Source` and `MarketingChannel` columns | Cross-tab pivot: each row is a Source x MarketingChannel combination | `MarketingChannelNewProspects` (no good/bad split available) | `MarketingChannelSold` | `MarketingChannelTopGross`, `MarketingChannelFIGross`, `MarketingChannelTotalGross` | Not available | `$877475` (no commas in dollars); `$-8797` for negatives; `95%` | Rollup: aggregate all rows with same `MarketingChannel`; combine Internet + Phone Up + Fresh Up for the same vendor. Skip `====SYSTEM SOURCES====` marker rows. `Dealer Mgmt Sys` is always an artifact (95% close rate = DMS imports). Every row has `Total*` columns with the same grand total: ignore these |

## Adding New CRMs (eLeads, etc.)

When a new CRM format is encountered:
1. User provides a sample CSV
2. Update this reference file (`references/crm-formats-and-vendor-rollup.md`) with the detection fingerprint and column mapping
3. Add a new parser class in `dealership_forecast.py`
4. Test with the sample data

## Vendor Rollup Rules

All CRMs produce granular sub-source names that must be rolled up into parent vendors for ROI analysis.

### Vendor Matching Loop (MATCHED / POSSIBLE / UNMATCHED)

After vendor rollup, classify every budget line against CRM sources into one of three buckets before running ROI calculations:

- **MATCHED**: high-confidence match (keyword hit, >80% lead volume overlap). Proceed automatically.
- **POSSIBLE**: low-confidence match (partial name, <50% overlap, or multiple candidates). Surface to user: "I matched [budget line] to [CRM source]. Confidence: low. Confirm?"
- **UNMATCHED**: no CRM source found. Ask user: "No CRM data found for [budget line]. Map it to an existing source, or flag as UNMEASURED?"

Loop until every budget line is MATCHED or UNMEASURED before running CPL/CPS calculations. POSSIBLE items that the user declines to confirm become UNMEASURED.

---

### Rollup Mapping (case-insensitive keyword match)

| Keyword in source name | Rolls up to |
|---|---|
| `autotrader`, `auto trader` | AutoTrader |
| `cargurus`, `car gurus` | CarGurus |
| `cars.com`, `cars.com phone` | Cars.com |
| `carfax`, `car fax` | CARFAX |
| `truecar` | TrueCar |
| `edmunds` | Edmunds |
| `costco` | Costco |
| `gubagoo`, `gobagoo`, `carnow` | Chat/Digital Retailing |
| `dealer inspire`, `dealer website`, `dealer contact`, `dealerwebsite`, `e-pricer`, `epricer` | Dealer Website |
| `kbb`, `kelley blue book` | KBB |
| `capital one`, `chase auto` | Finance Partners |
| `lotlinx` | LotLinx (UNMEASURED) |
| `facebook`, `meta`, `instagram` | Meta/Social |
| `bmwusa`, `nissan usa`, `nissan third party`, `oem`, `stellantis`, `chrysler`, `jeep`, `dodge`, `ram` | OEM/Factory |
| `podium` | Podium |
| `team velocity` | Team Velocity |
| `dealer.com`, `dealersgear` | Dealer.com |
| `pixelmotion`, `pixel motion`, `mcpeek` (website) | Dealer Website |

Sources that don't match any keyword keep their original name.

### Artifact Detection

Auto-flag these as potential artifacts (close rate > 20%):
- Names containing: `service`, `previous customer`, `repeat customer`, `referral`, `location`, `fresh up`, `dealer mgmt`, `dms`, `lease return`, `lease loyalty`, `walk-in`, `walk in`
- DealerSocket `Source` = `Dealer Mgmt Sys` (always artifact)
- Any source with close rate > 50% and < 10 leads (statistical noise)
