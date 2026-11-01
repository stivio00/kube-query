"""`kube-query overview` — one-shot cluster health snapshot for triage."""

from __future__ import annotations

import click

from ..access import list_objects
from ..cli_kit import all_namespaces_option, namespace_option, output_option, verbose_option
from ..discovery import resolve
from ..errors import KqError
from ..events import list_events
from ..output import console, emit_data, md_heading, md_table, rich_table
from ..summarize import (
    age,
    deployment_brief,
    deployment_is_healthy,
    dig,
    node_is_healthy,
    node_status,
    now_utc,
    pod_is_healthy,
    pod_restarts,
    pod_status,
)

_EVENT_LIMIT = 15


def _section(fn):
    """Tolerate a failing section (RBAC / missing resource) instead of dying."""
    try:
        return fn(), None
    except KqError as e:
        return None, str(e.message).splitlines()[0]


def build_overview(settings, *, namespace: str | None, since: str) -> dict:
    client = settings.client
    report: dict = {
        "context": client.context_name,
        "scope": f"namespace: {namespace}" if namespace else "all namespaces",
    }

    nodes, nodes_err = _section(lambda: list_objects(client, resolve(client, "nodes")))
    if nodes is not None:
        not_ready = [
            {"name": dig(n, "metadata", "name", default=""), "status": node_status(n)[0], "problems": node_status(n)[1]}
            for n in nodes
            if not node_is_healthy(n)
        ]
        report["nodes"] = {
            "total": len(nodes),
            "healthy": len(nodes) - len(not_ready),
            "problems": not_ready,
        }
    elif nodes_err:
        report["nodes"] = {"unavailable": nodes_err}

    pods, pods_err = _section(lambda: list_objects(client, resolve(client, "pods"), namespace=namespace))
    if pods is not None:
        problems, restarted = [], []
        for p in pods:
            name = dig(p, "metadata", "name", default="") or ""
            ns = dig(p, "metadata", "namespace", default="") or ""
            if pod_is_healthy(p):
                r = pod_restarts(p)
                if r > 0:
                    restarted.append(
                        {
                            "name": name,
                            "namespace": ns,
                            "restarts": r,
                            "age": age(dig(p, "metadata", "creationTimestamp")),
                        }
                    )
                continue
            problems.append(
                {
                    "name": name,
                    "namespace": ns,
                    "status": pod_status(p),
                    "restarts": pod_restarts(p),
                    "node": dig(p, "spec", "nodeName") or "",
                    "age": age(dig(p, "metadata", "creationTimestamp")),
                }
            )
        problems.sort(key=lambda x: (x["namespace"], x["name"]))
        report["pods"] = {"total": len(pods), "healthy": len(pods) - len(problems), "problems": problems}
        if restarted:
            report["pods"]["restartedButReady"] = restarted
    elif pods_err:
        report["pods"] = {"unavailable": pods_err}

    deps, deps_err = _section(lambda: list_objects(client, resolve(client, "deployments"), namespace=namespace))
    if deps is not None:
        unavailable = []
        for d in deps:
            if deployment_is_healthy(d):
                continue
            b = deployment_brief(d)
            unavailable.append(
                {
                    "name": dig(d, "metadata", "name", default="") or "",
                    "namespace": dig(d, "metadata", "namespace", default="") or "",
                    "desired": b["desired"],
                    "ready": b["ready"],
                    "available": b["available"],
                    "age": age(dig(d, "metadata", "creationTimestamp")),
                }
            )
        unavailable.sort(key=lambda x: (x["namespace"], x["name"]))
        report["deployments"] = {"total": len(deps), "unavailable": unavailable}
    elif deps_err:
        report["deployments"] = {"unavailable": deps_err}

    pvcs, pvcs_err = _section(
        lambda: list_objects(client, resolve(client, "persistentvolumeclaims"), namespace=namespace)
    )
    if pvcs is not None:
        pending = [
            {
                "name": dig(p, "metadata", "name", default="") or "",
                "namespace": dig(p, "metadata", "namespace", default="") or "",
                "phase": dig(p, "status", "phase") or "",
            }
            for p in pvcs
            if (dig(p, "status", "phase") or "") not in ("Bound",)
        ]
        if pending:
            report["persistentVolumeClaims"] = {"notBound": pending}
    elif pvcs_err:
        report["persistentVolumeClaims"] = {"unavailable": pvcs_err}

    events, events_err = _section(lambda: list_events(client, namespace=namespace, since=since, types=("Warning",)))
    if events is not None:
        trimmed = [{k: v for k, v in e.items() if not k.startswith("_")} for e in events[:_EVENT_LIMIT]]
        report["warningEvents"] = {
            "window": since,
            "count": len(events),
            "recent": trimmed,
        }
    elif events_err:
        report["warningEvents"] = {"unavailable": events_err}

    report["generatedAt"] = now_utc().isoformat(timespec="seconds")
    issue_count = 0
    if report.get("nodes", {}).get("problems"):
        issue_count += len(report["nodes"]["problems"])
    if report.get("pods", {}).get("problems"):
        issue_count += len(report["pods"]["problems"])
    if report.get("deployments", {}).get("unavailable"):
        issue_count += len(report["deployments"]["unavailable"])
    if report.get("persistentVolumeClaims", {}).get("notBound"):
        issue_count += len(report["persistentVolumeClaims"]["notBound"])
    report["summary"] = {"issues": issue_count, "healthy": issue_count == 0}
    return report


