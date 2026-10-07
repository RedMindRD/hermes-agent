---
name: pipeline-check
description: "Find stale tier-A leads and overdue follow-ups."
version: 1.0.0
author: RedMind (RedMindRD)
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    category: wh-crm
    tags: [crm, sales, pipeline]
---

# Pipeline check

Finds leads that are slipping and suggests what to do. Suggestions only:
nothing is changed unless the owner says so.

## Tools

Only the `wh-crm` MCP tools: `list_hot_leads`, `get_contact`, `list_reminders`,
`list_sequences`, `list_enrollments`, `create_reminder`.

## Steps

1. **Stale tier-A leads.** `list_hot_leads(limit=50)`. A lead is stale when it
   is older than 24 hours and `first_response_at` is null (nobody has replied
   to it). For up to 5 stale leads, `get_contact(id)` to read the tier reason,
   owner and notes.
2. **Overdue follow-ups.** `list_reminders(kind="overdue")`: group by owner,
   oldest first.
3. **Stuck sequences (optional).** `list_sequences()`; flag active sequences
   with many enrollments and a reply rate far below the others.
4. **Report** (short, for Telegram):
   - stale tier-A leads: name, age, owner, one-line reason;
   - overdue follow-ups per owner (count + oldest);
   - 1–3 suggested actions, each concrete, e.g. "Ask Ravi to call <name> today",
     "Create a follow-up for <name> tomorrow 10:00 for <owner>?".
5. **Act only on request.** If the owner accepts a suggestion that needs a
   write (only `create_reminder` here), read back contact, title, time and
   assignee and wait for a yes before calling it.

## Rules

- Use only the wh-crm MCP tools listed above.
- Never message a customer, directly or by any other tool or channel. Suggest
  that a person replies instead.
- Never touch the do-not-contact list or consent.
- Always confirm before any write action.
- Never invent numbers or contact details; if data is missing, say so.
