"""Jira REST calls, read-only. Works with Jira Cloud (account email plus API
token, scoped or not) and Jira Data Center (personal access token)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import httpx

from ...adapters import rest
from ...adapters.http import send
from ...core import errors
from ...core.model import Direction, JiraEndpoint, JiraFlavor

GATEWAY = "https://api.atlassian.com/ex/jira"

# Open issues assigned to or reported by the user, most recently updated
# first.
JQL = "(assignee = currentUser() OR reporter = currentUser()) AND statusCategory != Done ORDER BY updated DESC"
FIELDS = "summary,status,assignee,reporter,updated,project"


@dataclass
class Credential:
    """What is kept in the OS credential store. With an email it is a Jira
    Cloud API token (HTTP Basic); without, a Data Center personal access
    token (Bearer)."""

    email: str | None
    token: str

    def to_secret(self) -> str:
        # Byte for byte what serde_json wrote, so stored sign-ins carry over.
        return json.dumps({"email": self.email, "token": self.token}, separators=(",", ":"), ensure_ascii=False)

    @staticmethod
    def from_secret(text: str) -> Credential | None:
        """`None` when the stored value is not a credential."""
        try:
            o = rest.obj(json.loads(text))
            return Credential(email=rest.opt_string(o, "email"), token=rest.string(o, "token"))
        except ValueError:
            return None


def url(endpoint: JiraEndpoint, path: str) -> str:
    version = "3" if endpoint.flavor == JiraFlavor.CLOUD else "2"
    return f"{endpoint.api_base}/rest/api/{version}/{path}"


@dataclass
class Me:
    # Cloud account ID, or the Data Center user key.
    id: str
    name: str


@dataclass
class IssueMeta:
    issue_id: str
    key: str
    summary: str
    direction: Direction
    status: str
    project: str
    assignee: str
    reporter: str
    url: str
    date: str


@dataclass
class RawUser:
    account_id: str | None
    key: str | None
    name: str | None
    display_name: str

    def id(self) -> str | None:
        return next((v for v in (self.account_id, self.key, self.name) if v is not None), None)


@dataclass
class RawFields:
    summary: str
    status: str | None
    project: str | None
    assignee: RawUser | None
    reporter: RawUser | None
    updated: str | None


@dataclass
class RawIssue:
    id: str
    key: str
    fields: RawFields


def _read_user(value: Any) -> RawUser:
    o = rest.obj(value)
    return RawUser(
        account_id=rest.opt_string(o, "accountId"),
        key=rest.opt_string(o, "key"),
        name=rest.opt_string(o, "name"),
        display_name=rest.default_string(o, "displayName"),
    )


def _read_name(value: Any) -> str:
    return rest.string(rest.obj(value), "name")


def _read_key(value: Any) -> str:
    return rest.string(rest.obj(value), "key")


def read_issue(value: Any) -> RawIssue:
    o = rest.obj(value)
    f = rest.obj(o.get("fields"))
    return RawIssue(
        id=rest.string(o, "id"),
        key=rest.string(o, "key"),
        fields=RawFields(
            summary=rest.default_string(f, "summary"),
            status=rest.opt(f, "status", _read_name),
            project=rest.opt(f, "project", _read_key),
            assignee=rest.opt(f, "assignee", _read_user),
            reporter=rest.opt(f, "reporter", _read_user),
            updated=rest.opt_string(f, "updated"),
        ),
    )


def _read_search(value: Any) -> list[RawIssue]:
    return rest.default_list(rest.obj(value), "issues", read_issue)


def _read_tenant(value: Any) -> str:
    return rest.string(rest.obj(value), "cloudId")


def _error_message(response: httpx.Response) -> str | None:
    """The first of `errorMessages`, else `message`. `None` when the body is
    not an error body."""

    def read(value: Any) -> str | None:
        o = rest.obj(value)
        messages = rest.default_list(o, "errorMessages", lambda v: rest.string({"v": v}, "v"))
        message = rest.opt_string(o, "message")
        return messages[0] if messages else message

    try:
        return rest.read_body(response, read)
    except ValueError:
        return None


def normalize_site(input: str) -> str:
    """Accepts `acme.atlassian.net`, `https://acme.atlassian.net/` or a Data
    Center URL with a context path, and returns it as `https://host[/path]`.
    Plain `http` is refused: tokens never travel unencrypted."""
    input = input.strip()
    with_scheme = input if "://" in input else f"https://{input}"
    parsed = rest.parse_url(with_scheme)
    if parsed is None:
        raise errors.Auth("the Jira site address is not valid.")
    if parsed.scheme != "https":
        raise errors.Auth("the Jira site must use https://.")
    if parsed.host is None:
        raise errors.Auth("the Jira site address is not valid.")
    port = f":{parsed.port}" if parsed.port is not None else ""
    path = parsed.path.rstrip("/")
    return f"https://{parsed.host}{port}{path}"


def is_cloud_site(site: str) -> bool:
    parsed = rest.parse_url(site)
    return parsed is not None and parsed.host is not None and parsed.host.endswith(".atlassian.net")


async def get(http: httpx.AsyncClient, credential: Credential, url: str, query: list[tuple[str, str]], read):
    headers = {"Accept": "application/json"}
    auth = None
    if credential.email is not None:
        auth = httpx.BasicAuth(credential.email, credential.token)
    else:
        headers["Authorization"] = f"Bearer {credential.token}"
    response = await send(http, "GET", url, params=query or None, headers=headers, auth=auth)
    status = response.status_code
    if 200 <= status < 300:
        return rest.decode(response, read)
    if status == 401:
        raise errors.Reauthorize("Jira")
    message = _error_message(response)
    raise errors.Api("Jira", status, message if message is not None else rest.reason(status))


async def myself(http: httpx.AsyncClient, credential: Credential, endpoint: JiraEndpoint) -> Me:
    user: RawUser = await get(http, credential, url(endpoint, "myself"), [], _read_user)
    id = user.id()
    if id is None:
        raise errors.Auth("Jira did not identify the user.")
    return Me(id=id, name=user.display_name)


async def connect(http: httpx.AsyncClient, site: str, credential: Credential) -> tuple[JiraEndpoint, Me]:
    """Finds a working endpoint for this credential and identifies the user.
    Cloud tokens are tried against the site first; a scoped token is only
    accepted by the Atlassian gateway, so on 401 the site's cloud ID is
    looked up and the gateway is tried."""
    flavor = JiraFlavor.CLOUD if credential.email is not None else JiraFlavor.DATA_CENTER
    direct = JiraEndpoint(site=site, api_base=site, flavor=flavor)

    def rejected() -> errors.Auth:
        return errors.Auth("Jira rejected the token. Check the site, email and API token.")

    try:
        return direct, await myself(http, credential, direct)
    except errors.Reauthorize:
        if not (flavor == JiraFlavor.CLOUD and is_cloud_site(site)):
            raise rejected() from None
    except errors.Api as e:
        if e.status == 404:
            raise errors.Auth(f"no Jira was found at {site}. Check the site address.") from None
        raise

    response = await send(http, "GET", f"{site}/_edge/tenant_info")
    try:
        cloud_id = rest.read_body(response, _read_tenant)
    except ValueError:
        raise rejected() from None
    gateway = JiraEndpoint(site=site, api_base=f"{GATEWAY}/{cloud_id}", flavor=flavor)
    try:
        return gateway, await myself(http, credential, gateway)
    except errors.Reauthorize:
        raise rejected() from None


async def open_issues(
    http: httpx.AsyncClient, credential: Credential, endpoint: JiraEndpoint, me: str, count: int
) -> list[IssueMeta]:
    """The `count` most recently updated open issues assigned to or reported
    by the user."""
    # Jira Cloud replaced /search with /search/jql; Data Center keeps /search.
    path = "search/jql" if endpoint.flavor == JiraFlavor.CLOUD else "search"
    issues: list[RawIssue] = await get(
        http,
        credential,
        url(endpoint, path),
        [("jql", JQL), ("maxResults", str(count)), ("fields", FIELDS)],
        _read_search,
    )
    return [to_meta(issue, me, endpoint.site) for issue in issues[:count]]


def to_meta(issue: RawIssue, me: str, site: str) -> IssueMeta:
    f = issue.fields
    assigned_to_me = f.assignee is not None and f.assignee.id() == me
    return IssueMeta(
        url=f"{site}/browse/{issue.key}",
        direction=Direction.INBOUND if assigned_to_me else Direction.OUTBOUND,
        status=f.status or "",
        project=f.project or "",
        assignee=f.assignee.display_name if f.assignee else "",
        reporter=f.reporter.display_name if f.reporter else "",
        date=to_rfc3339(f.updated) if f.updated is not None else "",
        summary=f.summary.strip(),
        issue_id=issue.id,
        key=issue.key,
    )


# `[year]-[month]-[day]T[hour]:[minute]:[second].[subsecond]` followed by
# `+hhmm`, as Jira writes dates. RFC 3339 as the `time` crate reads it:
# any one-byte separator between date and time, `Z` in either case.
_JIRA_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})\.(\d{1,9})([+-])(\d{2})(\d{2})", re.ASCII)
_RFC3339 = re.compile(
    r"(\d{4})-(\d{2})-(\d{2})[\x00-\x7f](\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(?:([Zz])|([+-])(\d{2}):(\d{2}))",
    re.ASCII,
)


def to_rfc3339(jira: str) -> str:
    """Jira dates look like `2026-10-23T10:00:00.000+0200`. Returns UTC RFC
    3339, or an empty string for a date in neither form."""
    if m := _JIRA_DATE.fullmatch(jira):
        *civil, fraction, sign, oh, om = m.groups()
        offset = _offset(sign, oh, om, max_hours=25)
    elif m := _RFC3339.fullmatch(jira):
        *civil, fraction, z, sign, oh, om = m.groups()
        offset = timedelta(0) if z else _offset(sign, oh, om, max_hours=23)
    else:
        return ""
    if offset is None:
        return ""
    try:
        year, month, day, hour, minute, second = map(int, civil)
        utc = datetime(year, month, day, hour, minute, second) - offset
    except (ValueError, OverflowError):
        return ""
    # Nanosecond precision, trailing zeros dropped, as the `time` crate
    # writes it.
    nanos = (fraction or "0")[:9].ljust(9, "0").rstrip("0")
    subsecond = f".{nanos}" if nanos else ""
    return f"{utc.year:04}-{utc.month:02}-{utc.day:02}T{utc.hour:02}:{utc.minute:02}:{utc.second:02}{subsecond}Z"


def _offset(sign: str, hours: str, minutes: str, max_hours: int) -> timedelta | None:
    h, m = int(hours), int(minutes)
    if h > max_hours or m > 59:
        return None
    offset = timedelta(hours=h, minutes=m)
    return -offset if sign == "-" else offset
