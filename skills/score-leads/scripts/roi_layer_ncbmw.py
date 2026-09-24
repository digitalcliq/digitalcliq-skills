#!/usr/bin/env python3
"""NCBMW July 2026 Lead ROI workbook — layers July campaign costs onto the
score-leads scorecard. Built to the DigitalCLIQ design system; uploaded to
Google Drive as a Google Sheet after build."""
import csv, re, sys
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.drawing.image import Image as XLImage

VAULT = "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ"
RAW = "/Users/drewmoon/Library/CloudStorage/GoogleDrive-drewmoon@digitalcliq.com/Shared drives/DigitalCLIQ Shared Drive/Clients/New Century BMW/Documents/Reporting/July26thLeadsNCBMW.csv"
SCORECARD = VAULT + "/outputs/New_Century_BMW_Lead_Scores_2026-07-26.xlsx"
OUT = VAULT + "/outputs/New_Century_BMW_Lead_ROI_July_2026.xlsx"
LOGO = VAULT + "/Resources/brand-assets/digital-cliq-logo-solid-1000px-wide.png"

# ---- palette (Design-System tokens only) ----
BLUE   = "405FAB"  # Digital Blue
SKY    = "6B9DD4"  # Sky Blue
GREY   = "949592"  # Warm Grey
NAVY   = "131B30"  # Card Navy
TILE   = "2E4780"  # Tile Blue
TINT   = "EDF2F9"  # Callout Tint
CARD   = "FBFBFD"  # Card White
BORDER = "D8E1F0"

H = "Dosis"; B = "Roboto Slab"

def money(s):
    s = (s or "").strip()
    if not s: return None
    neg = s.startswith("(")
    v = float(re.sub(r"[^\d.]", "", s) or 0)
    return -v if neg else v

# ---- read raw CSV ----
rows = {}
with open(RAW, newline="") as f:
    r = csv.reader(f)
    header = next(r)
    for row in r:
        name = row[0].strip()
        if name in ("Average", "Total"): continue
        rows[name] = {
            "leads": int(row[6] or 0), "appts": int(row[7] or 0),
            "shows": int(row[11] or 0), "sold": int(row[16] or 0),
            "gross": money(row[18]) or 0.0,
        }
print(f"raw sources: {len(rows)}")

# ---- read scorecard for score/tier/bench ----
swb = openpyxl.load_workbook(SCORECARD, data_only=True)
sws = swb["Lead Source Scores"]
scores = {}
for row in sws.iter_rows(min_row=6, values_only=True):
    if row[2] is None: continue
    scores[str(row[2]).strip()] = {"score": row[0], "tier": row[1],
                                   "sale_pct": row[12], "bench": row[13], "vs": row[14]}
print(f"scored sources: {len(scores)}")

# ---- July cost ledger (from Drew's 2026 budget Google Sheet, July column) ----
# (vendor, july_cost or "NO DATA", class, note)
NO = "NO DATA"
LEDGER = [
    ("CarGurus",                       3633, "3rd-Party Leads", "Listings + Digital Deal + Reengagement"),
    ("AutoTrader",                     6500, "3rd-Party Leads", ""),
    ("CarFax Car Listings",            3380, "3rd-Party Leads", "ZERO CarFax-labeled leads in CRM this month — investigate tagging or cancel"),
    ("Cars.com",                       3100, "3rd-Party Leads", "Incl. Shopper Alert"),
    ("Edmunds",                        3300, "3rd-Party Leads", "Budget drops to $0 in Sep"),
    ("TrueCar",                           0, "3rd-Party Leads", "Not active"),
    ("Costco",                            0, "3rd-Party Leads", "Not active"),
    ("Automotive Mastermind",          8436, "Equity Mining",   "Budgeted under Traditional Media"),
    ("Gubagoo Virtual Retailing",      1200, "Website Tools",   ""),
    ("Gubagoo Website Chat",            799, "Website Tools",   "Incl. SMS + Dealer Website - Chat"),
    ("Website (Team Velocity)",        2500, "Website Tools",   "All Apollo + Dealer Website form leads"),
    ("PPC (NabThat)",                 28000, "Traffic Driver",  "Drives site traffic; leads land under website sources"),
    ("Paid Media Multicultural (Constellation)", 22613, "Traffic Driver", "Drives traffic/awareness; no CRM source rows"),
    ("Conquest Emails",                1100, "Traffic Driver",  "July one-off"),
    ("DigitalCLIQ",                    3000, "Traffic Driver",  "Agency"),
    ("School Sponsors",                 500, "Traffic Driver",  "Community sponsorship"),
    ("Call Revue",                     1500, "Infrastructure",  "Call tracking/coaching tool, not a lead source"),
    ("Radio Or TV",                       0, "Traditional",     "Budget $0 — but CRM logged 1 radio-attributed sale"),
    ("Service Mailer / Direct Mail",      0, "Traditional",     "Budget $0 — CRM logged 1 direct-mail prospect"),
    ("BMW / BMWUSA OEM programs",        NO, "OEM",             "OEM lead programs (BYO, BMWUSA, test-drive events) — cost not in budget sheet"),
    ("BMW FS equity leads",              NO, "OEM",             "FS lease/loan/warranty lists — cost not in budget sheet"),
    ("Current Owner in Markt",           NO, "Unmapped vendor", "44 leads — vendor unclear (conquest email? Mastermind?)"),
    ("IntellaFUEL - BeBack",             NO, "Unmapped vendor", "25 leads — not in budget sheet"),
    ("JD Power SmartLeads",              NO, "Unmapped vendor", "Not in budget sheet"),
    ("Internal / Organic",                0, "Organic",         "Referral, repeat, service, walk-in, desking — no media cost"),
]

