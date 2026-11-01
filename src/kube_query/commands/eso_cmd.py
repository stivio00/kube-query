"""`kq eso` — External Secrets Operator health: ExternalSecrets and SecretStores."""

from __future__ import annotations

import click

from ..cli_kit import all_namespaces_option, namespace_option, output_option, verbose_option
from ..eso import eso_rows, store_rows
from ..output import console, emit_data, render_rows

ES_COLUMNS = ["NAME", "NAMESPACE", "STORE", "TARGET", "READY", "REASON", "AGE"]
STORE_COLUMNS = ["NAME", "KIND", "NAMESPACE", "PROVIDER", "READY", "REASON", "AGE"]


@click.command("eso")
@click.option("--stores", is_flag=True, default=False, help="List SecretStores/ClusterSecretStores instead.")
@all_namespaces_option
@namespace_option
@verbose_option
@output_option
@click.pass_obj
def eso(settings, stores, all_namespaces, namespace, verbose, output_fmt):
    """External Secrets Operator status: ExternalSecrets (--stores for SecretStores)"""
    eff = settings.effect(namespace=namespace, output=output_fmt, verbose=verbose, all_namespaces=all_namespaces)
    ns = eff.namespace if eff.namespace else (None if eff.all_namespaces else settings.client.default_namespace())
    rows = store_rows(settings.client, namespace=ns) if stores else eso_rows(settings.client, namespace=ns)

    if eff.output in ("yaml", "json"):
        emit_data(rows, eff.output)
        return

    if eff.output in ("rich", "md"):
        headers = STORE_COLUMNS if stores else ES_COLUMNS
        title = "secret stores" if stores else "external secrets"
        where = f" in namespace '{ns}'" if ns else " (all namespaces)"
        table_rows = [{h: r.get(h.lower(), "") for h in headers} for r in rows]
        render_rows(headers, table_rows, eff.output, title=title, subtitle=f"{len(rows)} {title}{where}")
        if not rows:
            console().print(f"[dim]no {title} found{where}[/dim]")
        return

    from ..errors import KqError

    raise KqError(f"format '{eff.output}' is not supported here")
