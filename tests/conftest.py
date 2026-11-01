"""Fake Kubernetes API server + kubeconfig fixtures for smoke tests."""

from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar
from urllib.parse import parse_qs, urlparse

import pytest
import yaml
from click.testing import CliRunner

from fixtures import build_discovery, build_objects

# plural -> (kind, namespaced)
PLURAL_KINDS = {
    "pods": ("Pod", True),
    "secrets": ("Secret", True),
    "configmaps": ("ConfigMap", True),
    "events": ("Event", True),
    "services": ("Service", True),
    "persistentvolumeclaims": ("PersistentVolumeClaim", True),
    "nodes": ("Node", False),
    "namespaces": ("Namespace", False),
    "deployments": ("Deployment", True),
    "replicasets": ("ReplicaSet", True),
    "externalsecrets": ("ExternalSecret", True),
    "secretstores": ("SecretStore", True),
    "clustersecretstores": ("ClusterSecretStore", False),
    "customresourcedefinitions": ("CustomResourceDefinition", False),
    "endpoints": ("Endpoints", True),
    "applications": ("Application", True),
}
# bases where each plural is served
BASES = [
    "/api/v1",
    "/apis/apps/v1",
    "/apis/external-secrets.io/v1beta1",
    "/apis/apiextensions.k8s.io/v1",
    "/apis/argoproj.io/v1",
]


def lookup(obj, dotted: str):
    cur = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def matches_selectors(item, labels: str | None, fields: str | None) -> bool:
    if labels:
        for pair in labels.split(","):
            if "=" not in pair:
                return False
            k, v = pair.split("=", 1)
            if (lookup(item, "metadata.labels") or {}).get(k) != v:
                return False
    if fields:
        for pair in fields.split(","):
            if "=" not in pair:
                return False
            k, v = pair.split("=", 1)
            if str(lookup(item, k) or "") != v:
                return False
    return True


class FakeKubeHandler(BaseHTTPRequestHandler):
    server_version = "FakeKube/1.0"
    objects: ClassVar[dict] = {}
    discovery: ClassVar[dict] = {}

    def log_message(self, *a):  # silence
        pass

    def do_GET(self):
        u = urlparse(self.path)
        path = u.path.rstrip("/")
        qs = {k: v[0] for k, v in parse_qs(u.query).items()}

        if path in self.discovery:
            return self._json(200, self.discovery[path])
        if path == "/api" or path == "/apis":
            return self._json(200, self.discovery[path])

        log = re.fullmatch(r"(/api/v1)/namespaces/([^/]+)/pods/([^/]+)/log", path)
        if log:
            return self._log(log.group(2), log.group(3), qs)

        for base in BASES:
            for plural, (kind, namespaced) in PLURAL_KINDS.items():
                items = self.objects.get(plural)
                if items is None:
                    continue
                if namespaced:
                    m = re.fullmatch(
                        re.escape(base) + r"(?:/namespaces/([^/]+))?/" + re.escape(plural) + r"(?:/([^/]+))?", path
                    )
                    if not m:
                        continue
                    ns, name = m.group(1), m.group(2)
                    if ns:
                        pool = [i for i in items if (i.get("metadata") or {}).get("namespace") == ns]
                    else:
                        pool = list(items)  # all-namespaces list
                    return self._serve(plural, kind, pool, name, qs)
                else:
                    m = re.fullmatch(re.escape(base) + r"/" + re.escape(plural) + r"(?:/([^/]+))?", path)
                    if not m:
                        continue
                    name = m.group(1)
                    return self._serve(plural, kind, items, name, qs)
        return self._json(
            404,
            {
                "kind": "Status",
                "apiVersion": "v1",
                "metadata": {},
                "status": "Failure",
                "message": f"the server could not find the requested resource: {path}",
                "reason": "NotFound",
                "code": 404,
            },
        )

    def _serve(self, plural, kind, pool, name, qs):
        pool = [i for i in pool if matches_selectors(i, qs.get("labelSelector"), qs.get("fieldSelector"))]
        if name:
            for i in pool:
                if (i.get("metadata") or {}).get("name") == name:
                    return self._json(200, i)
            return self._json(
                404,
                {
                    "kind": "Status",
                    "apiVersion": "v1",
                    "metadata": {},
                    "status": "Failure",
                    "message": f'{kind} "{name}" not found',
                    "reason": "NotFound",
                    "code": 404,
                },
            )
        return self._json(
            200,
            {
                "apiVersion": "v1",
                "kind": f"{kind}List",
                "metadata": {"resourceVersion": "1"},
                "items": pool,
            },
        )

    def _log(self, ns, pod, qs):
        pods = self.objects.get("pods") or []
        if not any(
            (p.get("metadata") or {}).get("name") == pod and (p.get("metadata") or {}).get("namespace") == ns
            for p in pods
        ):
            return self._json(
                404, {"kind": "Status", "status": "Failure", "message": f'pod "{pod}" not found', "code": 404}
            )
        text = (
            "previous crash log line A\nprevious crash log line B\n"
            if qs.get("previous") == "true"
            else "fake log line 1\nfake log line 2\n"
        )
        body = text.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status, doc):
        body = json.dumps(doc).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(scope="session")
def fake_api():
    objects = build_objects()
    FakeKubeHandler.objects = objects
    FakeKubeHandler.discovery = build_discovery()
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeKubeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    thread.join(timeout=5)


@pytest.fixture(scope="session")
def kubeconfig(fake_api, tmp_path_factory):
    path = tmp_path_factory.mktemp("kq") / "kubeconfig"
    path.write_text(
        yaml.safe_dump(
            {
                "apiVersion": "v1",
                "kind": "Config",
                "clusters": [{"name": "fake", "cluster": {"server": fake_api}}],
                "contexts": [
                    {"name": "fake", "context": {"cluster": "fake", "user": "fake", "namespace": "default"}},
                    {"name": "fake2", "context": {"cluster": "fake", "user": "fake", "namespace": "prod"}},
                ],
                "current-context": "fake",
                "users": [{"name": "fake", "user": {"token": "test-token"}}],
            }
        )
    )
    return str(path)


@pytest.fixture
def run(kubeconfig):
    """Invoke the kube-query CLI against the fake API server."""
    from kube_query.cli import main

    runner = CliRunner()

    def invoke(*args, env=None, check=True):
        result = runner.invoke(
            main,
            ["--kubeconfig", kubeconfig, *(str(a) for a in args)],
            env={"COLUMNS": "240", **(env or {})},  # keep rich tables unwrapped for assertions
        )
        if check and result.exit_code != 0:
            raise AssertionError(
                f"kube-query {' '.join(str(a) for a in args)} failed (exit {result.exit_code}):\n"
                f"{getattr(result, 'output', '')}\n{getattr(result, 'stderr', '')}"
            )
        return result

    return invoke


@pytest.fixture
def out(run):
    """Invoke and return combined stdout+stderr text."""

    def fetch(*args, **kw):
        result = run(*args, **kw)
        return result.output + getattr(result, "stderr", "")

    return fetch
