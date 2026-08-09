#!/usr/bin/env python3
"""Safe CRM operations for the sales pipeline. Stdlib only.

Why this exists: writes go through sqlite3 *parameters* (no quote-escaping of
scraped text), and the business rules that must never be violated are enforced
here in code, not left to prose:

  - lead stage changes follow the legal state machine (see TRANSITIONS)
  - no outreach draft for do_not_contact / rejected / unsubscribed leads
  - an outreach row can only become 'sent' from 'approved' (approval gate)
  - 'unsubscribed' is one-way and sets do_not_contact

Usage:
  python3 crm.py [--db PATH] <command> [options]

DB default: $HERMES_HOME/data/leads.db, else ~/.hermes/data/leads.db.
Output: exactly one JSON line. {"ok": true, ...} on success;
{"ok": false, "error": "..."} and exit 1 on failure.

Commands:
  upsert-company   --name --domain [--website --industry --size --location
                   --services --source-query --notes]        -> company_id
  ensure-lead      --company-id                              -> lead_id
  add-contact      --company-id [--name --role --email --phone --linkedin
                   --source-url --email-status --phone-status --primary]
                                                             -> contact_id
  set-lead         --lead-id [--stage [--force]] [--score --tier
                   --icp-pass --icp-reasons --pain-hypothesis --notes
                   --do-not-contact]
  draft-outreach   --lead-id --channel --step [--contact-id --subject
                   --body|--body-file --outbox-path]         -> outreach_id
  mark-outreach    --id --status {approved,sent,failed,discarded}
  log-response     --lead-id --intent [--channel --body|--body-file]
                                                             -> response_id
  record-run       --discovered N --qualified N ... (any counters) [--notes]
  query            "SELECT ..."   (read-only; SELECT/PRAGMA/EXPLAIN only)
"""
import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path


def default_db() -> Path:
    home = os.environ.get("HERMES_HOME", "").strip()
    base = Path(home).expanduser() if home else Path.home() / ".hermes"
    return base / "data" / "leads.db"


def fail(msg: str) -> "NoReturn":  # noqa: F821 - py3.11+ typing not needed
    print(json.dumps({"ok": False, "error": msg}))
    raise SystemExit(1)


def ok(**payload) -> None:
    print(json.dumps({"ok": True, **payload}))


def connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        fail(f"database not found: {db_path} — run init_db.sql first")
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def read_body(args) -> str:
    body = getattr(args, "body", None)
    body_file = getattr(args, "body_file", None)
    if body and body_file:
        fail("pass --body or --body-file, not both")
    if body_file:
        if body_file == "-":
            return sys.stdin.read()
        try:
            return Path(body_file).read_text(encoding="utf-8")
        except OSError as e:
            fail(f"cannot read --body-file: {e}")
    return body or ""


# ── Lead state machine ──────────────────────────────────────────────────────
TERMINAL = {"won", "unsubscribed"}
TRANSITIONS = {
    "discovered":         {"researched", "rejected"},
    "researched":         {"verified", "rejected"},
    "verified":           {"qualified", "rejected"},
    "qualified":          {"outreach_drafted", "rejected"},
    "rejected":           {"qualified"},           # ICP change re-admits
    "outreach_drafted":   {"outreach_sent", "qualified"},
    "outreach_sent":      {"replied_interested", "replied_not_now",
                           "replied_reject", "lost"},
    "replied_interested": {"won", "lost"},
    "replied_not_now":    {"qualified", "lost"},
    "replied_reject":     {"lost"},
    "lost":               {"qualified"},           # explicit revival only
    "won":                set(),
    "unsubscribed":       set(),
}
ALL_STAGES = set(TRANSITIONS)
NO_OUTREACH_STAGES = {"rejected", "unsubscribed", "won", "lost"}
OUTREACH_STATUSES = {"draft", "approved", "sent", "failed", "discarded"}
INTENTS = {"interested", "not_now", "reject", "unsubscribe", "other"}