# ---- map every CRM source -> vendor group ----
WEB = ["Apollo Website", "Apollo Websites - Check Availability", "Apollo Websites - Contact Dealer",
       "Apollo Websites - Contact Us - Admin", "Apollo Websites - Contact Us - Service",
       "Apollo Websites - iX3 Pre-Order", "Apollo Websites - Schedule Service - Recall",
       "Apollo Websites - SRP-Vehicle Interest-Email", "Apollo Websites - Trade - Scheduled Valuation",
       "Apollo Websites - Trade - Value Your Trade", "Dealer Website - Check Availability",
       "Dealer Website - Instant ePrice", "Dealer Website-Contact Us", "Dealer Contact - Inventory",
       "Dealer Contact Non KPI", "Get A Quote - Inventory", "New Car Inventory - Contact Dealer",
       "Special Offer", "Test Drive", "Loaner Lease Special"]
OEM = ["BMW Contact Dealer - Special Offers", "BMW Group", "BMWUSA Pre-Owned Contact Us - MACO",
       "BMWUSA Test Drive Appointment", "BYO", "BYO - Dealer Contact Non KPI", "BYO - Get A Quote",
       "BYO - Get a Quote - Non-KPI", "BYO - Test Drive Request", "BYO Matching Inventory - Get a Quote",
       "Order Now - Build Your Own",
       "Domestic Military Program Validated Customer", "MTD26_Circuit of the Americas_Attended",
       "MTD26_Willow Springs_Attended", "PDS_Corporate Group A_CA"]
FS  = ["FS Active Lead Service", "FS CPO Expiration", "FS Lease Customer Intent Lead", "FS Lease Lead 270",
       "FS Loan Lead", "FS Loan Lead Service", "FS Warranty Exp", "Lease Buyout - Still In Vehicle",
       "Lease Buyout - Still In Vehicle FS Loan"]
ORG = ["*Drove By", "*Lives in Area", "*Referral", "*Repeat Customer", "*Service Customer", "*Unknown",
       "*Works in Area", "Unknown", "Other", "Referral", "Desking"]

GROUPS = {
    "CarGurus": ["CarGurus", "CarGurus - Digital Deal", "CarGurus Reengagement"],
    "AutoTrader": ["AutoTrader - CPO", "AutoTrader.com"],
    "CarFax Car Listings": [],
    "Cars.com": ["Cars.com", "Cars.com Shopper Alert"],
    "Edmunds": ["Edmunds"],
    "TrueCar": [], "Costco": [],
    "Automotive Mastermind": ["Automotive Mastermind", "automotiveMastermind"],
    "Gubagoo Virtual Retailing": ["Gubagoo - Virtual Retailing"],
    "Gubagoo Website Chat": ["Gubagoo - Chat", "Gubagoo - SMS", "Dealer Website - Chat"],
    "Website (Team Velocity)": WEB,
    "PPC (NabThat)": ["Nabthat Web Lease Return"],
    "Paid Media Multicultural (Constellation)": [], "Conquest Emails": [],
    "DigitalCLIQ": [], "School Sponsors": [],
    "Call Revue": ["Dealer Phone Lead"],
    "Radio Or TV": ["*Radio"],
    "Service Mailer / Direct Mail": ["*Direct Mail"],
    "BMW / BMWUSA OEM programs": OEM,
    "BMW FS equity leads": FS,
    "Current Owner in Markt": ["Current Owner in Markt"],
    "IntellaFUEL - BeBack": ["IntellaFUEL - BeBack"],
    "JD Power SmartLeads": ["JD Power SmartLeads"],
    "Internal / Organic": ORG,
}
src2grp = {}
for g, members in GROUPS.items():
    for m in members: src2grp[m] = g
