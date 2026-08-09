#!/usr/bin/env python3
"""Check that company websites are live. Stdlib only, no external deps.

Usage:
  python3 check_domain.py domain1 [domain2 ...]     # bare domains or URLs
  ... | python3 check_domain.py -                    # one per line on stdin

Output: one JSON object per line:
  {"domain", "live", "status_code", "final_url", "redirected_offsite", "detail"}

live=false + detail containing "dns" means genuinely dead — drop the lead.
live=false with a transient detail (timeout/reset) means UNKNOWN — keep the
lead, note "site unreachable this run". Bot-blockers (403/405/429) count as
live. Transient failures are retried once before being reported.
Exit 0 always; one bad domain never aborts the batch.
"""
import json
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = 10
UA = "Mozilla/5.0 (compatible; lead-verifier/1.1)"
BOT_BLOCK_CODES = {401, 403, 405, 406, 429, 503}
TRANSIENT = (TimeoutError, socket.timeout, ConnectionResetError, ssl.SSLEOFError)


def root_domain(host: str) -> str:
    parts = host.lower().split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def probe(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA}, method="GET")
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
        return {"status_code": resp.status, "final_url": resp.url}


def check_once(domain: str) -> dict:
    result = {"domain": domain, "live": False, "status_code": None,
              "final_url": None, "redirected_offsite": False, "detail": ""}
    details = []
    for scheme in ("https", "http"):
        try:
            info = probe(f"{scheme}://{domain}/")
            final_host = urllib.parse.urlsplit(info["final_url"]).hostname or domain
            result.update(
                live=info["status_code"] < 400,
                status_code=info["status_code"],
                final_url=info["final_url"],
                redirected_offsite=root_domain(final_host) != root_domain(domain),
                detail=scheme,
            )
            return result
        except urllib.error.HTTPError as e:
            # An HTTP response means the site exists; 4xx/5xx class decides.
            result.update(live=e.code in BOT_BLOCK_CODES,
                          status_code=e.code, detail=f"{scheme} HTTP {e.code}")
            return result
        except urllib.error.URLError as e:
            reason = e.reason
            if isinstance(reason, socket.gaierror):
                details.append(f"{scheme}: dns failure ({reason})")
                continue
            if isinstance(reason, TRANSIENT):
                details.append(f"{scheme}: transient {type(reason).__name__}")
                continue
            details.append(f"{scheme}: {type(reason).__name__}: {reason}")
        except TRANSIENT as e:
            details.append(f"{scheme}: transient {type(e).__name__}")
        except ssl.SSLError as e:
            # Broken TLS on a host that answered — site exists, cert is bad.
            result.update(live=True, detail=f"{scheme}: ssl error ({e.reason})")
            return result
        except Exception as e:
            details.append(f"{scheme}: {type(e).__name__}")
    result["detail"] = "; ".join(details) or "unreachable"
    return result


def check(raw: str) -> dict:
    domain = raw.strip().lower()
    for prefix in ("https://", "http://"):
        domain = domain.removeprefix(prefix)
    domain = domain.split("/")[0].removeprefix("www.")
    if not domain or "." not in domain:
        return {"domain": domain, "live": False, "status_code": None,
                "final_url": None, "redirected_offsite": False,
                "detail": "invalid domain"}
    result = check_once(domain)
    if not result["live"] and "transient" in result["detail"]:
        time.sleep(2)                       # single retry for flaky networks
        retry = check_once(domain)
        retry["detail"] = f"retried: {retry['detail']}"
        return retry
    return result


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__.strip(), file=sys.stderr)
        raise SystemExit(2)
    targets = (line for line in sys.stdin) if args == ["-"] else args
    for raw in targets:
        raw = raw.strip()
        if not raw:
            continue
        try:
            result = check(raw)
        except Exception as e:  # one bad domain must not kill the batch
            result = {"domain": raw, "live": False, "status_code": None,
                      "final_url": None, "redirected_offsite": False,
                      "detail": f"unexpected {type(e).__name__}: {e}"}
        print(json.dumps(result), flush=True)


if __name__ == "__main__":
    socket.setdefaulttimeout(TIMEOUT)
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit(130)
