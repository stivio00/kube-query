"""External Secrets Operator (ESO) views: ExternalSecrets and SecretStores."""

from __future__ import annotations

from .access import list_objects
from .discovery import resolve
from .errors import KqError
from .summarize import age, dig


def _ready_condition(obj: dict) -> dict:
    conds = {c.get("type"): c for c in dig(obj, "status", "conditions", default=[]) or []}
    return conds.get("Ready") or {}


def eso_rows(ctx, *, namespace: str | None = None) -> list[dict]:
    try:
        entry = resolve(ctx, "externalsecrets")
    except KqError:
        raise KqError(
            "ExternalSecret CRD not found - is External Secrets Operator installed?\n"
            "  Hint: 'kq api' to list resource types (look for external-secrets.io)."
        ) from None
    items = list_objects(ctx, entry, namespace=namespace)
    rows = []
    for it in items:
        ready = _ready_condition(it)
        store = dig(it, "spec", "secretStoreRef") or {}
        target = dig(it, "spec", "target", "secretRef", "name") or dig(it, "spec", "target", "name") or ""
        row = {
            "name": dig(it, "metadata", "name", default="") or "",
            "namespace": dig(it, "metadata", "namespace", default="") or "",
            "store": f"{store.get('kind', '')}/{store.get('name', '')}" if store else "",
            "target": target,
            "refresh": dig(it, "spec", "refreshInterval") or "",
            "ready": ready.get("status") or "",
            "healthy": ready.get("status") == "True",
            "age": age(dig(it, "metadata", "creationTimestamp")),
        }
        if ready.get("reason"):
            row["reason"] = ready["reason"]
        if ready.get("message"):
            row["message"] = ready["message"]
        rows.append(row)
    rows.sort(key=lambda r: (r["namespace"], r["name"]))
    return rows


def store_rows(ctx, *, namespace: str | None = None) -> list[dict]:
    rows = []
    found_any = False
    for plural in ("secretstores", "clustersecretstores"):
        try:
            entry = resolve(ctx, plural)
        except KqError:
            continue
        found_any = True
        items = list_objects(ctx, entry, namespace=namespace)
        for it in items:
            ready = _ready_condition(it)
            provider = dig(it, "spec", "provider") or {}
            provider_type = next(iter(provider), "") if isinstance(provider, dict) else ""
            rows.append(
                {
                    "name": dig(it, "metadata", "name", default="") or "",
                    "kind": entry.kind,
                    "namespace": dig(it, "metadata", "namespace", default="") or "",
                    "provider": provider_type,
                    "ready": ready.get("status") or "",
                    "healthy": ready.get("status") == "True",
                    "reason": ready.get("reason") or "",
                    "age": age(dig(it, "metadata", "creationTimestamp")),
                }
            )
    if not found_any:
        raise KqError(
            "SecretStore CRDs not found - is External Secrets Operator installed?\n"
            "  Hint: 'kq api' to list resource types (look for external-secrets.io)."
        )
    rows.sort(key=lambda r: (r["namespace"], r["kind"], r["name"]))
    return rows
