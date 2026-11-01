"""`kube-query ver` — client and server version."""

from __future__ import annotations

import click

from .. import __version__
from ..access import server_version
from ..cli_kit import output_option
from ..output import console, emit_data


@click.command("version")
@output_option
@click.pass_obj
def version(settings, output_fmt):
    """Client + server version (which cluster am I on?)"""
    eff = settings.effect(output=output_fmt)
    client = settings.client
    try:
        sv = server_version(client)
        server = {
            "version": sv.get("gitVersion") or "",
            "platform": sv.get("platform") or "",
        }
        server_err = None
    except Exception as e:
        server = None
        server_err = str(e).splitlines()[0]

    data = {"client": f"kube-query {__version__} (python)", "context": client.context_name}
    if server:
        data["server"] = server
    else:
        data["server"] = {"unavailable": server_err}

    if eff.output in ("yaml", "json"):
        emit_data(data, eff.output)
        return

    rows = [
        {"KEY": "client", "VALUE": data["client"]},
        {"KEY": "context", "VALUE": data["context"]},
        {"KEY": "server", "VALUE": (server["version"] if server else f"unavailable: {server_err}")},
    ]
    if server and server["platform"]:
        rows.append({"KEY": "platform", "VALUE": server["platform"]})
    if eff.output == "rich":
        console().print()
        from ..output import rich_table

        console().print(rich_table(["KEY", "VALUE"], rows))
        console().print()
    elif eff.output == "md":
        from ..output import md_table

        click.echo(md_table(["KEY", "VALUE"], rows) + "\n")
