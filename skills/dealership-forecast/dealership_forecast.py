#!/usr/bin/env python3
"""
DigitalCLIQ Dealership Forecast Tool
Supports: MomentumCRM, VinSolutions, Tekion, DealerSocket

Usage:
    python3 dealership_forecast.py detect <input_folder>
    python3 dealership_forecast.py build <config.json>
"""
import sys, os, json
from collections import defaultdict
import pandas as pd
import numpy as np

# --- Constants ---
# DigitalCLIQ Design-System tokens (Resources/design-system/Design-System.md).
# Palette-only: no generic greens/reds/oranges. Tier meaning is carried by the
# Tier/Rating TEXT labels; fills are treatments only (Sky = strong, Grey = weak).
DC = {
    'BLUE': '405FAB',      # Digital Blue — mastheads, header rows, emphasis
    'SKY': '6B9DD4',       # Sky Blue — strong/Tier 1 treatment, accents
    'BLACK': '000000',
    'WHITE': 'FFFFFF',
    'GREY': '949592',      # Warm Grey — weak/Tier 4/UNMEASURED treatment
    'LIGHT_BG': 'EDF2F9',  # Callout Tint — alternating body rows
    'CARD': 'FBFBFD',      # Card White
    'ACCENT': '2E4780',    # Tile Blue — totals rows, deep accents
    'BORDER': 'D8E1F0',    # thin cell borders
}
NADA = {1:.88,2:.94,3:1.08,4:1.04,5:1.02,6:1.0,7:.96,8:1.03,9:1.02,10:1.05,11:.98,12:1.0}

CPS_TIERS = [(500,'TIER 1','STAR'),(1000,'TIER 2','GOOD'),(1500,'TIER 3','AVG'),(float('inf'),'TIER 4','REVIEW')]
CR_TIERS = [(8,'TIER 1','STAR'),(5,'TIER 2','GOOD'),(2,'TIER 3','AVG'),(0,'TIER 4','REVIEW')]

ARTIFACT_KW = [
    'service dept','service department','previous customer','repeat customer',
    'previous buyer','referral','location','fresh up','dealer mgmt','dms import',
    'dms sales','lease return','lease loyalty','lease maturity','walk-in','walk in',
    'history import','vehicle acquisition',
]

VENDOR_RULES = [
    (['autotrader','auto trader'], 'AutoTrader'),
    (['cargurus','car gurus'], 'CarGurus'),
    (['cars.com','cars.com phone'], 'Cars.com'),
    (['carsdirect'], 'CarsDirect'),
    (['carfax','car fax'], 'CARFAX'),
    (['truecar'], 'TrueCar'),
    (['edmunds'], 'Edmunds'),
    (['costco'], 'Costco'),
    (['gubagoo','gobagoo'], 'Gubagoo'),
    (['carnow'], 'CarNow'),
    (['dealer inspire'], 'Dealer Inspire'),
    (['dealer website','dealerwebsite','e-pricer','epricer','check availability',
      'credit application','dealer contact','contact us','request more info',
      'get a quote','get e-price','dealers website','pixel motion'], 'Dealer Website'),
    (['kbb','kelley blue book'], 'KBB'),
    (['capital one'], 'Capital One'),
    (['chase auto'], 'Chase Auto'),
    (['lotlinx'], 'LotLinx'),
    (['facebook','meta ','instagram','cpm social'], 'Meta/Social'),
    (['bmwusa','byo ','order now'], 'BMW USA (OEM)'),
    (['nissan usa','nissan third party','choose nissan'], 'Nissan (OEM)'),
    (['stellantis','chrysler capital','jeep.com','dodge.com','ram ','ramtrucks',
      'chrysler.com','oem'], 'Stellantis (OEM)'),
    (['podium'], 'Podium'),
    (['team velocity'], 'Team Velocity'),
    (['dealer.com','dealersgear'], 'Dealer.com'),
    (['work truck','worktruck'], 'Work Truck Solutions'),
    (['blackbook','black book'], 'BlackBook'),
    (['auto credit express'], 'Auto Credit Express'),
    (['search optics'], 'Search Optics'),
    (['e-shop'], 'E-Shop (Digital Retailing)'),
    (['ace'], 'ACE (SubPrime)'),
    (['intelliprice'], 'Intelliprice'),
    (['current owner','fs lease','fs loan','fs warranty','fs active','fs cpo',
      'lease buyout','lease loyalty','lease maturity'], 'BMW FS / Lease Programs'),
    (['service dept','service department'], 'Service Dept'),
    (['previous customer','repeat customer','previous buyer'], 'Repeat/Previous Customer'),
    (['referral'], 'Referral'),
    (['location','fresh up','walk-in','walk in'], 'Walk-In / Location'),
    (['dealer mgmt','dms','history import'], 'DMS Import'),
    (['la auto show','auto show','firebolt'], 'Auto Show / Event'),
    (['direct marketing','mailer','email blast'], 'Direct Marketing'),
    (['radio','television','tv ','billboard','newspaper'], 'Traditional Media'),
    (['pownder'], 'Pownder'),
    (['apollo'], 'Apollo'),
]

