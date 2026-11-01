"""`kube-query ctx` — kubeconfig contexts (no API calls)."""

from __future__ import annotations

import click

from ..cli_kit import ResourceGroup, group_options, list_options, merge_group_options, resolve_show_name, show_options
from ..output import emit_data, render_rows

COLUMNS = [
    ("CURRENT", lambda r: "*" if r.get("current") else ""),
    ("NAME", lambda r: r["name"]),
    ("CLUSTER", lambda r: r["cluster"]),
    ("SERVER", lambda r: r["server"]),
    ("USER", lambda r: r["user"]),
    ("NAMESPACE", lambda r: r["namespace"]),
]


def make_contexts_group() -> ResourceGroup:
    @click.command("ls")
    @list_options(include_pattern=False)
    @click.pass_obj
    def ls(
        settings,
        name_filter,
        all_namespaces,
        label_selector,
        field_selector,
        show_labels,
        namespace,
        verbose,
        output_fmt,
    ):
        """List kubeconfig contexts (the current one is marked). Use -f to filter by regex."""
        eff = settings.effect(namespace=namespace, output=output_fmt, verbose=verbose)
        rows = settings.client.contexts()
        if name_filter:
            import re

            from ..errors import KqError

            try:
                rx = re.compile(name_filter, re.IGNORECASE)
            except re.error as e:
                raise KqError(f"invalid filter regex '{name_filter}': {e}") from None
            rows = [r for r in rows if rx.search(r["name"])]
        if eff.output in ("yaml", "json"):
            emit_data(rows, eff.output)
            return
        headers = [h for h, _ in COLUMNS]
        trows = [{h: fn(r) for h, fn in COLUMNS} for r in rows]
        current = next((r["name"] for r in rows if r.get("current")), None)
        subtitle = f"{len(rows)} contexts" + (f" - current: {current}" if current else "")
        render_rows(headers, trows, eff.output, title="contexts", subtitle=subtitle)

    ls.help = "List kubeconfig contexts (the current one is marked)."

    @click.command("show")
    @show_options()
    @click.pass_context
    def show(ctx, name, namespace, verbose, output_fmt):
        """Show one context's details."""
        settings = ctx.obj
        name = resolve_show_name(ctx, name)
        eff = settings.effect(namespace=namespace, output=output_fmt, verbose=verbose)
        rows = settings.client.contexts()
        row = next((r for r in rows if r["name"] == name), None)
        if row is None:
            from ..errors import KqError

            raise KqError(f"context '{name}' not found.\n  Hint: 'kube-query ctx ls' lists available contexts.")
        if eff.output in ("yaml", "json"):
            emit_data(row, eff.output)
        elif eff.output in ("rich", "md"):
            from ..output import print_object

            print_object(row, eff.output, title=f"context {name}")
        else:
            from ..errors import KqError

            raise KqError(f"format '{eff.output}' is not supported here")

    @click.group(cls=ResourceGroup, name="ctx", invoke_without_command=True, default_command="ls")
    @group_options
    @click.pass_context
    def grp(ctx, namespace, output_fmt, verbose, all_namespaces):
        """Kubeconfig contexts: ls | show NAME (no API calls)

        \b
        Examples:
          kube-query ctx ls
          kube-query c l
          kube-query --ctx <name> p l
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