def get_lead(conn, lead_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
    if row is None:
        fail(f"lead {lead_id} not found")
    return row


# ── Commands ────────────────────────────────────────────────────────────────
def cmd_upsert_company(conn, a) -> None:
    domain = a.domain.strip().lower().removeprefix("www.")
    if not domain or "." not in domain:
        fail(f"invalid domain: {a.domain!r}")
    conn.execute(
        """INSERT INTO companies (name, domain, website, industry, size,
                                  location, services, source_query, notes)
           VALUES (?,?,?,?,?,?,?,?,?)
           ON CONFLICT(domain) DO UPDATE SET
             name=excluded.name,
             website=COALESCE(NULLIF(excluded.website,''), website),
             industry=COALESCE(NULLIF(excluded.industry,''), industry),
             size=COALESCE(NULLIF(excluded.size,''), size),
             location=COALESCE(NULLIF(excluded.location,''), location),
             services=COALESCE(NULLIF(excluded.services,''), services),
             notes=COALESCE(NULLIF(excluded.notes,''), notes)""",
        (a.name, domain, a.website, a.industry, a.size,
         a.location, a.services, a.source_query, a.notes),
    )
    row = conn.execute("SELECT id FROM companies WHERE domain=?", (domain,)).fetchone()
    conn.commit()
    ok(company_id=row["id"], domain=domain)


def cmd_ensure_lead(conn, a) -> None:
    if conn.execute("SELECT 1 FROM companies WHERE id=?", (a.company_id,)).fetchone() is None:
        fail(f"company {a.company_id} not found")
    conn.execute("INSERT OR IGNORE INTO leads (company_id) VALUES (?)", (a.company_id,))
    row = conn.execute(
        "SELECT id, stage FROM leads WHERE company_id=?", (a.company_id,)
    ).fetchone()
    conn.commit()
    ok(lead_id=row["id"], stage=row["stage"])


def cmd_add_contact(conn, a) -> None:
    email = (a.email or "").strip().lower() or None
    cur = conn.execute(
        """INSERT INTO contacts (company_id, name, role, email, phone, linkedin,
                                 email_status, phone_status, is_primary, source_url)
           VALUES (?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(company_id, email) DO UPDATE SET
             name=COALESCE(NULLIF(excluded.name,''), name),
             role=COALESCE(NULLIF(excluded.role,''), role),
             phone=COALESCE(NULLIF(excluded.phone,''), phone),
             linkedin=COALESCE(NULLIF(excluded.linkedin,''), linkedin),
             email_status=excluded.email_status,
             phone_status=excluded.phone_status""",
        (a.company_id, a.name, a.role, email, a.phone, a.linkedin,
         a.email_status, a.phone_status, 1 if a.primary else 0, a.source_url),
    )
    row = conn.execute(
        "SELECT id FROM contacts WHERE company_id=? AND email IS ?",
        (a.company_id, email),
    ).fetchone()
    conn.commit()
    ok(contact_id=(row["id"] if row else cur.lastrowid))


def cmd_set_lead(conn, a) -> None:
    lead = get_lead(conn, a.lead_id)
    sets, params, result = [], [], {}

    if a.stage is not None:
        new, cur = a.stage, lead["stage"]
        if new not in ALL_STAGES:
            fail(f"unknown stage {new!r}; valid: {sorted(ALL_STAGES)}")
        if cur in TERMINAL and new != cur and not a.force:
            fail(f"lead {a.lead_id} is terminal ({cur}); leaving it requires "
                 f"--force (explicit user instruction only)")
        legal = new == cur or new == "unsubscribed" or new in TRANSITIONS[cur]
        if not legal and not a.force:
            fail(f"illegal transition {cur} -> {new} "
                 f"(legal: {sorted(TRANSITIONS[cur] | {'unsubscribed'})}; "
                 f"use --force only on explicit user instruction)")
        sets.append("stage=?"); params.append(new)
        result["stage"] = new
        if new == "unsubscribed":
            sets.append("do_not_contact=1")
            result["do_not_contact"] = 1

    for flag, col in (("score", "score"), ("tier", "tier"),
                      ("icp_pass", "icp_pass"), ("icp_reasons", "icp_reasons"),
                      ("pain_hypothesis", "pain_hypothesis"), ("notes", "notes"),
                      ("do_not_contact", "do_not_contact")):
        val = getattr(a, flag)
        if val is not None:
            sets.append(f"{col}=?"); params.append(val)
            result[col] = val
    if a.tier is not None and a.tier not in {"hot", "warm", "cold"}:
        fail(f"invalid tier {a.tier!r}")
    if a.do_not_contact == 0 and lead["do_not_contact"] == 1:
        # Clearing an opt-out is a user-only decision; require --force.
        if not a.force:
            fail("clearing do_not_contact requires --force (explicit user instruction)")
    if not sets:
        fail("nothing to update — pass at least one field")

    params.append(a.lead_id)
    conn.execute(f"UPDATE leads SET {', '.join(sets)} WHERE id=?", params)
    conn.commit()
    ok(lead_id=a.lead_id, **result)


def cmd_draft_outreach(conn, a) -> None:
    lead = get_lead(conn, a.lead_id)
    if lead["do_not_contact"]:
        fail(f"lead {a.lead_id} has do_not_contact=1 — refusing to draft")
    if lead["stage"] in NO_OUTREACH_STAGES:
        fail(f"lead {a.lead_id} is in stage {lead['stage']!r} — refusing to draft")
    if a.channel not in {"email", "whatsapp", "linkedin"}:
        fail(f"invalid channel {a.channel!r}")
    dup = conn.execute(
        """SELECT id, status FROM outreach
           WHERE lead_id=? AND sequence_step=? AND status IN ('draft','approved','sent')""",
        (a.lead_id, a.step),
    ).fetchone()
    if dup:
        fail(f"outreach step {a.step} already exists for lead {a.lead_id} "
             f"(id={dup['id']}, status={dup['status']}) — discard it first to redraft")
    body = read_body(a)
    if not body.strip():
        fail("empty body — pass --body or --body-file")
    cur = conn.execute(
        """INSERT INTO outreach (lead_id, contact_id, channel, sequence_step,
                                 subject, body, status, outbox_path)
           VALUES (?,?,?,?,?,?,'draft',?)""",
        (a.lead_id, a.contact_id, a.channel, a.step, a.subject, body, a.outbox_path),
    )
    if lead["stage"] in ("qualified", "replied_not_now"):
        conn.execute("UPDATE leads SET stage='outreach_drafted' WHERE id=?", (a.lead_id,))
    conn.commit()
    ok(outreach_id=cur.lastrowid, lead_id=a.lead_id, step=a.step)


def cmd_mark_outreach(conn, a) -> None:
    row = conn.execute("SELECT * FROM outreach WHERE id=?", (a.id,)).fetchone()
    if row is None:
        fail(f"outreach {a.id} not found")
    cur_status, new = row["status"], a.status
    legal = {
        "draft":    {"approved", "discarded"},
        "approved": {"sent", "failed", "discarded"},
        "failed":   {"approved", "discarded"},   # user may retry after a failure
    }.get(cur_status, set())
    if new not in legal:
        fail(f"illegal outreach status change {cur_status} -> {new} "
             f"(legal from {cur_status!r}: {sorted(legal)}). "
             f"'sent' is only reachable from 'approved' — the approval gate.")
    stamp = {"approved": "approved_at", "sent": "sent_at"}.get(new)
    if stamp:
        conn.execute(
            f"UPDATE outreach SET status=?, {stamp}=datetime('now') WHERE id=?",
            (new, a.id))
    else:
        conn.execute("UPDATE outreach SET status=? WHERE id=?", (new, a.id))
    if new == "sent":
        conn.execute(
            """UPDATE leads SET stage='outreach_sent'
               WHERE id=? AND stage='outreach_drafted'""", (row["lead_id"],))
    conn.commit()
    ok(outreach_id=a.id, status=new, lead_id=row["lead_id"])


def cmd_log_response(conn, a) -> None:
    lead = get_lead(conn, a.lead_id)
    if a.intent not in INTENTS:
        fail(f"invalid intent {a.intent!r}; valid: {sorted(INTENTS)}")
    body = read_body(a)
    cur = conn.execute(
        """INSERT INTO responses (lead_id, channel, body, intent, handled)
           VALUES (?,?,?,?,1)""",
        (a.lead_id, a.channel, body, a.intent),
    )
    stage_map = {"interested": "replied_interested", "not_now": "replied_not_now",
                 "reject": "replied_reject", "unsubscribe": "unsubscribed"}
    new_stage = stage_map.get(a.intent)
    cancelled = 0
    if new_stage:
        if lead["stage"] not in TERMINAL:
            extra = ", do_not_contact=1" if new_stage == "unsubscribed" else ""
            conn.execute(f"UPDATE leads SET stage=?{extra} WHERE id=?",
                         (new_stage, a.lead_id))
        cancelled = conn.execute(
            "UPDATE outreach SET status='discarded' WHERE lead_id=? AND status IN ('draft','approved')",
            (a.lead_id,),
        ).rowcount
    conn.commit()
    ok(response_id=cur.lastrowid, lead_id=a.lead_id,
       new_stage=new_stage or lead["stage"], drafts_cancelled=cancelled)


def cmd_record_run(conn, a) -> None:
    cur = conn.execute(
        """INSERT INTO pipeline_runs (discovered, researched, verified, qualified,
                                      rejected, hot, warm, cold, drafts, notes)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (a.discovered, a.researched, a.verified, a.qualified,
         a.rejected, a.hot, a.warm, a.cold, a.drafts, a.notes),
    )
    conn.commit()
    ok(run_id=cur.lastrowid)


def cmd_query(conn, a) -> None:
    sql = a.sql.strip().rstrip(";")
    if sql.split(None, 1)[0].upper() not in {"SELECT", "PRAGMA", "EXPLAIN", "WITH"}:
        fail("query is read-only: SELECT/WITH/PRAGMA/EXPLAIN only "
             "(use the dedicated commands for writes)")
    try:
        rows = [dict(r) for r in conn.execute(sql).fetchall()]
    except sqlite3.Error as e:
        fail(f"SQL error: {e}")
    ok(rows=rows, count=len(rows))


# ── CLI wiring ──────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="crm.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", type=Path, default=None)
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("upsert-company")
    s.add_argument("--name", required=True)
    s.add_argument("--domain", required=True)
    for f in ("website", "industry", "size", "location", "services",
              "source-query", "notes"):
        s.add_argument(f"--{f}", default="")
    s.set_defaults(fn=cmd_upsert_company)

    s = sub.add_parser("ensure-lead")
    s.add_argument("--company-id", type=int, required=True)
    s.set_defaults(fn=cmd_ensure_lead)

    s = sub.add_parser("add-contact")
    s.add_argument("--company-id", type=int, required=True)
    for f in ("name", "role", "email", "phone", "linkedin", "source-url"):
        s.add_argument(f"--{f}", default="")
    s.add_argument("--email-status", default="unverified")
    s.add_argument("--phone-status", default="unverified")
    s.add_argument("--primary", action="store_true")
    s.set_defaults(fn=cmd_add_contact)

    s = sub.add_parser("set-lead")
    s.add_argument("--lead-id", type=int, required=True)
    s.add_argument("--stage")
    s.add_argument("--force", action="store_true")
    s.add_argument("--score", type=int)
    s.add_argument("--tier")
    s.add_argument("--icp-pass", type=int, choices=(0, 1))
    s.add_argument("--icp-reasons")
    s.add_argument("--pain-hypothesis")
    s.add_argument("--notes")
    s.add_argument("--do-not-contact", type=int, choices=(0, 1))
    s.set_defaults(fn=cmd_set_lead)

    s = sub.add_parser("draft-outreach")
    s.add_argument("--lead-id", type=int, required=True)
    s.add_argument("--channel", required=True)
    s.add_argument("--step", type=int, required=True)
    s.add_argument("--contact-id", type=int)
    s.add_argument("--subject", default="")
    s.add_argument("--body")
    s.add_argument("--body-file")
    s.add_argument("--outbox-path", default="")
    s.set_defaults(fn=cmd_draft_outreach)

    s = sub.add_parser("mark-outreach")
    s.add_argument("--id", type=int, required=True)
    s.add_argument("--status", required=True, choices=sorted(OUTREACH_STATUSES - {"draft"}))
    s.set_defaults(fn=cmd_mark_outreach)

    s = sub.add_parser("log-response")
    s.add_argument("--lead-id", type=int, required=True)
    s.add_argument("--intent", required=True)
    s.add_argument("--channel", default="")
    s.add_argument("--body")
    s.add_argument("--body-file")
    s.set_defaults(fn=cmd_log_response)

    s = sub.add_parser("record-run")
    for f in ("discovered", "researched", "verified", "qualified",
              "rejected", "hot", "warm", "cold", "drafts"):
        s.add_argument(f"--{f}", type=int, default=0)
    s.add_argument("--notes", default="")
    s.set_defaults(fn=cmd_record_run)

    s = sub.add_parser("query")
    s.add_argument("sql")
    s.set_defaults(fn=cmd_query)
    return p


def main() -> None:
    args = build_parser().parse_args()
    db = args.db or default_db()
    conn = connect(db)
    try:
        args.fn(conn, args)
    except sqlite3.Error as e:
        conn.rollback()
        fail(f"database error: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        fail("interrupted")
