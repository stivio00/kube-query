"""Argo CD application health: read-only view over the Applications CRD."""

from __future__ import annotations

from .access import list_objects
from .discovery import resolve
from .errors import KqError
from .summarize import age, dig


def app_rows(ctx, *, namespace: str | None = None) -> list[dict]:
    try:
        entry = resolve(ctx, "applications")
    except KqError:
        raise KqError(
            "Argo CD 'applications' CRD not found - is Argo CD installed?\n"
            "  Hint: 'kube-query crd ls' to check for argoproj.io CRDs."
        ) from None
    items = list_objects(ctx, entry, namespace=namespace)
    rows = []
    for it in items:
        health = dig(it, "status", "health") or {}
        sync = dig(it, "status", "sync") or {}
        dest = dig(it, "spec", "destination") or {}
        row = {
            "name": dig(it, "metadata", "name", default="") or "",
            "namespace": dig(it, "metadata", "namespace", default="") or "",
            "project": dig(it, "spec", "project") or "",
            "health": health.get("status") or "",
            "sync": sync.get("status") or "",
            "destination": dest.get("name") or dest.get("server") or "",
            "age": age(dig(it, "metadata", "creationTimestamp")),
            "healthy": health.get("status") == "Healthy",
        }
        if health.get("message"):
            row["message"] = health["message"]
        rows.append(row)
    rows.sort(key=lambda r: (r["namespace"], r["name"]))
    return rows