unmapped = [s for s in rows if s not in src2grp]
if unmapped:
    print("UNMAPPED SOURCES:", unmapped); sys.exit(1)

def agg(g):
    ms = [rows[m] for m in GROUPS[g] if m in rows]
    return {k: sum(m[k] for m in ms) for k in ("leads","appts","shows","sold","gross")}

# ---- totals ----
TOT = {k: sum(v[k] for v in rows.values()) for k in ("leads","appts","shows","sold","gross")}
SPEND = sum(c for _, c, _, _ in LEDGER if isinstance(c, (int, float)))
print("totals:", TOT, "spend:", SPEND)

# ================= workbook =================
wb = openpyxl.Workbook()
thin = Border(*[Side(style="thin", color=BORDER)]*4)

def fill(hexc): return PatternFill("solid", fgColor=hexc)
def band(ws, row, ncols, text, sub=None):
    ws.row_dimensions[row].height = 44
    for c in range(1, ncols+1):
        ws.cell(row=row, column=c).fill = fill(BLUE)
    ws.cell(row=row, column=2, value=text).font = Font(name=H, size=18, bold=True, color="FFFFFF")
    ws.cell(row=row, column=2).alignment = Alignment(vertical="center")
    try:
        img = XLImage(LOGO); img.height = 34; img.width = 110
        ws.add_image(img, "A" + str(row))
    except Exception as e:
        raise RuntimeError(f"logo failed to embed: {e}")
    if sub:
        ws.row_dimensions[row+1].height = 20
        for c in range(1, ncols+1): ws.cell(row=row+1, column=c).fill = fill(TILE)
        ws.cell(row=row+1, column=2, value=sub).font = Font(name=H, size=10, bold=True, color="FFFFFF")
        ws.cell(row=row+1, column=2).alignment = Alignment(vertical="center")

def hdr(ws, row, cols, start=1):
    for i, t in enumerate(cols):
        c = ws.cell(row=row, column=start+i, value=t)
        c.font = Font(name=H, size=10, bold=True, color="FFFFFF")
        c.fill = fill(NAVY); c.border = thin
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[row].height = 30

CUR = '"$"#,##0'; CUR2 = '"$"#,##0.00'; PCT = '0%'

# ---------- Tab 1: ROI Summary ----------
ws = wb.active; ws.title = "ROI Summary"
ws.sheet_view.showGridLines = False
for col, w in zip("ABCDEFGH", [16, 30, 16, 16, 16, 16, 16, 30]): ws.column_dimensions[col].width = w
band(ws, 1, 8, "New Century BMW — Lead ROI Scorecard", "Leads 01–26 Jul 2026 (Focus CRM)  |  Costs: full July 2026 budget  |  Built by DigitalCLIQ  |  July 26, 2026")

stats = [("July Ad Spend", SPEND, CUR), ("Total Leads", TOT["leads"], '#,##0'),
         ("Units Sold", TOT["sold"], '#,##0'), ("Front Gross", TOT["gross"], CUR),
         ("Net After Spend", TOT["gross"] - SPEND, CUR),
         ("Blended ROI", (TOT["gross"] - SPEND) / SPEND, PCT)]
