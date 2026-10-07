"""Every tool: success, input validation, 403 mapping and timeout (HTTP mocked with respx)."""

import json

import httpx
import pytest
import respx
from mcp.server.fastmcp.exceptions import ToolError

import server
from conftest import BASE

# tool name -> (valid kwargs, HTTP method, API path, mocked JSON body, invalid kwargs)
CASES = {
    "search_contacts": (
        {"query": "Priya", "limit": 5}, "GET", "/api/contacts",
        {"data": [{"id": 1, "name": "Priya", "lead_tier": "A", "notes": "x"}], "meta": {"total": 1}},
        {"query": "   "},
    ),
    "get_contact": ({"contact_id": 7}, "GET", "/api/contacts/7", {"id": 7, "name": "Priya", "research": None}, {"contact_id": 0}),
    "list_hot_leads": (
        {"limit": 10}, "GET", "/api/contacts",
        {"data": [{"id": 3, "name": "Hot", "lead_tier": "A"}], "meta": {"total": 1}},
        {"limit": 500},
    ),
    "list_prospects": (
        {"status": "pending", "min_score": 60}, "GET", "/api/prospects",
        {"data": [{"id": 9, "name": "Dr. Rao", "score": 80, "source_details": "big"}], "meta": {"total": 1}, "stats": {"pending": 1}},
        {"min_score": 101},
    ),
    "approve_prospects": (
        {"prospect_ids": [4, 5, 4]}, "POST", "/api/prospects/bulk-approve",
        {"success": True, "approved": 2, "contact_ids": [11, 12], "message": "ok"},
        {"prospect_ids": []},
    ),
    "trigger_prospect_search": (
        {"industry": "dental clinics", "location": "Chennai", "roles": ["Owner"]}, "POST", "/api/prospects/search",
        {"success": True, "brief": "dental clinics", "run_id": "r1", "message": "started"},
        {"industry": "dental", "location": " "},
    ),
    "list_sequences": (
        {}, "GET", "/api/sequences",
        {"data": [{"id": 2, "name": "Cold", "status": "active", "enrollments_count": 10, "replied_enrollments_count": 3}]},
        None,
    ),
    "list_enrollments": (
        {"sequence_id": 2, "status": "replied"}, "GET", "/api/sequences/2/enrollments",
        {"data": [{"id": 1, "contact_id": 4, "status": "replied"}], "total": 1},
        {"sequence_id": -1},
    ),
    "enroll_in_sequence": (
        {"sequence_id": 2, "contact_ids": [11, 12]}, "POST", "/api/sequences/2/enroll",
        {"enrolled": [11], "skipped": [{"contact_id": 12, "reason": "do_not_contact"}]},
        {"sequence_id": 2, "contact_ids": list(range(1, 52))},
    ),
    "pause_sequence": ({"sequence_id": 2}, "POST", "/api/sequences/2/pause", {"id": 2, "name": "Cold", "status": "paused"}, {"sequence_id": 0}),
    "list_review_queue": (
        {"channel": "email"}, "GET", "/api/outbound-drafts",
        {"data": [{"id": 5, "channel": "email", "payload": {"subject": "Hi"}, "contact": {"id": 1, "name": "P", "research": {"hook": "new clinic"}},
                   "enrollment": {"current_step": 1, "sequence": {"name": "Cold"}}}], "total": 1},
        {"sequence_id": 0},
    ),
    "approve_draft": ({"draft_id": 5}, "POST", "/api/outbound-drafts/5/approve", {"id": 5, "status": "approved"}, {"draft_id": 0}),
    "reject_draft": (
        {"draft_id": 5, "reason": "Too pushy", "stop_sequence": True}, "POST", "/api/outbound-drafts/5/reject",
        {"id": 5, "status": "rejected"},
        {"draft_id": 5, "reason": " "},
    ),
    "list_reminders": (
        {"kind": "overdue"}, "GET", "/api/reminders-overdue",
        {"data": [{"id": 1, "title": "Call", "contact": {"name": "P"}, "user": {"name": "Owner"}}]},
        {"kind": "yesterday"},
    ),
    "create_reminder": (
        {"contact_id": 3, "title": "Call back", "remind_at": "2030-01-02 10:30"}, "POST", "/api/reminders",
        {"data": {"id": 8, "title": "Call back", "remind_at": "2030-01-02T05:00:00Z", "user": {"name": "Hermes"}}},
        {"contact_id": 3, "title": "Call back", "remind_at": "tomorrow"},
    ),
    "get_report": ({"days": 7}, "GET", "/api/reports/overview", {"data": {"total_messages": 10}}, {"days": 0}),
    "get_kpis": (
        {"from_date": "2026-09-01", "to_date": "2026-09-30"}, "GET", "/api/sales-agent/kpis",
        {"data": {"tier_distribution": {"A": 2}}},
        {"from_date": "2026-10-01", "to_date": "2026-09-01"},
    ),
    "get_learning_report": (
        {"report": "variants", "from_date": "2026-09-01", "to_date": "2026-09-30"}, "GET", "/api/reports/variants",
        {"data": {"min_sample": 50, "steps": []}},
        {"report": "variants", "from_date": "30-09-2026"},
    ),
    "list_script_suggestions": (
        {"status": "pending"}, "GET", "/api/script-suggestions",
        {"data": [{"id": 1, "status": "pending", "summary": "S", "suggestion": "T", "sequence": {"name": "Cold"}, "step": {"order": 1}}], "total": 1},
        {"status": "approved"},
    ),
}


