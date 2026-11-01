"""Event listing, filtering and compaction (shared by ev / describe / overview)."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from .access import list_objects
from .discovery import resolve
from .errors import KqError
from .summarize import dig, now_utc, parse_since, parse_ts

EVENT_COLUMNS = [
    ("LAST", lambda e: e.get("_age", "")),
    ("TYPE", lambda e: e.get("type", "")),
    ("REASON", lambda e: e.get("reason", "")),
    ("OBJECT", lambda e: e.get("object", "")),
    ("MESSAGE", lambda e: e.get("message", "")),
]
EVENT_COLUMNS_NS = [("NAMESPACE", lambda e: e.get("namespace", "")), *EVENT_COLUMNS]


def compact_event(ev: dict, *, with_age: bool = True) -> dict:
    inv = ev.get("involvedObject") or {}
    ts = ev.get("lastTimestamp") or ev.get("eventTime") or ev.get("firstTimestamp")
    src = (ev.get("source") or {}).get("component") or ev.get("reportingComponent") or ""
    from .summarize import age  # local import to keep module import graph flat

    out = {
        "lastSeen": ts or "",
        "type": ev.get("type") or "",
        "reason": ev.get("reason") or "",
        "object": f"{inv.get('kind') or '?'}/{inv.get('name') or '?'}",
        "namespace": inv.get("namespace") or (ev.get("metadata") or {}).get("namespace") or "",
        "count": ev.get("count") or 1,
        "source": src,
        "message": ev.get("message") or "",
    }
    if with_age:
        out["_age"] = age(out["lastSeen"])
    return {k: v for k, v in out.items() if v not in ("", None, [], {}) or k == "count"}


def list_events(
    ctx,
    *,
    namespace: str | None = None,
    since: str | None = None,
    types: tuple[str, ...] = (),
    involved: dict | None = None,
    limit: int | None = None,
    pattern: str | None = None,
) -> list[dict]:
    """Compact events, newest first."""
    entry = resolve(ctx, "events")
    raw = list_objects(ctx, entry, namespace=namespace)
    out = []
    cutoff = (now_utc() - parse_since(since)) if since else None
    rx = None
    if pattern:
        try:
            rx = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            raise KqError(f"invalid filter regex '{pattern}': {e}") from None
    for ev in raw:
        c = compact_event(ev)
        if types and c.get("type") not in types:
            continue
        if involved and not _matches(ev, involved):
            continue
        if cutoff:
            ts = parse_ts(c.get("lastSeen"))
            if not ts or ts < cutoff:
                continue
        if rx and not rx.search(f"{c.get('reason', '')} {c.get('object', '')} {c.get('message', '')}"):
            continue
        out.append(c)
    out.sort(key=lambda c: parse_ts(c.get("lastSeen")) or datetime.min.replace(tzinfo=UTC), reverse=True)
    if limit:
        out = out[:limit]
    return out


def _matches(ev: dict, involved: dict) -> bool:
    inv = ev.get("involvedObject") or {}
    if involved.get("uid") and inv.get("uid") != involved["uid"]:
        return False
    if involved.get("kind") and (inv.get("kind") or "").lower() != involved["kind"].lower():
        return False
    if involved.get("name") and inv.get("name") != involved["name"]:
        return False
    return not (involved.get("namespace") and (inv.get("namespace") or "") != involved["namespace"])


def related_events(ctx, obj: dict) -> list[dict]:
    """Events whose involvedObject is ``obj`` (uid match preferred)."""
    uid = dig(obj, "metadata", "uid")
    involved: dict = {"uid": uid} if uid else {}
    if not involved:
        involved = {"kind": obj.get("kind"), "name": dig(obj, "metadata", "name")}
    ns = dig(obj, "metadata", "namespace")
    if ns:
        involved["namespace"] = ns
    return list_events(ctx, namespace=ns, involved=involved)
