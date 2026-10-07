"""WH-CRM MCP server for Hermes Agent.

Thin, typed wrappers over the WH-CRM REST API. Read tools are safe to call at
any time. Write tools only act on ids passed explicitly (there is no
"approve all"), and none of them sends a customer message directly: approved
drafts and sequence steps still go through the CRM's compliance checks.

Run:  python hermes-mcp/server.py        (stdio transport)
Env:  CRM_BASE_URL, CRM_API_TOKEN, optional CRM_TIMEOUT (seconds, default 20)
"""

from __future__ import annotations

import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

sys.path.insert(0, str(Path(__file__).resolve().parent))  # works from any cwd / launcher

from crm_client import CrmClient, CrmConfig, CrmError, load_dotenv  # noqa: E402

load_dotenv(Path(__file__).with_name(".env"))

MAX_WRITE_IDS = 50
MAX_LIST = 50

mcp = FastMCP(
    "wh-crm",
    instructions=(
        "Tools for managing the WH-CRM sales pipeline as the owner's manager agent. "
        "Read tools are safe. Before any write tool (approve_prospects, trigger_prospect_search, "
        "enroll_in_sequence, pause_sequence, approve_draft, reject_draft, create_reminder) confirm "
        "the exact ids with the owner. These tools never send customer messages directly and cannot "
        "change the do-not-contact list."
    ),
)

READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)


def get_client() -> CrmClient:
    """Build a client from the environment (tests patch the environment)."""
    return CrmClient(CrmConfig.from_env())


async def _call(method: str, path: str, what: str, **kwargs: Any) -> Any:
    try:
        return await get_client().request(method, path, what, **kwargs)
    except CrmError as exc:
        raise ToolError(str(exc)) from exc


# ── validation helpers (also enforced when tools are called directly) ─────────