def tool(name):
    return getattr(server, name)


def test_every_registered_tool_is_covered():
    import asyncio

    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert names == set(CASES)


@pytest.mark.parametrize("name", CASES)
@respx.mock
async def test_success(name):
    kwargs, method, path, body, _ = CASES[name]
    route = respx.route(method=method, url=f"{BASE}{path}").mock(return_value=httpx.Response(200, json=body))

    result = await tool(name)(**kwargs)

    assert route.called
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer 1|test-token"
    assert request.headers["Accept"] == "application/json"
    assert isinstance(result, dict)


@pytest.mark.parametrize("name", [n for n, c in CASES.items() if c[4] is not None])
async def test_validation_error_never_calls_the_crm(name):
    *_, invalid = CASES[name]
    with respx.mock(assert_all_called=False) as router:
        route = router.route(host="crm.test").mock(return_value=httpx.Response(200, json={}))

        # Through FastMCP (pydantic schema) and directly (the tool's own checks).
        with pytest.raises(ToolError):
            await server.mcp.call_tool(name, invalid)
        if name not in {"list_reminders", "list_script_suggestions"}:  # a Literal is only checked by the schema
            with pytest.raises(ToolError):
                await tool(name)(**invalid)
        assert not route.called


@pytest.mark.parametrize("name", CASES)
@respx.mock
async def test_403_is_a_plain_sentence(name):
    kwargs, method, path, *_ = CASES[name]
    respx.route(method=method, url=f"{BASE}{path}").mock(return_value=httpx.Response(403, json={"message": "Unauthorized"}))

    with pytest.raises(ToolError) as err:
        await tool(name)(**kwargs)

    assert "Hermes is not allowed to" in str(err.value)
    assert "ask the owner" in str(err.value)


@pytest.mark.parametrize("name", CASES)
@respx.mock
async def test_timeout_is_reported(name):
    kwargs, method, path, *_ = CASES[name]
    respx.route(method=method, url=f"{BASE}{path}").mock(side_effect=httpx.ReadTimeout("slow"))

    with pytest.raises(ToolError) as err:
        await tool(name)(**kwargs)

    assert "did not answer within 5 seconds" in str(err.value)


# ── request details ───────────────────────────────────────────────────────────


@respx.mock
async def test_hot_leads_filter_tier_a_and_trim_fields():
    route = respx.get(f"{BASE}/api/contacts").mock(return_value=httpx.Response(200, json=CASES["list_hot_leads"][3]))
    result = await server.list_hot_leads(limit=10)
    params = route.calls.last.request.url.params
    assert params["lead_tier"] == "A" and params["per_page"] == "10"
    assert result == {"total": 1, "contacts": [{"id": 3, "name": "Hot", "lead_tier": "A"}]}


@respx.mock
async def test_write_tools_send_explicit_deduplicated_ids():
    route = respx.post(f"{BASE}/api/prospects/bulk-approve").mock(return_value=httpx.Response(200, json=CASES["approve_prospects"][3]))
    result = await server.approve_prospects(prospect_ids=[4, 5, 4])
    assert json.loads(route.calls.last.request.content) == {"ids": [4, 5]}
    assert result["contact_ids"] == [11, 12]

    with pytest.raises(ToolError, match="At most 50"):
        await server.approve_prospects(prospect_ids=list(range(1, 52)))


