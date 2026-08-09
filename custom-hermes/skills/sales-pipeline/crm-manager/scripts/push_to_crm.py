#!/usr/bin/env python3
"""Push qualified Hermes leads into the WhatsApp AI CRM. Stdlib only.

Delivers via the CRM's inbound-lead webhook:
    POST {CRM_BASE_URL}/api/webhook/lead/{source}/{token}
The CRM owns dedupe, auto-assignment, and lead_status. Extra fields beyond
name/phone/email are packed into the contact's notes by the CRM, so score,
tier, industry, and pain hypothesis arrive without any CRM schema change.

Config (env, falling back to $HERMES_HOME/.env):
    CRM_WEBHOOK_URL    full webhook URL (overrides the three below)
    CRM_BASE_URL       e.g. http://localhost:8000
    CRM_WEBHOOK_TOKEN  from CRM Settings -> Lead Integrations -> Hermes Sales Agent
    CRM_LEAD_SOURCE    default: hermes-agent

Usage:
    python3 push_to_crm.py [--db PATH] [--tiers hot,warm] [--lead-id N]
                           [--limit N] [--dry-run]

Eligibility: icp_pass=1, do_not_contact=0, stage not rejected/unsubscribed,
tier in --tiers, has phone or email, not already pushed (tracked in the
crm_sync table; --lead-id repushes regardless).
Output: one JSON line per lead + a final summary line. Exit 1 only on
config/abort errors (bad token, unknown source, DB missing).
"""
import argparse
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

TIMEOUT = 20
EMAIL_RANK = {"mx_ok": 3, "domain_ok": 2, "format_ok": 1, "unverified": 0, "invalid": -1}


def hermes_home() -> Path:
    home = os.environ.get("HERMES_HOME", "").strip()
    return Path(home).expanduser() if home else Path.home() / ".hermes"


def load_dotenv_fallback() -> None:
    """Fill os.environ from $HERMES_HOME/.env for keys not already set."""
    env_file = hermes_home() / ".env"
    if not env_file.exists():
        return
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = val
    except OSError:
        pass


def abort(msg: str) -> "NoReturn":  # noqa: F821
    print(json.dumps({"ok": False, "error": msg}))
    raise SystemExit(1)


def webhook_url() -> str:
    url = os.environ.get("CRM_WEBHOOK_URL", "").strip()
    if url:
        return url
    base = os.environ.get("CRM_BASE_URL", "").strip().rstrip("/")
    token = os.environ.get("CRM_WEBHOOK_TOKEN", "").strip()
    source = os.environ.get("CRM_LEAD_SOURCE", "hermes-agent").strip()
    if not base or not token:
        abort("CRM not configured: set CRM_BASE_URL + CRM_WEBHOOK_TOKEN "
              "(or CRM_WEBHOOK_URL) in $HERMES_HOME/.env")
    return f"{base}/api/webhook/lead/{source}/{token}"


def post_lead(url: str, payload: dict) -> tuple[int, dict]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json",
                 "User-Agent": "hermes-sales-agent/1.0"})
    last_exc = None
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read().decode("utf-8") or "{}")
            except (ValueError, OSError):
                detail = {}
            if e.code >= 500 and attempt == 1:
                time.sleep(2)
                continue
            return e.code, detail
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_exc = e
            if attempt == 1:
                time.sleep(2)
                continue
    raise ConnectionError(f"CRM unreachable after retry: {last_exc}")


def pick_contact(conn, company_id: int) -> sqlite3.Row | None:
    rows = conn.execute(
        "SELECT * FROM contacts WHERE company_id=? AND email_status != 'invalid'",
        (company_id,)).fetchall()
    if not rows:
        return None
    return max(rows, key=lambda r: (
        r["is_primary"],
        EMAIL_RANK.get(r["email_status"], 0),
        bool(r["email"]),
        bool(r["phone"]),
    ))


