"""`kube-query describe` — object + summary + ownership children + related events."""

from __future__ import annotations

import json

import click

from ..cleanup import compact
from ..cli_kit import show_options
from ..config import Settings
from ..discovery import parse_target, resolve
from ..events import related_events
from ..output import as_yaml, console, emit_data, md_code, md_heading, md_table, rich_table
from ..summarize import (
    age,
    deployment_brief,
    dig,
    pod_ready_ratio,
    pod_restarts,
    pod_status,
    summary_for,
)
from ..tree import child_index


def _child_row(kentry, kobj: dict) -> dict:
    k = kentry.kind.lower()
    row = {
        "kind": kentry.kind,
        "name": dig(kobj, "metadata", "name", default="") or "",
        "age": age(dig(kobj, "metadata", "creationTimestamp")),
    }
    if k == "pod":
        row["status"] = pod_status(kobj)
        row["ready"] = pod_ready_ratio(kobj)
        row["restarts"] = pod_restarts(kobj)
    elif k == "deployment":
        row["ready"] = "{ready}/{desired}".format(**deployment_brief(kobj))
    elif k == "replicaset":
        row["ready"] = (
            f"{dig(kobj, 'status', 'readyReplicas', default=0) or 0}/{dig(kobj, 'spec', 'replicas', default=0) or 0}"
        )
    elif k == "job":
        failed = dig(kobj, "status", "failed", default=0) or 0
        succeeded = dig(kobj, "status", "succeeded", default=0) or 0
        row["status"] = "Failed" if failed else ("Complete" if succeeded else "Running")
    return row


_CHILD_HEADERS = ["KIND", "NAME", "STATUS", "READY", "RESTARTS", "AGE"]
_CHILD_KEY_MAP = {
    "KIND": "kind",
    "NAME": "name",
    "STATUS": "status",
    "READY": "ready",
    "RESTARTS": "restarts",
    "AGE": "age",
}


def _child_table_rows(children: list[dict]) -> list[dict]:
    return [{h: c.get(_CHILD_KEY_MAP[h], "") for h in _CHILD_HEADERS} for c in children]


def describe_impl(settings: Settings, entry, name: str, eff, *, namespace: str | None = None):
    client = settings.client
    from ..access import get_object

    ns = None
    if entry.namespaced:
        ns = namespace or eff.namespace or client.default_namespace()
    obj = get_object(client, entry, name, namespace=ns)

    summary = summary_for(entry, obj)
    children: list[dict] = []
    obj_ns = dig(obj, "metadata", "namespace")
    if obj_ns and entry.kind.lower() != "pod":
        idx = child_index(client, obj_ns)
        for kentry, kobj in idx.get(dig(obj, "metadata", "uid"), []):
            children.append(_child_row(kentry, kobj))
        children.sort(key=lambda r: (r["kind"], r["name"]))
    events = related_events(client, obj)[:20]

    doc = {"summary": summary, "object": compact(obj, eff.verbose)}
    if children:
        doc["children"] = children
    if events:
        doc["events"] = events

    if eff.output in ("yaml", "json"):
        emit_data(doc, eff.output)
        return

    if eff.output == "tree":
        from ..tree import build_forest, rich_forest

        console().print(rich_forest(build_forest(client, entry, obj)))
        return

    title = f"{entry.kind} {name}" + (f" (namespace {ns})" if ns else "")
    if eff.output == "rich":
        c = console()
        c.print(f"[bold]{title}[/bold]\n")
        c.print(rich_table(["KEY", "VALUE"], _kv_rows(summary), title="summary"))
        if children:
            c.print()
            c.print(rich_table(_CHILD_HEADERS, _child_table_rows(children), title="children"))
        if events:
            c.print()
            from ..events import EVENT_COLUMNS, EVENT_COLUMNS_NS

            cols = EVENT_COLUMNS_NS if len({e.get("namespace") for e in events}) > 1 else EVENT_COLUMNS
            headers = [h for h, _ in cols]
            rows = [{h: fn(e) for h, fn in cols} for e in events]
            c.print(rich_table(headers, rows, title="events (20 most recent)"))
        c.print()
        c.print("[bold]object[/bold]")
        from rich.syntax import Syntax

        c.print(Syntax(as_yaml(doc["object"]), "yaml", background_color="default", word_wrap=True))
    elif eff.output == "md":
        parts = [md_heading(title, 2)]
        parts.append(md_heading("summary", 3))
        parts.append(md_table(["KEY", "VALUE"], _kv_rows(summary)) + "\n")
        if children:
            parts.append(md_heading("children", 3))
            parts.append(md_table(_CHILD_HEADERS, _child_table_rows(children)) + "\n")
        if events:
            from ..events import EVENT_COLUMNS, EVENT_COLUMNS_NS

            parts.append(md_heading("events (20 most recent)", 3))
            cols = EVENT_COLUMNS_NS if len({e.get("namespace") for e in events}) > 1 else EVENT_COLUMNS
            headers = [h for h, _ in cols]
            rows = [{h: fn(e) for h, fn in cols} for e in events]
            parts.append(md_table(headers, rows) + "\n")
        parts.append(md_heading("object", 3))
        parts.append(md_code(as_yaml(doc["object"])))
        click.echo("".join(parts), nl=False)
    else:
        from ..errors import KqError

        raise KqError(f"format '{eff.output}' is not supported here")


def _kv_rows(d: dict) -> list[dict]:
    rows = []
    for k, v in d.items():
        if isinstance(v, (dict, list)):
            v = json.dumps(v, ensure_ascii=False, default=str)
            if len(str(v)) > 300:
                v = str(v)[:300] + "..."
        rows.append({"KEY": k, "VALUE": "" if v is None else str(v)})
    return rows


@click.command("describe")
@click.argument("resource")
@show_options()
@click.pass_obj
def describe(settings, resource, name, namespace, verbose, output_fmt):
    """Diagnose one object: summary + status + children + events."""
    eff = settings.effect(namespace=namespace, output=output_fmt, verbose=verbose)
    api_version, res_name, obj_name = parse_target(resource, name)
    if not obj_name:
        raise click.UsageError("Missing NAME (or use RESOURCE/NAME).")
    entry = resolve(settings.client, res_name, api_version=api_version)
    describe_impl(settings, entry, obj_name, eff)
