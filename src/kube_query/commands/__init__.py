"""Command registry for the kq root group."""

from __future__ import annotations

from .api_resources import api
from .contexts import make_contexts_group
from .describe import describe
from .eso_cmd import eso
from .events_cmd import ev
from .get import get
from .groups import CONFIGMAPS, DEPLOYMENTS, NAMESPACES, NODES, PODS, SECRETS, SERVICES
from .helm_cmd import make_helm_group
from .logs import logs
from .overview import overview
from .tree_cmd import tree
from .version import version


def register(main) -> None:
    """Attach all commands and their aliases to the root group."""
    # triage first
    main.add_command(overview, "overview")
    main.add_command(overview, "ov", alias=True)
    main.add_command(overview, "o", alias=True)
    main.add_command(overview, "health", alias=True)

    main.add_command(PODS, "pod")
    main.add_command(PODS, "pods", alias=True)
    main.add_command(PODS, "p", alias=True)
    main.add_command(PODS, "po", alias=True)

    main.add_command(NAMESPACES, "ns")
    main.add_command(NAMESPACES, "namespaces", alias=True)
    main.add_command(NAMESPACES, "namespace", alias=True)
    main.add_command(NAMESPACES, "n", alias=True)

    main.add_command(DEPLOYMENTS, "deploy")
    main.add_command(DEPLOYMENTS, "deployments", alias=True)
    main.add_command(DEPLOYMENTS, "deployment", alias=True)
    main.add_command(DEPLOYMENTS, "dep", alias=True)
    main.add_command(DEPLOYMENTS, "d", alias=True)

    main.add_command(SERVICES, "svc")
    main.add_command(SERVICES, "services", alias=True)
    main.add_command(SERVICES, "service", alias=True)

    main.add_command(SECRETS, "secret")
    main.add_command(SECRETS, "secrets", alias=True)
    main.add_command(SECRETS, "sec", alias=True)

    main.add_command(CONFIGMAPS, "cm")
    main.add_command(CONFIGMAPS, "configmaps", alias=True)
    main.add_command(CONFIGMAPS, "configmap", alias=True)

    main.add_command(NODES, "node")
    main.add_command(NODES, "nodes", alias=True)
    main.add_command(NODES, "no", alias=True)

    main.add_command(ev, "ev")
    main.add_command(ev, "events", alias=True)
    main.add_command(ev, "event", alias=True)
    main.add_command(ev, "e", alias=True)

    main.add_command(logs, "logs")
    main.add_command(logs, "log", alias=True)

    main.add_command(make_helm_group(), "helm")
    main.add_command(make_helm_group(), "h", alias=True)

    main.add_command(eso, "eso")
    main.add_command(eso, "externalsecrets", alias=True)

    main.add_command(make_contexts_group(), "ctx")
    main.add_command(make_contexts_group(), "contexts", alias=True)
    main.add_command(make_contexts_group(), "context", alias=True)
    main.add_command(make_contexts_group(), "c", alias=True)

    main.add_command(get, "get")
    main.add_command(get, "g", alias=True)

    main.add_command(describe, "describe")
    main.add_command(describe, "desc", alias=True)

    main.add_command(tree, "tree")
    main.add_command(tree, "t", alias=True)

    main.add_command(api, "api")
    main.add_command(api, "api-resources", alias=True)
    main.add_command(api, "ar", alias=True)

    main.add_command(version, "version")
    main.add_command(version, "ver", alias=True)
