# plan.json contract (for /blog-content)

Author ONE `plan.json` (data only). The scripts render everything from it. Read this instead of
opening the Python. Every field optional except `meta` + `pieces`.

```jsonc
{
  "meta": { "client", "business_type", "period_label", "generated_on", "goal",
            "prepared_by", "primary_market", "semrush_used": true|false },
  "brand_voice": { "summary", "tone_attributes":[], "reading_level",
                   "do":[], "dont":[], "sample_phrases":[], "sources":[] },
  "pieces": [{
    "id", "title", "type":"Blog"|"Landing Page", "funnel_stage":"TOFU"|"MOFU"|"BOFU",
    "target_date", "word_count_target": 2000, "status", "asset_id",   // asset_id -> assets[].id
    "seo": { "primary_keyword": {"term","volume","kd","intent"},
             "secondary_keywords":[{"term","volume","kd"}], "serp_competitors":[],
             "content_gap", "meta_title", "meta_description", "url_slug",
             "internal_links":[], "schema_type", "search_intent" },
    "aeo": { "target_question", "citable_answer", "entities":[],
             "structured_data", "eeat_signals":[], "why_cited" },
    "outline": { "h1", "sections":[{"h2","h3":[],"key_points":[]}],
                 "faq":[{"q","a"}], "sources":[] },
    "body_markdown": "## H2 ...\\n\\nparagraph **bold** ...\\n\\n- bullet"
  }],
  "assets": [{ "id","title","type","platform","model","settings","prompt",
               "credits","src_url","src_thumb_url","web" }],
  "contact": { "company","tagline","contact_name","title","email","phone","website","note" }
}
```

## Author-once rule (no duplicate prose)
`outline.faq`, `aeo.citable_answer`, and the `outline` skeleton are authored ONCE here.
- `write_docs.py` renders `body_markdown` + (if the body has no FAQ heading) appends `outline.faq`.
- So put the FAQ in `outline.faq` and do NOT also retype it inside `body_markdown`.
- The Excel briefs read `seo`/`aeo`/`outline` directly. Never retype the same content twice.

## body_markdown supported syntax
`#`/`##`/`###` headings (a body `#` H1 is auto-demoted; the title already renders), `-`/`*` bullets,
`1.` numbered, blank-line paragraphs, `**bold**`. NOT supported: markdown tables, inline `![img]()`.

## What the scripts fill in
`download_assets.py` sets `assets[].file` + `assets[].thumb` from `src_url`/`src_thumb_url`.
`write_docs.py` sets each `pieces[].doc_path`. You only author URLs + prose once.
