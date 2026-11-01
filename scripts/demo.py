#!/usr/bin/env python3
"""Run kube-query against a fake Kubernetes API server — try the tool with no cluster.

Starts an in-process API server with realistic fixture data (pods in several
states, a stuck deployment, warning events, helm release secrets, ESO CRDs),
writes a throwaway kubeconfig, and prints ready-to-paste commands.

Ctrl+C to stop.
"""

from __future__ import annotations

import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys_path_test = ROOT / "tests"

import sys  # noqa: E402

sys.path.insert(0, str(sys_path_test))

from conftest import FakeKubeHandler  # noqa: E402
from fixtures import build_discovery, build_objects  # noqa: E402

EXAMPLES = """\
  kube-query overview                        # snapshot: problems first
  kube-query ctx ls                          # which context am I on?
  kube-query p l -A                          # all pods, all namespaces
  kube-query p desc web-7f9c6-b              # crashloop diagnosis bundle
  kube-query p logs web-7f9c6-b --previous   # crashed instance logs
  kube-query tree deploy/web                 # Deployment -> ReplicaSet -> Pods
  kube-query ev -A --type Warning --since 2h # cluster warnings
  kube-query sec show regcred --reveal       # decode a secret (explicit opt-in)
  kube-query helm ls -A && kube-query helm show wordpress
  kube-query eso -A                          # ExternalSecret sync status
  kube-query get externalsecrets -A          # CRDs via the generic core
  kube-query api | head -30                  # discovery
  kube-query overview -o md > report.md      # markdown report
"""


def main() -> int:
    sys.stdout.reconfigure(line_buffering=True)  # usable when piped/backgrounded
    FakeKubeHandler.objects = build_objects()
    FakeKubeHandler.discovery = build_discovery()
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeKubeHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    kubeconfig = Path(tempfile.mkdtemp(prefix="kube-query-demo-")) / "kubeconfig"
    kubeconfig.write_text(
        yaml.safe_dump(
            {
                "apiVersion": "v1",
                "kind": "Config",
                "clusters": [{"name": "fake", "cluster": {"server": f"http://127.0.0.1:{server.server_port}"}}],
                "contexts": [
                    {"name": "fake", "context": {"cluster": "fake", "user": "fake", "namespace": "default"}},
                    {"name": "fake-prod", "context": {"cluster": "fake", "user": "fake", "namespace": "prod"}},
                ],
                "current-context": "fake",
                "users": [{"name": "fake", "user": {"token": "demo"}}],
            }
        )
    )

    print(f"kube-query demo — fake Kubernetes API on 127.0.0.1:{server.server_port}")
    print()
    print("In another terminal (or set it in this shell):")
    print(f"  export KUBECONFIG={kubeconfig}")
    print()
    print("Try:")
    print(EXAMPLES)
    print("Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
