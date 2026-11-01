"""`kube-query argo` — Argo CD Applications: health + sync status."""

from __future__ import annotations

import re

import click

from ..argo import app_rows
from ..cli_kit import all_namespaces_option, filter_option, namespace_option, output_option, verbose_option
from ..errors import KqError
from ..output import console, emit_data, render_rows

ARGO_COLUMNS = ["NAME", "NAMESPACE", "PROJECT", "HEALTH", "SYNC", "DESTINATION", "AGE"]


@click.command("argo")
@click.argument("pattern", required=False)
@all_namespaces_option
@filter_option
@namespace_option
@verbose_option
@output_option
@click.pass_obj
def argo(settings, pattern, all_namespaces, name_filter, namespace, verbose, output_fmt):
    """Argo CD Applications: health + sync (read-only, via the Applications CRD).

    \b
    Examples:
      kube-query argo -A
      kube-query argo -A -o rich
      kube-query argo '^payments' -n argocd
      kube-query get applications -A            # raw CRD objects
    """
    eff = settings.effect(namespace=namespace, output=output_fmt, verbose=verbose, all_namespaces=all_namespaces)
    ns = eff.namespace if eff.namespace else (None if eff.all_namespaces else settings.client.default_namespace())
    rows = app_rows(settings.client, namespace=ns)

    rx = None
    if pattern or name_filter:
        try:
            rx = re.compile(pattern or name_filter, re.IGNORECASE)
        except re.error as e:
            raise KqError(f"invalid filter regex: {e}") from None
        rows = [r for r in rows if rx.search(r["name"])]

    if eff.output in ("yaml", "json"):
        emit_data(rows, eff.output)
        return

    if eff.output in ("rich", "md"):
        table_rows = [{h: r.get(h.lower(), "") for h in ARGO_COLUMNS} for r in rows]
        where = f" in namespace '{ns}'" if ns else " (all namespaces)"
        render_rows(
            ARGO_COLUMNS, table_rows, eff.output, title="argo applications", subtitle=f"{len(rows)} apps{where}"
        )
        if not rows:
            console().print(f"[dim]no applications found{where}[/dim]")
        return

    raise KqError(f"format '{eff.output}' is not supported here")
