#!/usr/bin/env python3
"""Generate the README screenshots (docs/img/*.svg) from the fake demo cluster.

Drives the real CLI via CliRunner with a recording rich Console and exports
terminal-styled SVGs. No real cluster or real data is involved.

Usage: .venv/bin/python scripts/screenshots.py   (or: make screenshots)
"""

from __future__ import annotations

import io
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import yaml
from click.testing import CliRunner
from rich.console import Console

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

import kube_query.output as kq_output  # noqa: E402
from conftest import FakeKubeHandler  # noqa: E402
from fixtures import build_discovery, build_objects  # noqa: E402
from kube_query.cli import main  # noqa: E402

WIDTH = 112

SHOTS = [
    ("overview.svg", "kube-query — cluster overview", ["overview", "-o", "rich"]),
    ("pods.svg", "kube-query — pods (--show-labels)", ["p", "l", "-A", "--show-labels", "-o", "rich"]),
    ("describe.svg", "kube-query — pod diagnosis", ["p", "desc", "web-7f9c6-b", "-o", "rich"]),
    ("tree.svg", "kube-query — ownership tree", ["tree", "deploy/web"]),
    ("argo.svg", "kube-query — argo applications", ["argo", "-A", "-o", "rich"]),
]


def main_gen() -> int:
    FakeKubeHandler.objects = build_objects()
    FakeKubeHandler.discovery = build_discovery()
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeKubeHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    kubeconfig = Path(tempfile.mkdtemp(prefix="kq-shots-")) / "kubeconfig"
    kubeconfig.write_text(
        yaml.safe_dump(
            {
                "apiVersion": "v1",
                "kind": "Config",
                "clusters": [{"name": "fake", "cluster": {"server": f"http://127.0.0.1:{server.server_port}"}}],
                "contexts": [{"name": "fake", "context": {"cluster": "fake", "user": "fake", "namespace": "default"}}],
                "current-context": "fake",
                "users": [{"name": "fake", "user": {"token": "demo"}}],
            }
        )
    )

    out_dir = ROOT / "docs" / "img"
    out_dir.mkdir(parents=True, exist_ok=True)
    runner = CliRunner()

    for fname, title, args in SHOTS:
        console = Console(file=io.StringIO(), record=True, force_terminal=True, width=WIDTH, highlight=False)
        kq_output._console = console  # pre-seed the CLI's console singleton
        result = runner.invoke(
            main,
            ["--kubeconfig", str(kubeconfig), *args],
            env={"COLUMNS": str(WIDTH)},
        )
        if result.exit_code != 0:
            print(f"FAILED: {' '.join(args)} (exit {result.exit_code})")
            print(result.output)
            return 1
        path = out_dir / fname
        console.save_svg(str(path), title=title)
        print(f"wrote {path.relative_to(ROOT)} ({path.stat().st_size // 1024} KB)")

    server.shutdown()
    print(f"\n{len(SHOTS)} screenshots written to docs/img/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_gen())
