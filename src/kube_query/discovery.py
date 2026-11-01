"""API discovery and resource-name resolution (built-ins, shortnames, CRDs)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import get_close_matches

from .config import Ctx
from .errors import KqError
from .http import get_json

_VERSION_RE = re.compile(r"^v\d[a-z0-9.]*$", re.IGNORECASE)

# Groups to prefer when a name matches in several groups (kubectl-ish priority).
GROUP_PREFERENCE = (
    "",
    "apps",
    "batch",
    "networking.k8s.io",
    "rbac.authorization.k8s.io",
    "storage.k8s.io",
    "autoscaling",
    "policy",
    "apiextensions.k8s.io",
    "external-secrets.io",
    "cert-manager.io",
)


@dataclass(frozen=True)
class ApiResource:
    api_version: str  # "v1" or "apps/v1"
    group: str
    version: str
    plural: str
    singular: str
    kind: str
    namespaced: bool
    short_names: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()

    @property
    def group_kind(self) -> str:
        return f"{self.kind}.{self.group}" if self.group else self.kind


def fetch_resources(ctx: Ctx) -> list[ApiResource]:
    """All resources of the cluster's preferred API versions (cached on the Ctx)."""
    if ctx.resources is None:
        client = ctx.api_client
        entries: list[ApiResource] = []
        core = get_json(client, "/api")
        for version in core.get("versions") or []:
            rl = get_json(client, f"/api/{version}")
            entries.extend(_entries(rl, group="", version=str(version)))
        groups = get_json(client, "/apis")
        for g in groups.get("groups") or []:
            pv = (g.get("preferredVersion") or {}).get("groupVersion")
            gvs = [pv] if pv else [v.get("groupVersion") for v in g.get("versions") or []]
            for gv in [x for x in gvs if x]:
                group, _, version = str(gv).partition("/")
                rl = get_json(client, f"/apis/{gv}")
                entries.extend(_entries(rl, group=group, version=version))
        ctx.resources = entries
    return ctx.resources


def _entries(rl: dict, *, group: str, version: str) -> list[ApiResource]:
    gv = f"{group}/{version}" if group else version
    out = []
    for r in rl.get("resources") or []:
        name = r.get("name") or ""
        if "/" in name or not r.get("kind"):  # subresources (pods/log, nodes/proxy, ...)
            continue
        out.append(
            ApiResource(
                api_version=gv,
                group=group,
                version=version,
                plural=name,
                singular=r.get("singularName") or "",
                kind=r["kind"],
                namespaced=bool(r.get("namespaced")),
                short_names=tuple(r.get("shortNames") or ()),
                categories=tuple(r.get("categories") or ()),
            )
        )
    return out


def resolve(ctx: Ctx, name: str, *, api_version: str | None = None, group: str | None = None) -> ApiResource:
    """Resolve a user-supplied resource reference to one ApiResource.

    Accepts plurals, singulars, kinds, shortnames (case-insensitive) and
    group-qualified forms (``deployments.apps``). Raises KqError with
    suggestions when nothing matches.
    """
    entries = fetch_resources(ctx)
    n = name.lower()
    pool = entries
    if api_version:
        want = api_version.lower()
        pool = [e for e in pool if e.api_version.lower() == want]
        if not pool:
            raise KqError(f"unknown api version '{api_version}'. Hint: 'kube-query api' lists all.")
    elif group:
        want = group.lower()
        pool = [e for e in pool if e.group.lower() == want]

    found = _match(pool, n)
    if found:
        return found
    if group is None and api_version is None and "." in name:
        base, grp = name.rsplit(".", 1)
        found = _match([e for e in entries if e.group.lower() == grp.lower()], base.lower())
        if found:
            return found
    raise _unknown(entries, name, api_version=api_version, group=group)


def _match(pool: list[ApiResource], n: str) -> ApiResource | None:
    if not pool:
        return None
    for keyfn in (lambda e: e.plural.lower(), lambda e: e.singular.lower(), lambda e: e.kind.lower()):
        hits = [e for e in pool if keyfn(e) == n]
        if hits:
            return _prefer(hits)
    hits = [e for e in pool if n in e.short_names]
    if hits:
        return _prefer(hits)
    return None


def _prefer(hits: list[ApiResource]) -> ApiResource:
    def rank(e: ApiResource) -> tuple:
        try:
            gi = GROUP_PREFERENCE.index(e.group)
        except ValueError:
            gi = len(GROUP_PREFERENCE)
        return (gi, e.group, e.version)

    return sorted(hits, key=rank)[0]


def _unknown(entries: list[ApiResource], name: str, *, api_version: str | None, group: str | None) -> KqError:
    known: set[str] = set()
    for e in entries:
        known.add(e.plural.lower())
        if e.singular:
            known.add(e.singular.lower())
        known.add(e.kind.lower())
        known.update(x.lower() for x in e.short_names)
    known.discard("")
    close = get_close_matches(name.lower(), sorted(known), n=4, cutoff=0.5)
    scope = ""
    if api_version:
        scope = f" in api version '{api_version}'"
    elif group:
        scope = f" in group '{group}'"
    msg = f"unknown resource type '{name}'{scope}."
    if close:
        msg += f" Did you mean: {', '.join(close)}?"
    msg += "\n  Hint: 'kube-query api' lists every resource type in this cluster (incl. CRDs)."
    return KqError(msg)


def parse_target(resource: str, name: str | None = None) -> tuple[str | None, str, str | None]:
    """Split a resource reference into ``(api_version, resource, object_name)``.

    Supported forms::

        pods                        -> (None, "pods", None)
        deploy/web                  -> (None, "deploy", "web")
        apps/v1/deployments         -> ("apps/v1", "deployments", None)
        apps/v1/deployments/web     -> ("apps/v1", "deployments", "web")
    """
    if name is not None:
        return None, resource, name
    parts = resource.split("/")
    if len(parts) == 2:
        return None, parts[0], parts[1]
    if len(parts) == 3:
        return "/".join(parts[:2]), parts[2], None
    if len(parts) == 4:
        return "/".join(parts[:2]), parts[2], parts[3]
    return None, resource, None


def looks_like_version(token: str) -> bool:
    return bool(_VERSION_RE.match(token))
