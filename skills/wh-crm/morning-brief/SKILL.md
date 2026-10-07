---
name: morning-brief
description: "WH-CRM morning brief for the owner on Telegram."
version: 1.0.0
author: RedMind (RedMindRD)
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    category: wh-crm
    tags: [crm, sales, daily, telegram]
---

# Morning brief

A short daily summary of the WH-CRM pipeline, sent to the owner (Telegram).
Read-only: this skill never changes anything in the CRM.

## Tools

Only the `wh-crm` MCP tools (in Hermes they are prefixed `mcp_<server>_`):
`list_hot_leads`, `list_sequences`, `list_enrollments`, `list_reminders`,
`list_review_queue`, `get_kpis`.

## Steps

1. **Hot leads.** `list_hot_leads(limit=10)`. Count them; name up to 3 where
   `first_response_at` is null (nobody has answered yet) with the lead's age.
2. **Replies overnight.** `list_sequences()`; for each sequence with `replied > 0`,
   `list_enrollments(sequence_id, status="replied", limit=20)` and keep those whose
   `updated_at` is in the last 16 hours. List contact name + sequence (max 5).
3. **Meetings today.** `list_reminders(kind="upcoming")`; keep items with a
   `meet_link` whose `remind_at` is today (owner's timezone, IST unless told
   otherwise). Time + contact + owner.
4. **Overdue follow-ups.** `list_reminders(kind="overdue")`: count only.
5. **Drafts waiting.** `list_review_queue(limit=50)`: the `pending` count and the
   oldest draft's age.
6. **KPIs.** `get_kpis(from_date=<7 days ago>, to_date=<today>)`: median lead
   response time, share answered within 5 minutes, tier A/B/C/D counts,
   meetings booked.
7. Write the message (format below) and deliver it.

## Message format

Plain text, at most ~15 lines, no tables:

```
WH-CRM - <weekday, date>
Hot leads: <n> (<k> not answered yet: <name> <age>, ...)
Replies overnight: <n> - <name> (<sequence>), ...
Meetings today: <time> <contact> (<owner>), ... | none
Overdue follow-ups: <n>
Drafts waiting for you: <n> (oldest <age>)
Last 7 days: median first reply <x> min, <y>% within 5 min; tiers A<a> B<b> C<c> D<d>; meetings <m>
Next: <one suggested action, e.g. "review 6 drafts" or "call <name>">
```

If a tool fails, write the line as "<section>: unavailable (<short reason>)" and
carry on with the rest. Never guess numbers.

## Rules

- Use only the wh-crm MCP tools listed above.
- Never send a message to a customer, directly or through any other channel or tool.
- Never touch the do-not-contact list, consent or opt-outs.
- This skill is read-only. If the owner replies asking for an action (approve a
  draft, enroll someone), confirm the exact ids with them before calling any
  write tool, one action at a time.
- Do not paste phone numbers or emails into the brief; names are enough.

## Schedule (suggestion, documentation only)

Daily at 08:30 IST, delivered to Telegram, e.g.
`hermes cron create "30 8 * * *" "Run the WH-CRM morning brief" --skill morning-brief --deliver telegram`.
Hermes cron uses the gateway's local time; set the server to Asia/Kolkata or
convert (08:30 IST = 03:00 UTC).
