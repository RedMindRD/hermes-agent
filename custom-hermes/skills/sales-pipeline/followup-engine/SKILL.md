---
name: followup-engine
description: Drafts day 3/7/14 follow-ups for unanswered outreach.
version: 1.0.0
author: redmindtech.ai
metadata:
  hermes:
    category: sales-pipeline
    tags: [sales, outreach, followup, cadence]
    related_skills: [outreach-writer, response-classifier, crm-manager]
---

# Follow-up Engine Skill

Stage 10: finds sent outreach with no reply at day 3 / 7 / 14 and stages the
next sequence step. Like all outreach, follow-ups are DRAFTS pending approval
— the engine never sends.

## When to Use

Fired by its own cron job (recommended: daily, offset from the main
pipeline), or manually via `/followup-engine`.

## Procedure

1. Find due leads — for each `sequence_step` S in (0,1,2), a lead is due for
   step S+1 when ALL hold:
   - latest outreach row has `sequence_step=S`, `status='sent'`
   - `sent_at` is >= 3 (S=0), 7 (S=1), 14 (S=2) days ago
     (thresholds measured from the ORIGINAL step-0 `sent_at`, per the
     day-0/3/7/14 cadence)
   - no `responses` row for the lead, stage is still `outreach_sent`
   - `do_not_contact=0` and no existing draft for step S+1
2. For each due lead, load the matching section of outreach-writer's
   `templates/followup_sequence.md`, draft in the same channel and thread
   (same subject with no "Re:" games — reuse the subject verbatim), write
   `$HERMES_HOME/outbox/<lead_id>_<slug>_step<N>.md`, then stage via
   `crm.py draft-outreach --step <N> --body-file <outbox file>` — its
   guards (do_not_contact, duplicate step, wrong stage) are the safety net
   for the due-lead query above; an `ok:false` means this lead was not
   actually due — log it and move on.
3. Step 3 (day 14) is the breakup. After it is APPROVED AND SENT, set lead
   stage -> `lost` with a note; the lead exits the cadence.
4. Summarize: "N follow-ups staged (a×day-3, b×day-7, c×day-14 breakups) —
   awaiting approval in outbox", delivered like the pipeline summary.

## Pitfalls

- The no-reply check must query `responses` at draft time, not trust stage
  alone — a reply classified minutes ago may not have moved the stage yet.
- Weekends/holidays in the lead's market: if the due date lands on one,
  hold the draft for the next business day rather than staging a Saturday
  send.
- Never re-draft a step whose draft the user discarded — a discard is a
  decision, not a gap. Skip that lead and note it in the summary.
- If approval latency stacks two due steps for one lead (day-3 draft still
  unapproved when day-7 arrives), keep only the newer draft and discard the
  stale one — a lead never gets two pending follow-ups.

## Verification

No lead has more than one `status='draft'` follow-up;
`SELECT lead_id, COUNT(*) FROM outreach WHERE status='sent' GROUP BY lead_id
HAVING COUNT(*) > 4` returns nothing (step 0 + 3 follow-ups is the ceiling).
