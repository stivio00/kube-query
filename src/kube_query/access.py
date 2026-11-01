"""Object-level access: list/get any resource by its ApiResource, read pod logs."""

from __future__ import annotations

from urllib.parse import quote

from .config import Ctx
from .discovery import ApiResource
from .errors import KqApiError, KqError
from .http import get_json, get_text


def resource_path(entry: ApiResource, namespace: str | None = None, name: str | None = None) -> str:
    if entry.group:
        base = f"/apis/{quote(entry.api_version, safe='/')}"
    else:
        base = f"/api/{entry.version}"
    if entry.namespaced and namespace:
        base += f"/namespaces/{quote(namespace, safe='')}"
    base += f"/{entry.plural}"
    if name:
        base += f"/{quote(name, safe='')}"
    return base


def list_objects(
    ctx: Ctx,
    entry: ApiResource,
    *,
    namespace: str | None = None,
    label_selector: str | None = None,
    field_selector: str | None = None,
) -> list[dict]:
    """List objects. ``namespace=None`` on a namespaced resource lists all namespaces."""
    if not entry.namespaced and namespace:
        namespace = None
    params = {"labelSelector": label_selector, "fieldSelector": field_selector}
    data = get_json(ctx.api_client, resource_path(entry, namespace), params)
    items = data.get("items")
    if not isinstance(items, list):
        raise KqError(f"unexpected response while listing {entry.plural}")
    return items


def get_object(ctx: Ctx, entry: ApiResource, name: str, *, namespace: str | None = None) -> dict:
    if entry.namespaced and not namespace:
        raise KqError(f"internal: namespace required to fetch a namespaced {entry.kind}")
    try:
        return get_json(ctx.api_client, resource_path(entry, namespace, name))
    except KqApiError as e:
        if e.status == 404:
            where = f" in namespace '{namespace}'" if entry.namespaced else ""
            scope = f" -n {namespace}" if entry.namespaced else ""
            alt = " (or -A for all namespaces)" if entry.namespaced else ""
            raise KqError(
                f"{entry.kind} '{name}' not found{where}.\n"
                f"  Hint: list candidates with 'kube-query get {entry.plural}{scope}'{alt}."
            ) from None
        raise


def pod_logs(
    ctx: Ctx,
    namespace: str,
    pod: str,
    *,
    container: str | None = None,
    tail: int | None = None,
    previous: bool = False,
    since_seconds: int | None = None,
    timestamps: bool = False,
) -> str:
    path = f"/api/v1/namespaces/{quote(namespace, safe='')}/pods/{quote(pod, safe='')}/log"
    params = {
        "container": container,
        "tailLines": tail,
        "previous": "true" if previous else None,
        "sinceSeconds": since_seconds,
        "timestamps": "true" if timestamps else None,
    }
    return get_text(ctx.api_client, path, params)


def server_version(ctx: Ctx) -> dict:
    return get_json(ctx.api_client, "/version")
