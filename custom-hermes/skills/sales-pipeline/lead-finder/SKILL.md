---
name: lead-finder
description: Finds candidate companies matching the ICP via web search.
version: 1.0.0
author: redmindtech.ai
metadata:
  hermes:
    category: sales-pipeline
    tags: [sales, leads, discovery, search]
    related_skills: [prospect-pipeline, company-researcher]
---

# Lead Finder Skill

Discovery strategies for Stage 1 of the prospect pipeline: turn the ICP into
`web_search` queries and return a deduplicated candidate list. Finds companies,
not contacts — contact extraction happens later.

## When to Use

Loaded by `/prospect-pipeline` at Stage 1, or standalone via `/lead-finder
<segment>` to test what a search strategy yields before a full run.

## Prerequisites

- `$HERMES_HOME/context/icp.md` read (industry, geography, size, exclusions).
- `web_search` tool available.

## Procedure

1. Build 4-6 query variants per run; rotate strategies day to day so runs
   don't rediscover the same first page of Google:
   - **Directory mining**: `"<industry>" companies in <city/region>`,
     `top <industry> firms <region>`, industry-association member lists.
   - **Pain-signal search**: job boards / posts implying the pain
     (e.g. hiring for the role our product replaces or augments).
   - **Adjacency**: customers of complementary vendors, exhibitor lists of
     relevant trade shows, "alternatives to <big competitor>" listicles.
   - **Local**: maps-style queries (`<service> near <city>`) for
     brick-and-mortar segments.
2. From results, collect candidate companies with a **root domain** each —
   the domain is the dedupe key. Strip `www.`, lowercase. Directories,
   aggregators, and marketplaces (Yelp, JustDial, Clutch, LinkedIn itself)
   are sources, never candidates.
3. Apply the ICP hard filters that are visible at this distance (geography,
   obviously wrong industry, exclusion list). Don't guess size yet.
4. Dedupe against the CRM:
   `sqlite3 $HERMES_HOME/data/leads.db "SELECT domain FROM companies;"` — drop
   any already-known domain.
5. Return: `[{name, domain, url, source_query, why_candidate}]` — aim for
   ~15 net-new candidates; stop searching when you have them.

## Pitfalls

- A franchise/chain has many locations, one buyer — one candidate per brand.
- Foreign-language results in the wrong geography usually mean the query
  needs a region qualifier, not that the segment is empty.
- If two consecutive runs yield < 5 net-new candidates, report search
  exhaustion for this segment in the summary — the ICP geography or industry
  terms need widening. Don't silently pad with weak matches.

## Verification

Every returned candidate has a live-looking root domain, is not in
`companies`, and has a one-line `why_candidate` tied to an ICP criterion.
