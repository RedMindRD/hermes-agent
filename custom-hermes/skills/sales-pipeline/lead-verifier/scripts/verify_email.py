#!/usr/bin/env python3
"""Verify email addresses without sending anything. Stdlib only.

Levels (each implies the previous): format_ok -> domain_ok -> mx_ok.
Terminal statuses: invalid (definitely bad), error (check itself failed —
treat as unverified, do NOT drop the contact).

Usage:
  python3 verify_email.py addr1 [addr2 ...]
  ... | python3 verify_email.py -          # one address per line on stdin

Output: one JSON object per line: {"email", "status", "detail"}.
Exit 0 always; a batch never aborts because one address misbehaves.
"""
import json
import re
import socket
import subprocess
import sys

DNS_TIMEOUT = 8       # getaddrinfo can otherwise hang for minutes
LOOKUP_TIMEOUT = 10

EMAIL_RE = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)
JUNK_LOCALPARTS = {"noreply", "no-reply", "donotreply", "example", "test", "postmaster"}


def domain_resolves(domain: str) -> bool | None:
    """True/False on a definitive answer, None when DNS itself failed."""
    try:
        socket.getaddrinfo(domain, None, proto=socket.IPPROTO_TCP)
        return True
    except socket.gaierror as e:
        # EAI_NONAME/NODATA = authoritative "no such host"; anything else
        # (EAI_AGAIN etc.) is our resolver having a bad day, not their domain.
        if e.errno in (socket.EAI_NONAME, getattr(socket, "EAI_NODATA", -5)):
            return False
        return None
    except (UnicodeError, OSError):
        return False


def has_mx(domain: str) -> bool | None:
    """True/False on a clear answer, None when no tool gave one."""
    for cmd, positive in (
        (["dig", "+short", "+time=5", "MX", domain], None),  # any output = MX
        (["nslookup", "-type=mx", domain], "mail exchanger"),
    ):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True,
                                 timeout=LOOKUP_TIMEOUT)
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            continue
        text = ((out.stdout or "") + (out.stderr or "")).lower()
        if positive is None:                     # dig
            if out.returncode == 0:
                if out.stdout.strip():
                    return True
                return False                     # clean empty answer = no MX
            continue                             # dig error -> try nslookup
        if positive in text:                     # nslookup
            return True
        if "can't find" in text or "nxdomain" in text:
            return False
    return None


def verify(email: str) -> dict:
    email = email.strip().strip("<>").lower()
    if not email:
        return {"email": email, "status": "invalid", "detail": "empty"}
    if not EMAIL_RE.match(email):
        # Allow IDN domains the ASCII regex rejects: try punycode round-trip.
        try:
            local, domain = email.rsplit("@", 1)
            domain = domain.encode("idna").decode("ascii")
            email_ascii = f"{local}@{domain}"
        except (ValueError, UnicodeError):
            return {"email": email, "status": "invalid", "detail": "syntax"}
        if not EMAIL_RE.match(email_ascii):
            return {"email": email, "status": "invalid", "detail": "syntax"}
        email = email_ascii
    local, domain = email.rsplit("@", 1)
    if local in JUNK_LOCALPARTS:
        return {"email": email, "status": "invalid", "detail": "junk localpart"}
    resolves = domain_resolves(domain)
    if resolves is False:
        return {"email": email, "status": "invalid", "detail": "domain does not resolve"}
    if resolves is None:
        return {"email": email, "status": "error",
                "detail": "DNS lookup failed (resolver issue) — retry later"}
    mx = has_mx(domain)
    if mx is True:
        return {"email": email, "status": "mx_ok", "detail": "domain + MX verified"}
    if mx is False:
        return {"email": email, "status": "domain_ok", "detail": "no MX record found"}
    return {"email": email, "status": "domain_ok", "detail": "MX check unavailable"}


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__.strip(), file=sys.stderr)
        raise SystemExit(2)
    addrs = (line for line in sys.stdin) if args == ["-"] else args
    for addr in addrs:
        addr = addr.strip()
        if not addr:
            continue
        try:
            result = verify(addr)
        except Exception as e:  # one bad input must not kill the batch
            result = {"email": addr, "status": "error",
                      "detail": f"unexpected {type(e).__name__}: {e}"}
        print(json.dumps(result), flush=True)


if __name__ == "__main__":
    socket.setdefaulttimeout(DNS_TIMEOUT)
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit(130)
