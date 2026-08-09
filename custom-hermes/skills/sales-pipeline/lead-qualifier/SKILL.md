---
name: lead-qualifier
description: Scores leads against the ICP and assigns tiers.
version: 1.0.0
author: redmindtech.ai
metadata:
  hermes:
    category: sales-pipeline
    tags: [sales, leads, qualification, scoring]
    related_skills: [prospect-pipeline, crm-manager]
---

# Lead Qualifier Skill

Stages 6-7: apply the ICP's hard filters, score survivors 0-100 with the
rubric from `icp.md`, and tier them Hot/Warm/Cold. The rubric lives in
`$HERMES_HOME/context/icp.md` — this skill is the procedure for applying it
consistently, not a second copy of the rules.

## When to Use

Loaded by `/prospect-pipeline` after verification; standalone via
`/lead-qualifier` to re-score existing leads after an ICP edit.

## Procedure

1. Re-read the **Hard filters**, **Scoring dimensions**, and **Tier
   thresholds** sections of `icp.md` — never score from memory of a previous
   run.
2. **Hard filters first.** Any failure -> `icp_pass=0`, stage `rejected`,
   and `icp_reasons` records which filter failed and the evidence
   (e.g. `["FAIL size: ~500 employees, ICP max 200"]`). Rejected leads are
   never scored — a 92-point company in the wrong country is still a reject.
3. **Score each dimension separately**, citing evidence from the research
   JSON for every non-zero award. Unknown data scores that dimension's
   minimum, not the midpoint — the pipeline must not reward ignorance.
4. Sum, clamp to 0-100, apply tier thresholds from icp.md. The Hot tier's
   contact requirement is part of the threshold: a 75-scorer with only an
   `info@` inbox is Warm, and `icp_reasons` should say so.
5. Persist: `score`, `tier`, `icp_pass`, `icp_reasons` (JSON array of
   `"PASS/FAIL/+N <dimension>: <evidence>"` strings), stage -> `qualified`
   or `rejected`.

## Pitfalls

- Score drift: if today's average score jumps ±20 vs `pipeline_runs`
  history without an ICP edit, your interpretation drifted — recheck rule 3.
- Don't re-qualify `rejected` leads on later runs unless the ICP file
  changed since `updated_at` (that's the one legitimate re-score trigger).
- `icp_reasons` is what the user sees when they ask "why is this lead Hot?"
  — write evidence, not restatements of the rubric.

## Verification

`sqlite3 $HERMES_HOME/data/leads.db "SELECT tier, COUNT(*), AVG(score) FROM
leads WHERE date(updated_at)=date('now') GROUP BY tier;"` — every scored lead
has non-empty `icp_reasons`, and no `rejected` row has a score.