@respx.mock
async def test_reject_sends_reason_and_stop_flag():
    route = respx.post(f"{BASE}/api/outbound-drafts/5/reject").mock(return_value=httpx.Response(200, json={"id": 5, "status": "rejected"}))
    await server.reject_draft(draft_id=5, reason="Too pushy", stop_sequence=True)
    assert json.loads(route.calls.last.request.content) == {"reason": "Too pushy", "stop_enrollment": True}


@respx.mock
async def test_create_reminder_never_requests_a_meeting():
    route = respx.post(f"{BASE}/api/reminders").mock(return_value=httpx.Response(201, json=CASES["create_reminder"][3]))
    await server.create_reminder(contact_id=3, title="Call back", remind_at="2030-01-02T10:30", assign_to_user_id=4)
    sent = json.loads(route.calls.last.request.content)
    assert sent == {"contact_id": 3, "title": "Call back", "remind_at": "2030-01-02 10:30", "user_id": 4}


@respx.mock
async def test_list_sequences_computes_reply_rate():
    respx.get(f"{BASE}/api/sequences").mock(return_value=httpx.Response(200, json=CASES["list_sequences"][3]))
    result = await server.list_sequences()
    assert result["sequences"][0]["reply_rate"] == 0.3


@respx.mock
async def test_call_through_fastmcp_returns_structured_result():
    respx.get(f"{BASE}/api/contacts/7").mock(return_value=httpx.Response(200, json={"id": 7, "name": "Priya"}))
    result = await server.mcp.call_tool("get_contact", {"contact_id": 7})
    assert "Priya" in json.dumps(result, default=str)


# ── error mapping ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "status,body,expected",
    [
        (401, {"message": "Unauthenticated."}, "rejected the API token"),
        (404, {"message": "Not Found"}, "Not found while trying to approve draft 5"),
        (422, {"message": "x", "errors": {"id": ["This draft is no longer pending."]}}, "refused to approve draft 5: This draft is no longer pending."),
        (429, {}, "rate-limiting"),
        (500, {"message": "Server Error"}, "had a problem while trying to approve draft 5 (HTTP 500)"),
        (502, {"success": False, "message": "Prospecting agent unreachable"}, "Prospecting agent unreachable"),
    ],
)
@respx.mock
async def test_error_statuses_become_sentences(status, body, expected):
    respx.post(f"{BASE}/api/outbound-drafts/5/approve").mock(return_value=httpx.Response(status, json=body))
    with pytest.raises(ToolError) as err:
        await server.approve_draft(draft_id=5)
    assert expected in str(err.value)


@respx.mock
async def test_unreachable_crm_and_non_json_answer():
    respx.get(f"{BASE}/api/contacts/1").mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(ToolError, match="Could not reach the CRM"):
        await server.get_contact(contact_id=1)

    respx.get(f"{BASE}/api/contacts/2").mock(return_value=httpx.Response(200, text="<html>login</html>"))
    with pytest.raises(ToolError, match="non-JSON"):
        await server.get_contact(contact_id=2)


async def test_missing_configuration_is_explained(monkeypatch):
    monkeypatch.delenv("CRM_API_TOKEN")
    with pytest.raises(ToolError, match="CRM_API_TOKEN is not set"):
        await server.get_contact(contact_id=1)

    monkeypatch.setenv("CRM_API_TOKEN", "t")
    monkeypatch.setenv("CRM_BASE_URL", "crm.test")
    with pytest.raises(ToolError, match="must start with http"):
        await server.get_contact(contact_id=1)


@respx.mock
async def test_base_url_with_trailing_api_is_accepted(monkeypatch):
    monkeypatch.setenv("CRM_BASE_URL", f"{BASE}/api/")
    route = respx.get(f"{BASE}/api/contacts/1").mock(return_value=httpx.Response(200, json={"id": 1}))
    await server.get_contact(contact_id=1)
    assert route.called


@respx.mock
async def test_learning_report_maps_to_the_right_endpoint():
    route = respx.get(f"{BASE}/api/reports/funnel").mock(return_value=httpx.Response(200, json={"data": {"rows": []}}))

    await server.get_learning_report(report="funnel_by_sequence")

    assert route.calls.last.request.url.params["group_by"] == "sequence"