# --- Data Validation ---

CONFIG_REQUIRED = {
    "crm":          ("str",  True),
    "input_files":  ("list", True),
    "dealership":   ("str",  True),
    "date_start":   ("str",  True),
    "date_end":     ("str",  True),
    "output_path":  ("str",  True),
}

VALID_CRMS = {"momentum", "vinsolutions", "tekion", "dealersocket"}

PARSED_ROW_REQUIRED = [
    "source_name", "good_leads", "total_leads", "bad_leads",
    "duplicate_leads", "sales", "sales_metric", "contact_count",
    "contact_pct", "appt_set", "appt_shown", "cost",
    "gross_profit", "avg_gross",
]


def _type_name(expected):
    mapping = {
        "str": "string", "int": "integer", "float": "float",
        "num": "number (int or float)", "list": "list",
        "dict": "dict",
    }
    return mapping.get(expected, expected)


def _check_type(value, expected):
    if expected == "str":
        return isinstance(value, str)
    elif expected == "num":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    elif expected == "list":
        return isinstance(value, list)
    elif expected == "dict":
        return isinstance(value, dict)
    return True


def validate_config(config, source_path="<config>"):
    """
    Validate a build-mode config.json before running the forecast pipeline.

    Checks:
      1. All required fields exist
      2. Data types match expectations
      3. CRM value is recognized
      4. input_files is a non-empty list of strings

    Returns (is_valid, errors).
    """
    errors = []

    if not isinstance(config, dict):
        errors.append(
            f"Config: expected dict, got {type(config).__name__}\n"
            f"  Expected: {{\"crm\": ..., \"input_files\": [...], ...}}\n"
            f"  Actual:   {type(config).__name__}"
        )
        return False, errors

    for field, (exp_type, required) in CONFIG_REQUIRED.items():
        val = config.get(field)
        if val is None:
            if required:
                errors.append(
                    f"config.{field}: missing required field\n"
                    f"  Expected: {_type_name(exp_type)}\n"
                    f"  Actual:   not present"
                )
        elif not _check_type(val, exp_type):
            errors.append(
                f"config.{field}: wrong type\n"
                f"  Expected: {_type_name(exp_type)}\n"
                f"  Actual:   {type(val).__name__} = {repr(val)[:80]}"
            )
        elif required and exp_type == "str" and not val:
            errors.append(
                f"config.{field}: required field is empty\n"
                f"  Expected: non-empty {_type_name(exp_type)}\n"
                f"  Actual:   \"\""
            )

    # CRM must be valid
    crm_val = config.get("crm", "")
    if isinstance(crm_val, str) and crm_val and crm_val not in VALID_CRMS:
        errors.append(
            f"config.crm: unrecognized CRM\n"
            f"  Expected: one of {sorted(VALID_CRMS)}\n"
            f"  Actual:   {repr(crm_val)}"
        )

    # input_files must be non-empty list of strings
    input_files = config.get("input_files", [])
    if isinstance(input_files, list):
        if not input_files:
            errors.append(
                "config.input_files: empty list\n"
                "  Expected: list with 1+ file paths\n"
                "  Actual:   []"
            )
        else:
            for i, fp in enumerate(input_files):
                if not isinstance(fp, str) or not fp:
                    errors.append(
                        f"config.input_files[{i}]: must be a non-empty string\n"
                        f"  Expected: file path string\n"
                        f"  Actual:   {repr(fp)}"
                    )

    if errors:
        shown = errors[:50]
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"CONFIG VALIDATION FAILED — {source_path}", file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)
        print(f"{len(errors)} error(s) found:\n", file=sys.stderr)
        for idx, e in enumerate(shown, 1):
            print(f"  {idx}. {e}\n", file=sys.stderr)
        print(f"{'='*60}\n", file=sys.stderr)
        return False, errors

    return True, []


