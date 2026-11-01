"""`kq api` — list every resource type the cluster serves (incl. CRDs)."""

from __future__ import annotations

import click

from ..cli_kit import output_option
from ..discovery import fetch_resources
from ..output import emit_data, render_rows

COLUMNS = [
    ("APIVERSION", lambda e: e.api_version),
    ("NAME", lambda e: e.plural),
    ("KIND", lambda e: e.kind),
    ("NAMESPACED", lambda e: "namespaced" if e.namespaced else "cluster"),
    ("SHORTNAMES", lambda e: ",".join(e.short_names)),
]


@click.command("api")
@click.argument("pattern", required=False)
@output_option
@click.pass_obj
def api(settings, pattern, output_fmt):
    """All resource types including CRDs: kq api [REGEX]"""
    eff = settings.effect(output=output_fmt)
    entries = fetch_resources(settings.client)
    if pattern:
        import re

        from ..errors import KqError

        try:
            rx = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            raise KqError(f"invalid pattern regex '{pattern}': {e}") from None
        entries = [
            e
            for e in entries
            if rx.search(f"{e.plural} {e.kind} {e.singular} {e.api_version} {' '.join(e.short_names)}")
        ]
    entries.sort(key=lambda e: (e.group, e.kind, e.plural))

    if eff.output in ("yaml", "json"):
        emit_data(
            [
                {
                    "apiVersion": e.api_version,
                    "name": e.plural,
                    "kind": e.kind,
                    "namespaced": e.namespaced,
                    **({"shortNames": list(e.short_names)} if e.short_names else {}),
                }
                for e in entries
            ],
            eff.output,
        )
        return

    headers = [h for h, _ in COLUMNS]
    rows = [{h: fn(e) for h, fn in COLUMNS} for e in entries]
    render_rows(headers, rows, eff.output, title="api resources", subtitle=f"{len(entries)} types")
    if not entries:
        from ..output import console

        console().print("[dim]no matching resource types[/dim]")
