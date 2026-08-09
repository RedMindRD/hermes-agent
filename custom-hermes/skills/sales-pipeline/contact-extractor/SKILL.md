---
name: contact-extractor
description: Extracts public business contact details from web pages.
version: 1.0.0
author: redmindtech.ai
metadata:
  hermes:
    category: sales-pipeline
    tags: [sales, leads, contacts]
    related_skills: [company-researcher, lead-verifier]
---

# Contact Extractor Skill

Stage 4 rules: pull emails, phone numbers, and LinkedIn profiles for a company
from its own public pages. Extraction only — verification is `lead-verifier`'s
job, and everything found starts as `unverified`.

## When to Use

Loaded alongside `company-researcher` inside research subagents; standalone
via `/contact-extractor <url>` to mine a specific page.

## Procedure

1. Priority order of sources: Contact page > Team/About page > page footer >
   `web_search "<company>" email contact` snippets > WHOIS-style public
   listings. Cite the `source_url` for every datum.
2. **Emails**: prefer a named person's address over `info@`/`sales@`, but
   keep the generic one as fallback. Handle obfuscation (`name [at] domain`,
   `name(dot)lastname@...`). Record exactly as deobfuscated — do NOT
   pattern-guess addresses (`firstname@domain` because a colleague has that
   shape). A guessed address is fabricated data.
3. **Phones**: normalize to E.164 where the country is known
   (`+91 98… `), keep the raw form in notes otherwise. Prefer numbers labeled
   business/sales/office over generic toll-free.
4. **LinkedIn**: company page URL + personal profiles of decision-makers when
   they're linked from the company's own site or appear in search snippets.
5. Attach each contact to a person `{name, role}` when possible; company-level
   contacts get `name: ""`.

## Pitfalls

- `example@`, `noreply@`, and the web-design agency's credit-line email are
  not contacts.
- One page listing 30 branch emails: take HQ + the branch matching the ICP
  geography, not all 30.
- Personal data discipline: business contact info from the company's own
  public pages only. No data brokers, no paid enrichment scraping, nothing
  from behind a login.

## Verification

Every extracted contact has a `source_url` on the company's own domain (or a
cited public directory), and no email was constructed by analogy.
