---
name: weekly-script-review
description: "Weekly reply-rate review of outbound sequences."
version: 2.0.0
author: RedMind (RedMindRD)
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    category: wh-crm
    tags: [crm, sales, outbound, review]
---

# Weekly script review

Looks at how the outbound sequences performed and reports what to try next.
**It never edits templates, sequences, variants or settings**: the owner (or a
person they choose) makes changes in the CRM.

The CRM runs its own review every Sunday at 20:00 (`scripts:weekly-review`) and
stores suggestions that a person accepts or dismisses under Reports →
Outbound learning. This skill reads those results; it does not replace them.

## Tools

Only the `wh-crm` MCP tools (read-only here): `get_learning_report`,
`list_script_suggestions`, `list_sequences`, `list_enrollments`,
`list_review_queue`, `get_report`, `get_kpis`.

## Steps

1. **Funnel.** `get_learning_report(report="funnel_by_sequence")` for the last
   28 days (`from_date`/`to_date`), then `"funnel_by_source"`: prospects →
   contacted → replied → meeting → won with step rates. Name the best and worst
   sequence and source.
2. **Variants.** `get_learning_report(report="variants")` for the same window.
   Per step, report each variant's sent / replied / reply rate and the
   `verdict`:
   - `winner`: the leader is ahead at 95% confidence (z in the verdict);
   - `no_clear_winner`: enough sends, difference not reliable: say so;
   - `collecting`: say how many more sends are needed (`needed`);
   - `single_arm`: only one version is sending.
   Never call a variant a winner unless the verdict says `winner`.
3. **Objections.** `get_learning_report(report="objections")`: the top
   AI-tagged objections with counts and shares, and how many replies are still
   waiting to be tagged.
4. **CRM suggestions.** `list_script_suggestions(status="pending")`: list them
   with their id and summary so the owner can decide in the CRM.
5. **Context.** `get_kpis` for the last 7 days (response time, tiers, meetings)
   and `get_report(days=7)` for delivery/read rates. `list_review_queue` for
   rejected-draft patterns if relevant.
6. **Report** (short): top and bottom sequence with numbers, the variant
   verdicts, the top three objections, the pending CRM suggestions, and 2–4
   concrete ideas of your own (opening line, hook use, step timing, call to
   action), each marked "suggestion - not applied".

## Rules

- Use only the wh-crm MCP tools listed above.
- Never edit templates, sequences, steps, variants or settings, and never ask a
  tool to. Accepting or dismissing suggestions is done by a person in the CRM.
- Never send messages to customers.
- Never touch the do-not-contact list or consent.
- Base every number on tool output; do not estimate missing data or invent
  significance.

## Schedule (suggestion, documentation only)

Sundays at 20:30 IST (after the CRM's own review), delivered to Telegram, e.g.
`hermes cron create "30 20 * * 0" "Run the WH-CRM weekly script review" --skill weekly-script-review --deliver telegram`
(gateway local time; 20:30 IST = 15:00 UTC).
