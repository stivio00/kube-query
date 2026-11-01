"""CLI building blocks: alias-hiding groups, resource groups, common options."""

from __future__ import annotations

import click

from .output import FORMATS


class KqGroup(click.Group):
    """A click Group that hides registered aliases from help listings."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._aliases: set[str] = set()

    def add_command(self, cmd, name=None, *, alias: bool = False) -> None:
        super().add_command(cmd, name)
        if alias:
            self._aliases.add(name or cmd.name)

    def list_commands(self, ctx) -> list[str]:
        return [n for n in self.commands if n not in self._aliases]


class ResourceGroup(KqGroup):
    """A resource group:

    - ``kube-query pod``           -> runs the default command (ls)
    - ``kube-query pod nginx-123`` -> unknown token dispatches to `show` with the name
    - ``kube-query pod ls``        -> normal subcommand
    """

    def __init__(self, *args, **kwargs) -> None:
        self.default_command = kwargs.pop("default_command", "ls")
        super().__init__(*args, **kwargs)

    def get_command(self, ctx, cmd_name):
        cmd = super().get_command(ctx, cmd_name)
        if cmd is not None or cmd_name.startswith("-"):
            return cmd
        show = super().get_command(ctx, "show")
        if show is None:
            return None
        ctx._implicit_name = cmd_name
        return show


# -- shared option decorators ---------------------------------------------------


def output_option(fn):
    return click.option(
        "-o",
        "--output",
        "output_fmt",
        type=click.Choice(FORMATS),
        default=None,
        help="Output format: yaml (default), json, rich, md, tree. [env: KQ_OUTPUT]",
    )(fn)


def verbose_option(fn):
    return click.option(
        "-v",
        "--verbose",
        count=True,
        default=0,
        help="Verbosity: -v keep system metadata, -vv raw object.",
    )(fn)


def namespace_option(fn):
    return click.option(
        "-n",
        "--ns",
        "--namespace",
        "namespace",
        default=None,
        help="Namespace (default: current context's namespace).",
    )(fn)


def all_namespaces_option(fn):
    return click.option(
        "-A",
        "--all-namespaces",
        "all_namespaces",
        is_flag=True,
        default=False,
        help="All namespaces.",
    )(fn)


def selector_options(fn):
    fn = click.option(
        "-l",
        "--selector",
        "label_selector",
        default=None,
        help="Label selector, e.g. app=web,tier=frontend.",
    )(fn)
    return click.option(
        "--field-selector",
        "field_selector",
        default=None,
        help="Field selector, e.g. status.phase=Running.",
    )(fn)


def filter_option(fn):
    return click.option(
        "-f",
        "--filter",
        "name_filter",
        default=None,
        help="Regex filter on object name.",
    )(fn)


def list_options(include_pattern: bool = True):
    """Options for `ls`-style commands (order matters for help output)."""

    def deco(fn):
        if include_pattern:
            fn = click.argument("pattern", required=False)(fn)
        fn = filter_option(fn)
        fn = all_namespaces_option(fn)
        fn = selector_options(fn)
        fn = namespace_option(fn)
        fn = verbose_option(fn)
        return output_option(fn)

    return deco


def show_options():
    """Options for `show`-style commands (NAME may come from group dispatch)."""

    def deco(fn):
        fn = click.argument("name", required=False)(fn)
        fn = namespace_option(fn)
        fn = verbose_option(fn)
        return output_option(fn)

    return deco


def group_options(fn):
    """Options acceptable directly on a resource group (before the subcommand)."""
    fn = all_namespaces_option(fn)
    fn = namespace_option(fn)
    fn = verbose_option(fn)
    return output_option(fn)


def resolve_show_name(ctx: click.Context, name: str | None) -> str:
    if name:
        return name
    implicit = getattr(getattr(ctx, "parent", None), "_implicit_name", None)
    if implicit:
        return implicit
    raise click.UsageError("Missing NAME.")


def merge_group_options(settings, *, namespace=None, output_fmt=None, verbose=0, all_namespaces=False) -> None:
    """Fold group-level option values into the shared Settings object."""
    if namespace is not None:
        settings.namespace = namespace
    if output_fmt is not None:
        settings.output = output_fmt
    if verbose:
        settings.verbose = max(settings.verbose, verbose)
    if all_namespaces:
        settings.all_namespaces = True
