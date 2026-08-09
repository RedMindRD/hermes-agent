---
name: company-researcher
description: Researches one company for industry, size, and buyers.
version: 1.0.0
author: redmindtech.ai
metadata:
  hermes:
    category: sales-pipeline
    tags: [sales, leads, research]
    related_skills: [prospect-pipeline, lead-finder, contact-extractor]
---

# Company Researcher Skill

Stages 2-3 of the pipeline: given a candidate company (name + URL), build a
factual profile from its public web presence. This is the checklist handed to
each research subagent; it defines the JSON contract the pipeline consumes.

## When to Use

Loaded by `/prospect-pipeline` research subagents (one company each), or
standalone via `/company-researcher <name or url>` to profile a single firm.

## Procedure

1. `web_extract` the homepage. Then, if linked: About, Services/Products,
   Contact, Team/Leadership pages. 4-5 page fetches max per company.
2. One `web_search` for `"<company name>" <location>` to catch news, funding,
   reviews, or LinkedIn company page data not on the site.
3. Fill the profile:
   - **industry** — what they actually do, not their slogan.
   - **size** — employee band. Signals: team page headcount, LinkedIn
     "X employees", "our N offices", job-posting volume. Say `unknown` over
     guessing.
   - **location** — HQ city/region/country (footer, contact page).
   - **services** — 1-3 sentences, concrete.
   - **decision_makers** — names + roles matching the ICP's buyer roles
     (founders, owners, relevant heads). Public info only.
   - **signals** — anything the qualifier can score: hiring, expansion,
     funding, tech stack, complaints in reviews, outdated tooling visible.
4. Hand off found people/pages to `contact-extractor` rules for emails,
   phones, LinkedIn URLs.

## Output contract

Return exactly one JSON object (the pipeline parses it):

```json
{
  "name": "", "domain": "", "website": "",
  "industry": "", "size": "", "location": "", "services": "",
  "decision_makers": [{"name": "", "role": ""}],
  "contacts": [{"name": "", "role": "", "email": "", "phone": "", "linkedin": "", "source_url": ""}],
  "signals": [""],
  "research_notes": ""
}
```

Empty string / empty list for anything not found. Never invent values.

## Pitfalls

- Marketing pages inflate size ("global leader" ≠ big). Trust footers, team
  pages, and LinkedIn numbers over prose.
- A site that's a single landing page with no contact info is a signal in
  itself — note it; the qualifier will penalize reachability.
- Don't log into anything, don't scrape behind auth walls, don't use
  LinkedIn beyond what search snippets and public pages show.

## Verification

The JSON parses, `domain` matches the candidate, and every `contacts[].email`
came from a cited `source_url` — not from pattern-guessing.
