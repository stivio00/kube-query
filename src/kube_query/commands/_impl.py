"""Shared command implementations: list / show rendering used by `get` and the sugar groups."""

from __future__ import annotations

import re

from ..access import get_object, list_objects
from ..cleanup import compact
from ..config import Settings
from ..discovery import ApiResource
from ..errors import KqError
from ..output import console, emit_data, note, print_object, render_rows
from ..summarize import columns_for, dig


def effective_namespace(settings: Settings, entry: ApiResource, eff, *, name_given: bool) -> str | None:
    """Namespace for this call (None => all namespaces when listing)."""
    if not entry.namespaced:
        return None
    if name_given:
        return eff.namespace or settings.client.default_namespace()
    if eff.all_namespaces:
        return None
    return eff.namespace or settings.client.default_namespace()


def apply_filter(items: list[dict], patterns: list[str | None]) -> list[dict]:
    pats = [p for p in patterns if p]
    if not pats:
        return items
    regexes = []
    for p in pats:
        try:
            regexes.append(re.compile(p, re.IGNORECASE))
        except re.error as e:
            raise KqError(f"invalid filter regex '{p}': {e}") from None
    return [it for it in items if all(rx.search(dig(it, "metadata", "name", default="") or "") for rx in regexes)]


def sort_items(items: list[dict]) -> list[dict]:
    return sorted(
        items,
        key=lambda o: (dig(o, "metadata", "namespace", default="") or "", dig(o, "metadata", "name", default="") or ""),
    )


def tabulate(entry: ApiResource, items: list[dict], *, include_ns: bool) -> tuple[list[str], list[dict]]:
    cols = columns_for(entry.kind)
    if include_ns:
        cols = [("NAMESPACE", lambda o: dig(o, "metadata", "namespace", default="") or ""), *cols]
    headers = [h for h, _ in cols]
    rows = []
    for it in items:
        r = {}
        for h, fn in cols:
            try:
                r[h] = fn(it)
            except Exception:
                r[h] = ""
        rows.append(r)
    return headers, rows


def format_labels(labels: dict | None) -> str:
    return ",".join(f"{k}={v}" for k, v in sorted((labels or {}).items()))


def render_list(
    settings: Settings, entry: ApiResource, items: list[dict], eff, *, namespace: str | None, show_labels: bool = False
) -> None:
    """Render a list of objects in the requested format."""
    if eff.output in ("yaml", "json"):
        emit_data([compact(it, eff.verbose) for it in items], eff.output)
        if not items:
            where = f" in namespace '{namespace}'" if namespace else ""
            note(f"no {entry.plural} found{where} (0 items)")
        return

    if eff.output == "tree":
        from ..tree import forest_for_items, rich_forest

        forest = forest_for_items(settings.client, entry, items)
        console().print(rich_forest(forest))
        return

    include_ns = bool(
        items
        and any(dig(o, "metadata", "namespace") for o in items)
        and (namespace is None or len({dig(o, "metadata", "namespace", default="") or "" for o in items}) > 1)
    )
    headers, rows = tabulate(entry, items, include_ns=include_ns)
    if show_labels:
        headers = [*headers, "LABELS"]
        for r, it in zip(rows, items, strict=True):
            r["LABELS"] = format_labels(dig(it, "metadata", "labels"))
    headers, rows = drop_empty_columns(headers, rows)
    where = f" in namespace '{namespace}'" if namespace else " (all namespaces)"
    subtitle = f"{len(items)} {entry.plural}{where}"

    if not items:
        console().print(f"[dim]no {entry.plural} found{where}[/dim]")
        return

    render_rows(headers, rows, eff.output, title=entry.kind, subtitle=subtitle)


def drop_empty_columns(headers: list[str], rows: list[dict]) -> tuple[list[str], list[dict]]:
    """Omit columns whose value is empty in every row (e.g. STATUS on kinds
    that have no detectable status)."""
    if not rows:
        return headers, rows
    keep = [h for h in headers if any(str(r.get(h, "")) != "" for r in rows)]
    if not keep:
        keep = headers[:1]
    return keep, [{h: r.get(h, "") for h in keep} for r in rows]


def render_single(
    settings: Settings,
    entry: ApiResource,
    name: str,
    eff,
    *,
    transform=None,
) -> None:
    """Fetch and render one object (`show`-style)."""
    ns = effective_namespace(settings, entry, eff, name_given=True)
    obj = get_object(settings.client, entry, name, namespace=ns)

    if eff.output == "tree":
        from ..tree import build_forest, rich_forest

        console().print(rich_forest(build_forest(settings.client, entry, obj)))
        return

    data = compact(obj, eff.verbose)
    if transform is not None:
        data = transform(data)

    if eff.output in ("yaml", "json"):
        emit_data(data, eff.output)
    elif eff.output in ("rich", "md"):
        title = f"{entry.kind} {name}" + (f" -n {ns}" if ns else "")
        print_object(data, eff.output, title=title)
    else:
        raise KqError(f"format '{eff.output}' is not supported here")


def fetch_list(
    settings: Settings,
    entry: ApiResource,
    eff,
    *,
    label_selector: str | None = None,
    field_selector: str | None = None,
    pattern: str | None = None,
    name_filter: str | None = None,
) -> tuple[list[dict], str | None]:
    """Resolve namespace, list + filter + sort. Returns (items, namespace)."""
    ns = effective_namespace(settings, entry, eff, name_given=False)
    items = list_objects(
        settings.client,
        entry,
        namespace=ns,
        label_selector=label_selector,
        field_selector=field_selector,
    )
    items = sort_items(apply_filter(items, [pattern, name_filter]))
    return items, ns