def build_payload(lead, company, contact) -> dict:
    payload = {
        "name": (contact["name"] if contact and contact["name"] else company["name"]),
        "phone": (contact["phone"] or "") if contact else "",
        "email": (contact["email"] or "") if contact else "",
        # Everything below lands in the CRM contact's notes automatically.
        "company": company["name"],
        "website": company["website"] or f"https://{company['domain']}",
        "industry": company["industry"] or "",
        "location": company["location"] or "",
        "contact_role": (contact["role"] or "") if contact else "",
        "icp_score": lead["score"],
        "tier": lead["tier"] or "",
        "pipeline_stage": lead["stage"],
        "pain_hypothesis": lead["pain_hypothesis"] or "",
        "icp_reasons": lead["icp_reasons"] or "",
        "hermes_lead_id": lead["id"],
    }
    return {k: v for k, v in payload.items() if v not in ("", None)}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", type=Path, default=None)
    p.add_argument("--tiers", default="hot,warm")
    p.add_argument("--lead-id", type=int)
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    db = a.db or hermes_home() / "data" / "leads.db"
    if not db.exists():
        abort(f"database not found: {db}")
    load_dotenv_fallback()
    url = None if a.dry_run else webhook_url()

    conn = sqlite3.connect(db, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("""CREATE TABLE IF NOT EXISTS crm_sync (
        lead_id INTEGER PRIMARY KEY REFERENCES leads(id) ON DELETE CASCADE,
        pushed_at TEXT NOT NULL DEFAULT (datetime('now')),
        crm_contact_id INTEGER, created INTEGER, response TEXT)""")

    tiers = [t.strip() for t in a.tiers.split(",") if t.strip()]
    if a.lead_id:
        rows = conn.execute("SELECT * FROM leads WHERE id=?", (a.lead_id,)).fetchall()
    else:
        rows = conn.execute(
            f"""SELECT l.* FROM leads l
                LEFT JOIN crm_sync s ON s.lead_id = l.id
                WHERE s.lead_id IS NULL AND l.icp_pass=1 AND l.do_not_contact=0
                  AND l.stage NOT IN ('rejected','unsubscribed')
                  AND l.tier IN ({','.join('?' * len(tiers))})
                ORDER BY l.score DESC LIMIT ?""",
            (*tiers, a.limit)).fetchall()

    pushed = skipped = failed = 0
    for lead in rows:
        company = conn.execute("SELECT * FROM companies WHERE id=?",
                               (lead["company_id"],)).fetchone()
        contact = pick_contact(conn, lead["company_id"])
        payload = build_payload(lead, company, contact)
        line = {"lead_id": lead["id"], "company": company["name"]}
        if not payload.get("phone") and not payload.get("email"):
            skipped += 1
            print(json.dumps({**line, "ok": False, "skipped": "no phone or email"}))
            continue
        if a.dry_run:
            print(json.dumps({**line, "ok": True, "dry_run": True, "payload": payload}))
            continue
        try:
            status, resp = post_lead(url, payload)
        except ConnectionError as e:
            abort(str(e))  # network down — every further POST would fail too
        if status in (200, 201) and resp.get("success"):
            conn.execute(
                """INSERT OR REPLACE INTO crm_sync
                   (lead_id, crm_contact_id, created, response) VALUES (?,?,?,?)""",
                (lead["id"], resp.get("contact_id"),
                 1 if resp.get("created") else 0, json.dumps(resp)))
            conn.commit()
            pushed += 1
            print(json.dumps({**line, "ok": True, "crm_contact_id": resp.get("contact_id"),
                              "created": bool(resp.get("created"))}))
        elif status == 401:
            abort("CRM rejected the token (401) — reconnect Hermes Sales Agent "
                  "in CRM Settings -> Lead Integrations and update CRM_WEBHOOK_TOKEN")
        elif status == 404:
            abort("CRM says unknown source (404) — deploy the backend with the "
                  "'hermes-agent' source registered in LeadIntegrationsController")
        else:
            failed += 1
            print(json.dumps({**line, "ok": False, "http_status": status,
                              "response": resp}))
    conn.close()
    print(json.dumps({"ok": True, "summary": True, "pushed": pushed,
                      "skipped": skipped, "failed": failed,
                      "eligible": len(rows), "dry_run": a.dry_run}))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        abort("interrupted")
