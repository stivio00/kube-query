"""Compaction / verbosity / secret- and configmap-display unit tests."""

from __future__ import annotations

from kube_query.cleanup import cap_map_values, compact, redact_map_values, reveal_map_values

OBJ = {
    "apiVersion": "apps/v1",
    "kind": "Deployment",
    "metadata": {
        "name": "web",
        "namespace": "default",
        "uid": "abc-123",
        "resourceVersion": "9876",
        "generation": 4,
        "creationTimestamp": "2026-10-01T00:00:00Z",
        "managedFields": [{"manager": "kubectl"}],
        "annotations": {
            "kubectl.kubernetes.io/last-applied-configuration": '{"big":"json"}',
            "deployment.kubernetes.io/revision": "4",
            "team": "platform",
        },
        "labels": {"app": "web"},
    },
    "spec": {"replicas": 3, "paused": False},
    "status": {"readyReplicas": 3},
}


def test_compact_default():
    out = compact(OBJ, 0)
    m = out["metadata"]
    assert "uid" not in m and "resourceVersion" not in m and "generation" not in m
    assert "managedFields" not in m
    assert m["annotations"] == {"team": "platform"}
    assert m["labels"] == {"app": "web"}
    assert m["creationTimestamp"] == "2026-10-01T00:00:00Z"
    assert out["spec"] == {"replicas": 3, "paused": False}
    assert out["status"] == {"readyReplicas": 3}


def test_compact_drops_empty_values():
    obj = {"a": None, "b": "", "c": {}, "d": [], "e": 0, "f": False, "g": "x"}
    out = compact(obj, 0)
    assert out == {"e": 0, "f": False, "g": "x"}


def test_compact_v1_keeps_system_metadata():
    out = compact(OBJ, 1)
    m = out["metadata"]
    assert m["uid"] == "abc-123"
    assert m["resourceVersion"] == "9876"
    assert m["generation"] == 4
    assert "managedFields" not in m
    assert m["annotations"] == {"team": "platform"}


def test_compact_v2_raw():
    out = compact(OBJ, 2)
    assert out == OBJ


def test_cap_map_values():
    obj = {"data": {"small": "abc", "big": "x" * 5000}}
    out = cap_map_values(obj)
    assert out["data"]["small"] == "abc"
    assert out["data"]["big"].startswith("x" * 2000)
    assert "truncated" in out["data"]["big"]


def test_redact_and_reveal():
    import base64

    obj = {"data": {"password": base64.b64encode(b"hunter2").decode()}}
    red = redact_map_values({"data": dict(obj["data"])})
    assert "hidden" in red["data"]["password"]
    assert "hunter2" not in red["data"]["password"]
    rev = reveal_map_values({"data": dict(obj["data"])})
    assert rev["data"]["password"] == "hunter2"
