"""`kube-query ev` — events, newest first, with type/since/object filters."""

from __future__ import annotations

import click

from ..cli_kit import all_namespaces_option, filter_option, namespace_option, output_option, verbose_option
from ..events import EVENT_COLUMNS, EVENT_COLUMNS_NS, list_events
from ..output import console, emit_data, note, render_rows


@click.command("ev")
@click.argument("pattern", required=False)
@click.option("--type", "types", multiple=True, help="Filter by type, e.g. --type Warning (repeatable).")
@click.option("--since", default=None, help="Only events newer than this duration, e.g. 30m, 2h, 1d.")
@click.option("--limit", type=int, default=50, show_default=True, help="Max events to show (0 = all).")
@click.option("--for", "for_obj", default=None, metavar="KIND/NAME", help="Events for one object, e.g. pod/web-5d9c6.")
@all_namespaces_option
@filter_option
@namespace_option
@verbose_option
@output_option
@click.pass_obj
def ev(settings, pattern, types, since, limit, for_obj, all_namespaces, name_filter, namespace, verbose, output_fmt):
    """Events, newest first: kube-query ev [REGEX] [--type Warning] [--since 2h] [--for pod/NAME]

    \b
    Examples:
      kube-query ev -A --type Warning --since 1h
      kube-query ev --for pod/web-5d9c6 -n prod
      kube-query ev BackOff -A --limit 100
    """
    eff = settings.effect(namespace=namespace, output=output_fmt, verbose=verbose, all_namespaces=all_namespaces)
    involved = None
    if for_obj:
        kind, _, obj_name = for_obj.partition("/")
        if not obj_name:
            from ..errors import KqError

            raise KqError("--for expects KIND/NAME, e.g. pod/web-5d9c6")
        involved = {"kind": kind, "name": obj_name}

    ns = eff.namespace if eff.namespace else (None if eff.all_namespaces else settings.client.default_namespace())
    events = list_events(
        settings.client,
        namespace=ns,
        since=since,
        types=tuple(t.capitalize() for t in types),
        involved=involved,
        limit=(limit or None),
        pattern=pattern or name_filter,
    )
    _render(events, eff, namespace=ns)


def _render(events: list[dict], eff, *, namespace: str | None) -> None:
    if eff.output in ("yaml", "json"):
        data = [{k: v for k, v in e.items() if not k.startswith("_")} for e in events]
        emit_data(data, eff.output)
        if not events:
            where = f" in namespace '{namespace}'" if namespace else ""
            note(f"no events found{where}")
        return

    if not events:
        console().print("[dim]no events found[/dim]")
        return

    multi_ns = len({e.get("namespace") for e in events}) > 1
    cols = EVENT_COLUMNS_NS if multi_ns else EVENT_COLUMNS
    headers = [h for h, _ in cols]
    rows = [{h: fn(e) for h, fn in cols} for e in events]
    where = f" in namespace '{namespace}'" if namespace else " (all namespaces)"
    render_rows(headers, rows, eff.output, title="events", subtitle=f"{len(events)} events{where}")
