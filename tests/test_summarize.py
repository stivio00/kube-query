"""Status/health/age computation unit tests."""

from __future__ import annotations

import pytest

from kube_query.errors import KqError
from kube_query.summarize import (
    age,
    deployment_brief,
    deployment_is_healthy,
    node_status,
    parse_since,
    parse_ts,
    pod_is_healthy,
    pod_ready_ratio,
    pod_restarts,
    pod_status,
)


def pod(phase, container_status):
    return {
        "spec": {"containers": [{"name": "app"}]},
        "status": {"phase": phase, "containerStatuses": [container_status]},
    }


RUNNING_READY = pod("Running", {"name": "app", "ready": True, "restartCount": 0, "state": {"running": {}}})
CRASHLOOP = pod(
    "Running", {"name": "app", "ready": False, "restartCount": 7, "state": {"waiting": {"reason": "CrashLoopBackOff"}}}
)
PENDING = pod(
    "Pending", {"name": "app", "ready": False, "restartCount": 0, "state": {"waiting": {"reason": "ContainerCreating"}}}
)
SUCCEEDED = pod(
    "Succeeded", {"name": "app", "ready": False, "restartCount": 0, "state": {"terminated": {"reason": "Completed"}}}
)


def test_pod_status():
    assert pod_status(RUNNING_READY) == "Running"
    assert pod_status(CRASHLOOP) == "CrashLoopBackOff"
    assert pod_status(PENDING) == "ContainerCreating"
    assert pod_status(SUCCEEDED) == "Completed"
    assert (
        pod_status(pod("Failed", {"name": "app", "ready": False, "restartCount": 1, "state": {"terminated": {}}}))
        == "Error"
    )


def test_pod_health():
    assert pod_is_healthy(RUNNING_READY)
    assert pod_is_healthy(SUCCEEDED)
    assert not pod_is_healthy(CRASHLOOP)
    assert not pod_is_healthy(PENDING)


def test_pod_ready_and_restarts():
    assert pod_ready_ratio(RUNNING_READY) == "1/1"
    assert pod_ready_ratio(CRASHLOOP) == "0/1"
    assert pod_restarts(CRASHLOOP) == 7
    two = {
        "spec": {"containers": [{"name": "a"}, {"name": "b"}]},
        "status": {
            "phase": "Running",
            "containerStatuses": [
                {"name": "a", "ready": True, "restartCount": 0, "state": {"running": {}}},
                {"name": "b", "ready": False, "restartCount": 2, "state": {"waiting": {"reason": "CrashLoopBackOff"}}},
            ],
        },
    }
    assert pod_ready_ratio(two) == "1/2"
    assert pod_restarts(two) == 2


DEP_UNHEALTHY = {
    "spec": {"replicas": 3},
    "status": {
        "readyReplicas": 1,
        "updatedReplicas": 3,
        "availableReplicas": 1,
        "unavailableReplicas": 2,
        "conditions": [{"type": "Available", "status": "False"}],
    },
}
DEP_OK = {"spec": {"replicas": 2}, "status": {"readyReplicas": 2, "updatedReplicas": 2, "availableReplicas": 2}}


def test_deployment_health():
    assert not deployment_is_healthy(DEP_UNHEALTHY)
    assert deployment_is_healthy(DEP_OK)
    assert deployment_brief(DEP_UNHEALTHY) == {"desired": 3, "ready": 1, "updated": 3, "available": 1, "unavailable": 2}


def test_node_status():
    ready = {"status": {"conditions": [{"type": "Ready", "status": "True"}]}}
    bad = {"status": {"conditions": [{"type": "Ready", "status": "False"}, {"type": "DiskPressure", "status": "True"}]}}
    assert node_status(ready) == ("Ready", [])
    assert node_status(bad) == ("NotReady", ["DiskPressure"])


def test_parse_ts_and_age():
    ts = parse_ts("2026-10-31T10:00:00Z")
    assert ts is not None and ts.year == 2026
    assert parse_ts("garbage") is None
    a = age("1970-01-01T00:00:00Z")
    assert a.endswith(("d", "w", "mo"))


def test_parse_since():
    from datetime import timedelta

    assert parse_since("30s") == timedelta(seconds=30)
    assert parse_since("2h") == timedelta(hours=2)
    assert parse_since("3d") == timedelta(days=3)
    assert parse_since("45") == timedelta(seconds=45)
    with pytest.raises(KqError):
        parse_since("nope")


# -- CRD / unknown-kind status -------------------------------------------------


def test_generic_status_conditions_and_phase():
    from kube_query.summarize import generic_status

    ready = {"status": {"conditions": [{"type": "Other", "status": "True"}, {"type": "Ready", "status": "False"}]}}
    assert generic_status(ready) == "False"  # Ready wins over condition order
    established = {"status": {"conditions": [{"type": "Established", "status": "True"}]}}
    assert generic_status(established) == "True"
    only_other = {"status": {"conditions": [{"type": "Pending", "status": "True"}]}}
    assert generic_status(only_other) == "Pending=True"
    phase = {"status": {"phase": "Running"}}
    assert generic_status(phase) == "Running"
    assert generic_status({"spec": {}}) == ""


def test_drop_empty_columns():
    from kube_query.commands._impl import drop_empty_columns

    headers, _rows = drop_empty_columns(
        ["NAME", "STATUS", "AGE"],
        [{"NAME": "a", "STATUS": "", "AGE": "1d"}, {"NAME": "b", "STATUS": "", "AGE": "2d"}],
    )
    assert headers == ["NAME", "AGE"]
    headers, _rows = drop_empty_columns(
        ["NAME", "STATUS"],
        [{"NAME": "a", "STATUS": "True"}],
    )
    assert headers == ["NAME", "STATUS"]