@click.command("overview")
@click.option("--since", default="1h", show_default=True, help="Warning-event window, e.g. 30m, 2h, 1d.")
@all_namespaces_option
@namespace_option
@verbose_option
@output_option
@click.pass_obj
def overview(settings, since, all_namespaces, namespace, verbose, output_fmt):
    """Cluster snapshot: problem pods, nodes, deployments, PVCs, warnings. Start here.

    \b
    Examples:
      kube-query overview
      kube-query overview -o rich
      kube-query overview -n prod --since 4h -o md
    """
    eff = settings.effect(namespace=namespace, output=output_fmt, verbose=verbose, all_namespaces=all_namespaces)
    # overview defaults to all namespaces unless -n is given
    ns = eff.namespace
    report = build_overview(settings, namespace=ns, since=since)

    if eff.output in ("yaml", "json"):
        emit_data(report, eff.output)
        return

    title = f"cluster overview - {report['context']} - {report['scope']}"
    if eff.output == "rich":
        c = console()
        c.print(f"[bold]{title}[/bold]\n")
        _print_rich(c, report)
    elif eff.output == "md":
        parts = [md_heading(title, 2)]
        parts.extend(_md_sections(report))
        click.echo("".join(parts), nl=False)
    else:
        raise KqError(f"format '{eff.output}' is not supported here")


