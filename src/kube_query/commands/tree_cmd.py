"""`kq tree` — ownership tree (Deployment -> ReplicaSet -> Pods, ...)."""

from __future__ import annotations

import click

from ..access import get_object
from ..discovery import parse_target, resolve
from ..errors import KqError
from ..output import console, emit_data
from ..tree import build_forest, md_forest, node_dict, rich_forest


@click.command("tree")
@click.argument("resource")
@click.argument("name", required=False)
@click.option("-n", "--ns", "--namespace", "namespace", default=None, help="Namespace.")
@click.option("-o", "--output", "output_fmt", default=None, help="Format: tree (default), yaml, json, md, rich.")
@click.option("-v", "--verbose", count=True, default=0, help="Verbosity (affects yaml/json payloads).")
@click.pass_obj
def tree(settings, resource, name, namespace, output_fmt, verbose):
    """Ownership tree: kq tree RESOURCE/NAME (deploy/web, cronjob/backup, node/worker-1)"""
    eff = settings.effect(namespace=namespace, output=output_fmt, verbose=verbose, default_output="tree")
    api_version, res_name, obj_name = parse_target(resource, name)
    if not obj_name:
        raise click.UsageError("Missing NAME (or use RESOURCE/NAME).")
    entry = resolve(settings.client, res_name, api_version=api_version)
    ns = None
    if entry.namespaced:
        ns = eff.namespace or settings.client.default_namespace()
    obj = get_object(settings.client, entry, obj_name, namespace=ns)
    roots = build_forest(settings.client, entry, obj)

    if eff.output == "tree":
        console().print(rich_forest(roots))
        return
    data = [node_dict(r) for r in roots]
    if len(data) == 1:
        data = data[0]
    if eff.output in ("yaml", "json"):
        emit_data(data, eff.output)
    elif eff.output == "md":
        click.echo(md_forest(roots))
    elif eff.output == "rich":
        console().print(rich_forest(roots))
    else:
        raise KqError(f"format '{eff.output}' is not supported here")
