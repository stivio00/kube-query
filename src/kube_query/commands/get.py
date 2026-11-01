"""`kube-query get RESOURCE [NAME]` — generic query for any resource, including CRDs."""

from __future__ import annotations

import click

from ..discovery import parse_target, resolve
from ..errors import KqError
from ._impl import fetch_list, render_list, render_single


@click.command("get")
@click.argument("resource")
@click.argument("name", required=False)
@click.option("-A", "--all-namespaces", "all_namespaces", is_flag=True, default=False, help="All namespaces.")
@click.option("-l", "--selector", "label_selector", default=None, help="Label selector, e.g. app=web.")
@click.option("--field-selector", "field_selector", default=None, help="Field selector, e.g. status.phase=Running.")
@click.option("-f", "--filter", "name_filter", default=None, help="Regex filter on object name (list mode).")
@click.option("--show-labels", "show_labels", is_flag=True, default=False, help="Add a LABELS column (table formats).")
@click.option("-n", "--ns", "--namespace", "namespace", default=None, help="Namespace.")
@click.option("-v", "--verbose", count=True, default=0, help="Verbosity: -v keep system metadata, -vv raw.")
@click.option("-o", "--output", "output_fmt", type=None, default=None, help="Format: yaml, json, rich, md, tree.")
@click.pass_obj
def get(
    settings,
    resource,
    name,
    all_namespaces,
    label_selector,
    field_selector,
    name_filter,
    show_labels,
    namespace,
    verbose,
    output_fmt,
):
    """Get any resource (built-ins and CRDs): kube-query get RESOURCE[/NAME]

    \b
    Examples:
      kube-query get pods -A --show-labels
      kube-query get deploy/web -n prod
      kube-query get externalsecrets -A -o rich
      kube-query get apps/v1/deployments -n prod
    """
    eff = settings.effect(namespace=namespace, output=output_fmt, verbose=verbose, all_namespaces=all_namespaces)
    api_version, res_name, obj_name = parse_target(resource, name)
    if obj_name and (label_selector or field_selector):
        raise KqError("selectors cannot be combined with an object name")
    entry = resolve(settings.client, res_name, api_version=api_version)
    if obj_name:
        render_single(settings, entry, obj_name, eff)
    else:
        items, ns = fetch_list(
            settings,
            entry,
            eff,
            label_selector=label_selector,
            field_selector=field_selector,
            pattern=name_filter,
        )
        render_list(settings, entry, items, eff, namespace=ns, show_labels=show_labels)