def validate_parsed_rows(parsed_rows, source_path="<parsed>"):
    """
    Validate parsed CRM rows before vendor rollup.

    Checks:
      1. Each row is a dict with all required fields
      2. Numeric fields are numbers
      3. source_name is non-empty

    Returns (is_valid, errors).
    """
    errors = []

    if not isinstance(parsed_rows, list):
        errors.append(
            f"Parsed data: expected list, got {type(parsed_rows).__name__}\n"
            f"  Expected: list of dicts\n"
            f"  Actual:   {type(parsed_rows).__name__}"
        )
        return False, errors

    if not parsed_rows:
        errors.append(
            "Parsed data: empty list — no sources parsed from CRM file(s)\n"
            "  Expected: at least 1 row\n"
            "  Actual:   0 rows"
        )
        return False, errors

    for i, row in enumerate(parsed_rows):
        if not isinstance(row, dict):
            errors.append(
                f"parsed_rows[{i}]: wrong type\n"
                f"  Expected: dict\n"
                f"  Actual:   {type(row).__name__}"
            )
            continue

        missing = [f for f in PARSED_ROW_REQUIRED if f not in row]
        if missing:
            errors.append(
                f"parsed_rows[{i}]: missing fields\n"
                f"  Expected: {PARSED_ROW_REQUIRED}\n"
                f"  Missing:  {missing}"
            )

        name = row.get("source_name", "")
        if isinstance(name, str) and not name.strip():
            errors.append(
                f"parsed_rows[{i}].source_name: empty\n"
                f"  Expected: non-empty string\n"
                f"  Actual:   \"\""
            )

        if len(errors) >= 50:
            break

    if errors:
        shown = errors[:50]
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"PARSED DATA VALIDATION — {source_path}", file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)
        print(f"{len(errors)} warning(s):\n", file=sys.stderr)
        for idx, e in enumerate(shown, 1):
            print(f"  {idx}. {e}\n", file=sys.stderr)
        print(f"{'='*60}\n", file=sys.stderr)

    return len(errors) == 0, errors


# --- Parsing Utilities ---

def pnum(val, fmt='int'):
    """Universal number parser. fmt: 'int', 'float', 'dollar', 'pct'"""
    if pd.isna(val) or val == '' or val == '-':
        return 0 if fmt == 'int' else 0.0
    s = str(val).strip()
    neg = s.startswith('(') and s.endswith(')')
    if neg: s = s[1:-1]
    s = s.replace('$','').replace(',','').replace('%','').strip()
    if not s or s == '-':
        return 0 if fmt == 'int' else 0.0
    try:
        v = float(s)
        if neg: v = -v
        return int(v) if fmt == 'int' else v
    except ValueError:
        return 0 if fmt == 'int' else 0.0


def make_row(name, good=0, total=0, bad=0, dups=0, sales=0, metric='',
             contact=0, contact_pct=0.0, appt_set=0, appt_shown=0,
             cost=0.0, gross=0.0, avg_gross=0.0):
    """Build a canonical source row with defaults."""
    return {
        'source_name': name, 'good_leads': good, 'total_leads': total,
        'bad_leads': bad, 'duplicate_leads': dups, 'sales': sales,
        'sales_metric': metric, 'contact_count': contact,
        'contact_pct': contact_pct, 'appt_set': appt_set,
        'appt_shown': appt_shown, 'cost': cost,
        'gross_profit': gross, 'avg_gross': avg_gross,
    }


def safe_div(a, b, default=0.0):
    return a / b if b > 0 else default


# --- CRM Detection ---

CRM_FINGERPRINTS = [
    ('momentum',    'MomentumCRM',  lambda c: 'lead_provider' in c and 'total_leads' in c),
    ('vinsolutions','VinSolutions', lambda c: 'lead source group' in c and any('sold from leads' in x for x in c)),
    ('tekion',      'Tekion',       lambda c: any('source type' in x and 'consolidated' in x for x in c)),
    ('dealersocket','DealerSocket', lambda c: 'source' in c and 'marketingchannel' in c),
]

