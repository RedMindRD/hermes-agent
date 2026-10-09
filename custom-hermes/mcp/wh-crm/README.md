# hermes-mcp — WH-CRM tools for Hermes Agent

An MCP server (Python, `FastMCP` from the official `mcp` package) that lets
[Hermes Agent](https://hermes-agent.nousresearch.com/) manage the WH-CRM
pipeline through the CRM's REST API. Hermes runs next to the CRM, never inside
it: every tool is a thin HTTP call with a scoped API token.

Ground rules built into the server and the token:

- Read tools are safe to call any time. Write tools act only on ids passed
  explicitly (max 50 per call); there is no "approve all".
- No tool sends a customer message. Approved drafts and sequence steps still go
  through the CRM's compliance check (do-not-contact, consent, caps) before sending.
- The token cannot send chats, touch the do-not-contact list / consent / erasure,
  delete anything, change settings, users or roles, or edit sequences.

## Install

Python 3.10+ (tested with 3.11). Keep the virtualenv outside the repo.

```bash
python3.11 -m venv ~/.venvs/wh-crm-mcp
~/.venvs/wh-crm-mcp/bin/pip install -r hermes-mcp/requirements.txt
```

`mcp` is pinned to `<2`: mcp 2.x renamed `FastMCP` to `MCPServer`.

## Token and environment

On the CRM server, issue the token for one tenant (id or slug):

```bash
cd backend
php artisan hermes:token --tenant=demo            # create, or rotate (old token is deleted)
php artisan hermes:token --tenant=demo --revoke   # delete it
```

The command creates a dedicated **Hermes** user and **Hermes** role in that
tenant and prints the token **once**. The token does not expire (login tokens
still expire after `SANCTUM_EXPIRATION` minutes); rotate or revoke it instead.

Copy `.env.example` to `hermes-mcp/.env` (read at start-up; real environment
variables win) or pass the variables through Hermes' config:

| Variable | Required | Meaning |
| --- | --- | --- |
| `CRM_BASE_URL` | yes | CRM API host, e.g. `https://crm.example.com` (a trailing `/api` is fine) |
| `CRM_API_TOKEN` | yes | Token from `hermes:token` |
| `CRM_TIMEOUT` | no | Seconds per request, 1–120 (default 20) |

The server exits with a plain message if the URL or token is missing.

## Register with Hermes

Hermes reads MCP servers from `~/.hermes/config.yaml` under `mcp_servers`
(keys `command`, `args`, `env`, `timeout`, …) and exposes each tool as
`mcp_<server>_<tool>` [1] (whether `wh-crm` becomes `wh_crm` in that prefix is not confirmed):

```yaml
mcp_servers:
  wh-crm:
    command: python
    args: ["/opt/hermes/custom-hermes/mcp/wh-crm/server.py"]
    env:
      CRM_BASE_URL: "http://web:8080"
      CRM_API_TOKEN: "${CRM_API_TOKEN:-}"
    timeout: 60
```

Or, as given in the project roadmap:

```bash
hermes mcp add wh-crm --command "python hermes-mcp/server.py"
hermes mcp test wh-crm
```

`hermes mcp test <name>` checks the connection [1]. The `hermes mcp add … --command`
form is **unverified**: the Hermes MCP page documents `config.yaml` and
`hermes mcp add <name> --preset <type>`; `--url`/`--command` only appeared in a
search-result summary [2]. If it is not accepted, use the YAML above. Use the
venv's Python (absolute path) so `mcp` and `httpx` are found.

## Tools

| Tool | Kind | CRM endpoint | Token ability |
| --- | --- | --- | --- |
| `search_contacts` | read | `GET /api/contacts?search=` | `contacts.view` |
| `get_contact` | read | `GET /api/contacts/{id}` | `contacts.view` |
| `list_hot_leads` | read | `GET /api/contacts?lead_tier=A` | `contacts.view` |
| `list_prospects` | read | `GET /api/prospects` | `prospects.view` |
| `approve_prospects` | write | `POST /api/prospects/bulk-approve` (`ids`, ≤50) | `prospects.approve` |
| `trigger_prospect_search` | write | `POST /api/prospects/search` | `prospects.search` |
| `list_sequences` | read | `GET /api/sequences` | `sequences.view` |
| `list_enrollments` | read | `GET /api/sequences/{id}/enrollments` | `sequences.view` |
| `enroll_in_sequence` | write | `POST /api/sequences/{id}/enroll` (`contact_ids`, ≤50) | `sequences.enroll` |
| `pause_sequence` | write | `POST /api/sequences/{id}/pause` | `sequences.enroll` |
| `list_review_queue` | read | `GET /api/outbound-drafts?status=pending` | `sequences.view` |
| `approve_draft` | write | `POST /api/outbound-drafts/{id}/approve` | `outbound-drafts.decide` |
| `reject_draft` | write | `POST /api/outbound-drafts/{id}/reject` (`reason`, `stop_enrollment`) | `outbound-drafts.decide` |
| `list_reminders` | read | `GET /api/reminders-overdue` / `reminders-upcoming` | `reminders.view` |
| `create_reminder` | write | `POST /api/reminders` (never `create_meeting`) | `reminders.create` |
| `get_report` | read | `GET /api/reports/overview?days=` | `reports.view` |
| `get_kpis` | read | `GET /api/sales-agent/kpis?from=&to=` | `reports.view` |
| `get_learning_report` | read | `GET /api/reports/funnel?group_by=` · `/api/reports/variants` · `/api/reports/objections` (`from`, `to`) | `reports.view` |
| `list_script_suggestions` | read | `GET /api/script-suggestions?status=` | `reports.view` |

`list_sequences`, `list_enrollments` and `list_reminders` are read-only additions
the skills need (reply rates, overnight replies, overdue follow-ups, meetings).

Errors come back as plain sentences, e.g. 401 → "The CRM rejected the API token…
issue a new one with `php artisan hermes:token`", 403 → "Hermes is not allowed to …;
ask the owner to do it in the CRM", 404, 422 (with the CRM's validation message),
429, 5xx, timeouts and connection failures.

## Tests

```bash
~/.venvs/wh-crm-mcp/bin/pip install -r hermes-mcp/requirements-dev.txt
cd hermes-mcp && ~/.venvs/wh-crm-mcp/bin/python -m pytest -q
```

HTTP is mocked with `respx`; every tool is tested for success, input validation,
the 403 message and timeouts.

## Sources

1. Hermes Agent docs, MCP: https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp
2. Hermes Agent docs, CLI summary seen via web search (mintlify mirror): https://www.mintlify.com/NousResearch/hermes-agent
