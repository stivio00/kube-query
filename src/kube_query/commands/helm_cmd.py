"""`kube-query helm` — Helm releases decoded from the cluster's release Secrets (read-only)."""

from __future__ import annotations

import click

from ..cli_kit import (
    ResourceGroup,
    group_options,
    list_options,
    merge_group_options,
    resolve_show_name,
    show_options,
)
from ..helm import chart_str, list_releases, show_release
from ..output import emit_data, render_rows

COLUMNS = [
    ("NAME", lambda r: r["name"]),
    ("NAMESPACE", lambda r: r["namespace"]),
    ("REVISION", lambda r: r["revision"]),
    ("STATUS", lambda r: r["status"]),
    ("CHART", chart_str),
    ("UPDATED", lambda r: r.get("_age", "")),
]


def make_helm_group() -> ResourceGroup:
    @click.command("ls")
    @list_options()
    @click.pass_obj
    def ls(
        settings,
        pattern,
        name_filter,
        all_namespaces,
        label_selector,
        field_selector,
        show_labels,
        namespace,
        verbose,
        output_fmt,
    ):
        """List Helm releases (latest revision per release)."""
        eff = settings.effect(namespace=namespace, output=output_fmt, verbose=verbose, all_namespaces=all_namespaces)
        ns = None
        if eff.namespace:
            ns = eff.namespace
        elif not eff.all_namespaces:
            ns = settings.client.default_namespace()
        releases = list_releases(settings.client, namespace=ns)
        if pattern or name_filter:
            import re

            from ..errors import KqError

            rx = []
            for p in (pattern, name_filter):
                if not p:
                    continue
                try:
                    rx.append(re.compile(p, re.IGNORECASE))
                except re.error as e:
                    raise KqError(f"invalid filter regex '{p}': {e}") from None
            releases = [r for r in releases if all(x.search(r["name"]) for x in rx)]
        if eff.output in ("yaml", "json"):
            data = [{k: v for k, v in r.items() if not k.startswith("_")} for r in releases]
            emit_data(data, eff.output)
            return
        headers = [h for h, _ in COLUMNS]
        rows = [{h: fn(r) for h, fn in COLUMNS} for r in releases]
        where = f" in namespace '{ns}'" if ns else " (all namespaces)"
        render_rows(headers, rows, eff.output, title="helm releases", subtitle=f"{len(releases)} releases{where}")

    ls.help = "List Helm releases (latest revision per release)."

    @click.command("show")
    @show_options()
    @click.pass_context
    def show(ctx, name, namespace, verbose, output_fmt):
        """One release in full: chart metadata, effective values, status."""
        settings = ctx.obj
        name = resolve_show_name(ctx, name)
        eff = settings.effect(namespace=namespace, output=output_fmt, verbose=verbose)
        ns = eff.namespace or settings.client.default_namespace()
        rel = show_release(settings.client, name, namespace=ns)
        if eff.output in ("yaml", "json"):
            emit_data(rel, eff.output)
        elif eff.output in ("rich", "md"):
            from ..output import print_object

            print_object(rel, eff.output, title=f"helm release {name} -n {ns}")
        else:
            from ..errors import KqError

            raise KqError(f"format '{eff.output}' is not supported here")

    @click.group(cls=ResourceGroup, name="helm", invoke_without_command=True, default_command="ls")
    @group_options
    @click.pass_context
    def grp(ctx, namespace, output_fmt, verbose, all_namespaces):
        """Helm releases, decoded read-only from release Secrets: ls -A | show NAME

        \b
        Examples:
          kube-query helm ls -A
          kube-query helm show grafana -n monitoring
          kube-query helm wordpress -n monitoring    # implicit show
        """
        settings = ctx.obj
        merge_group_options(
            settings,
            namespace=namespace,
            output_fmt=output_fmt,
            verbose=verbose,
            all_namespaces=all_namespaces,
        )
        if ctx.invoked_subcommand is None:
            ctx.invoke(grp.get_command(ctx, "ls"))

    grp.add_command(ls, "ls")
    grp.add_command(ls, "list", alias=True)
    grp.add_command(ls, "l", alias=True)
    grp.add_command(show, "show")
    return grp
