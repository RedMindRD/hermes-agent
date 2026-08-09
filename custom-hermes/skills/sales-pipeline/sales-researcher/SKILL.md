---
name: sales-researcher
description: Builds a pain-point hypothesis for each hot lead.
version: 1.0.0
author: redmindtech.ai
metadata:
  hermes:
    category: sales-pipeline
    tags: [sales, research, personalization]
    related_skills: [outreach-writer, lead-qualifier]
---

# Sales Researcher Skill

Stage 8 prep: for each Hot lead, connect what we observed about the company
to a specific pain our product removes (per `product.md`). The output is the
one-line hypothesis that makes outreach personal instead of templated.

## When to Use

Loaded by `/prospect-pipeline` for Hot leads before drafting; standalone via
`/sales-researcher <company>` before a call or manual email.

## Procedure

1. Inputs: the lead's research JSON (`signals`, `services`, `size`), the
   pain bullets from `product.md`, and `icp_reasons` (what made them Hot).
2. Pick the ONE observed signal that most plausibly maps to one of our pain
   bullets. Observed > inferred: "they're hiring 3 dispatch coordinators"
   beats "logistics firms usually struggle with dispatch".
3. If nothing observed maps cleanly, do one extra `web_search`
   (`"<company>" reviews`, `"<company>" hiring`) — five minutes max. Still
   nothing? Write hypothesis `generic` — the outreach-writer will fall back
   to the industry-level angle, honestly, instead of faking specificity.
4. Persist to `leads.pain_hypothesis`:
   `"<observed signal> -> likely <pain> -> our <capability> angle"`.

## Pitfalls

- The hypothesis must survive being read BY the prospect. "You seem
  understaffed" is an insult; "you're growing the dispatch team" is a
  compliment with the same evidence.
- One hypothesis per lead. Two angles in one first-touch email reads as a
  mail-merge blast.
- Never fabricate a trigger event ("saw your recent funding" when there was
  none) — a false personalization destroys the reply before it's read.

## Verification

Every Hot lead has `pain_hypothesis` set, and each non-`generic` hypothesis
names a signal actually present in that lead's stored research.