r = 4
ws.cell(row=r, column=2, value="STORE TOTALS — GROSS vs SPEND").font = Font(name=H, size=13, bold=True, color=BLUE)
r += 1
for i, (label, val, fmt) in enumerate(stats):
    c = 2 + (i % 3) * 2; rr = r + (i // 3) * 3
    lc = ws.cell(row=rr, column=c, value=label); lc.font = Font(name=H, size=10, bold=True, color=GREY)
    vc = ws.cell(row=rr+1, column=c, value=val); vc.font = Font(name=H, size=22, bold=True, color=SKY); vc.number_format = fmt
r += 6
more = [("Cost per Lead (blended)", SPEND / TOT["leads"], CUR2),
        ("Cost per Sale (blended)", SPEND / TOT["sold"], CUR),
        ("Gross per Unit", TOT["gross"] / TOT["sold"], CUR),
        ("Appt Rate", TOT["appts"] / TOT["leads"], '0.0%'),
        ("Show Rate (of appts)", TOT["shows"] / TOT["appts"], '0.0%'),
        ("Close Rate", TOT["sold"] / TOT["leads"], '0.0%')]
for i, (label, val, fmt) in enumerate(more):
    c = 2 + (i % 3) * 2; rr = r + (i // 3) * 3
    lc = ws.cell(row=rr, column=c, value=label); lc.font = Font(name=H, size=10, bold=True, color=GREY)
    vc = ws.cell(row=rr+1, column=c, value=val); vc.font = Font(name=H, size=18, bold=True, color=BLUE); vc.number_format = fmt
r += 7
ws.cell(row=r, column=2, value="NADA BENCHMARK: 13.4% close on acquisition leads vs 18.6% luxury expectation for this lead mix — BELOW by 5.2 pts").font = Font(name=B, size=10, bold=True, color="FFFFFF")
for c in range(2, 9): ws.cell(row=r, column=c).fill = fill(TILE)
ws.row_dimensions[r].height = 24
r += 2
ws.cell(row=r, column=2, value="WHAT JUMPS OUT").font = Font(name=H, size=13, bold=True, color=BLUE)
findings = [
    "1. CarFax: $3,380/mo with ZERO CarFax-labeled leads in the CRM. Either source tagging is broken or this is pure waste — resolve before renewal.",
    "2. Gubagoo Virtual Retailing is the pound-for-pound winner: $1,200 produced 3 sales and $13.9K gross (11.6x return, $400/sale).",
    "3. Automotive Mastermind: $8,436 for 107 leads, 1 sale at a $3,456 LOSS on the car. Worst net line on the sheet (−$11.9K). Renegotiate or cut.",
    "4. AutoTrader: $6,500 for 4 leads, 0 sales ($1,625/lead). Cars.com: $3,100, 20 leads, 0 sales. The used-car marketplace stack is $16.3K/mo for 2 CarGurus sales.",
    "5. CarGurus is the only 3rd-party lead vendor in the black: $3,633 → 2 sales, $9.4K gross (+158% ROI).",
    "6. Traffic drivers (NabThat PPC $28K + Constellation $22.6K) = 57% of spend. Their output lands inside website lead rows — judge them on the website group's 9 sales + total store volume, not a CRM row.",
    "7. Internal/organic (referral, repeat, service, walk-in, desking) delivered 54 of 79 sales at $0 media cost. Paid media closed the remaining 25 at ~$3,580 per sale.",
]
r += 1
for i, f in enumerate(findings):
    rr = r + i
    ws.merge_cells(start_row=rr, start_column=2, end_row=rr, end_column=8)
    c = ws.cell(row=rr, column=2, value=f); c.font = Font(name=B, size=10, color=NAVY)
    c.alignment = Alignment(wrap_text=True, vertical="top"); c.fill = fill(TINT)
    ws.row_dimensions[rr].height = 30
r += len(findings) + 1
ws.cell(row=r, column=2, value="Costs are the full-July budget; leads run through 7/26 (84% of the month). See Methodology tab. Fill any NO DATA cost on the Vendor ROI tab and its ROI math updates automatically.").font = Font(name=B, size=9, italic=True, color=GREY)
ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=8)

# ---------- Tab 2: Vendor ROI ----------
ws = wb.create_sheet("Vendor ROI")
ws.sheet_view.showGridLines = False
widths = [34, 15, 10, 12, 13, 9, 11, 8, 8, 8, 11, 13, 12, 13, 9, 46]
for i, w in enumerate(widths, 1): ws.column_dimensions[get_column_letter(i)].width = w
band(ws, 1, len(widths), "Vendor ROI — July Cost vs CRM Results", "Edit any NO DATA cost cell → CPL / Net / ROI recalc automatically")
COLS = ["Vendor / Program", "Class", "Score/Tier", "July Cost", "Cost thru 7/26", "Leads", "Cost/Lead",
        "Appts", "Shows", "Sold", "Cost/Sale", "Front Gross", "Gross/Unit", "Net (Gross−Cost)", "ROI", "Read"]
hdr(ws, 3, COLS)

def best_tier(g):
    ts = [scores[m] for m in GROUPS[g] if m in scores]
    if not ts: return ""
    bt = max(ts, key=lambda x: (x["score"] or 0))
    return f'{bt["score"]}/{bt["tier"]}'

READS = {
    "CarGurus": "KEEP — only 3rd-party vendor in the black",
    "AutoTrader": "CUT / RENEGOTIATE — 4 leads, 0 sales at $6.5K",
    "CarFax Car Listings": "INVESTIGATE — paying with zero attributed leads",
    "Cars.com": "WATCH — 20 leads, 0 sales this month",
    "Edmunds": "WATCH — 39 leads, 1 sale, negative net; already sunsetting in Sep",
    "TrueCar": "Inactive", "Costco": "Inactive",
    "Automotive Mastermind": "RENEGOTIATE / CUT — worst net line (−$11.9K)",
    "Gubagoo Virtual Retailing": "KEEP — best ROI on the sheet",
    "Gubagoo Website Chat": "Cheap top-of-funnel; fine at $799",
    "Website (Team Velocity)": "Core converter — 9 sales from site forms",
    "PPC (NabThat)": "Traffic driver — output lands in website rows; judge via GA4 + website group",
    "Paid Media Multicultural (Constellation)": "Traffic driver — no CRM rows; needs its own attribution check",
    "Conquest Emails": "July test — no tagged CRM rows",
    "DigitalCLIQ": "Agency fee — store-wide",
    "School Sponsors": "Community — not lead-attributable",
    "Call Revue": "Tool, not a source",
    "Radio Or TV": "1 sale attributed with $0 recorded spend — check for unbudgeted radio",
    "Service Mailer / Direct Mail": "1 prospect, $0 budget",
    "BMW / BMWUSA OEM programs": "OEM-funded volume; fill cost if any",
    "BMW FS equity leads": "82-lead FS lease list drove appts but 0 closes tagged; sales leak to other rows",
    "Current Owner in Markt": "44 leads — identify the vendor and its bill",
    "IntellaFUEL - BeBack": "25 leads, 0 activity — identify vendor",
    "JD Power SmartLeads": "Low volume",
    "Internal / Organic": "54 of 79 sales, $0 media cost",
}
ORDER_SECTIONS = [
    ("PAID — DIRECT ATTRIBUTION", ["CarGurus", "AutoTrader", "CarFax Car Listings", "Cars.com", "Edmunds",
                                   "TrueCar", "Costco", "Automotive Mastermind", "Gubagoo Virtual Retailing",
                                   "Gubagoo Website Chat", "Website (Team Velocity)"]),
    ("PAID — TRAFFIC DRIVERS & TOOLS (site-wide, no single CRM row)", ["PPC (NabThat)", "Paid Media Multicultural (Constellation)",
                                   "Conquest Emails", "DigitalCLIQ", "School Sponsors", "Call Revue",
                                   "Radio Or TV", "Service Mailer / Direct Mail"]),
    ("OEM / UNKNOWN COST — fill in the NO DATA cells", ["BMW / BMWUSA OEM programs", "BMW FS equity leads",
                                   "Current Owner in Markt", "IntellaFUEL - BeBack", "JD Power SmartLeads"]),
    ("NO MEDIA COST", ["Internal / Organic"]),
]
ledger_map = {v: (c, cls, note) for v, c, cls, note in LEDGER}
r = 4
data_rows = []
for section, vendors in ORDER_SECTIONS:
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=len(widths))
    sc = ws.cell(row=r, column=1, value=section)
    sc.font = Font(name=H, size=10, bold=True, color="FFFFFF"); sc.fill = fill(TILE)
    ws.row_dimensions[r].height = 20
    r += 1
    for v in vendors:
        cost, cls, note = ledger_map[v]
        a = agg(v)
        ws.cell(row=r, column=1, value=v).font = Font(name=B, size=10, bold=True, color=NAVY)
        ws.cell(row=r, column=2, value=cls).font = Font(name=B, size=9, color=GREY)
        ws.cell(row=r, column=3, value=best_tier(v)).font = Font(name=H, size=10, bold=True, color=BLUE)
        cc = ws.cell(row=r, column=4, value=cost)
        if cost == NO:
            cc.font = Font(name=H, size=10, bold=True, color="FFFFFF"); cc.fill = fill(GREY)
            cc.alignment = Alignment(horizontal="center")
        else:
            cc.number_format = CUR; cc.font = Font(name=B, size=10, color=NAVY)
        ws.cell(row=r, column=5, value=f'=IF(ISNUMBER(D{r}),ROUND(D{r}*26/31,0),"—")').number_format = CUR
        ws.cell(row=r, column=6, value=a["leads"])
        ws.cell(row=r, column=7, value=f'=IF(AND(ISNUMBER(D{r}),F{r}>0),D{r}/F{r},"—")').number_format = CUR2
        ws.cell(row=r, column=8, value=a["appts"]); ws.cell(row=r, column=9, value=a["shows"])
        ws.cell(row=r, column=10, value=a["sold"])
        ws.cell(row=r, column=11, value=f'=IF(AND(ISNUMBER(D{r}),J{r}>0),D{r}/J{r},"—")').number_format = CUR
        gc = ws.cell(row=r, column=12, value=a["gross"]); gc.number_format = CUR
        ws.cell(row=r, column=13, value=f'=IF(J{r}>0,L{r}/J{r},"—")').number_format = CUR
        ws.cell(row=r, column=14, value=f'=IF(ISNUMBER(D{r}),L{r}-D{r},"—")').number_format = CUR
        ws.cell(row=r, column=15, value=f'=IF(AND(ISNUMBER(D{r}),D{r}>0),(L{r}-D{r})/D{r},"—")').number_format = PCT
        nc = ws.cell(row=r, column=16, value=READS.get(v, "")); nc.font = Font(name=B, size=9, color=NAVY)
        nc.alignment = Alignment(wrap_text=True, vertical="center")
        for c in range(1, len(widths)+1):
            cell = ws.cell(row=r, column=c); cell.border = thin
            if cell.font is None or cell.font.name is None: cell.font = Font(name=B, size=10, color=NAVY)
            if c in (6, 8, 9, 10): cell.alignment = Alignment(horizontal="center"); cell.font = Font(name=B, size=10, color=NAVY)
        if r % 2 == 0:
            for c in range(1, len(widths)+1):
                if ws.cell(row=r, column=c).fill.fgColor.rgb in (None, "00000000"):
                    ws.cell(row=r, column=c).fill = fill(TINT)
        data_rows.append(r)
        r += 1
