#!/usr/bin/env python3
"""Run kq against a fake Kubernetes API server — try the tool with no cluster.

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
  kq overview                        # snapshot: problems first
  kq ctx ls                          # which context am I on?
  kq p l -A                          # all pods, all namespaces
  kq p desc web-7f9c6-b              # crashloop diagnosis bundle
  kq p logs web-7f9c6-b --previous   # crashed instance logs
  kq tree deploy/web                 # Deployment -> ReplicaSet -> Pods
  kq ev -A --type Warning --since 2h # cluster warnings
  kq sec show regcred --reveal       # decode a secret (explicit opt-in)
  kq helm ls -A && kq helm show wordpress
  kq eso -A                          # ExternalSecret sync status
  kq get externalsecrets -A          # CRDs via the generic core
  kq api | head -30                  # discovery
  kq overview -o md > report.md      # markdown report
"""


def main() -> int:
    sys.stdout.reconfigure(line_buffering=True)  # usable when piped/backgrounded
    FakeKubeHandler.objects = build_objects()
    FakeKubeHandler.discovery = build_discovery()
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeKubeHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    kubeconfig = Path(tempfile.mkdtemp(prefix="kq-demo-")) / "kubeconfig"
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
