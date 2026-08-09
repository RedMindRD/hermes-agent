---
name: prospect-pipeline
description: Runs the daily lead prospecting pipeline end to end.
version: 1.0.0
author: redmindtech.ai
metadata:
  hermes:
    category: sales-pipeline
    tags: [sales, leads, crm, outreach, pipeline]
    related_skills: [lead-finder, company-researcher, contact-extractor, lead-verifier, lead-qualifier, sales-researcher, outreach-writer, crm-manager]
---

# Prospect Pipeline Skill

Master orchestrator: discovers companies matching the ICP, researches and
verifies them, scores and tiers them, stores everything in the CRM, and stages
personalized outreach drafts for the user's approval. It NEVER sends outreach
itself — sending happens only in the approval flow (see outreach-writer).

## When to Use

- Fired by the daily cron job, or manually via `/prospect-pipeline`.
- Optional argument: a focus hint, e.g. `/prospect-pipeline textile exporters
  in Tirupur` narrows today's discovery to that segment.

## Prerequisites

- `$HERMES_HOME` is this deployment's home directory (the `.hermes/` folder
  this skill tree lives in). If the env var is unset in the shell, resolve it
  as two directories above this skill's own directory.
- `$HERMES_HOME/context/product.md` and `$HERMES_HOME/context/icp.md` filled in.
  **If either still contains "TODO:", STOP** and tell the user to fill them —
  do not run the pipeline on placeholder context.
- `sqlite3` on PATH. DB lives at `$HERMES_HOME/data/leads.db`.
- `web_search` + `web_extract` tools available.
- Telegram (or another gateway platform) configured if the daily summary
  should be delivered as a message; otherwise the summary is printed.

## How to Run

1. Read both context files in full. Extract: hard filters, scoring rubric,
   tier thresholds, decision-maker roles, geography (from icp.md) and the
   offer/pain points/sender identity (from product.md).
2. Initialize/migrate the DB (idempotent):
   `sqlite3 $HERMES_HOME/data/leads.db < <crm-manager skill dir>/scripts/init_db.sql`
   (resolve the path via the crm-manager skill directory, a sibling of this one).
3. Run stages 1-8 below, keeping a running tally for the summary.

## Procedure

**Stage 1 — DISCOVER** (load `lead-finder` for query strategies):
Target ~15 new candidate companies. Before researching any candidate, dedupe:
`SELECT 1 FROM companies WHERE domain = ?` — skip known domains silently.

**Stages 2-4 — RESEARCH / EXTRACT / VERIFY**, one company at a time or via
`delegate_task` batch (max 3 concurrent) when more than 5 candidates:
- Each subagent gets: company name + URL, the research checklist from
  `company-researcher`, the contact rules from `contact-extractor`, and must
  return a single JSON object (schema in company-researcher).
- Verify with `lead-verifier` scripts:
  `python3 <lead-verifier dir>/scripts/check_domain.py <domain>` and
  `python3 <lead-verifier dir>/scripts/verify_email.py <emails...>`.
  Drop candidates whose domain is dead. Record email status per contact.

**Stages 5-6 — QUALIFY + SCORE** (load `lead-qualifier`):
Apply hard filters first (fail -> stage `rejected`, store the reason — a
rejected company must not be re-researched tomorrow). Score survivors 0-100
per the icp.md rubric, assign Hot/Warm/Cold.

**Stage 7 — STORE** via `crm.py` (see `crm-manager`; never string-built SQL):
`upsert-company` -> `ensure-lead` -> `add-contact` per contact ->
`set-lead` for stage/score/tier/reasons. Finish with `record-run` carrying
today's counts (write it even for an empty/failed run, with `--notes` on
what happened). Every call returns one JSON line — check `"ok"` on each; an
`ok:false` is a guard firing: fix the premise, don't bypass it.

