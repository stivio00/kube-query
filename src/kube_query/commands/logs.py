"""`kube-query logs` — pod container logs (read-only)."""

from __future__ import annotations

import click

from ..access import get_object, pod_logs
from ..discovery import resolve
from ..errors import KqError
from ..summarize import dig, parse_since


@click.command("logs")
@click.argument("name")
@click.option("-c", "--container", default=None, help="Container name (required when a pod has several).")
@click.option("--tail", type=int, default=100, show_default=True, help="Lines to fetch (0 = all).")
@click.option("--since", default=None, help="Only logs newer than this duration, e.g. 30m, 2h.")
@click.option("--previous", is_flag=True, default=False, help="Previous (terminated) container instance logs.")
@click.option("--timestamps", is_flag=True, default=False, help="Include timestamps.")
@click.option(
    "--all-containers", "all_containers", is_flag=True, default=False, help="Dump every container (incl. init)."
)
@click.option("-n", "--ns", "--namespace", "namespace", default=None, help="Namespace.")
@click.pass_obj
def logs(settings, name, container, tail, since, previous, timestamps, all_containers, namespace):
    """Pod logs (plain text): kube-query logs POD [-c CONTAINER] [--tail N] [--previous]"""
    client = settings.client
    eff_ns = namespace or settings.namespace
    ns = eff_ns or client.default_namespace()
    entry = resolve(client, "pods")
    pod = get_object(client, entry, name, namespace=ns)
    names = [
        c.get("name")
        for c in (dig(pod, "spec", "containers", default=[]) or [])
        + (dig(pod, "spec", "initContainers", default=[]) or [])
        if c.get("name")
    ]
    if container:
        if container not in names:
            raise KqError(f"container '{container}' not found in pod '{name}'.\n  Containers: {', '.join(names)}")
        targets = [container]
    elif all_containers or len(names) <= 1:
        targets = names
    else:
        raise KqError(f"pod '{name}' has multiple containers; pick one with -c.\n  Containers: {', '.join(names)}")

    since_s = int(parse_since(since).total_seconds()) if since else None
    tail_lines = tail if tail and tail > 0 else None
    output_any = False
    for cname in targets:
        if len(targets) > 1:
            click.echo(f"--- pod/{name} container/{cname} (ns {ns}) ---")
        text = pod_logs(
            client,
            ns,
            name,
            container=cname,
            tail=tail_lines,
            previous=previous,
            since_seconds=since_s,
            timestamps=timestamps,
        )
        if text.strip():
            output_any = True
            click.echo(text.rstrip("\n"))
        elif len(targets) == 1:
            from ..output import note

            note(f"no log output for container '{cname}'")
    if not output_any and len(targets) > 1:
        from ..output import note

        note("no log output from any container")
