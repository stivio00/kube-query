"""Sugar groups: pod/p, ns/n, deploy/d, svc, secret/sec, cm, node/no.

Each group gets: ls (default), show (implicit via `kube-query pod NAME`), desc,
and for pods also logs. All of them share the generic core, so CRD-like
behavior (label selectors, -A, --field-selector, formats) works everywhere.
"""

from __future__ import annotations

import click

from ..cleanup import cap_map_values, redact_map_values, reveal_map_values
from ..cli_kit import (
    ResourceGroup,
    group_options,
    list_options,
    merge_group_options,
    resolve_show_name,
    show_options,
)
from ..discovery import resolve
from ._impl import fetch_list, render_list, render_single
from .describe import describe_impl
from .logs import logs as logs_cmd


def make_resource_group(
    *,
    name: str,
    plural: str,
    group_help: str,
    has_logs: bool = False,
    secret_like: bool = False,
    cm_like: bool = False,
) -> ResourceGroup:
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
        eff = settings.effect(namespace=namespace, output=output_fmt, verbose=verbose, all_namespaces=all_namespaces)
        entry = resolve(settings.client, plural)
        items, ns = fetch_list(
            settings,
            entry,
            eff,
            label_selector=label_selector,
            field_selector=field_selector,
            pattern=pattern,
            name_filter=name_filter,
        )
        render_list(settings, entry, items, eff, namespace=ns, show_labels=show_labels)

    ls.help = f"List {plural}. [PATTERN] is a regex on the name."

    @click.command("show")
    @show_options()
    @click.option("-r", "--reveal", is_flag=True, default=False, help="Reveal decoded secret values (secrets only).")
    @click.pass_context
    def show(ctx, name, namespace, verbose, output_fmt, reveal):
        settings = ctx.obj
        name = resolve_show_name(ctx, name)
        eff = settings.effect(namespace=namespace, output=output_fmt, verbose=verbose)
        entry = resolve(settings.client, plural)

        def transform(data):
            if secret_like:
                return reveal_map_values(data) if reveal else redact_map_values(data)
            if cm_like and eff.verbose == 0:
                return cap_map_values(data)
            return data

        render_single(settings, entry, name, eff, transform=transform)

    if secret_like:
        show.help = "Show one secret. Values are hidden; add --reveal to decode them."
    elif cm_like:
        show.help = "Show one configmap (long values are capped; -v for full)."
    else:
        show.help = f"Show one {singular_name(plural)} in full."

    @click.command("desc")
    @show_options()
    @click.pass_context
    def desc(ctx, name, namespace, verbose, output_fmt):
        settings = ctx.obj
        name = resolve_show_name(ctx, name)
        eff = settings.effect(namespace=namespace, output=output_fmt, verbose=verbose)
        entry = resolve(settings.client, plural)
        describe_impl(settings, entry, name, eff)

    desc.help = f"Describe one {singular_name(plural)}: object + status + children + events."

    @click.group(cls=ResourceGroup, name=name, invoke_without_command=True, default_command="ls")
    @group_options
    @click.pass_context
    def grp(ctx, namespace, output_fmt, verbose, all_namespaces):
        """{help}"""
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

    grp.help = group_help
    grp.add_command(ls, "ls")
    grp.add_command(ls, "list", alias=True)
    grp.add_command(ls, "l", alias=True)
    grp.add_command(show, "show")
    grp.add_command(desc, "desc")
    grp.add_command(desc, "describe", alias=True)
    grp.add_command(desc, "d", alias=True)
    if has_logs:
        grp.add_command(logs_cmd, "logs")
        grp.add_command(logs_cmd, "log", alias=True)
    return grp


def singular_name(plural: str) -> str:
    return plural[:-1] if plural.endswith("s") else plural


PODS = make_resource_group(
    name="pod",
    plural="pods",
    group_help="Pods: ls | NAME | desc NAME | logs NAME.",
    has_logs=True,
)
NAMESPACES = make_resource_group(
    name="ns",
    plural="namespaces",
    group_help="Namespaces: ls | NAME | desc NAME.",
)
DEPLOYMENTS = make_resource_group(
    name="deploy",
    plural="deployments",
    group_help="Deployments: ls | NAME | desc NAME | tree deploy/NAME.",
)
SERVICES = make_resource_group(
    name="svc",
    plural="services",
    group_help="Services: ls | NAME.",
)
SECRETS = make_resource_group(
    name="secret",
    plural="secrets",
    group_help="Secrets: ls | NAME [--reveal]. Values hidden by default.",
    secret_like=True,
)
CONFIGMAPS = make_resource_group(
    name="cm",
    plural="configmaps",
    group_help="ConfigMaps: ls | NAME.",
    cm_like=True,
)
NODES = make_resource_group(
    name="node",
    plural="nodes",
    group_help="Nodes: ls | NAME | tree node/NAME.",
)
CRDS = make_resource_group(
    name="crd",
    plural="customresourcedefinitions",
    group_help="CRDs installed in this cluster: ls | NAME | desc NAME.",
)
