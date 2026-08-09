---
name: response-classifier
description: Classifies inbound replies and updates lead stages.
version: 1.0.0
author: redmindtech.ai
metadata:
  hermes:
    category: sales-pipeline
    tags: [sales, responses, crm]
    related_skills: [followup-engine, crm-manager]
---

# Response Classifier Skill

Stage 11: when a prospect replies (forwarded by the user, or arriving through
a connected email/messaging integration), classify the intent, record it, and
move the lead to the right stage so the cadence reacts correctly.

## When to Use

- The user pastes/forwards a reply: `/response-classifier` + the message.
- An inbound integration surfaces a reply from a known lead contact.

## Procedure

1. Identify the lead: match sender email/phone against `contacts`, else fuzzy
   match the company name and confirm with the user. Never guess silently —
   a reply logged against the wrong lead corrupts two cadences at once.
2. Classify intent (one of):
   - `interested` — wants a call/info/pricing, asks questions.
   - `not_now` — timing objection, "try next quarter", mild positive.
   - `reject` — clear no.
   - `unsubscribe` — "stop", "remove me", any anger, ANY legal reference.
   - `other` — auto-replies, bounces, wrong person, ambiguous.
3. Record with one call — `crm.py log-response --lead-id N --intent
   <intent> --channel <ch> --body-file -` (body on stdin). It inserts the
   response, applies the stage transition, sets `do_not_contact` on
   unsubscribe, and cancels pending drafts atomically; its JSON reply tells
   you `new_stage` and `drafts_cancelled`. The intent semantics:
   - `interested` -> stage `replied_interested`; draft a suggested reply for
     the user (not auto-sent) and flag it "reply ASAP".
   - `not_now` -> stage `replied_not_now`; cancel pending follow-up drafts;
     note the stated timing in `leads.notes` for a future re-approach the
     USER schedules — the engine doesn't self-schedule months out.
   - `reject` -> stage `replied_reject`, cancel drafts.
   - `unsubscribe` -> stage `unsubscribed`, `do_not_contact=1`, cancel
     drafts, delete their outbox files. This is irreversible by the
     pipeline; only the user can clear the flag.
   - `other`/bounce -> mark the contact's `email_status='invalid'` if a hard
     bounce; if wrong-person, note the redirect and clear stage back to
     `qualified` for re-contact research.
4. Report: "<Company>: <intent> — <one-line summary> -> <new_stage>,
   N drafts cancelled" (from the log-response JSON, not from assumption).

## Pitfalls

- Auto-replies (OOO) are `other`, not `not_now` — the cadence continues, but
  shift the next follow-up past the return date in the OOO text.
- Sarcasm reads as interest to keyword matching ("sure, because what I need
  is more software") — classify from tone, and when genuinely torn between
  `reject` and `not_now`, pick `reject`; over-contacting costs more than
  under-contacting.
- An `unsubscribe` on one contact applies to the whole company
  (`do_not_contact` is on the lead), not just that mailbox.

## Verification

Every `responses` row has `handled=1`, an intent, and the lead's stage is
consistent with the latest response's intent; no pending drafts exist for
leads in `replied_*`/`unsubscribed` stages.
