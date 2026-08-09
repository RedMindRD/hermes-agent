---
name: outreach-writer
description: Drafts personalized outreach staged for user approval.
version: 1.0.0
author: redmindtech.ai
metadata:
  hermes:
    category: sales-pipeline
    tags: [sales, outreach, email, whatsapp]
    related_skills: [sales-researcher, followup-engine, crm-manager]
---

# Outreach Writer Skill

Stage 9: turn a Hot lead + pain hypothesis into a short, personalized first
touch (email and/or WhatsApp). Drafts are STAGED, never sent — every message
waits in the outbox for explicit user approval.

## When to Use

Loaded by `/prospect-pipeline` for Hot leads; standalone via
`/outreach-writer <company>` to draft or redraft one message.

## Prerequisites

- `product.md` read: proof points, tone rules, sender identity.
- Lead has `pain_hypothesis` set (run `sales-researcher` first if not).
- Never draft for leads with `do_not_contact=1` or stage
  `rejected`/`unsubscribed`.

## Procedure

1. Pick the channel: email when a named contact has `email_status` of
   `mx_ok`/`domain_ok`; WhatsApp only if product.md lists a WhatsApp business
   number AND the lead's phone is `format_ok`. When both work, email is the
   first touch; do not double-tap both channels on step 0.
2. Start from the matching file in `templates/` (`email_cold.md`,
   `whatsapp_cold.md`) — the template is structure + rules, not copy to fill
   in blindly.
3. Personalization bar: the first sentence must be specific to THIS company
   (from `pain_hypothesis` / stored research) and must be true. If the
   hypothesis is `generic`, open with the industry-level pain honestly —
   never simulate familiarity.
4. Apply product.md tone rules. Hard limits: email ≤ 120 words + subject
   ≤ 6 words; WhatsApp ≤ 60 words, no links in the first message.
5. Every email includes a one-line honest opt-out ("If this isn't relevant,
   reply 'no' and I won't write again."). Physical-address / footer rules
   from product.md's sender identity apply as written.
6. Stage it:
   - Write the review copy to
     `$HERMES_HOME/outbox/<lead_id>_<company-slug>_step0.md` with a header
     block: To / Channel / Subject / Why-this-lead (score + hypothesis).
   - `python3 <crm-manager dir>/scripts/crm.py draft-outreach --lead-id N
     --channel email --step 0 --contact-id C --subject "..."
     --body-file <outbox file> --outbox-path <outbox file>` — it sets the
     lead to `outreach_drafted` itself and refuses opted-out leads, wrong
     stages, and duplicate steps. An `ok:false` here means don't draft;
     report why instead of retrying around it.

## Sending (approval flow only)

Only on the user's explicit instruction ("approve all" / "approve 12"),
in an interactive session — never inside the cron pipeline:
`crm.py mark-outreach --id N --status approved`, send via the channel as
product.md's sender identity, then `--status sent` (the tool enforces
approved-before-sent and stamps timestamps + lead stage), and delete the
outbox file. `discard N` -> `--status discarded`, remove the file, and
`set-lead --stage qualified` to release the lead. A failed send ->
`--status failed`; the retry path is user-directed `failed -> approved`.

## Pitfalls

- Claims discipline: only proof points listed in product.md. No invented
  customer counts, no "we helped companies like yours" without a named case.
- One draft per lead per step — check
  `SELECT 1 FROM outreach WHERE lead_id=? AND sequence_step=0` before
  inserting; redrafting replaces (discard the old row), not duplicates.
- Cold WhatsApp to individuals is legally restricted in many markets and
  against WhatsApp ToS outside the Business API with opt-in. Default to
  email; use WhatsApp only where product.md explicitly says the user has a
  compliant channel for it.

## Verification

`SELECT COUNT(*) FROM outreach WHERE status='draft'` equals the file count in
`$HERMES_HOME/outbox/`, and reading any draft aloud passes the test: specific,
true, under the word limit, with an opt-out line.
