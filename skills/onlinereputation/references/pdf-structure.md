## PDF Structure (Page Layout)

Visual-first per the Design System block above: the generator hand-authors HTML + CSS from the canonical component library (stat cards, stat band, callout bars, comparison splits, checklist rows, ghost numerals, running furniture) and renders to PDF. Max ~55% of any page as body text.

### Page 1: Canonical Dark Cover
- The `cover-portrait.html` recipe rendered inline: full-bleed `#070A15 → #151E37` gradient with glow orbs
- White DigitalCLIQ logo top-left, cursor glyph lower-right, pillars strip at the bottom
- Eyebrow, ALL-CAPS display title with Sky Blue accent word, accent rule, subtitle naming the dealer
- Location: brand and address meta line; "Prepared by DigitalCLIQ. Digital Strategy & Development." + dealer + generation timestamp

### Page 2: Overall Ratings Snapshot
- Section header (eyebrow + Dosis Bold H2 + Sky Blue accent rule + ghost numeral)
- KPI stat-card row: Google, Yelp, DealerRater, CarFax (Card White `#FBFBFD` tiles, `#D8E1F0` border, Sky Blue stat values, SVG star rows, brand TTFs carry no star glyph). Rating quality carries an explicit STRONG / MIXED / WEAK text label, never color alone
- Delta indicators if prior data exists (UP / DOWN / FLAT with signed values)
- Dark stat band: total review volume across platforms
- Data-pulled timestamps line + "Inside this report" numbered TOC cards

### Page 3+: Platform Deep Dive (Subject Dealer)
- Section header: "Google Reviews" with SVG star row, rating, and review count
- Positive reviews table (last 5)
- Negative reviews table (last 5)
- Positive vs negative themes as a comparison split (negative greyed with Warm Grey label, positive blue-bordered with Digital Blue label); trending issues as a Callout Tint `#EDF2F9` bar with Digital Blue left bar. The bold text lead-ins carry the meaning
- Repeat for Yelp, DealerRater, CarFax

### Competitor Comparison
- Section header: "Competitor Comparison"
- Side-by-side table (Digital Blue header row, white Dosis text, alternating White / Callout Tint rows, `#D8E1F0` grid): Dealer | Google | Yelp | DealerRater | CarFax | Total Reviews
- Subject dealer highlighted (`#D8E1F0` row fill, bold, "(subject)" label)
- "What Competitors Are Doing Right" section with bullet insights per competitor

### Recommendations & SEO/LLM Impact
- Section header: "Recommendations", checklist rows (rounded check glyph in Digital Blue), actionable items in priority order
- Section header: "Why Online Reviews Matter for SEO & AI"
- SEO/LLM educational copy (standard on every report), rendered as a Callout Tint callout bar with a Digital Blue left bar, never a bare paragraph run

### Month-over-Month Trends (if delta data)
- Section header: "Month-over-Month Trends"
- Stat-card row: new reviews per platform since the prior snapshot
- Table: Platform | Prior Rating | Current Rating | Change (UP / DOWN / FLAT) | Prior Count | Current Count | New Reviews
- Callout-bar summary of improvements/declines

---
