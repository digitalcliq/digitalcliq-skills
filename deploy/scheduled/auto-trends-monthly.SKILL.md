---
name: auto-trends-monthly
description: Monthly DigitalCLIQ automotive market trend report: PDF, blog HTML, and publishing kit, on the 5th
---

Run the monthly DigitalCLIQ Automotive Market Trend Report.

Invoke the `anthropic-skills:auto-trends` skill with the Skill tool and follow its SKILL.md end to end. Region: Southern California (the default). The vault root is `/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ` (note the `HQ`); there is no vault-scoped copy of this skill.

Find the skill's scripts ONLY through the Skill tool: when the skill loads it prints "Base directory for this skill: ...". Run every script from that folder, double-quoted, as the SKILL.md shows with `"${CLAUDE_SKILL_DIR}/<file>"` (if the variable did not expand, substitute that printed Base directory; `<base>` below means that folder). Never use `find`, `mdfind`, `locate` or `ls -R` to hunt for the skill or its scripts: stale copies of this skill exist elsewhere on disk (`~/Desktop/Skills`, old synced folders) and running or patching one of them is how past fixes landed in the wrong place.

This run starts with no memory of any prior conversation, so work only from the skill file and the vault. Key points the skill will walk you through, restated here so nothing is skipped:

1. PRE-FLIGHT. Read `Context/vault-facts.md` first. Then confirm these two directories are NON-EMPTY before generating anything:
   - `Resources/brand-assets/fonts/` (11 Dosis + Roboto Slab .ttf files)
   - `Resources/design-system/templates/` (render_check.py, tokens.css, cover-portrait.html, cover-16x9.html)
   A vault sync has emptied both before. If either is empty, restore from the frozen read-only copy at `~/Documents/backed up/DigitalCLIQ/Resources/` and say so in your summary. The generator hard-fails on missing fonts.

2. READ THE PRIOR RUN FIRST. Check `Intelligence/market/auto-trends/` for the most recent archived JSON. If one exists, read it BEFORE researching and use it to target the research at what actually changed rather than rediscovering the market from zero. The prior archive is a checklist of metrics to refresh, never a source: re-verify every carried-forward figure at its original publisher, with its publication date, before it goes back into the report, and do not reuse its prose (outlook, risks, "record" claims, event dates that have passed). Report month-over-month movement on the headline numbers. If the folder is empty, this is the baseline run.

3. RESEARCH. Launch the 5 parallel research agents per the skill (New Vehicle, Used Vehicle, Fixed Ops, Parts, Strategic/Macro), and paste the skill's Period discipline block into every agent prompt. Each finding comes back as {stat, value, source, url, published: YYYY-MM-DD, period: YYYY-MM | YYYY-Qn | YYYY-Hn | YYYY | YTD, kind: actual | forecast | estimate | market-implied, geo}. Do not fabricate numbers. Period discipline, in short:
   - Every stat needs a named source, the page URL, a publication date and a data period.
   - An "actual" published before its period ended is the wrong year or a forecast: reject it and keep searching. Early in the month (this run fires on the 5th), search results surface LAST YEAR's edition of the same monthly report first; check every same-month figure against its publication year.
   - If this month's figure is not out yet, use the latest published month and say so in the copy ("July 2026 data").
   - Label forecasts and market-implied odds as such, in `kind` and in the words that print next to the number.
   - Any "record", "peak" or "high" in prose carries its as-of date in the same sentence.
   - When two findings conflict for the same metric, the later publication date wins. Never keep the older figure "for internal consistency".

4. BUILD THE JSON. Fill every field in the skill's schema, including the fields that keep the report from going stale: `executive_summary.hero`, `executive_summary.headline_stats`, `executive_summary.throughline`, `fixed_ops.hero`, each section's `headline`, and `metadata.period_label`. Every hero, headline stat and metric also carries `source`, `url`, `published`, `period` and `kind` from the research payload, and each metric `detail` ends with its citation `(Publisher, Month YYYY)`. The generator holds no hardcoded stats by design. An unfilled field renders as a thinner page, never as a prior month's number, so fill them all fresh.

   Then run the skill's claims check (Step 4b): `python3 "<base>/validate_claims.py" /tmp/auto_trends_data.json`. It is warn-only this cycle and always exits 0. If it prints any ERROR or WARN line, fix the DATA (re-research the missing URL or publication date, correct the period or kind, move to the latest published month, add the as-of date) and re-run it until it is clean or every remaining line is explained in the report-back. Never edit the checker, never work around it.

5. GENERATE. Run `generate_trends_report.py` for the PDF, then `generate_blog_assets.py` for the blog HTML, publishing kit, and JSON archive. Both write to the vault `outputs/` folder. The PDF generator re-runs the claims check and writes `Auto_Trends_Report_YYYY-MM-DD.facts.json` next to the PDF; that is the reviewer's manifest (append prose-only figures to it as the skill's Final QA step describes, never rewrite it).

6. RENDER GATE (mandatory, per root rule 17). Rasterize every PDF page and READ each one against `Resources/design-system/Visual-QA.md`. For the blog HTML, run the deterministic pre-check instead of screenshots: `python3 "<base>/validate_claims.py" --blog-html "<path to the _blog.html>"` confirms every JSON-LD block parses and there are no em dashes and no placeholder tokens; fix anything it prints and re-run. Do NOT launch headless Chrome to screenshot the blog. The HTML visual gate is not run unattended; say so in the report-back so Drew reads the blog in a browser before publishing.

   Never fix anything by hand-editing the output files. Fix defects in the data first (for example a trailing "(Publisher, Month YYYY)" on each detail string, or a shorter caption). If the generator itself must change, patch a scratch copy of the generator and render from it; never edit the installed copy in the skill's base directory, and never patch `~/Desktop/Skills`. Save the diff to `outputs/auto-trends-patches/YYYY-MM-DD.diff` (`diff -u "<base>/generate_trends_report.py" "<scratch copy>" > ...`, make the folder if needed) and list it in the report-back. Repeat until two consecutive fully clean passes. Then run the post-flight validator on the PDF, path double-quoted:
   `python3 "/Users/drewmoon/Desktop/DigitalCLIQ Brain HQ/.claude/skills/post_flight.py" "<PDF path>" --min-pages 8`

7. DO NOT PUBLISH ANYTHING. Produce drafts only. Never post to LinkedIn, never publish to the website, never send email. Drew reviews and publishes himself. Remind Drew in the report-back that the kit's email draft goes out as BCC: the recipient list spans competing stores and several clients.

8. REPORT BACK. 8 to 10 lines: region, period, source count, one highlight per section, month-over-month movement versus the archive, how many render passes ran and what defects were caught, the claims-check result (clean, or the remaining lines and why), the blog pre-check result plus "HTML visual gate not run unattended", any patch diff saved under `outputs/auto-trends-patches/`, and the full paths to the PDF, the blog HTML, the publishing kit and the facts manifest.

Finally, append a short entry to today's `Daily/YYYY-MM-DD.md` noting the report ran, linking [[DigitalCLIQ]], and listing the three output paths.
