"""Helpers for the REST API adapters (Jira and GitHub today), so that they
accept, refuse and report exactly what the Rust versions did:

- `parse_url`: WHATWG URL parsing as the Rust `url` crate does it, for the
  parts a site or server address uses;
- `reason`: HTTP reason phrases as the Rust `http` crate spells them;
- strict JSON field reads with serde's rules, so a response serde would
  have refused is refused here too;
- `arg`: method params checked as Tauri checked command arguments.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote_to_bytes

import httpx
import idna

from ..core import errors

# --- URLs -----------------------------------------------------------------

# Special schemes and their default ports.
_SPECIAL = {"ftp": 21, "file": None, "http": 80, "https": 443, "ws": 80, "wss": 443}
# Hosts may not contain these, nor anything up to U+0020, nor U+007F.
_DENIED = set("%#/:<>?@[\\]^|")
# Path characters the parser percent-encodes; anything outside ASCII too.
_PATH_ENCODE = set(' "<>`#?{}')


@dataclass(frozen=True)
class Url:
    # Lowercase.
    scheme: str
    # As `Url::host_str`: lowercase ASCII, dotted IPv4 or bracketed IPv6.
    # `None` for schemes other than the special ones.
    host: str | None
    # `None` when absent or the scheme's default.
    port: int | None
    # Dot segments resolved and percent-encoded; at least `/`.
    path: str


def parse_url(text: str) -> Url | None:
    """Parses an absolute URL; `None` where `Url::parse` fails. Query and
    fragment are dropped, and so are credentials. Non-special schemes are
    taken as parsed: callers refuse them anyway."""
    text = text.strip("".join(map(chr, range(0x21))))
    text = re.sub("[\t\n\r]", "", text)
    m = re.match(r"[A-Za-z][A-Za-z0-9+.\-]*:", text)
    if m is None:
        return None
    scheme = m.group()[:-1].lower()
    if scheme not in _SPECIAL or scheme == "file":
        return Url(scheme, None, None, "")

    # Any run of slashes or backslashes leads to the authority.
    rest = text[m.end() :].lstrip("/\\")
    end = _find_any(rest, "/\\?#")
    authority, rest = rest[:end], rest[end:]
    # Credentials end at the last `@`.
    authority = authority[authority.rfind("@") + 1 :]

    host_text, port_text = authority, None
    in_brackets = False
    for i, c in enumerate(authority):
        if c == "[":
            in_brackets = True
        elif c == "]":
            in_brackets = False
        elif c == ":" and not in_brackets:
            host_text, port_text = authority[:i], authority[i + 1 :]
            break
    if not host_text:
        return None
    host = _host(host_text)
    if host is None:
        return None

    port = None
    if port_text is not None:
        if not re.fullmatch("[0-9]*", port_text):
            return None
        if port_text:
            number = int(port_text)
            if number > 0xFFFF:
                return None
            if number != _SPECIAL[scheme]:
                port = number

    return Url(scheme, host, port, _path(rest[: _find_any(rest, "?#")]))


def _find_any(text: str, chars: str) -> int:
    return next((i for i, c in enumerate(text) if c in chars), len(text))


def _host(text: str) -> str | None:
    if text.startswith("["):
        if not text.endswith("]"):
            return None
        return _ipv6(text[1:-1])
    try:
        domain = unquote_to_bytes(text).decode("utf-8")
    except UnicodeDecodeError:
        return None
    domain = _domain_to_ascii(domain)
    if not domain:
        return None
    if _ends_in_number(domain):
        return _ipv4(domain)
    return domain


def _domain_to_ascii(domain: str) -> str | None:
    """UTS 46 as the URL standard runs it, then its deny list."""
    if domain.isascii():
        domain = domain.lower()
        for label in domain.split("."):
            if label.startswith("xn--"):
                try:
                    idna.decode(label)
                except (idna.IDNAError, UnicodeError):
                    return None
    else:
        try:
            domain = idna.encode(domain, uts46=True).decode("ascii")
        except (idna.IDNAError, UnicodeError):
            return None
    if any(c in _DENIED or ord(c) <= 0x20 or ord(c) == 0x7F for c in domain):
        return None
    return domain


def _ends_in_number(domain: str) -> bool:
    parts = domain.split(".")
    if parts[-1] == "" and len(parts) > 1:
        parts.pop()
    last = parts[-1]
    if last and re.fullmatch("[0-9]+", last):
        return True
    return _ipv4_number(last) is not False


def _ipv4_number(text: str) -> int | None | bool:
    """The number, `None` if it overflows 32 bits, `False` if it is not one."""
    if not text:
        return False
    radix = 10
    if text[:2] in ("0x", "0X"):
        text, radix = text[2:], 16
    elif len(text) >= 2 and text[0] == "0":
        text, radix = text[1:], 8
    if not text:
        return 0
    digits = {8: "[0-7]+", 10: "[0-9]+", 16: "[0-9A-Fa-f]+"}[radix]
    if not re.fullmatch(digits, text):
        return False
    number = int(text, radix)
    return number if number <= 0xFFFFFFFF else None


def _ipv4(domain: str) -> str | None:
    parts = domain.split(".")
    if parts[-1] == "":
        parts.pop()
    if len(parts) > 4:
        return None
    numbers = []
    for part in parts:
        n = _ipv4_number(part)
        if n is None or n is False:
            return None
        numbers.append(n)
    address = numbers.pop()
    if address > 0xFFFFFFFF >> (8 * len(numbers)) or any(n > 255 for n in numbers):
        return None
    for i, n in enumerate(numbers):
        address += n << (8 * (3 - i))
    return str(ipaddress.IPv4Address(address))


def _ipv6(text: str) -> str | None:
    if "%" in text:
        return None
    try:
        packed = ipaddress.IPv6Address(text).packed
    except ValueError:
        return None
    pieces = [int.from_bytes(packed[i : i + 2]) for i in range(0, 16, 2)]
    # Compress the longest run of two or more zero pieces, the first on a tie.
    start, length = -1, 1
    i = 0
    while i < 8:
        if pieces[i] == 0:
            j = i
            while j < 8 and pieces[j] == 0:
                j += 1
            if j - i > length:
                start, length = i, j - i
            i = j
        else:
            i += 1
    hexes = [f"{p:x}" for p in pieces]
    if start < 0:
        return f"[{':'.join(hexes)}]"
    head, tail = ":".join(hexes[:start]), ":".join(hexes[start + length :])
    return f"[{head}::{tail}]"


def _path(text: str) -> str:
    """`text` is empty or starts with a separator."""
    segments: list[str] = []
    buffer = ""
    for c in [*text[1:], None]:
        if c is None or c in "/\\":
            dots = buffer.lower().replace("%2e", ".")
            if dots == "..":
                if segments:
                    segments.pop()
                if c is None:
                    segments.append("")
            elif dots == ".":
                if c is None:
                    segments.append("")
            else:
                segments.append(buffer)
            buffer = ""
        elif c in _PATH_ENCODE or ord(c) < 0x20 or ord(c) >= 0x7F:
            buffer += "".join(f"%{b:02X}" for b in c.encode("utf-8", "surrogatepass"))
        else:
            buffer += c
    return "/" + "/".join(segments)


# --- HTTP reason phrases --------------------------------------------------

# `StatusCode::canonical_reason` in the `http` crate. Python's own phrases
# differ for a few codes and between versions.
_REASONS = {
    100: "Continue", 101: "Switching Protocols", 102: "Processing", 103: "Early Hints",
    200: "OK", 201: "Created", 202: "Accepted", 203: "Non Authoritative Information",
    204: "No Content", 205: "Reset Content", 206: "Partial Content", 207: "Multi-Status",
    208: "Already Reported", 226: "IM Used",
    300: "Multiple Choices", 301: "Moved Permanently", 302: "Found", 303: "See Other",
    304: "Not Modified", 305: "Use Proxy", 307: "Temporary Redirect", 308: "Permanent Redirect",
    400: "Bad Request", 401: "Unauthorized", 402: "Payment Required", 403: "Forbidden",
    404: "Not Found", 405: "Method Not Allowed", 406: "Not Acceptable",
    407: "Proxy Authentication Required", 408: "Request Timeout", 409: "Conflict", 410: "Gone",
    411: "Length Required", 412: "Precondition Failed", 413: "Payload Too Large",
    414: "URI Too Long", 415: "Unsupported Media Type", 416: "Range Not Satisfiable",
    417: "Expectation Failed", 418: "I'm a teapot", 421: "Misdirected Request",
    422: "Unprocessable Entity", 423: "Locked", 424: "Failed Dependency", 425: "Too Early",
    426: "Upgrade Required", 428: "Precondition Required", 429: "Too Many Requests",
    431: "Request Header Fields Too Large", 451: "Unavailable For Legal Reasons",
    500: "Internal Server Error", 501: "Not Implemented", 502: "Bad Gateway",
    503: "Service Unavailable", 504: "Gateway Timeout", 505: "HTTP Version Not Supported",
    506: "Variant Also Negotiates", 507: "Insufficient Storage", 508: "Loop Detected",
    510: "Not Extended", 511: "Network Authentication Required",
}  # fmt: skip


def reason(status: int) -> str:
    return _REASONS.get(status, "unknown error")


# --- JSON -----------------------------------------------------------------


class Invalid(ValueError):
    """A response that does not have the shape the API promises."""


def read_body(response: httpx.Response, read):
    """`read` applied to the JSON body. Raises `Invalid` when the body is
    not JSON or `read` refuses it."""
    try:
        value = response.json()
    except ValueError:
        raise Invalid() from None
    return read(value)


def decode(response: httpx.Response, read):
    """`read_body`, with a malformed body reported as reqwest did."""
    try:
        return read_body(response, read)
    except Invalid:
        raise errors.Network("error decoding response body") from None


def obj(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise Invalid()
    return value


def string(o: dict[str, Any], key: str) -> str:
    """A required string."""
    value = o.get(key)
    if not isinstance(value, str):
        raise Invalid()
    return value


def opt_string(o: dict[str, Any], key: str) -> str | None:
    """A string, `None` when missing or null."""
    value = o.get(key)
    if value is not None and not isinstance(value, str):
        raise Invalid()
    return value


def default_string(o: dict[str, Any], key: str) -> str:
    """A string, empty when missing. Null is refused, as serde does."""
    if key not in o:
        return ""
    return string(o, key)


def default_bool(o: dict[str, Any], key: str) -> bool:
    if key not in o:
        return False
    value = o[key]
    if not isinstance(value, bool):
        raise Invalid()
    return value


def u64(o: dict[str, Any], key: str) -> int:
    value = o.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 2**64:
        raise Invalid()
    return value


def default_list(o: dict[str, Any], key: str, read) -> list:
    if key not in o:
        return []
    value = o[key]
    if not isinstance(value, list):
        raise Invalid()
    return [read(v) for v in value]


def opt(o: dict[str, Any], key: str, read):
    """`read(value)`, `None` when missing or null."""
    value = o.get(key)
    return None if value is None else read(value)


# --- Arguments ------------------------------------------------------------


def arg(params: dict[str, Any], key: str, method: str, required: bool = True) -> str | None:
    """A string param of `method`, as the Rust command's typed argument was:
    `None` only when optional and missing or null."""
    value = params.get(key)
    if value is None and not required:
        return None
    if not isinstance(value, str):
        problem = "is missing" if value is None else "must be a string"
        raise errors.AppError(f"invalid params for `{method}`: `{key}` {problem}")
    return value
