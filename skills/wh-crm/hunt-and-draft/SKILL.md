---
name: hunt-and-draft
description: "Find prospects, get owner approval, enroll in a sequence."
version: 1.0.0
author: RedMind (RedMindRD)
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    category: wh-crm
    tags: [crm, sales, prospecting, outbound]
---

# Hunt and draft

Input from the owner: **niche**, **city** and **count** (how many prospects
they want to look at, max 50 per batch). Example: "hunt 20 dental clinics in
Chennai".

The result is never a sent message: approved prospects become contacts, get
enrolled in a sequence, and the first messages wait in the CRM review queue
(when approval mode is on) for the owner.

## Tools

Only the `wh-crm` MCP tools: `trigger_prospect_search`, `list_prospects`,
`approve_prospects`, `list_sequences`, `enroll_in_sequence`, `list_review_queue`.

## Steps

1. **Confirm the search.** Repeat niche, city, country (if known) and count to
   the owner and ask "Start the search?". A search uses scraping/LLM credits.
   Only on a clear yes: `trigger_prospect_search(industry=<niche>, location=<city>, ...)`.
   Keep the returned `brief`.
2. **Wait for results.** The run is in the background. Check
   `list_prospects(status="pending", brief=<brief>, limit=<count>)` every few
   minutes (stop after ~30 minutes and tell the owner if nothing arrived).
3. **Summarise.** Show the best `<count>` by `score`: numbered list with
   id, name, company, role/decision maker, score, email status and the hook
   (one line each). Mention prospects without a phone or a verified email.
4. **Ask which to approve.** "Reply with the numbers or ids to approve, or 'none'."
   Never assume "all"; if the owner says "all", read back the exact id list and
   ask them to confirm it.
5. **Approve.** `approve_prospects(prospect_ids=[...])` with exactly the
   confirmed ids (batches of max 50). Keep the returned `contact_ids`.
6. **Choose the sequence.** `list_sequences()`; show active ones (name, steps,
   reply rate) and ask which one. Do not enroll in a paused sequence without
   saying so.
7. **Enroll.** After a yes on "Enroll <n> contacts in <sequence>?":
   `enroll_in_sequence(sequence_id, contact_ids=[...])`. Report enrolled and
   skipped with the reason in plain words (already enrolled, do-not-contact,
   no phone, no email ...).
8. **Point to the review queue.** `list_review_queue(sequence_id=...)` and
   tell the owner how many drafts are waiting. Approving drafts is a separate,
   explicit step (one draft at a time with `approve_draft`, only when the owner
   approves that draft).

## Rules

- Use only the wh-crm MCP tools listed above.
- Never send a message to a customer yourself; sequences and the review queue
  do the sending after compliance checks.
- Never touch the do-not-contact list or consent. Skipped "do_not_contact"
  contacts stay skipped; do not try to work around it.
- Always confirm before every write action (search, approve, enroll), with the
  exact ids or names. No "approve all".
- Never invent prospect data; report only what the tools return.
- Do not scrape or look up people on LinkedIn or elsewhere yourself.