# totals row
first, last = data_rows[0], data_rows[-1]
ws.cell(row=r, column=1, value="TOTAL").font = Font(name=H, size=11, bold=True, color="FFFFFF")
ws.cell(row=r, column=4, value=f"=SUMIF(D{first}:D{last},\">=0\")").number_format = CUR
for col, f in [(5, f"=SUMIF(E{first}:E{last},\">=0\")"), (6, f"=SUM(F{first}:F{last})"),
               (8, f"=SUM(H{first}:H{last})"), (9, f"=SUM(I{first}:I{last})"),
               (10, f"=SUM(J{first}:J{last})"), (12, f"=SUM(L{first}:L{last})"),
               (14, f"=L{r}-D{r}")]:
    cc = ws.cell(row=r, column=col, value=f)
    cc.number_format = CUR if col in (4, 5, 12, 14) else '#,##0'
ws.cell(row=r, column=7, value=f"=D{r}/F{r}").number_format = CUR2
ws.cell(row=r, column=11, value=f"=D{r}/J{r}").number_format = CUR
ws.cell(row=r, column=13, value=f"=L{r}/J{r}").number_format = CUR
ws.cell(row=r, column=15, value=f"=(L{r}-D{r})/D{r}").number_format = PCT
for c in range(1, len(widths)+1):
    cell = ws.cell(row=r, column=c); cell.fill = fill(NAVY); cell.border = thin
    if not (cell.font and cell.font.color and cell.font.color.rgb == "FFFFFFFF"):
        cell.font = Font(name=H, size=10, bold=True, color="FFFFFF")
