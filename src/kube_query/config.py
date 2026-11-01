"""Kubeconfig / cluster connection handling and per-invocation settings."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from kubernetes import config as k8s_config
from kubernetes.client import ApiClient
from kubernetes.config.config_exception import ConfigException

from .errors import KqError
from .output import resolve_format

IN_CLUSTER_NS_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"


@dataclass
class Eff:
    """Effective (resolved) options for one command invocation."""

    namespace: str | None = None
    output: str = "yaml"
    verbose: int = 0
    all_namespaces: bool = False

    @property
    def full(self) -> bool:
        return self.verbose >= 2

    @property
    def keep_system_meta(self) -> bool:
        return self.verbose >= 1


class Ctx:
    """A lazily-initialized connection to a Kubernetes cluster.

    Nothing is loaded until the first API call, so commands that only read
    the kubeconfig (e.g. ``kq ctx ls``) never touch the network.
    """

    def __init__(self, context: str | None = None, kubeconfig: str | None = None) -> None:
        self.context = context
        self.kubeconfig = kubeconfig
        self._client: ApiClient | None = None
        self._context_name: str | None = None
        self._default_ns: str | None = None
        # discovery cache, set by kube_query.discovery
        self.resources: list | None = None

    # -- connection -----------------------------------------------------

    @property
    def api_client(self) -> ApiClient:
        if self._client is None:
            self._load()
        return self._client  # type: ignore[return-value]

    def _load(self) -> None:
        try:
            k8s_config.load_kube_config(config_file=self.kubeconfig, context=self.context, persist_config=False)
            self._context_name = self.context or self._current_context_name()
        except ConfigException as e:
            if not self.kubeconfig and os.environ.get("KUBERNETES_SERVICE_HOST"):
                try:
                    k8s_config.load_incluster_config()
                except ConfigException as e2:
                    raise KqError(f"failed to load in-cluster config: {e2}") from None
                self._context_name = "in-cluster"
                self._client = ApiClient()
                return
            raise KqError(
                f"could not load kubeconfig: {e}\n"
                "  Hint: set KUBECONFIG, or pass --kubeconfig / --context. See available contexts: kq ctx ls"
            ) from None
        self._client = ApiClient()

    # -- kubeconfig introspection (no API calls) -------------------------

    def _current_context_name(self) -> str:
        try:
            contexts, current = k8s_config.list_kube_config_contexts(config_file=self.kubeconfig)
        except Exception:
            if os.environ.get("KUBERNETES_SERVICE_HOST"):
                return "in-cluster"
            return "<unknown>"
        if self.context:
            for c in contexts or []:
                if c.get("name") == self.context:
                    return self.context
        return (current or {}).get("name") or "<none>"

    @property
    def context_name(self) -> str:
        if self._context_name is None:
            self._context_name = self._current_context_name()
        return self._context_name

    def default_namespace(self) -> str:
        if self._default_ns is None:
            ns = ""
            try:
                contexts, current = k8s_config.list_kube_config_contexts(config_file=self.kubeconfig)
                if self.context:
                    current = next((c for c in contexts or [] if c.get("name") == self.context), current)
                ns = ((current or {}).get("context") or {}).get("namespace") or ""
            except Exception:
                pass
            if not ns and os.path.exists(IN_CLUSTER_NS_PATH):
                try:
                    ns = Path(IN_CLUSTER_NS_PATH).read_text().strip()
                except OSError:
                    ns = ""
            self._default_ns = ns or "default"
        return self._default_ns

    def contexts(self) -> list[dict]:
        """Context rows for ``kq ctx ls`` (read from kubeconfig, no API calls)."""
        try:
            contexts, current = k8s_config.list_kube_config_contexts(config_file=self.kubeconfig)
        except Exception:
            if os.environ.get("KUBERNETES_SERVICE_HOST"):
                return [
                    {
                        "current": True,
                        "name": "in-cluster",
                        "cluster": "",
                        "server": "service environment",
                        "user": "service account",
                        "namespace": self.default_namespace(),
                    }
                ]
            raise KqError("no readable kubeconfig found.\n  Hint: set KUBECONFIG or pass --kubeconfig.") from None
        current_name = (current or {}).get("name")
        servers = self._cluster_servers()
        rows = []
        for c in contexts or []:
            inner = c.get("context") or {}
            rows.append(
                {
                    "current": c.get("name") == current_name,
                    "name": c.get("name") or "",
                    "cluster": inner.get("cluster") or "",
                    "server": servers.get(inner.get("cluster"), ""),
                    "user": inner.get("user") or "",
                    "namespace": inner.get("namespace") or "default",
                }
            )
        return rows

    def _cluster_servers(self) -> dict[str, str]:
        servers: dict[str, str] = {}
        for p in self._kubeconfig_paths():
            try:
                doc = yaml.safe_load(Path(p).read_text()) or {}
            except Exception:
                continue
            for cl in doc.get("clusters") or []:
                name = cl.get("name")
                if name:
                    servers[name] = (cl.get("cluster") or {}).get("server") or ""
        return servers

    def _kubeconfig_paths(self) -> list[str]:
        if self.kubeconfig:
            return [self.kubeconfig]
        env = os.environ.get("KUBECONFIG")
        if env:
            return [p for p in env.split(os.pathsep) if p]
        return [os.path.expanduser("~/.kube/config")]


@dataclass
class Settings:
    """Options gathered from the root command (and group-level re-statements)."""

    context: str | None = None
    kubeconfig: str | None = None
    namespace: str | None = None
    output: str | None = None
    verbose: int = 0
    all_namespaces: bool = False
    _ctx: Ctx | None = field(default=None, repr=False, compare=False)

    @property
    def client(self) -> Ctx:
        if self._ctx is None:
            self._ctx = Ctx(context=self.context, kubeconfig=self.kubeconfig)
        return self._ctx

    def effect(
        self,
        *,
        namespace: str | None = None,
        output: str | None = None,
        verbose: int = 0,
        all_namespaces: bool = False,
        default_output: str = "yaml",
    ) -> Eff:
        ns = namespace if namespace is not None else self.namespace
        out = output if output is not None else self.output
        return Eff(
            namespace=ns,
            output=resolve_format(out, default=default_output),
            verbose=max(verbose or 0, self.verbose),
            all_namespaces=all_namespaces or self.all_namespaces,
        )