**Stage 7b — PUSH TO WHATSAPP CRM** (skip silently if `CRM_WEBHOOK_TOKEN`
is not set in `$HERMES_HOME/.env`):
`python3 <crm-manager dir>/scripts/push_to_crm.py` — pushes newly qualified
hot/warm leads to the WhatsApp AI CRM's inbound-lead webhook (source
"Hermes Sales Agent"). It tracks pushes in the `crm_sync` table so re-runs
are idempotent, and skips leads with no phone/email (they retry
automatically on a later run once a contact is found). Read its JSON lines;
put `pushed/skipped/failed` in the summary. An `ok:false` abort (bad token,
unknown source, CRM unreachable) is a config problem for the user — report
it, don't retry in-loop.

**Stage 8 — OUTREACH DRAFTS** (Hot leads only):
- Load `sales-researcher` for a pain hypothesis, then `outreach-writer` to
  write the message. Stage it with `crm.py draft-outreach` (write the body
  to the outbox file first, pass it via `--body-file`). The command itself
  refuses `do_not_contact` leads, wrong stages, and duplicate steps.
- **HARD RULE: no send. Drafts wait for explicit approval.**

**Summary** — deliver via `send_message` to the user's Telegram if messaging
is available, else print:
- counts (discovered / rejected+why / hot / warm / cold)
- the Hot list: company, score, one-line why, contact found
- pending drafts: "N drafts in outbox — reply 'approve all', 'approve 12,14'
  or 'discard 13' to act on them."

## Approval flow (interactive, not part of the cron run)

When the user replies with an approval instruction, per draft:
`crm.py mark-outreach --id N --status approved`, send on its channel as the
sender identity from product.md, then `--status sent` (the tool only allows
`sent` from `approved` — that's the approval gate; don't fight it).
Discard -> `--status discarded`. A failed send -> `--status failed` and
report it — never retry silently (`failed -> approved` is the user-directed
retry path).

## Failure handling (one failure never kills the run)

Keep an in-run error ledger: `[{stage, company/lead, error, action_taken}]`.
It goes in the summary and in `record-run --notes` — silent partial failure
is the worst outcome, because tomorrow's run trusts today's data.

- **web_search fails / returns nothing**: retry once with a reworded query;
  then proceed with whatever candidates exist and note the miss. Zero
  candidates -> still `record-run` (notes: "discovery failed: <error>").
- **One company's research/extract fails** (dead page, bot-block, subagent
  error): log to the ledger, leave the lead at its last valid stage, and
  move on. Never let one company abort the batch.
- **Verifier scripts return `"status": "error"`** (resolver down, tooling
  missing): that's *unknown*, not *invalid* — keep the contact as
  `unverified`, note it, and let a later run re-verify. Only `invalid` /
  `live:false` with a DNS detail disqualifies.
- **`crm.py` returns `ok:false`**: read the error. Guard errors (illegal
  transition, duplicate draft, do_not_contact) mean YOUR premise is wrong —
  re-read the lead's actual state with a query, then correct course.
  `database error: ... locked` -> wait 5s, retry once, then stop the STORE
  stage and report; never leave a lead half-written (company without lead
  row, lead without score).
- **Summary delivery fails** (gateway down): print the full summary to the
  session instead, and say delivery failed — the work is done either way.
- **Budget/interrupt pressure**: if the session is near its iteration budget
  mid-run, skip remaining research candidates, finish STORE + `record-run` +
  summary for what's complete, and note what was cut. A short honest run
  beats a truncated silent one.

## Pitfalls

- Cron sessions are watched for *inactivity* (default 600s idle) — long runs
  are fine, but don't sit in one giant silent web_extract loop; keep tool
  calls flowing. Cap the run at ~15 new companies rather than trawling wider.
- Don't re-run discovery for a segment that produced 0 qualifiable leads two
  runs in a row — tell the user the ICP/search terms need adjustment instead.
- `pipeline_runs` is the audit trail: write the row even when the run finds
  nothing, with a note saying why.
- Never draft outreach to a lead in stage `rejected`, `unsubscribed`, or with
  `do_not_contact=1`.

## Verification

- `sqlite3 $HERMES_HOME/data/leads.db "SELECT stage, COUNT(*) FROM leads GROUP BY stage;"`
  matches the summary you delivered.
- Every Hot lead has: a contact row with `email_status` at least `domain_ok`,
  an `icp_reasons` entry, and exactly one step-0 draft in `outreach`.
- `ls $HERMES_HOME/outbox/` shows one file per pending draft.
