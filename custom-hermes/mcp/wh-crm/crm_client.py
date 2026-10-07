"""Small async HTTP client for the WH-CRM REST API, used by the MCP tools.

Every failure is turned into a ``CrmError`` with a plain sentence that Hermes
can relay to the owner as-is (no stack traces, no raw HTML).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

DEFAULT_TIMEOUT = 20.0


class CrmError(Exception):
    """A CRM call failed; ``str(error)`` is a readable sentence."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def load_dotenv(path: Path) -> None:
    """Read KEY=VALUE lines from ``path`` into os.environ (existing vars win)."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class CrmConfig:
    base_url: str
    token: str
    timeout: float = DEFAULT_TIMEOUT

    @classmethod
    def from_env(cls) -> "CrmConfig":
        base_url = os.environ.get("CRM_BASE_URL", "").strip().rstrip("/")
        token = os.environ.get("CRM_API_TOKEN", "").strip()
        if not base_url:
            raise CrmError("CRM_BASE_URL is not set. Point it at the CRM, e.g. https://crm.example.com.")
        if not base_url.startswith(("http://", "https://")):
            raise CrmError("CRM_BASE_URL must start with http:// or https://.")
        if not token:
            raise CrmError(
                "CRM_API_TOKEN is not set. Create one with "
                "`php artisan hermes:token --tenant=<id or slug>` on the CRM server."
            )
        raw_timeout = os.environ.get("CRM_TIMEOUT", "").strip()
        try:
            timeout = float(raw_timeout) if raw_timeout else DEFAULT_TIMEOUT
        except ValueError as exc:
            raise CrmError("CRM_TIMEOUT must be a number of seconds, e.g. 20.") from exc
        if not 1 <= timeout <= 120:
            raise CrmError("CRM_TIMEOUT must be between 1 and 120 seconds.")
        # Accept both https://host and https://host/api.
        if base_url.endswith("/api"):
            base_url = base_url[: -len("/api")]
        return cls(base_url=base_url, token=token, timeout=timeout)


def _first_validation_error(body: Any) -> str | None:
    if isinstance(body, dict):
        errors = body.get("errors")
        if isinstance(errors, dict):
            messages = [m for msgs in errors.values() for m in (msgs if isinstance(msgs, list) else [msgs])]
            if messages:
                return " ".join(str(m) for m in messages[:3])
        message = body.get("message")
        if isinstance(message, str) and message:
            return message
    return None


def error_for_status(status: int, body: Any, what: str) -> CrmError:
    """Map an HTTP error status to a readable sentence."""
    detail = _first_validation_error(body)
    if status == 401:
        msg = (
            "The CRM rejected the API token (missing, revoked or rotated). Issue a new one with "
            "`php artisan hermes:token --tenant=<id or slug>` and update CRM_API_TOKEN."
        )
    elif status == 403:
        msg = (
            f"Hermes is not allowed to {what}. Its token is deliberately limited "
            "(no messaging, no do-not-contact changes, no deletes); ask the owner to do it in the CRM."
        )
    elif status == 404:
        msg = f"Not found while trying to {what}. Check the id; it may belong to another workspace or be deleted."
    elif status == 422:
        msg = f"The CRM refused to {what}: {detail or 'the input was invalid'}."
    elif status == 429:
        msg = "The CRM is rate-limiting requests. Wait a minute and try again."
    elif status >= 500:
        msg = f"The CRM had a problem while trying to {what} (HTTP {status})"
        msg += f": {detail}." if detail else ". Try again later or check the CRM logs."
    else:
        msg = f"The CRM answered HTTP {status} while trying to {what}"
        msg += f": {detail}." if detail else "."
    return CrmError(msg, status)


class CrmClient:
    def __init__(self, config: CrmConfig, transport: httpx.AsyncBaseTransport | None = None):
        self.config = config
        self._transport = transport

    async def request(
        self,
        method: str,
        path: str,
        what: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        """Call ``/api/<path>`` and return the decoded JSON body.

        ``what`` describes the action in plain words ("approve draft 12") and is
        used in error messages.
        """
        url = f"{self.config.base_url}/api/{path.lstrip('/')}"
        clean_params = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
        headers = {
            "Authorization": f"Bearer {self.config.token}",
            "Accept": "application/json",
            "User-Agent": "wh-crm-hermes-mcp/1.0",
        }
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout, transport=self._transport) as client:
                response = await client.request(method, url, params=clean_params, json=json, headers=headers)
        except httpx.TimeoutException as exc:
            raise CrmError(
                f"The CRM did not answer within {self.config.timeout:g} seconds while trying to {what}. Try again later."
            ) from exc
        except httpx.HTTPError as exc:
            raise CrmError(
                f"Could not reach the CRM at {self.config.base_url} while trying to {what}. "
                "Check CRM_BASE_URL and that the server is running."
            ) from exc

        try:
            body = response.json() if response.content else None
        except ValueError:
            body = None

        if response.status_code >= 400:
            raise error_for_status(response.status_code, body, what)
        if body is None and response.content:
            raise CrmError(f"The CRM sent an unexpected (non-JSON) answer while trying to {what}.")
        return body
