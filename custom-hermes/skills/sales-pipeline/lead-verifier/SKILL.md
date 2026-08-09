---
name: lead-verifier
description: Verifies domains, emails, and phones; dedupes leads.
version: 1.0.0
author: redmindtech.ai
metadata:
  hermes:
    category: sales-pipeline
    tags: [sales, leads, verification]
    related_skills: [contact-extractor, crm-manager]
---

# Lead Verifier Skill

Stage 5: cheap, deterministic checks that keep dead companies and fake
contacts out of the CRM. Ships two stdlib-only scripts; run them, don't
re-derive the logic by hand.

## When to Use

Loaded by `/prospect-pipeline` after research; standalone via `/lead-verifier`
to re-verify existing CRM rows (e.g. quarterly hygiene pass).

## How to Run

Resolve `scripts/` against this skill's directory, then with `terminal`:

```bash
python3 <skill_dir>/scripts/check_domain.py acme.com other.io
python3 <skill_dir>/scripts/verify_email.py a@acme.com b@other.io
printf 'a@x.com\nb@y.com\n' | python3 <skill_dir>/scripts/verify_email.py -   # stdin batch
```

Both print one JSON object per line and always exit 0 — a bad input yields
an error object, never a dead batch. Batch many targets into one call.
Status semantics: `invalid` / `live:false`-with-dns-detail = definitively
bad, act on it. `"status": "error"` or a transient/unreachable detail =
**unknown** — the check failed, not the lead; keep the data as `unverified`
and re-check on a later run. `redirected_offsite: true` means the domain
forwards to a different company's site — update the company's real domain
before storing contacts against it.

## Procedure

1. **Domain**: `check_domain.py` — `live:false` with a DNS-failure detail
   means drop the candidate entirely. `live:true` via a 403/429 detail means
   a bot-blocker: the site is fine, note it.
2. **Emails**: `verify_email.py` — map result to `contacts.email_status`:
   `mx_ok` / `domain_ok` / `format_ok` keep the contact; `invalid` clears the
   email field (keep the person + role, they may still have a LinkedIn).
3. **Phones**: format-check only (plausible length for the country, not a
   premium/short code). Set `format_ok` or `invalid`. Never call anything.
4. **Dedupe** against the CRM before insert:
   - company: `SELECT id FROM companies WHERE domain=?`
   - cross-company duplicate contact email is legitimate (an owner of two
     firms) — allow it, the schema only forbids dupes within a company.
5. A lead whose company is live but has zero surviving contacts is still
   stored — qualification will penalize reachability; it is not dropped.

## Pitfalls

- MX lookup is best-effort (`nslookup` may be absent): `domain_ok` with
  detail "MX check unavailable" is not a failure — don't downgrade it.
- Don't SMTP-probe mailboxes (no RCPT-TO pinging) — it gets the sender
  domain blocklisted and is the classic way to burn deliverability before
  the first real email goes out.

## Verification

Every stored contact row has `email_status`/`phone_status` set to a value the
scripts (or the phone rule) actually produced this run — no row left at
`unverified` unless it genuinely wasn't checked.