ws.row_dimensions[r].height = 22
ws.freeze_panes = "A4"

# ---------- Tab 3: Lead Source Scores ----------
ws = wb.create_sheet("Lead Source Scores")
ws.sheet_view.showGridLines = False
widths3 = [8, 6, 42, 8, 8, 9, 9, 9, 8, 9, 10, 12, 12, 26]
for i, w in enumerate(widths3, 1): ws.column_dimensions[get_column_letter(i)].width = w
band(ws, 1, len(widths3), "Per-Source Scorecard + Gross + Cost Group", "1–10 score & tier vs best-in-report  |  NADA benchmark flag  |  gross joined from CRM")
hdr(ws, 3, ["Score", "Tier", "Lead Source", "Leads", "Appts", "Shows", "Sold", "Close %", "Bench %",
            "vs Bench", "Front Gross", "Gross/Unit", "Cost Group ►", "Vendor (see Vendor ROI tab)"])
tier_fill = {"A": BLUE, "B": SKY, "C": GREY, "D": NAVY}
r = 4
ordered = sorted(scores.items(), key=lambda kv: -(kv[1]["score"] or 0))
for name, s in ordered:
    raw = rows.get(name, {"leads": 0, "appts": 0, "shows": 0, "sold": 0, "gross": 0})
    g = src2grp.get(name, "?")
    vals = [s["score"], s["tier"], name, raw["leads"], raw["appts"], raw["shows"], raw["sold"],
            s["sale_pct"], s["bench"], s["vs"], raw["gross"],
            (raw["gross"]/raw["sold"] if raw["sold"] else None), "", g]
    for c, v in enumerate(vals, 1):
        cell = ws.cell(row=r, column=c, value=v)
        cell.border = thin
        cell.font = Font(name=B, size=9, color=NAVY)
        if c in (1, 2):
            cell.font = Font(name=H, size=10, bold=True, color="FFFFFF")
            cell.fill = fill(tier_fill.get(s["tier"], GREY)); cell.alignment = Alignment(horizontal="center")
        if c in (4, 5, 6, 7): cell.alignment = Alignment(horizontal="center")
        if c in (8, 9): cell.number_format = '0.0%'
        if c in (11, 12): cell.number_format = CUR
        if c == 10: cell.alignment = Alignment(horizontal="center"); cell.font = Font(name=H, size=9, bold=True, color=BLUE)
        if c == 14: cell.font = Font(name=B, size=9, color=GREY)
    if r % 2 == 0:
        for c in (3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 14): ws.cell(row=r, column=c).fill = fill(TINT)
    r += 1