def _positive_id(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ToolError(f"{label} must be a positive whole number.")
    return value


def _id_list(values: list[int], label: str, maximum: int = MAX_WRITE_IDS) -> list[int]:
    if not isinstance(values, list) or not values:
        raise ToolError(f"Give at least one {label}. Write actions need an explicit list of ids.")
    ids: list[int] = []
    for v in values:
        _positive_id(v, label)
        if v not in ids:
            ids.append(v)
    if len(ids) > maximum:
        raise ToolError(f"At most {maximum} {label}s per call; split the list and confirm each batch.")
    return ids


def _text(value: str | None, label: str, maximum: int, required: bool = False) -> str | None:
    if value is None or not str(value).strip():
        if required:
            raise ToolError(f"{label} is required.")
        return None
    value = str(value).strip()
    if len(value) > maximum:
        raise ToolError(f"{label} is too long (max {maximum} characters).")
    return value


def _limit(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_LIST:
        raise ToolError(f"limit must be between 1 and {MAX_LIST}.")
    return value


def _pick(row: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {k: row.get(k) for k in keys if k in row}


CONTACT_FIELDS = (
    "id", "name", "phone", "email", "city", "lead_status", "lead_tier", "lead_tier_reason",
    "source", "assignee", "first_response_at", "created_at",
)
PROSPECT_FIELDS = (
    "id", "name", "company", "role", "decision_maker", "email", "email_status", "phone", "website",
    "industry", "location", "score", "brief", "hook", "service_fit", "status", "contact_id", "created_at",
)


def _contacts(body: dict[str, Any]) -> dict[str, Any]:
    return {
        "total": (body.get("meta") or {}).get("total"),
        "contacts": [_pick(c, CONTACT_FIELDS) for c in body.get("data", [])],
    }


# ── contacts ──────────────────────────────────────────────────────────────────


@mcp.tool(annotations=READ)
async def search_contacts(
    query: Annotated[str, Field(min_length=1, max_length=100, description="Part of a name, phone number or email")],
    lead_status: Annotated[
        str | None,
        Field(max_length=50, description="Only contacts with this lead status, e.g. new, qualified, converted"),
    ] = None,
    limit: Annotated[int, Field(ge=1, le=MAX_LIST)] = 20,
) -> dict[str, Any]:
    """Search CRM contacts by name, phone or email. Read-only.

    Returns up to `limit` contacts (newest first) with id, name, phone, email,
    lead status, lead tier (A=respond now, B=qualify, C=nurture, D=disqualified)
    and owner. Use get_contact for one contact's full record and research.
    """
    q = _text(query, "query", 100, required=True)
    body = await _call(
        "GET", "contacts", f"search contacts for '{q}'",
        params={"search": q, "lead_status": _text(lead_status, "lead_status", 50), "per_page": _limit(limit)},
    )
    return _contacts(body)


@mcp.tool(annotations=READ)
async def get_contact(contact_id: Annotated[int, Field(ge=1, description="CRM contact id")]) -> dict[str, Any]:
    """Get one contact's full record. Read-only.

    Includes lead status and tier (with the reason), owner, tags, notes, source
    and the prospect research (summary, pain points, hook, service fit) when
    the contact came from prospecting.
    """
    cid = _positive_id(contact_id, "contact_id")
    return await _call("GET", f"contacts/{cid}", f"load contact {cid}")


@mcp.tool(annotations=READ)
async def list_hot_leads(limit: Annotated[int, Field(ge=1, le=MAX_LIST)] = 20) -> dict[str, Any]:
    """List tier-A ("respond now") leads, newest first. Read-only.

    Tier A is set by the CRM's lead tiering. Check `first_response_at`: null
    means nobody has replied to the lead yet.
    """
    body = await _call("GET", "contacts", "list tier-A leads", params={"lead_tier": "A", "per_page": _limit(limit)})
    return _contacts(body)


# ── prospects ─────────────────────────────────────────────────────────────────


@mcp.tool(annotations=READ)
async def list_prospects(
    status: Annotated[Literal["pending", "approved", "rejected"], Field(description="Staging status")] = "pending",
    search: Annotated[str | None, Field(max_length=100, description="Name, company, email or phone")] = None,
    brief: Annotated[str | None, Field(max_length=255, description="Only prospects from this search brief")] = None,
    min_score: Annotated[int | None, Field(ge=0, le=100)] = None,
    limit: Annotated[int, Field(ge=1, le=MAX_LIST)] = 20,
) -> dict[str, Any]:
    """List prospects found by the prospecting agent (staging list). Read-only.

    Pending prospects are not contacts yet; they become contacts only through
    approve_prospects. Returns score, hook and service fit to help the owner choose,
    plus counts per status.
    """
    if min_score is not None and not 0 <= min_score <= 100:
        raise ToolError("min_score must be between 0 and 100.")
    body = await _call(
        "GET", "prospects", "list prospects",
        params={
            "status": status,
            "search": _text(search, "search", 100),
            "brief": _text(brief, "brief", 255),
            "min_score": min_score,
            "per_page": _limit(limit),
        },
    )
    return {
        "total": (body.get("meta") or {}).get("total"),
        "counts": body.get("stats"),
        "prospects": [_pick(p, PROSPECT_FIELDS) for p in body.get("data", [])],
    }


@mcp.tool(annotations=WRITE)
async def approve_prospects(
    prospect_ids: Annotated[
        list[int],
        Field(min_length=1, max_length=MAX_WRITE_IDS, description="Explicit prospect ids the owner approved"),
    ],
) -> dict[str, Any]:
    """WRITE: approve the given prospects so they become CRM contacts.

    Only the listed ids are approved (max 50 per call); there is no "approve
    all". Confirm the ids with the owner first. Nothing is sent to the prospects.
    Returns how many were approved and the resulting contact_ids (use them with
    enroll_in_sequence).
    """
    ids = _id_list(prospect_ids, "prospect id")
    body = await _call("POST", "prospects/bulk-approve", f"approve prospects {ids}", json={"ids": ids})
    return {"approved": body.get("approved"), "contact_ids": body.get("contact_ids", []), "message": body.get("message")}


@mcp.tool(annotations=WRITE)
async def trigger_prospect_search(
    industry: Annotated[str, Field(min_length=2, max_length=200, description="Niche, e.g. 'dental clinics'")],
    location: Annotated[str, Field(min_length=2, max_length=255, description="City or region, e.g. 'Chennai'")],
    country: Annotated[str | None, Field(max_length=100)] = None,
    business_type: Annotated[Literal["B2B", "B2C", "Both"] | None, Field()] = None,
    roles: Annotated[list[str] | None, Field(max_length=10, description="Decision-maker roles to look for")] = None,
    keywords: Annotated[list[str] | None, Field(max_length=10)] = None,
    name: Annotated[str | None, Field(max_length=255, description="Label for this search (brief name)")] = None,
) -> dict[str, Any]:
    """WRITE: start a prospect search run in the prospecting agent.

    Runs in the background; results arrive as *pending* prospects (see
    list_prospects with the returned brief). Nobody is contacted. Confirm the
    niche and city with the owner first, since each run uses scraping/LLM credits.
    """
    payload: dict[str, Any] = {
        "industry": _text(industry, "industry", 200, required=True),
        "location": _text(location, "location", 255, required=True),
        "country": _text(country, "country", 100),
        "business_type": business_type,
        "name": _text(name, "name", 255),
    }
    for key, values in (("roles", roles), ("keywords", keywords)):
        if values:
            if len(values) > 10:
                raise ToolError(f"At most 10 {key}.")
            payload[key] = [_text(v, key, 100, required=True) for v in values]
    payload = {k: v for k, v in payload.items() if v is not None}
    body = await _call("POST", "prospects/search", f"start a prospect search for {payload['industry']} in {payload['location']}", json=payload)
    return {"started": bool(body.get("success", True)), "brief": body.get("brief"), "run_id": body.get("run_id"), "message": body.get("message")}


# ── sequences and the review queue ────────────────────────────────────────────


@mcp.tool(annotations=READ)
async def list_sequences() -> dict[str, Any]:
    """List outbound sequences with their status and enrollment counts. Read-only.

    For each sequence: id, name, status (active/paused), steps, enrolled,
    active, replied and completed counts, and reply_rate (replied / enrolled).
    Use the id with enroll_in_sequence or pause_sequence.
    """
    body = await _call("GET", "sequences", "list sequences")
    rows = []
    for s in body.get("data", []):
        enrolled = s.get("enrollments_count") or 0
        replied = s.get("replied_enrollments_count") or 0
        rows.append({
            "id": s.get("id"), "name": s.get("name"), "status": s.get("status"), "goal": s.get("goal"),
            "steps": s.get("steps_count"), "enrolled": enrolled,
            "active": s.get("active_enrollments_count"), "replied": replied,
            "completed": s.get("completed_enrollments_count"),
            "reply_rate": round(replied / enrolled, 4) if enrolled else 0.0,
        })
    return {"sequences": rows}


@mcp.tool(annotations=READ)
async def list_enrollments(
    sequence_id: Annotated[int, Field(ge=1)],
    status: Annotated[Literal["active", "replied", "completed", "stopped", "failed"] | None, Field()] = None,
    limit: Annotated[int, Field(ge=1, le=MAX_LIST)] = 20,
) -> dict[str, Any]:
    """List a sequence's enrollments (newest first), optionally by status. Read-only.

    status=replied shows who answered (updated_at is roughly when).
    """
    sid = _positive_id(sequence_id, "sequence_id")
    body = await _call(
        "GET", f"sequences/{sid}/enrollments", f"list enrollments of sequence {sid}",
        params={"status": status, "per_page": _limit(limit)},
    )
    keys = ("id", "contact_id", "contact", "status", "current_step", "awaiting_approval", "stop_reason", "next_run_at", "updated_at", "ended_at")
    return {"total": body.get("total"), "enrollments": [_pick(e, keys) for e in body.get("data", [])]}


@mcp.tool(annotations=WRITE)
async def enroll_in_sequence(
    sequence_id: Annotated[int, Field(ge=1)],
    contact_ids: Annotated[list[int], Field(min_length=1, max_length=MAX_WRITE_IDS, description="Explicit contact ids")],
) -> dict[str, Any]:
    """WRITE: enroll the given contacts in a sequence (max 50 per call).

    Confirm the sequence and contacts with the owner first. Nothing is sent
    immediately: with approval mode on, each AI-written message becomes a draft
    in the review queue, and every send is compliance-checked by the CRM.
    Returns enrolled contact ids and skipped ones with reasons (already enrolled,
    do-not-contact, no phone/email, ...).
    """
    sid = _positive_id(sequence_id, "sequence_id")
    ids = _id_list(contact_ids, "contact id")
    return await _call("POST", f"sequences/{sid}/enroll", f"enroll contacts {ids} in sequence {sid}", json={"contact_ids": ids})


@mcp.tool(annotations=WRITE)
async def pause_sequence(sequence_id: Annotated[int, Field(ge=1)]) -> dict[str, Any]:
    """WRITE: pause a whole sequence so no further steps run until resumed in the CRM.

    Confirm with the owner first. Enrollments are kept; resuming is done by a person in the CRM.
    """
    sid = _positive_id(sequence_id, "sequence_id")
    body = await _call("POST", f"sequences/{sid}/pause", f"pause sequence {sid}")
    return {"id": body.get("id", sid), "name": body.get("name"), "status": body.get("status")}


@mcp.tool(annotations=READ)
async def list_review_queue(
    channel: Annotated[Literal["whatsapp", "email"] | None, Field()] = None,
    sequence_id: Annotated[int | None, Field(ge=1)] = None,
    limit: Annotated[int, Field(ge=1, le=MAX_LIST)] = 20,
) -> dict[str, Any]:
    """List AI-written outbound drafts waiting for approval (newest first). Read-only.

    Each draft has its id, channel, the payload (WhatsApp template params, or
    email subject/body), the contact, the research hook and the sequence.
    Show the owner the text before approve_draft / reject_draft.
    """
    if sequence_id is not None:
        _positive_id(sequence_id, "sequence_id")
    body = await _call(
        "GET", "outbound-drafts", "list the review queue",
        params={"status": "pending", "channel": channel, "sequence_id": sequence_id, "per_page": _limit(limit)},
    )
    drafts = []
    for d in body.get("data", []):
        contact = d.get("contact") or {}
        enrollment = d.get("enrollment") or {}
        drafts.append({
            "id": d.get("id"), "channel": d.get("channel"), "payload": d.get("payload"),
            "contact": _pick(contact, ("id", "name", "phone", "email")),
            "hook": (contact.get("research") or {}).get("hook"),
            "sequence": (enrollment.get("sequence") or {}).get("name"),
            "step": enrollment.get("current_step"), "created_at": d.get("created_at"),
        })
    return {"pending": body.get("total"), "drafts": drafts}


@mcp.tool(annotations=WRITE)
async def approve_draft(draft_id: Annotated[int, Field(ge=1)]) -> dict[str, Any]:
    """WRITE: approve ONE outbound draft from the review queue.

    Only after the owner explicitly approved this draft. The CRM re-checks
    compliance (do-not-contact, consent, caps) before sending; a contact who
    opted out in the meantime is not messaged.
    """
    did = _positive_id(draft_id, "draft_id")
    body = await _call("POST", f"outbound-drafts/{did}/approve", f"approve draft {did}")
    return {"id": body.get("id", did), "status": body.get("status")}


@mcp.tool(annotations=WRITE)
async def reject_draft(
    draft_id: Annotated[int, Field(ge=1)],
    reason: Annotated[str, Field(min_length=3, max_length=500, description="Why it was rejected (kept in the audit log)")],
    stop_sequence: Annotated[bool, Field(description="Also end this contact's enrollment in the sequence")] = False,
) -> dict[str, Any]:
    """WRITE: reject ONE outbound draft; the step is skipped.

    By default the contact moves on to the sequence's next step; with
    stop_sequence=true their enrollment ends instead. Confirm with the owner first.
    """
    did = _positive_id(draft_id, "draft_id")
    why = _text(reason, "reason", 500, required=True)
    if len(why) < 3:
        raise ToolError("reason is too short; say briefly why the draft was rejected.")
    if not isinstance(stop_sequence, bool):
        raise ToolError("stop_sequence must be true or false.")
    body = await _call(
        "POST", f"outbound-drafts/{did}/reject", f"reject draft {did}",
        json={"reason": why, "stop_enrollment": stop_sequence},
    )
    return {"id": body.get("id", did), "status": body.get("status"), "sequence_stopped": stop_sequence}


# ── reminders ─────────────────────────────────────────────────────────────────

_LOCAL_DT = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?$")


@mcp.tool(annotations=READ)
async def list_reminders(kind: Annotated[Literal["overdue", "upcoming"], Field()] = "overdue") -> dict[str, Any]:
    """List follow-up reminders: overdue ones, or the next 20 upcoming. Read-only.

    Reminders with a meet_link are booked meetings.
    """
    body = await _call("GET", f"reminders-{kind}", f"list {kind} reminders")
    keys = ("id", "title", "remind_at", "status", "priority", "meet_link", "contact_id")
    rows = []
    for r in body.get("data", []):
        row = _pick(r, keys)
        row["contact"] = (r.get("contact") or {}).get("name")
        row["owner"] = (r.get("user") or {}).get("name")
        rows.append(row)
    return {"reminders": rows}


@mcp.tool(annotations=WRITE)
async def create_reminder(
    contact_id: Annotated[int, Field(ge=1)],
    title: Annotated[str, Field(min_length=2, max_length=255)],
    remind_at: Annotated[str, Field(description="Local CRM time 'YYYY-MM-DD HH:MM', in the future")],
    description: Annotated[str | None, Field(max_length=2000)] = None,
    priority: Annotated[Literal["low", "medium", "high"] | None, Field()] = None,
    assign_to_user_id: Annotated[int | None, Field(ge=1, description="CRM user who should get it (default: Hermes)")] = None,
) -> dict[str, Any]:
    """WRITE: create a follow-up reminder on a contact for a team member.

    remind_at is wall-clock time in the CRM's timezone (no UTC offset). No
    calendar invite is sent. Confirm with the owner first.
    """
    cid = _positive_id(contact_id, "contact_id")
    when = (remind_at or "").strip()
    if not _LOCAL_DT.match(when):
        raise ToolError("remind_at must look like '2026-10-08 10:30' (CRM local time, no timezone).")
    try:
        datetime.fromisoformat(when.replace(" ", "T"))
    except ValueError as exc:
        raise ToolError("remind_at is not a real date/time.") from exc
    payload: dict[str, Any] = {
        "contact_id": cid,
        "title": _text(title, "title", 255, required=True),
        "remind_at": when.replace("T", " "),
        "description": _text(description, "description", 2000),
        "priority": priority,
    }
    if assign_to_user_id is not None:
        payload["user_id"] = _positive_id(assign_to_user_id, "assign_to_user_id")
    payload = {k: v for k, v in payload.items() if v is not None}
    body = await _call("POST", "reminders", f"create a reminder for contact {cid}", json=payload)
    data = body.get("data") or {}
    return {"id": data.get("id"), "title": data.get("title"), "remind_at": data.get("remind_at"), "owner": (data.get("user") or {}).get("name")}


# ── reports ───────────────────────────────────────────────────────────────────


@mcp.tool(annotations=READ)
async def get_report(days: Annotated[int, Field(ge=1, le=365)] = 30) -> dict[str, Any]:
    """Messaging/campaign report for the last `days` days. Read-only.

    Delivery and read rates, message volume, campaign and agent stats.
    """
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 365:
        raise ToolError("days must be between 1 and 365.")
    body = await _call("GET", "reports/overview", f"load the {days}-day report", params={"days": days})
    return body.get("data", body)


def _date_range(from_date: str | None, to_date: str | None) -> None:
    """Both optional YYYY-MM-DD dates; from_date on or before to_date."""
    parsed: dict[str, date] = {}
    for label, value in (("from_date", from_date), ("to_date", to_date)):
        if value:
            try:
                parsed[label] = date.fromisoformat(value.strip())
            except ValueError as exc:
                raise ToolError(f"{label} must be a date like 2026-10-01.") from exc
    if len(parsed) == 2 and parsed["from_date"] > parsed["to_date"]:
        raise ToolError("from_date must be on or before to_date.")


@mcp.tool(annotations=READ)
async def get_kpis(
    from_date: Annotated[str | None, Field(description="YYYY-MM-DD; default 30 days before to_date")] = None,
    to_date: Annotated[str | None, Field(description="YYYY-MM-DD; default today")] = None,
) -> dict[str, Any]:
    """Sales KPIs for leads created in a date window. Read-only.

    Lead response time (median, share answered within 5 minutes), qualification
    rate, tier distribution (A-D), meetings booked, conversion to qualified and
    CRM data quality.
    """
    _date_range(from_date, to_date)
    body = await _call(
        "GET", "sales-agent/kpis", "load sales KPIs",
        params={"from": from_date and from_date.strip(), "to": to_date and to_date.strip()},
    )
    return body.get("data", body)


LEARNING_REPORTS = {
    "funnel_by_source": ("reports/funnel", {"group_by": "source"}),
    "funnel_by_sequence": ("reports/funnel", {"group_by": "sequence"}),
    "variants": ("reports/variants", {}),
    "objections": ("reports/objections", {}),
}


@mcp.tool(annotations=READ)
async def get_learning_report(
    report: Annotated[Literal["funnel_by_source", "funnel_by_sequence", "variants", "objections"], Field()],
    from_date: Annotated[str | None, Field(description="YYYY-MM-DD; default 29 days before to_date")] = None,
    to_date: Annotated[str | None, Field(description="YYYY-MM-DD; default today")] = None,
) -> dict[str, Any]:
    """Outbound learning-loop report. Read-only.

    funnel_by_source / funnel_by_sequence: prospects -> contacted -> replied ->
    meeting -> won counts with step rates. variants: sent, replied and reply rate
    per A/B variant of each sequence step, with a verdict (collecting /
    single_arm / no_clear_winner / winner; a winner needs 50 sends per variant and
    a significant difference). objections: AI-tagged objections in replies.
    """
    if report not in LEARNING_REPORTS:
        raise ToolError("report must be one of: " + ", ".join(LEARNING_REPORTS) + ".")
    _date_range(from_date, to_date)
    path, params = LEARNING_REPORTS[report]
    body = await _call(
        "GET", path, f"load the {report.replace('_', ' ')} report",
        params={**params, "from": from_date and from_date.strip(), "to": to_date and to_date.strip()},
    )
    return body.get("data", body)


@mcp.tool(annotations=READ)
async def list_script_suggestions(
    status: Annotated[Literal["pending", "accepted", "dismissed"] | None, Field()] = "pending",
) -> dict[str, Any]:
    """Suggestions from the CRM's weekly script review. Read-only.

    Each has a summary, the suggested change and the evidence (variant numbers,
    top objections). Accepting or dismissing is done by a person in the CRM.
    """
    if status not in (None, "pending", "accepted", "dismissed"):
        raise ToolError("status must be pending, accepted or dismissed.")
    params: dict[str, Any] = {"per_page": 20}
    if status:
        params["status"] = status
    body = await _call("GET", "script-suggestions", "list script suggestions", params=params)
    return {
        "total": body.get("total"),
        "suggestions": [
            {
                "id": s.get("id"), "status": s.get("status"), "week": s.get("review_week"),
                "sequence": (s.get("sequence") or {}).get("name"), "step": (s.get("step") or {}).get("order"),
                "summary": s.get("summary"), "suggestion": s.get("suggestion"), "evidence": s.get("evidence"),
            }
            for s in body.get("data", [])
        ],
    }


def main() -> None:
    try:
        CrmConfig.from_env()
    except CrmError as exc:
        print(f"wh-crm MCP server: {exc}", file=sys.stderr)
        sys.exit(2)
    mcp.run()


if __name__ == "__main__":
    main()
