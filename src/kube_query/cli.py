"""kube-query — read-only Kubernetes queries for humans and AI agents."""

from __future__ import annotations

import click

from . import __version__
from .cli_kit import KqGroup
from .commands import register
from .config import Settings
from .output import FORMATS

EPILOG = """\
\b
USAGE PATTERNS
  kube-query overview                cluster snapshot: problems first
  kube-query p l [-A|-n NS] [REGEX]  list pods   (d=deploy, n=ns, no=node,
  kube-query p NAME / p desc NAME    inspect      sec=secret, cm, svc, ev)
  kube-query logs NAME [-c C]        pod logs     kube-query tree deploy/NAME
  kube-query get RESOURCE[/NAME]     any resource incl. CRDs ('api' lists all)
  kube-query helm ls -A / eso -A     helm releases / ExternalSecret status
  kube-query argo -A                  Argo CD apps: health + sync
  tip: alias kq=kube-query for a short form

\b
OPTIONS
  -o yaml|json|rich|md|tree        output (default: compact yaml)
  -n NS | -A | -l SEL | -f REGEX   scope: namespace / all / labels / name
  --show-labels                     add a LABELS column to listings
  -v (system metadata) -vv (raw)   verbosity
  --ctx NAME / --kubeconfig PATH   cluster selection

\b
ROLE
  kube-query CAPTURES cluster state for diagnosis; fixing belongs to
  other tools (kubectl apply, gitops, helm). It only sends GET requests -
  it can never create, update or delete anything.
"""


@click.group(
    cls=KqGroup,
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.version_option(__version__, "--version", prog_name="kube-query")
@click.option("--ctx", "--context", "context", default=None, help="Kubeconfig context to use.")
@click.option("--kubeconfig", default=None, type=click.Path(exists=True), help="Path to a kubeconfig file.")
@click.option("-n", "--ns", "--namespace", "namespace", default=None, help="Default namespace for this invocation.")
@click.option(
    "-A", "--all-namespaces", "all_namespaces", is_flag=True, default=False, help="All namespaces (where applicable)."
)
@click.option(
    "-o",
    "--output",
    "output_fmt",
    type=click.Choice(FORMATS),
    default=None,
    help="Output format: yaml, json, rich, md, tree. [env: KQ_OUTPUT]",
)
@click.option("-v", "--verbose", count=True, help="Verbosity: -v keep system metadata, -vv raw object.")
@click.pass_context
def main(ctx, context, kubeconfig, namespace, all_namespaces, output_fmt, verbose):
    """kube-query - read-only Kubernetes queries for AI agents and humans.

    Compact yaml by default; rich tables, markdown, json and ownership
    trees on request. Built-ins, shortnames, CRDs, Helm releases and
    External Secrets Operator. Start with: kube-query overview
    """
    ctx.obj = Settings(
        context=context,
        kubeconfig=kubeconfig,
        namespace=namespace,
        output=output_fmt,
        verbose=verbose,
        all_namespaces=all_namespaces,
    )


main.epilog = EPILOG
register(main)


if __name__ == "__main__":
    main()