ws.freeze_panes = "A4"

# ---------- Tab 4: Cost Ledger ----------
ws = wb.create_sheet("Cost Ledger (July)")
ws.sheet_view.showGridLines = False
for i, w in enumerate([40, 20, 14, 60], 1): ws.column_dimensions[get_column_letter(i)].width = w
band(ws, 1, 4, "July 2026 Cost Ledger", "Source: Drew's 2026 Budget Google Sheet (last update 07-11-2026), July column")
hdr(ws, 3, ["Line Item", "Class", "July Cost", "Note"])
r = 4
for v, cost, cls, note in LEDGER:
    ws.cell(row=r, column=1, value=v).font = Font(name=B, size=10, bold=True, color=NAVY)
    ws.cell(row=r, column=2, value=cls).font = Font(name=B, size=9, color=GREY)
    cc = ws.cell(row=r, column=3, value=cost)
    if cost == NO:
        cc.font = Font(name=H, size=10, bold=True, color="FFFFFF"); cc.fill = fill(GREY)
        cc.alignment = Alignment(horizontal="center")
    else:
        cc.number_format = CUR; cc.font = Font(name=B, size=10, color=NAVY)
    nc = ws.cell(row=r, column=4, value=note); nc.font = Font(name=B, size=9, color=NAVY)
    nc.alignment = Alignment(wrap_text=True, vertical="center")
    for c in range(1, 5): ws.cell(row=r, column=c).border = thin
    if r % 2 == 0:
        for c in (1, 2, 4): ws.cell(row=r, column=c).fill = fill(TINT)
    r += 1
ws.cell(row=r, column=1, value="TOTAL (known costs)").font = Font(name=H, size=11, bold=True, color="FFFFFF")
tc = ws.cell(row=r, column=3, value=f'=SUMIF(C4:C{r-1},">=0")'); tc.number_format = CUR
tc.font = Font(name=H, size=11, bold=True, color="FFFFFF")
for c in range(1, 5): ws.cell(row=r, column=c).fill = fill(NAVY); ws.cell(row=r, column=c).border = thin
r += 2
ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=4)
mc = ws.cell(row=r, column=1, value="Budget-sheet July gross spend: $89,561. Sep budget drops Edmunds ($3,300) — total planned falls to $85,161/mo.")
mc.font = Font(name=B, size=9, italic=True, color=GREY)

