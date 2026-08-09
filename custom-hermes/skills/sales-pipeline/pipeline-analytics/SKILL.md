---
name: pipeline-analytics
description: Reports pipeline health, conversion, and trends weekly.
version: 1.0.0
author: redmindtech.ai
metadata:
  hermes:
    category: sales-pipeline
    tags: [sales, analytics, reporting]
    related_skills: [crm-manager, prospect-pipeline]
---

# Pipeline Analytics Skill

Stage 13: turns `leads.db` history into the weekly report — what's working,
what's leaking, and what to change in the ICP or outreach. Read-only: this
skill never mutates the CRM.

## When to Use

Weekly cron (e.g. Monday 9am) or manually via `/pipeline-analytics`, and
whenever the user asks "how's the pipeline doing?".

## Procedure

Run these against `$HERMES_HOME/data/leads.db` (`sqlite3 -header -column`),
then interpret — the report is the reading, not the raw tables:

```sql
-- Funnel this week vs last week
SELECT date(run_at) d, discovered, qualified, hot, drafts
FROM pipeline_runs WHERE run_at >= date('now','-14 days') ORDER BY d;

-- Conversion by stage (all time)
SELECT stage, COUNT(*) FROM leads GROUP BY stage;

-- Reply performance by sequence step
SELECT o.sequence_step, COUNT(*) sent,
       SUM(EXISTS(SELECT 1 FROM responses r WHERE r.lead_id=o.lead_id
                  AND r.received_at >= o.sent_at)) got_reply
FROM outreach o WHERE o.status='sent' GROUP BY o.sequence_step;

-- Rejection reasons (top ICP filters killing leads)
SELECT icp_reasons, COUNT(*) FROM leads WHERE icp_pass=0
GROUP BY icp_reasons ORDER BY COUNT(*) DESC LIMIT 10;

-- Response intents
SELECT intent, COUNT(*) FROM responses GROUP BY intent;

-- Approval latency (drafts waiting on the user)
SELECT COUNT(*), MIN(drafted_at) oldest FROM outreach WHERE status='draft';
```

Report structure (delivered like the daily summary):
1. **Funnel** — discovered -> qualified -> hot -> sent -> replied, with
   week-over-week deltas.
2. **What's leaking** — the single biggest drop-off stage and the likely
   cause (e.g. "78% of rejects fail the size filter — search queries are
   pulling enterprises").
3. **Outreach performance** — reply rate per step; flag if breakups (step 3)
   outperform step 1 (means the opener is weak).
4. **Action suggestions** — max 3, each tied to a number above, phrased as a
   proposal for the user ("consider widening size filter to 500"), never
   auto-applied.
5. **Hygiene** — stale drafts awaiting approval, leads stuck in a stage
   > 14 days, contacts still `unverified`.

## Pitfalls

- Small-number humility: 2 replies out of 5 sends is not a "40% reply rate"
  worth a strategy change — say "n too small" below ~20 sends per cohort.
- Never edit icp.md or product.md from an analytics finding — recommend the
  edit; the user owns the spec.

## Verification

Every number in the report reproduces from one of the queries above, and the
report explicitly states the date window it covers.
