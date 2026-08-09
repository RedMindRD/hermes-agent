---
name: crm-manager
description: Owns the leads.db schema and CRM query patterns.
version: 1.0.0
author: redmindtech.ai
metadata:
  hermes:
    category: sales-pipeline
    tags: [sales, crm, sqlite, database]
    related_skills: [prospect-pipeline, pipeline-analytics]
---

# CRM Manager Skill

Stage 12: the single owner of `$HERMES_HOME/data/leads.db`. Schema lives in
`scripts/init_db.sql` (idempotent — run it freely). **All writes go through
`scripts/crm.py`** — it parameterizes scraped text (no quote-escaping bugs)
and enforces the business rules in code: legal stage transitions, the
approval-before-send gate, and the `do_not_contact` block. Raw `sqlite3` is
for reads only.

## When to Use

- Loaded implicitly by pipeline skills for query patterns.
- Standalone via `/crm-manager` for ad-hoc asks: "show hot leads", "mark
  Acme won", "export this week's leads to CSV".

## How to Run

```bash
sqlite3 $HERMES_HOME/data/leads.db < <skill_dir>/scripts/init_db.sql   # init/migrate
sqlite3 -header -column $HERMES_HOME/data/leads.db "<query>"           # reads
python3 <skill_dir>/scripts/crm.py <command> ...                       # ALL writes
```

`scripts/push_to_crm.py` syncs qualified leads OUT to the WhatsApp AI CRM
(inbound-lead webhook, source `hermes-agent`; config via `CRM_BASE_URL` +
`CRM_WEBHOOK_TOKEN` in `$HERMES_HOME/.env`). `--dry-run` previews payloads,
`--lead-id N` force-repushes one lead, `--tiers hot` narrows the sweep.
Push state lives in the `crm_sync` table; delete a row there to make a lead
eligible again.

`crm.py` prints one JSON line per call: `{"ok": true, ...}` or
`{"ok": false, "error": "..."}` with exit 1. **An `ok:false` is a rule
firing, not a malfunction** — read the error, fix the premise (wrong stage,
missing approval, opted-out lead); never work around it with raw SQL.

Write commands (see `crm.py --help` / the module docstring for flags):
`upsert-company`, `ensure-lead`, `add-contact`, `set-lead`,
`draft-outreach`, `mark-outreach`, `log-response`, `record-run`, plus a
read-only `query` that rejects non-SELECT statements. Long bodies: pass
`--body-file <path>` or `--body-file -` (stdin) instead of `--body`.
`--force` on `set-lead` exists solely for explicit user instructions
(reviving a lost/unsubscribed lead, clearing an opt-out) — never use it to
silence an illegal-transition error during pipeline runs.

## Quick Reference

```bash
# Writes (crm.py — dedupe on domain, one lead per company, all guarded)
python3 crm.py upsert-company --name "Acme" --domain acme.com --industry textiles
python3 crm.py ensure-lead --company-id 12
python3 crm.py add-contact --company-id 12 --name "Raj K" --role Owner \
        --email raj@acme.com --email-status mx_ok --source-url https://acme.com/about
python3 crm.py set-lead --lead-id 7 --stage qualified --score 78 --tier hot \
        --icp-pass 1 --icp-reasons '["PASS industry", "+20 size 11-50"]'
python3 crm.py draft-outreach --lead-id 7 --channel email --step 0 \
        --subject "..." --body-file /tmp/draft.md --outbox-path "$HERMES_HOME/outbox/7_acme_step0.md"
python3 crm.py mark-outreach --id 3 --status approved   # then: --status sent
python3 crm.py log-response --lead-id 7 --intent interested --channel email --body-file -
python3 crm.py record-run --discovered 15 --qualified 4 --hot 1 --drafts 1
```

```sql
-- Reads (raw sqlite3 is fine)
-- Today's hot list
SELECT c.name, l.score, l.pain_hypothesis FROM leads l
JOIN companies c ON c.id=l.company_id
WHERE l.tier='hot' AND date(l.updated_at)=date('now') ORDER BY l.score DESC;

-- Pipeline board
SELECT stage, COUNT(*) FROM leads GROUP BY stage;

-- Pending approvals
SELECT o.id, c.name, o.channel, o.sequence_step FROM outreach o
JOIN leads l ON l.id=o.lead_id JOIN companies c ON c.id=l.company_id
WHERE o.status='draft' ORDER BY o.drafted_at;
```

## Procedure (writes)

1. Never hand-build INSERT/UPDATE statements for scraped text — that's what
   `crm.py` is for. If a needed write has no crm.py command, that's a gap to
   report, not a reason to fall back to string-built SQL.
2. Stage transitions are enforced by `crm.py set-lead` — legal moves:
   `discovered->researched->verified->(qualified|rejected)`,
   `qualified->outreach_drafted->outreach_sent->replied_*`,
   `replied_interested->(won|lost)`, any->`unsubscribed`.
   An illegal-transition error means a bug upstream: stop and report, don't
   `--force` it.
3. Deletes are exceptional. Prospects are archived by stage (`rejected`,
   `lost`), not removed — history is what analytics runs on. Genuine
   removal (user demands data deletion): delete the company row; cascades
   clean up the rest.
4. Backup before bulk mutations:
   `cp $HERMES_HOME/data/leads.db $HERMES_HOME/data/leads.db.bak-$(date +%Y%m%d)`.
   Keep the two most recent backups, delete older ones.

## Pitfalls

- WAL mode means a reader mid-pipeline sees consistent data, but copy
  backups must include a `sqlite3 ... "PRAGMA wal_checkpoint(TRUNCATE);"`
  first, or the .bak misses recent writes.
- `leads.updated_at` is trigger-maintained — don't set it manually.
- One lead per company is a schema invariant (UNIQUE). Multiple locations
  or contacts hang off `contacts`, not extra lead rows.

## Verification

`PRAGMA integrity_check;` returns ok, and
`SELECT COUNT(*) FROM leads l LEFT JOIN companies c ON c.id=l.company_id
WHERE c.id IS NULL;` returns 0.
