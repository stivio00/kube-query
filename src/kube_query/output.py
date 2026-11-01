"""Rendering: YAML (default), JSON, rich tables, markdown, notes."""

from __future__ import annotations

import json
import os
from datetime import date, datetime

import click
import yaml
from rich import box
from rich.console import Console
from rich.syntax import Syntax
from rich.table import Table as RichTable

from .errors import KqError

FORMATS = ("yaml", "json", "rich", "md", "tree")


def resolve_format(value: str | None, *, default: str = "yaml") -> str:
    v = (value or os.environ.get("KQ_OUTPUT") or default).lower()
    if v not in FORMATS:
        raise KqError(
            f"invalid output format '{v}' (choose from: {', '.join(FORMATS)}; also settable via the KQ_OUTPUT env var)"
        )
    return v


class _Dumper(yaml.SafeDumper):
    pass


_Dumper.add_representer(datetime, lambda d, x: d.represent_str(x.isoformat()))
_Dumper.add_representer(date, lambda d, x: d.represent_str(x.isoformat()))


def as_yaml(data) -> str:
    return yaml.dump(
        data,
        Dumper=_Dumper,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        width=10**6,
    )


def as_json(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)


def emit_data(data, fmt: str) -> None:
    if fmt == "yaml":
        click.echo(as_yaml(data))
    elif fmt == "json":
        click.echo(as_json(data))
    else:
        raise KqError(f"internal: emit_data does not support '{fmt}'")


def note(msg: str) -> None:
    """Commentary on stderr; stdout stays machine-parseable."""
    click.echo(f"# {msg}", err=True)


_console: Console | None = None


def console() -> Console:
    global _console
    if _console is None:
        _console = Console(highlight=False)
    return _console


# -- status coloring -------------------------------------------------------------

_REDN = (
    "crashloop",
    "error",
    "failed",
    "imagepullback",
    "notready",
    "unknown",
    "lost",
    "evicted",
    "backoff",
    "unhealthy",
    "failureschedul",
    "createcontainerconfigerror",
    "createcontainererror",
    "errimage",
)
_YELN = ("pending", "creating", "initializing", "progressing", "pulling", "terminating", "deploying")
_GRNN = ("running", "completed", "succeeded", "active", "ready", "deployed", "bound", "available", "synced", "healthy")


def status_style(value) -> str:
    s = str(value).lower()
    if any(x in s for x in _REDN):
        return "red"
    if any(x in s for x in _YELN):
        return "yellow"
    if any(x in s for x in _GRNN):
        return "green"
    return ""


_STATUS_HEADERS = {"STATUS", "TYPE", "READY", "HEALTH", "PHASE", "PROBLEMS"}


def rich_table(headers: list[str], rows: list[dict], *, title: str | None = None) -> RichTable:
    t = RichTable(box=box.SIMPLE, header_style="bold", title=title, expand=False)
    for h in headers:
        t.add_column(h, overflow="fold")
    for r in rows:
        cells = []
        for h in headers:
            v = str(r.get(h, ""))
            style = ""
            if h.upper() in _STATUS_HEADERS:
                if h.upper() == "READY" and "/" in v:
                    a, _, b = v.partition("/")
                    style = "green" if a == b else "red"
                else:
                    style = status_style(v)
            cells.append(f"[{style}]{v}[/{style}]" if style else v)
        t.add_row(*cells)
    return t


# -- markdown -----------------------------------------------------------------------


def _md_escape(v) -> str:
    return str(v).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def md_table(headers: list[str], rows: list[dict]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join(["-------"] * len(headers)) + "|",
    ]
    for r in rows:
        lines.append("| " + " | ".join(_md_escape(r.get(h, "")) for h in headers) + " |")
    return "\n".join(lines)


def md_heading(text: str, level: int = 2) -> str:
    return "\n" + "#" * level + " " + text + "\n"


def md_code(text: str, lang: str = "yaml") -> str:
    return f"```{lang}\n{text.strip()}\n```\n"


def md_kv_table(d: dict) -> str:
    headers = ["KEY", "VALUE"]
    rows = [{"KEY": k, "VALUE": _md_value(v)} for k, v in d.items()]
    return md_table(headers, rows)


def _md_value(v) -> str:
    if isinstance(v, (dict, list)):
        s = json.dumps(v, ensure_ascii=False, default=str)
        return s[:400] + "…" if len(s) > 400 else s
    return "" if v is None else str(v)


def render_rows(
    headers: list[str],
    rows: list[dict],
    fmt: str,
    *,
    title: str | None = None,
    subtitle: str | None = None,
) -> None:
    """Emit a table in rich or md format."""
    if fmt == "rich":
        c = console()
        if title:
            c.print(f"[bold]{title}[/bold]")
        c.print(rich_table(headers, rows))
        if subtitle:
            c.print(f"[dim]{subtitle}[/dim]")
        c.print()
    elif fmt == "md":
        parts = []
        if title:
            parts.append(md_heading(title))
        if subtitle:
            parts.append(f"*{subtitle}*\n\n")
        parts.append(md_table(headers, rows) + "\n")
        click.echo("".join(parts), nl=False)
    else:
        raise KqError(f"format '{fmt}' cannot render tables (use rich or md)")


def print_object(data: dict, fmt: str, *, title: str | None = None) -> None:
    """Emit a single object for the rich/md formats (YAML text with highlighting)."""
    text = as_yaml(data)
    if fmt == "rich":
        c = console()
        if title:
            c.print(f"[bold]{title}[/bold]")
        c.print(Syntax(text, "yaml", background_color="default", word_wrap=True))
    elif fmt == "md":
        parts = []
        if title:
            parts.append(md_heading(title))
        parts.append(md_code(text))
        click.echo("".join(parts), nl=False)
    else:
        raise KqError(f"format '{fmt}' cannot render objects directly (use yaml or json)")
