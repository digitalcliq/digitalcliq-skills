## Manual Path (only if the fast path can't read the file)

Use this only when `--raw` reports an unknown format or a PDF it can't parse.

### Step 0: Resolve Input File

Always look in `01_Inbox/` first. Do NOT search the entire filesystem.

1. If `$ARGUMENTS` is a full absolute path that exists → use it directly
2. Otherwise, treat `$ARGUMENTS` as a search hint and look **only** in `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/01_Inbox/` for a matching file (glob for `*{hint}*` with common extensions: `.pdf`, `.csv`, `.xlsx`, `.xls`)
3. If exactly one match is found → use it
4. If multiple matches → show the matches and ask the user which one
5. If no match → tell the user: "I couldn't find that file in `01_Inbox/`. Please move it there and try again."

Do NOT search outside `01_Inbox/` unless the user provides a full path.

### Step 1: Determine File Type

Check the file extension of the resolved file path:
- `.pdf` → go to Step 2a
- `.csv` → go to Step 2b
- `.xlsx` or `.xls` → go to Step 2c

### Step 2a: PDF Extraction

Run pdftotext to extract raw text:
```
/opt/homebrew/bin/pdftotext "<file_path>" -
```

Then parse the extracted text to identify:
1. **Store name** (e.g., "Sterling BMW")
2. **Date range** (e.g., "01-Feb-2026 to 18-Feb-2026")
3. **Data rows**: each lead source with: leads, contact #, contact %, appts #, appts %, shows #, shows %, sales #, sales %

PDF layouts vary by CRM. Use judgment to parse the tabular data. Numbers and percentages typically follow the source name in consistent column order. Ignore page headers/footers that repeat.

### Step 2b: CSV Reading

Read the CSV file directly. Map columns to the expected fields. Common CRM column names include variations of: "Source", "Provider", "Leads", "Contact", "Appointments", "Shows", "Sales", "Sold". Adapt to whatever headers are present.

### Step 2c: Excel Reading

Read the Excel file. Same column mapping logic as CSV.

### Step 3: Write Normalized CSV

Write a temporary CSV file to `/tmp/lead_score_input.csv` with these exact headers:
```
source,leads,contact,contact_pct,appts,appts_pct,shows,shows_pct,sales,sales_pct
```

Rules:
- Percentage values should be numbers without % signs (e.g., `85.7` not `85.7%`)
- Include the "Totals" row if present in source data
- Every source from the report gets a row, do not filter or omit any

### Step 4: Run Scoring Script

Determine the output filename from the store name and date:
- Replace spaces with underscores in the store name
- Format: `{Store_Name}_Lead_Scores_{YYYY-MM-DD}.xlsx`
- Save to `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/outputs/` (vault outputs folder). Never the input file directory, never Desktop.

Run:
```
python3 /Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/score-leads/score_leads.py /tmp/lead_score_input.csv "<output_path>" "<store_name>" "<date_range>"
```

### Step 5: Report Results

Display a brief summary:
- Store name and date range
- Total lead sources scored
- Count by tier (e.g., "4 A-tier, 8 B-tier, 12 C-tier, 15 D-tier")
- **Store self-score**: overall close rate vs the NADA industry blend for the detected brand tier (the script prints this as an `INFO:` line on stderr, e.g. "store close 9.6% vs 17.0% (Below)")
- Path to the output Excel file

Keep the summary short: the Excel file is the deliverable.