# ---------- Tab 4b: GA4 Traffic vs Spend (from TSV, when present) ----------
GA4_TSV = VAULT + "/.claude/skills/score-leads/scripts/ncbmw_ga4_jul2026.tsv"
if __import__("os").path.exists(GA4_TSV):
    ws = wb.create_sheet("GA4 Traffic vs Spend")
    ws.sheet_view.showGridLines = False
    widths_g = [34, 10, 10, 34, 10, 11, 10, 12, 10, 11, 60]
    for i, w in enumerate(widths_g, 1): ws.column_dimensions[get_column_letter(i)].width = w
    band(ws, 1, len(widths_g), "GA4 Traffic vs Spend", "Sessions & key events pulled live from analytics.google.com, Jul 1-26 2026")
    SECTION_ROWS = {"PAID DOLLARS vs TRACKED TRAFFIC", "FREE / EARNED TRAFFIC FOR CONTEXT ($0 media)",
                    "FULL CHANNEL MIX (GA4 default channel groups)"}
    r = 3
    for line in open(GA4_TSV):
        cells = line.rstrip("\n").split("\t")
        if len(cells) == 1 and not cells[0]:
            r += 1; continue
        is_section = cells[0] in SECTION_ROWS
        is_header = cells[0] in ("Vendor", "Bucket", "Channel")
        for c, v in enumerate(cells, 1):
            cell = ws.cell(row=r, column=c, value=v)
            if is_section or r == 3:
                cell.font = Font(name=H, size=11, bold=True, color="FFFFFF"); cell.fill = fill(TILE)
            elif is_header:
                cell.font = Font(name=H, size=9, bold=True, color="FFFFFF"); cell.fill = fill(NAVY)
                cell.alignment = Alignment(wrap_text=True, vertical="center")
            else:
                cell.font = Font(name=B, size=9, color=NAVY)
        if is_section:
            for c in range(len(cells) + 1, len(widths_g) + 1):
                ws.cell(row=r, column=c).fill = fill(TILE)
        r += 1

# ---------- Tab 5: Methodology ----------
ws = wb.create_sheet("Methodology")
ws.sheet_view.showGridLines = False
ws.column_dimensions["A"].width = 18; ws.column_dimensions["B"].width = 120
band(ws, 1, 2, "Methodology & Caveats")
notes = [
    ("Data window", "Leads/appointments/sales: Focus CRM e-commerce report, 01–26 Jul 2026 (84% of the month). Costs: full-July lines from Drew's 2026 Budget Google Sheet (updated 07-11-2026). The 'Cost thru 7/26' column prorates cost x 26/31 for a fairer in-month read; end-of-month numbers will improve as the last 5 selling days land."),
    ("Gross", "'Front Gross' is the CRM's Total Gross per source (front-end vehicle gross, negatives included). It excludes F&I/back-end gross and any fixed-ops downstream value, so true ROI is UNDERSTATED — a vendor near break-even on front gross is likely profitable all-in. NADA-typical back-end runs ~$1.5-2K/copy retail."),
    ("Attribution", "Each CRM source is mapped to the vendor that bills for it (Cost Group column, Lead Source Scores tab). Website form leads (Apollo/Dealer Website rows) map to the Team Velocity website line, but PPC (NabThat) and Constellation SPEND those dollars to fill that funnel — their ROI must be judged on total website output and GA4 sessions, not a CRM row. CarFax has zero labeled rows: either tagging is broken in Focus or the product delivered nothing."),
    ("NO DATA", "A grey NO DATA cost cell means the budget sheet has no line for it (OEM programs, BMW FS lists, Current Owner in Markt, IntellaFUEL, JD Power). Type a monthly cost into the cell and CPL, Cost/Sale, Net, and ROI recalculate automatically."),
    ("Scoring", "1-10 score and A/B/C/D tier come from the DigitalCLIQ score-leads model (40% sale conversion, 20% show rate, 15% volume, 15% appt set, 10% contact; new-car sources get a 1.5x conversion boost internally). Scores are RELATIVE to the best source in this report. 'vs Bench' is ABSOLUTE vs the NADA/industry close rate for that source type at a luxury store."),
    ("Store read", "13.4% close on acquisition leads vs 18.6% expected for this lead mix (luxury tier) — BELOW by 5.2 pts. 311 data-list/credit-app leads are excluded from that store rate."),
    ("Duplicates", "The CRM reported 48 duplicate leads across sources; duplicates inflate lead counts and deflate per-source close rates slightly."),
]
r = 3
for title, body in notes:
    ws.cell(row=r, column=2, value=title.upper()).font = Font(name=H, size=11, bold=True, color=BLUE)
    r += 1
    ws.cell(row=r, column=2, value=body).font = Font(name=B, size=10, color=NAVY)
    ws.cell(row=r, column=2).alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[r].height = 58
    r += 2

wb.save(OUT)
print("SAVED:", OUT)