def _print_rich(c, report: dict) -> None:
    verdict = (
        "[green]healthy[/green]"
        if report["summary"]["healthy"]
        else f"[red]{report['summary']['issues']} issue(s)[/red]"
    )
    c.print(f"verdict: {verdict}\n")
    if "nodes" in report:
        n = report["nodes"]
        if "problems" in n:
            c.print(
                rich_table(
                    ["NAME", "STATUS", "PROBLEMS"],
                    [
                        {"NAME": p["name"], "STATUS": p["status"], "PROBLEMS": ",".join(p["problems"])}
                        for p in n["problems"]
                    ],
                    title=f"nodes ({n['healthy']}/{n['total']} healthy)",
                )
            )
            c.print()
    if "pods" in report:
        p = report["pods"]
        if p.get("problems"):
            c.print(
                rich_table(
                    ["NAMESPACE", "NAME", "STATUS", "RESTARTS", "NODE", "AGE"],
                    [
                        {
                            "NAMESPACE": x["namespace"],
                            "NAME": x["name"],
                            "STATUS": x["status"],
                            "RESTARTS": x["restarts"],
                            "NODE": x["node"],
                            "AGE": x["age"],
                        }
                        for x in p["problems"]
                    ],
                    title=f"problem pods ({len(p['problems'])} of {p['total']})",
                )
            )
            c.print()
    if "deployments" in report:
        d = report["deployments"]
        if isinstance(d.get("unavailable"), list) and d["unavailable"]:
            c.print(
                rich_table(
                    ["NAMESPACE", "NAME", "READY", "AVAILABLE", "AGE"],
                    [
                        {
                            "NAMESPACE": x["namespace"],
                            "NAME": x["name"],
                            "READY": f"{x['ready']}/{x['desired']}",
                            "AVAILABLE": x["available"],
                            "AGE": x["age"],
                        }
                        for x in d["unavailable"]
                    ],
                    title=f"unavailable deployments ({len(d['unavailable'])} of {d['total']})",
                )
            )
            c.print()
    we = report.get("warningEvents") or {}
    if we.get("recent"):
        c.print(
            rich_table(
                ["LAST", "REASON", "OBJECT", "NAMESPACE", "MESSAGE"],
                [
                    {
                        "LAST": age(e.get("lastSeen")),
                        "REASON": e.get("reason", ""),
                        "OBJECT": e.get("object", ""),
                        "NAMESPACE": e.get("namespace", ""),
                        "MESSAGE": e.get("message", ""),
                    }
                    for e in we["recent"]
                ],
                title=f"warning events (last {we.get('window', '?')}, {we.get('count', 0)} total)",
            )
        )


def _md_sections(report: dict) -> list[str]:
    parts = []
    parts.append(
        f"verdict: {'healthy' if report['summary']['healthy'] else str(report['summary']['issues']) + ' issue(s)'}\n"
    )
    if report.get("nodes", {}).get("problems"):
        parts.append(md_heading("nodes with problems", 3))
        parts.append(
            md_table(
                ["NAME", "STATUS", "PROBLEMS"],
                [
                    {"NAME": p["name"], "STATUS": p["status"], "PROBLEMS": ",".join(p["problems"])}
                    for p in report["nodes"]["problems"]
                ],
            )
            + "\n"
        )
    pods = report.get("pods", {})
    if pods.get("problems"):
        parts.append(md_heading(f"problem pods ({len(pods['problems'])} of {pods.get('total', '?')})", 3))
        parts.append(
            md_table(
                ["NAMESPACE", "NAME", "STATUS", "RESTARTS", "NODE", "AGE"],
                [
                    {
                        "NAMESPACE": x["namespace"],
                        "NAME": x["name"],
                        "STATUS": x["status"],
                        "RESTARTS": x["restarts"],
                        "NODE": x["node"],
                        "AGE": x["age"],
                    }
                    for x in pods["problems"]
                ],
            )
            + "\n"
        )
    deps = report.get("deployments", {})
    if isinstance(deps.get("unavailable"), list) and deps["unavailable"]:
        parts.append(md_heading(f"unavailable deployments ({len(deps['unavailable'])} of {deps.get('total', '?')})", 3))
        parts.append(
            md_table(
                ["NAMESPACE", "NAME", "READY", "AVAILABLE", "AGE"],
                [
                    {
                        "NAMESPACE": x["namespace"],
                        "NAME": x["name"],
                        "READY": f"{x['ready']}/{x['desired']}",
                        "AVAILABLE": x["available"],
                        "AGE": x["age"],
                    }
                    for x in deps["unavailable"]
                ],
            )
            + "\n"
        )
    we = report.get("warningEvents") or {}
    if we.get("recent"):
        parts.append(md_heading(f"warning events (last {we.get('window', '?')}, {we.get('count', 0)} total)", 3))
        parts.append(
            md_table(
                ["LAST", "REASON", "OBJECT", "NAMESPACE", "MESSAGE"],
                [
                    {
                        "LAST": age(e.get("lastSeen")),
                        "REASON": e.get("reason", ""),
                        "OBJECT": e.get("object", ""),
                        "NAMESPACE": e.get("namespace", ""),
                        "MESSAGE": e.get("message", ""),
                    }
                    for e in we["recent"]
                ],
            )
            + "\n"
        )
    return parts