def detect_crm(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    df = pd.read_excel(filepath, nrows=2) if ext in ('.xlsx','.xls') else pd.read_csv(filepath, nrows=2)
    cols = [str(c).strip().lower() for c in df.columns]
    cols_orig = [str(c).strip() for c in df.columns]
    for crm_id, label, test in CRM_FINGERPRINTS:
        if test(cols):
            return {'crm': crm_id, 'label': label, 'columns': cols_orig, 'file': filepath}
    return {'crm': 'unknown', 'label': 'Unknown CRM', 'columns': cols_orig, 'file': filepath}


def scan_folder(folder):
    results = []
    for fname in sorted(os.listdir(folder)):
        fpath = os.path.join(folder, fname)
        ext = os.path.splitext(fname)[1].lower()
        if not os.path.isfile(fpath) or ext not in ('.csv','.xlsx','.xls') or fname[0] in '.~':
            continue
        try:
            info = detect_crm(fpath)
            info['filename'] = fname
            results.append(info)
        except Exception as e:
            results.append({'crm':'error','label':str(e),'filename':fname,'file':fpath})
    return results


# --- CRM Parsers ---

def parse_momentum(filepath):
    df = pd.read_csv(filepath)
    rows = []
    for _, r in df.iterrows():
        name = str(r.get('lead_provider','')).strip()
        if not name: continue
        total = pnum(r.get('total_leads',0))
        inv = pnum(r.get('total_invalid_leads',0))
        dups = pnum(r.get('total_dups',0))
        rows.append(make_row(name, good=max(total-inv-dups,0), total=total,
                             bad=inv, dups=dups, sales=pnum(r.get('total_sales',0)),
                             metric='total_sales'))
    return rows


def parse_vinsolutions(filepath):
    df = pd.read_csv(filepath)
    rows = []
    for _, r in df.iterrows():
        name = str(r.get('Lead Source Group','')).strip()
        if not name: continue
        sales = pnum(r.get('Sold from Leads',0))
        metric = 'Sold from Leads'
        if sales == 0:
            s2 = pnum(r.get('Sold in Timeframe',0))
            if s2 > 0: sales, metric = s2, 'Sold in Timeframe'
        rows.append(make_row(name,
            good=pnum(r.get('Good Leads',0)), total=pnum(r.get('Total Leads',0)),
            bad=pnum(r.get('Bad Leads',0)), dups=pnum(r.get('Duplicate Leads',0)),
            sales=sales, metric=metric,
            contact=pnum(r.get('Internet Actual Contact',0)),
            contact_pct=pnum(r.get('Internet Actual Contact %',0),fmt='float'),
            appt_set=pnum(r.get('Appts Set',0)), appt_shown=pnum(r.get('Appts Shown',0)),
            cost=pnum(r.get('Total Cost',0),fmt='dollar'),
            gross=pnum(r.get('Total Gross',0),fmt='dollar'),
            avg_gross=pnum(r.get('Avg Gross',0),fmt='dollar')))
    return rows


def parse_tekion(filepath):
    df = pd.read_csv(filepath)
    groups = defaultdict(lambda: {'good':0,'total':0,'bad':0,'dups':0,'sales':0})
    for _, r in df.iterrows():
        g = str(r.get('Lead Source Group','')).strip()
        s = str(r.get('Source Name','')).strip()
        if not g or not s: continue
        d = groups[g]
        d['good']  += pnum(r.get('Total Good Leads',0))
        d['total'] += pnum(r.get('Total Leads',0))
        d['bad']   += pnum(r.get('Total Bad Leads',0))
        d['dups']  += pnum(r.get('Total Duplicate Leads',0))
        d['sales'] += pnum(r.get('Sold In Time Period',0))
    return [make_row(k, good=v['good'], total=v['total'], bad=v['bad'],
                     dups=v['dups'], sales=v['sales'], metric='Sold In Time Period')
            for k, v in groups.items()]


def parse_dealersocket(filepath):
    df = pd.read_csv(filepath)
    SKIP_CH = {'Unknown Marketing Channel','Marketing Channel Not Assigned','Uncategorized',''}
    ch = defaultdict(lambda: {'leads':0,'contacted':0,'ao':0,'as':0,'sold':0,'gross':0.0})
    for _, r in df.iterrows():
        src = str(r.get('Source','')).strip()
        chan = str(r.get('MarketingChannel','')).strip()
        if '====' in src or chan in SKIP_CH: continue
        d = ch[chan]
        d['leads']     += pnum(r.get('MarketingChannelNewProspects',0))
        d['contacted'] += pnum(r.get('MarketingChannelContacted',0))
        d['ao']        += pnum(r.get('MarketingChannelApptOpen',0))
        d['as']        += pnum(r.get('MarketingChannelApptShow',0))
        d['sold']      += pnum(r.get('MarketingChannelSold',0))
        d['gross']     += pnum(r.get('MarketingChannelTotalGross',0),fmt='dollar')
    return [make_row(k, good=v['leads'], total=v['leads'], sales=v['sold'],
                     metric='MarketingChannelSold', contact=v['contacted'],
                     contact_pct=safe_div(v['contacted'],v['leads'])*100,
                     appt_set=v['ao'], appt_shown=v['as'], gross=v['gross'],
                     avg_gross=safe_div(v['gross'],v['sold']))
            for k, v in ch.items()]

PARSERS = {
    'momentum': parse_momentum, 'vinsolutions': parse_vinsolutions,
    'tekion': parse_tekion, 'dealersocket': parse_dealersocket,
}


# --- Vendor Rollup ---

def rollup_vendor(name):
    lower = name.lower().strip()
    for keywords, vendor in VENDOR_RULES:
        if any(kw in lower for kw in keywords):
            return vendor
    return name


def assign_tier(sales, good_leads, cps, has_cost, close_rate):
    if sales == 0 and good_leads == 0:
        return 'UNMEASURED', '?'
    if has_cost:
        if sales == 0: return 'UNMEASURED', '?'
        for threshold, tier, label in CPS_TIERS:
            if cps < threshold: return tier, label
    else:
        if sales == 0: return 'UNMEASURED', '?'
        for threshold, tier, label in CR_TIERS:
            if close_rate >= threshold: return tier, label
    return 'TIER 4', 'REVIEW'


AGGREGATE_FIELDS = ['good_leads','total_leads','bad_leads','duplicate_leads',
                    'sales','contact_count','appt_set','appt_shown','cost','gross_profit']

def rollup_sources(parsed_rows):
    vendors = defaultdict(lambda: {f: 0 for f in AGGREGATE_FIELDS} | {'sources':[],'sales_metric':''})
    for row in parsed_rows:
        v = vendors[rollup_vendor(row['source_name'])]
        for f in AGGREGATE_FIELDS:
            v[f] += row.get(f, 0)
        v['sources'].append(row['source_name'])
        if not v['sales_metric']: v['sales_metric'] = row['sales_metric']

    total_good = sum(v['good_leads'] for v in vendors.values())
    result = []
    for name, v in vendors.items():
        cr = safe_div(v['sales'], v['good_leads']) * 100
        has_cost = v['cost'] > 0
        cps = safe_div(v['cost'], v['sales'])
        tier, tier_label = assign_tier(v['sales'], v['good_leads'], cps, has_cost, cr)
        result.append({
            'vendor': name, **{f: v[f] for f in AGGREGATE_FIELDS},
            'close_rate': cr, 'cpl': safe_div(v['cost'], v['good_leads']),
            'cps': cps, 'avg_gross': safe_div(v['gross_profit'], v['sales']),
            'lead_share': safe_div(v['good_leads'], total_good) * 100,
            'tier': tier, 'tier_label': tier_label,
            'sources': v['sources'], 'sales_metric': v['sales_metric'],
        })

    has_any_cost = any(r['cost'] > 0 for r in result)
    result.sort(key=lambda x: (x['cps'] if x['cps'] > 0 else 999999) if has_any_cost else -x['close_rate'])
    return result


# --- Artifact Detection ---

def detect_artifacts(vendor_rows):
    flagged = []
    for v in vendor_rows:
        lower = v['vendor'].lower()
        reason = next((f'Name matches: "{kw}"' for kw in ARTIFACT_KW if kw in lower), None)
        if not reason and v['close_rate'] > 20 and v['good_leads'] >= 5:
            reason = f'Close rate {v["close_rate"]:.1f}% unusually high'
        if not reason and v['close_rate'] >= 50 and v['good_leads'] < 10:
            reason = f'Noise: {v["good_leads"]} leads, {v["close_rate"]:.0f}% close'
        if reason:
            flagged.append({'vendor': v['vendor'], 'good_leads': v['good_leads'],
                           'sales': v['sales'], 'close_rate': v['close_rate'], 'reason': reason})
    return flagged


# --- NADA Projection ---

def nada_projection(annual_leads, months=12, yoy_growth=0.0):
    avg = annual_leads / months if months > 0 else 0
    gf = 1 + yoy_growth / 100
    proj = [{'month': m, 'baseline': round(avg * NADA[m] * gf),
             'lower_80': round(avg * NADA[m] * gf * 0.88),
             'upper_80': round(avg * NADA[m] * gf * 1.12),
             'nada_index': NADA[m]} for m in range(1, 13)]
    return proj, sum(p['baseline'] for p in proj)


# --- Excel Builder ---

def build_workbook(config, vendor_rows, parsed_rows, projections, artifacts_excluded):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter as col_letter
    from openpyxl.drawing.image import Image as XLImage

    LOGO_PATH = "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Resources/brand-assets/digital-cliq-logo-solid-1000px-wide.png"

    wb = Workbook()
    border = Border(*(Side(style='thin', color=DC['BORDER']),) * 4)

    def fill(color): return PatternFill(start_color=DC[color], end_color=DC[color], fill_type='solid')
    def font(bold=False, color='BLACK', size=10, italic=False, family='Roboto Slab'):
        # Dosis = structure (headings, headers, stats), Roboto Slab = body. Never Arial/Calibri.
        return Font(name=family, bold=bold, color=DC[color], size=size, italic=italic)

    dealership = config['dealership']
    date_text = f'{config.get("date_start","")} to {config.get("date_end","")}'

    def add_masthead(ws, ncols, title, subtitle=''):
        """Design-System §4 masthead on EVERY visible sheet: rows 1-2 Digital Blue
        band, WHITE knockout logo anchored A1 (~0.35in tall, true aspect ratio),
        sheet title in white Dosis 14 Bold, report date on the right side.
        Data content on every tab starts below: spacer row 3, header row 4."""
        band_cols = max(ncols, 10)  # narrow sheets still get room for logo + title + date
        ws.row_dimensions[1].height = 20
        ws.row_dimensions[2].height = 20
        if not os.path.exists(LOGO_PATH):
            raise RuntimeError(
                f"DigitalCLIQ logo not found at: {LOGO_PATH!r}\n"
                f"Canonical path: /Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/Resources/brand-assets/digital-cliq-logo-solid-1000px-wide.png"
            )
        img = XLImage(LOGO_PATH)
        aspect = img.width / img.height        # true source aspect, never squished
        img.height = 34                        # ~0.35in at 96dpi
        img.width = int(round(34 * aspect))
        ws.add_image(img, 'A1')
        # Title (row 1) + optional subtitle (row 2), merged left block after the logo
        t = ws.cell(1, 3, title)
        t.font = font(bold=True, color='WHITE', size=14, family='Dosis')
        t.alignment = Alignment(horizontal='left', vertical='center')
        ws.merge_cells(start_row=1, start_column=3, end_row=1, end_column=band_cols - 3)
        if subtitle:
            s = ws.cell(2, 3, subtitle)
            s.font = font(color='WHITE', size=9)
            s.alignment = Alignment(horizontal='left', vertical='center')
        ws.merge_cells(start_row=2, start_column=3, end_row=2, end_column=band_cols - 3)
        # Report date, right side, merged across rows 1-2
        d = ws.cell(1, band_cols - 2, date_text)
        d.font = font(bold=True, color='WHITE', size=10, family='Dosis')
        d.alignment = Alignment(horizontal='right', vertical='center')
        ws.merge_cells(start_row=1, start_column=band_cols - 2, end_row=2, end_column=band_cols)
        # Fill AFTER merging: merge_cells resets covered cells to unstyled MergedCells,
        # which would leave white holes in the band.
        for r in (1, 2):
            for c in range(1, band_cols + 1):
                ws.cell(row=r, column=c).fill = fill('BLUE')

    # Palette treatments only — Sky Blue = strong, Warm Grey = weak.
    # The Tier / Rating TEXT columns carry the meaning, never fill color alone.
    TIER_FILLS = {
        'TIER 1': fill('SKY'), 'TIER 2': None, 'TIER 3': None,
        'TIER 4': fill('GREY'), 'UNMEASURED': fill('GREY'),
    }

    has_cost = any(v['cost'] > 0 for v in vendor_rows)
    has_gross = any(v['gross_profit'] != 0 for v in vendor_rows)
    total_good = sum(v['good_leads'] for v in vendor_rows)
    total_sales = sum(v['sales'] for v in vendor_rows)
    total_cost = sum(v['cost'] for v in vendor_rows)
    total_gross = sum(v['gross_profit'] for v in vendor_rows)

    def write_header(ws, row, headers):
        for i, h in enumerate(headers, 1):
            c = ws.cell(row=row, column=i, value=h)
            c.font = font(bold=True, color='WHITE', size=11, family='Dosis')
            c.fill = fill('BLUE')
            c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
            c.border = border

    def write_row(ws, row, values, is_alt=False, fill_override=None):
        for i, val in enumerate(values, 1):
            c = ws.cell(row=row, column=i, value=val)
            c.font = font()
            c.border = border
            if fill_override: c.fill = fill_override
            elif is_alt: c.fill = fill('LIGHT_BG')

    def auto_width(ws, ncols, mn=10, mx=30):
        # Rows 1-2 are the masthead (long merged title/date strings) — size to data only.
        for c in range(1, ncols+1):
            w = max(mn, min(max((len(str(cell.value or ''))+2 for cell in ws[col_letter(c)] if cell.row > 2), default=mn), mx))
            ws.column_dimensions[col_letter(c)].width = w

    def accent_row(ws, row, ncols):
        for c in range(1, ncols+1):
            cell = ws.cell(row=row, column=c)
            cell.font = font(bold=True, color='WHITE')
            cell.fill = fill('ACCENT')
            cell.border = border

    # --- Tab 1: Executive Summary ---
    ws = wb.active
    ws.title = 'Executive Summary'
    ws.sheet_properties.tabColor = DC['BLUE']
    add_masthead(ws, 2, f'{dealership} — Marketing & Lead Analysis',
                 subtitle=f'Source: {config.get("crm_label","")} | Prepared by DigitalCLIQ | Digital Strategy & Development')

    kpis = [('Total Good Leads', f'{total_good:,}'), ('Total Sales', f'{total_sales:,}'),
            ('Overall Close Rate', f'{safe_div(total_sales,total_good)*100:.1f}%')]
    if has_cost:
        kpis += [('Total Spend', f'${total_cost:,.0f}'), ('CPL', f'${safe_div(total_cost,total_good):,.0f}'),
                 ('CPS', f'${safe_div(total_cost,total_sales):,.0f}')]
    if has_gross: kpis.append(('Gross Profit', f'${total_gross:,.0f}'))
    kpis += [('Vendors Analyzed', str(len(vendor_rows))), ('Artifacts Excluded', str(len(artifacts_excluded))),
             ('Sales Metric', vendor_rows[0]['sales_metric'] if vendor_rows else 'N/A')]

    write_header(ws, 4, ['Metric', 'Value'])
    ws.freeze_panes = 'A5'  # masthead (1-2) + spacer (3) + header (4) stay pinned
    for i, (m, v) in enumerate(kpis):
        r = 5 + i
        ws.cell(r, 1, m).font = font(bold=True)
        ws.cell(r, 2, v).font = font()
        for c in (1, 2):
            ws.cell(r, c).border = border
            if i % 2: ws.cell(r, c).fill = fill('LIGHT_BG')

    tr = 5 + len(kpis) + 2
    ws.cell(tr, 1, 'Vendor Tier Distribution').font = font(bold=True, color='BLUE', size=12, family='Dosis')
    tier_counts = defaultdict(int)
    for v in vendor_rows: tier_counts[v['tier']] += 1
    for tier_name in ['TIER 1','TIER 2','TIER 3','TIER 4','UNMEASURED']:
        cnt = tier_counts.get(tier_name, 0)
        if cnt > 0:
            tr += 1
            ws.cell(tr, 1, tier_name).font = font(bold=True)
            ws.cell(tr, 2, cnt).font = font()
            tf = TIER_FILLS.get(tier_name)
            if tf:
                ws.cell(tr, 1).fill = tf
                ws.cell(tr, 2).fill = tf
    auto_width(ws, 2, mn=20, mx=50)

    # --- Tab 3: Vendor ROI ---
    ws3 = wb.create_sheet('Vendor ROI')
    ws3.sheet_properties.tabColor = DC['SKY']

    hdrs = ['Tier','Vendor','Good Leads','Sales','Close Rate']
    if has_cost: hdrs += ['Spend','CPL','CPS']
    if has_gross: hdrs += ['Gross Profit','Avg Gross/Sale']
    hdrs += ['Lead Share','Rating','Sub-Sources']
    add_masthead(ws3, len(hdrs), f'{dealership} — Vendor Performance')
    write_header(ws3, 4, hdrs)
    ws3.freeze_panes = 'A5'

    for idx, v in enumerate(vendor_rows):
        r = 5 + idx
        vals = [v['tier'], v['vendor'], v['good_leads'], v['sales'],
                f'=IF(C{r}>0,D{r}/C{r},"-")']
        if has_cost:
            vals += [v['cost'], v['cpl'] if v['cpl'] > 0 else '-', v['cps'] if v['cps'] > 0 else '-']
        if has_gross:
            vals += [v['gross_profit'], v['avg_gross'] if v['avg_gross'] != 0 else '-']
        vals += [v['lead_share']/100, v['tier_label'], len(v['sources'])]
        write_row(ws3, r, vals, is_alt=idx%2==1, fill_override=TIER_FILLS.get(v['tier']))

        # Number formats
        ws3.cell(r, 5).number_format = '0.0%'
        c = 6
        if has_cost:
            ws3.cell(r, c).number_format = '$#,##0'; c += 1
            if v['cpl'] > 0: ws3.cell(r, c).number_format = '$#,##0'
            c += 1
            if v['cps'] > 0: ws3.cell(r, c).number_format = '$#,##0'
            c += 1
        if has_gross:
            ws3.cell(r, c).number_format = '$#,##0'; c += 1
            if v['avg_gross'] != 0: ws3.cell(r, c).number_format = '$#,##0'
            c += 1
        ws3.cell(r, c).number_format = '0.0%'

    # Totals
    tr = 5 + len(vendor_rows)
    accent_row(ws3, tr, len(hdrs))
    ws3.cell(tr, 1, 'TOTAL'); ws3.cell(tr, 2, 'All Vendors')
    ws3.cell(tr, 3, total_good); ws3.cell(tr, 4, total_sales)
    ws3.cell(tr, 5, f'=IF(C{tr}>0,D{tr}/C{tr},"-")'); ws3.cell(tr, 5).number_format = '0.0%'
    auto_width(ws3, len(hdrs))

    # --- Tab 4: Forecast ---
    if projections:
        ws4 = wb.create_sheet('Forecast')
        ws4.sheet_properties.tabColor = DC['SKY']
        fh = ['Month','Baseline','Lower 80%','Upper 80%','NADA Index']
        add_masthead(ws4, len(fh), f'{dealership} — Lead Forecast (NADA Seasonal Projection)')
        ws4.cell(3, 1, 'Based on NADA seasonal indices. Full ensemble forecast requires monthly data.').font = font(color='GREY', size=11)

        write_header(ws4, 4, fh)
        ws4.freeze_panes = 'A5'
        months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
        for i, p in enumerate(projections):
            r = 5 + i
            write_row(ws4, r, [months[p['month']-1], p['baseline'], p['lower_80'], p['upper_80'], p['nada_index']], is_alt=i%2==1)

        tr = 17
        accent_row(ws4, tr, len(fh))
        ws4.cell(tr, 1, 'TOTAL')
        for c in range(2, 5):
            ws4.cell(tr, c, f'=SUM({col_letter(c)}5:{col_letter(c)}16)')
        auto_width(ws4, len(fh))

    # --- Tab 7: All Providers ---
    ws7 = wb.create_sheet('All Providers')
    ws7.sheet_properties.tabColor = DC['ACCENT']

    ah = ['Source Name','Rolled Up To','Good Leads','Total Leads','Duplicates','Sales','Close Rate']
    add_masthead(ws7, len(ah), f'{dealership} — All Lead Sources (Ungrouped)')
    write_header(ws7, 4, ah)
    ws7.freeze_panes = 'A5'
    for idx, row in enumerate(sorted(parsed_rows, key=lambda x: -x['good_leads'])[:200]):
        r = 5 + idx
        write_row(ws7, r, [row['source_name'], rollup_vendor(row['source_name']),
                           row['good_leads'], row['total_leads'], row['duplicate_leads'],
                           row['sales'], f'=IF(C{r}>0,F{r}/C{r},"-")'], is_alt=idx%2==1)
        ws7.cell(r, 7).number_format = '0.0%'
    auto_width(ws7, len(ah))

    # Save
    os.makedirs(os.path.dirname(config['output_path']), exist_ok=True)
    wb.save(config['output_path'])
    return config['output_path']


# --- CLI ---

def cmd_detect(folder):
    if not os.path.isdir(folder):
        print(json.dumps({'error': f'Not found: {folder}'})); sys.exit(1)
    files = scan_folder(folder)
    print(json.dumps({'folder': folder, 'files_found': len(files),
                      'files': [{'filename':f['filename'],'crm':f['crm'],'label':f['label'],
                                 'columns':f.get('columns',[])[:10]} for f in files]}, indent=2))


def cmd_build(config_path):
    with open(config_path) as f: config = json.load(f)

    # Validate config before proceeding
    is_valid, val_errors = validate_config(config, source_path=config_path)
    if not is_valid:
        print(f'ERROR: Config validation failed with {len(val_errors)} error(s). Aborting.', file=sys.stderr)
        sys.exit(1)

    crm = config['crm']
    parser = PARSERS.get(crm)
    if not parser: print(f'ERROR: Unknown CRM: {crm}'); sys.exit(1)

    all_parsed = []
    for fpath in config['input_files']:
        if not os.path.isabs(fpath): fpath = os.path.join(os.getcwd(), fpath)
        rows = parser(fpath)
        all_parsed.extend(rows)
        print(f'  Parsed {len(rows)} sources from {os.path.basename(fpath)}')

    if not all_parsed: print('ERROR: No data parsed.'); sys.exit(1)

    # Validate parsed rows
    validate_parsed_rows(all_parsed, source_path=config_path)

    vendor_rows = rollup_sources(all_parsed)
    excluded = [v['vendor'] for v in vendor_rows if v['vendor'].lower() in [s.lower() for s in config.get('exclude_sources',[])]]
    vendor_rows = [v for v in vendor_rows if v['vendor'] not in excluded]
    print(f'  {len(vendor_rows)} vendors ({len(excluded)} excluded)')

    total_good = sum(v['good_leads'] for v in vendor_rows)
    projections, proj_total = nada_projection(total_good)

    config['crm_label'] = {'momentum':'MomentumCRM','vinsolutions':'VinSolutions',
                           'tekion':'Tekion','dealersocket':'DealerSocket'}.get(crm, crm)

    out = build_workbook(config, vendor_rows, all_parsed, projections, excluded)

    # Validate
    try:
        import openpyxl
        wb = openpyxl.load_workbook(out)
        for ws in wb.worksheets: print(f'  {ws.title}: OK')
    except Exception as e: print(f'  Validate: {e}')

    total_sales = sum(v['sales'] for v in vendor_rows)
    print(f'\n{"="*50}\n{config["dealership"]}\n{"="*50}')
    print(f'Good Leads:  {total_good:,}')
    print(f'Sales:       {total_sales:,}')
    if total_good > 0: print(f'Close Rate:  {total_sales/total_good*100:.1f}%')
    if any(v['cost']>0 for v in vendor_rows): print(f'Spend:       ${sum(v["cost"] for v in vendor_rows):,.0f}')
    print(f'Vendors:     {len(vendor_rows)}')
    print(f'Forecast:    {proj_total:,} leads/yr')
    print(f'Output:      {out}')


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('Usage:\n  dealership_forecast.py detect <folder>\n  dealership_forecast.py build <config.json>')
        sys.exit(1)
    {'detect': cmd_detect, 'build': cmd_build}.get(sys.argv[1], lambda _: print(f'Unknown: {sys.argv[1]}'))(sys.argv[2])
