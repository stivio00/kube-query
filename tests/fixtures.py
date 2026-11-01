"""Fixture data for the fake Kubernetes API server (tests)."""

from __future__ import annotations

import base64
import gzip
import json
from datetime import UTC, datetime, timedelta


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def now_minus(**kw) -> str:
    return iso(datetime.now(UTC) - timedelta(**kw))


# -- protobuf helpers (for Helm release payloads) --------------------------


def _varint(n: int) -> bytes:
    out = b""
    while True:
        b = n & 0x7F
        n >>= 7
        out += bytes([b | (0x80 if n else 0)])
        if not n:
            return out


def _tag(field: int, wire: int) -> bytes:
    return _varint((field << 3) | wire)


def pb_str(field: int, s: str) -> bytes:
    b = s.encode()
    return _tag(field, 2) + _varint(len(b)) + b


def pb_msg(field: int, b: bytes) -> bytes:
    return _tag(field, 2) + _varint(len(b)) + b


def helm3_release_secret(name: str, revision: int, status: str, ns: str, chart: dict, values: dict) -> dict:
    """Build a Helm-3-style release Secret with a protobuf payload."""
    chart_meta = pb_str(1, chart["name"]) + pb_str(4, chart["version"]) + pb_str(9, chart.get("appVersion", ""))
    config = pb_str(1, json.dumps(values))
    release = pb_msg(2, chart_meta) + pb_msg(3, config) + pb_str(5, ns)
    payload = base64.b64encode(gzip.compress(release)).decode()
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": f"sh.helm.release.v1.{name}.v{revision}",
            "namespace": ns,
            "creationTimestamp": now_minus(hours=3),
            "labels": {"owner": "helm", "name": name, "status": status, "version": str(revision)},
        },
        "type": "helm.sh/release.v1",
        "data": {"release": payload},
    }


# -- objects ------------------------------------------------------------------


def build_objects() -> dict:
    pods = [
        {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": "web-7f9c6-a",
                "namespace": "default",
                "uid": "uid-pod-a",
                "creationTimestamp": "2026-10-31T10:00:00Z",
                "labels": {"app": "web"},
                "ownerReferences": [
                    {"apiVersion": "apps/v1", "kind": "ReplicaSet", "name": "web-7f9c6", "uid": "uid-rs-web"}
                ],
            },
            "spec": {"nodeName": "node-1", "containers": [{"name": "app", "image": "nginx:1.27"}]},
            "status": {
                "phase": "Running",
                "podIP": "10.42.0.11",
                "conditions": [{"type": "Ready", "status": "True"}],
                "containerStatuses": [
                    {
                        "name": "app",
                        "ready": True,
                        "restartCount": 0,
                        "state": {"running": {"startedAt": "2026-10-31T10:00:05Z"}},
                    }
                ],
            },
        },
        {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": "web-7f9c6-b",
                "namespace": "default",
                "uid": "uid-pod-b",
                "creationTimestamp": "2026-10-31T10:00:00Z",
                "labels": {"app": "web"},
                "ownerReferences": [
                    {"apiVersion": "apps/v1", "kind": "ReplicaSet", "name": "web-7f9c6", "uid": "uid-rs-web"}
                ],
            },
            "spec": {"nodeName": "node-1", "containers": [{"name": "app", "image": "nginx:1.27"}]},
            "status": {
                "phase": "Running",
                "podIP": "10.42.0.12",
                "containerStatuses": [
                    {
                        "name": "app",
                        "ready": False,
                        "restartCount": 7,
                        "state": {
                            "waiting": {
                                "reason": "CrashLoopBackOff",
                                "message": "back-off 5m0s restarting failed container",
                            }
                        },
                        "lastState": {"terminated": {"reason": "Error", "exitCode": 1}},
                    }
                ],
            },
        },
        {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": "web-7f9c6-c",
                "namespace": "default",
                "uid": "uid-pod-c",
                "creationTimestamp": now_minus(minutes=2),
                "labels": {"app": "web"},
                "ownerReferences": [
                    {"apiVersion": "apps/v1", "kind": "ReplicaSet", "name": "web-7f9c6", "uid": "uid-rs-web"}
                ],
            },
            "spec": {"nodeName": "node-1", "containers": [{"name": "app", "image": "nginx:1.27"}]},
            "status": {
                "phase": "Pending",
                "containerStatuses": [
                    {
                        "name": "app",
                        "ready": False,
                        "restartCount": 0,
                        "state": {"waiting": {"reason": "ContainerCreating"}},
                    }
                ],
            },
        },
        {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": "api-6d4d9",
                "namespace": "prod",
                "uid": "uid-pod-api",
                "creationTimestamp": "2026-10-20T08:00:00Z",
                "ownerReferences": [{"kind": "ReplicaSet", "name": "api-6d4d9", "uid": "uid-rs-api"}],
            },
            "spec": {"nodeName": "node-1", "containers": [{"name": "api", "image": "api:2.4"}]},
            "status": {
                "phase": "Running",
                "containerStatuses": [{"name": "api", "ready": True, "restartCount": 0, "state": {"running": {}}}],
            },
        },
        {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": "db-0",
                "namespace": "prod",
                "uid": "uid-pod-db",
                "creationTimestamp": "2026-10-25T08:00:00Z",
            },
            "spec": {"containers": [{"name": "db", "image": "postgres:16"}]},
            "status": {
                "phase": "Succeeded",
                "containerStatuses": [
                    {"name": "db", "ready": False, "restartCount": 0, "state": {"terminated": {"reason": "Completed"}}}
                ],
            },
        },
        {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": "coredns-5d78",
                "namespace": "kube-system",
                "uid": "uid-pod-coredns",
                "creationTimestamp": "2026-09-01T00:00:00Z",
            },
            "spec": {"nodeName": "node-2", "containers": [{"name": "coredns", "image": "coredns:1.11"}]},
            "status": {
                "phase": "Running",
                "containerStatuses": [{"name": "coredns", "ready": True, "restartCount": 0, "state": {"running": {}}}],
            },
        },
    ]

    replicasets = [
        {
            "apiVersion": "apps/v1",
            "kind": "ReplicaSet",
            "metadata": {
                "name": "web-7f9c6",
                "namespace": "default",
                "uid": "uid-rs-web",
                "creationTimestamp": "2026-10-31T09:59:00Z",
                "ownerReferences": [
                    {"apiVersion": "apps/v1", "kind": "Deployment", "name": "web", "uid": "uid-deploy-web"}
                ],
            },
            "spec": {"replicas": 3},
            "status": {"replicas": 3, "readyReplicas": 2},
        },
        {
            "apiVersion": "apps/v1",
            "kind": "ReplicaSet",
            "metadata": {
                "name": "api-6d4d9",
                "namespace": "prod",
                "uid": "uid-rs-api",
                "creationTimestamp": "2026-10-20T07:55:00Z",
            },
            "spec": {"replicas": 1},
            "status": {"replicas": 1, "readyReplicas": 1},
        },
    ]

    deployments = [
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": "web",
                "namespace": "default",
                "uid": "uid-deploy-web",
                "creationTimestamp": "2026-10-31T09:58:00Z",
            },
            "spec": {"replicas": 3, "strategy": {"type": "RollingUpdate"}},
            "status": {
                "replicas": 3,
                "readyReplicas": 1,
                "updatedReplicas": 3,
                "availableReplicas": 1,
                "unavailableReplicas": 2,
                "conditions": [
                    {
                        "type": "Available",
                        "status": "False",
                        "reason": "MinimumReplicasUnavailable",
                        "message": "Deployment does not have minimum availability.",
                    },
                    {
                        "type": "Progressing",
                        "status": "True",
                        "reason": "ReplicaSetUpdated",
                        "message": "ReplicaSet web-7f9c6 is progressing.",
                    },
                ],
            },
        },
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": "api",
                "namespace": "prod",
                "uid": "uid-deploy-api",
                "creationTimestamp": "2026-10-20T07:50:00Z",
            },
            "spec": {"replicas": 1},
            "status": {
                "replicas": 1,
                "readyReplicas": 1,
                "updatedReplicas": 1,
                "availableReplicas": 1,
                "conditions": [{"type": "Available", "status": "True"}],
            },
        },
    ]

    nodes = [
        {
            "apiVersion": "v1",
            "kind": "Node",
            "metadata": {
                "name": "node-1",
                "uid": "uid-node-1",
                "creationTimestamp": "2026-09-01T00:00:00Z",
                "labels": {"node-role.kubernetes.io/control-plane": ""},
            },
            "status": {
                "conditions": [{"type": "Ready", "status": "True"}],
                "nodeInfo": {"kubeletVersion": "v1.31.1"},
            },
        },
        {
            "apiVersion": "v1",
            "kind": "Node",
            "metadata": {"name": "node-2", "uid": "uid-node-2", "creationTimestamp": "2026-09-01T00:00:00Z"},
            "status": {
                "conditions": [{"type": "Ready", "status": "False"}, {"type": "DiskPressure", "status": "True"}],
                "nodeInfo": {"kubeletVersion": "v1.31.1"},
            },
        },
    ]

    namespaces = [
        {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {"name": "default", "uid": "uid-ns-default", "creationTimestamp": "2026-09-01T00:00:00Z"},
            "status": {"phase": "Active"},
        },
        {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {"name": "prod", "uid": "uid-ns-prod", "creationTimestamp": "2026-09-01T00:00:00Z"},
            "status": {"phase": "Active"},
        },
        {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {
                "name": "kube-system",
                "uid": "uid-ns-kubesystem",
                "creationTimestamp": "2026-09-01T00:00:00Z",
            },
            "status": {"phase": "Active"},
        },
    ]

    events = [
        {
            "apiVersion": "v1",
            "kind": "Event",
            "metadata": {
                "name": "backoff.17abc",
                "namespace": "default",
                "uid": "uid-ev-1",
                "creationTimestamp": now_minus(minutes=5),
            },
            "involvedObject": {"kind": "Pod", "name": "web-7f9c6-b", "namespace": "default", "uid": "uid-pod-b"},
            "reason": "BackOff",
            "type": "Warning",
            "count": 8,
            "message": "Back-off restarting failed container app in pod web-7f9c6-b_default",
            "source": {"component": "kubelet"},
            "lastTimestamp": now_minus(minutes=1),
            "firstTimestamp": now_minus(minutes=40),
        },
        {
            "apiVersion": "v1",
            "kind": "Event",
            "metadata": {
                "name": "pulled.17abd",
                "namespace": "default",
                "uid": "uid-ev-2",
                "creationTimestamp": now_minus(minutes=50),
            },
            "involvedObject": {"kind": "Pod", "name": "web-7f9c6-a", "namespace": "default", "uid": "uid-pod-a"},
            "reason": "Pulled",
            "type": "Normal",
            "count": 1,
            "message": "Container image nginx:1.27 already present on machine",
            "source": {"component": "kubelet"},
            "lastTimestamp": now_minus(minutes=50),
            "firstTimestamp": now_minus(minutes=50),
        },
        {
            "apiVersion": "v1",
            "kind": "Event",
            "metadata": {
                "name": "sched.17abe",
                "namespace": "default",
                "uid": "uid-ev-3",
                "creationTimestamp": now_minus(minutes=2),
            },
            "involvedObject": {"kind": "Pod", "name": "web-7f9c6-c", "namespace": "default", "uid": "uid-pod-c"},
            "reason": "FailedScheduling",
            "type": "Warning",
            "count": 2,
            "message": "0/2 nodes are available: 1 node(s) had untolerated taint, 1 Insufficient memory.",
            "source": {"component": "default-scheduler"},
            "lastTimestamp": now_minus(minutes=2),
            "firstTimestamp": now_minus(minutes=3),
        },
        {
            "apiVersion": "v1",
            "kind": "Event",
            "metadata": {
                "name": "healthy.17abf",
                "namespace": "prod",
                "uid": "uid-ev-4",
                "creationTimestamp": now_minus(hours=10),
            },
            "involvedObject": {"kind": "Deployment", "name": "api", "namespace": "prod", "uid": "uid-deploy-api"},
            "reason": "ScalingReplicaSet",
            "type": "Normal",
            "count": 1,
            "message": "Scaled up replica set api-6d4d9 to 1",
            "source": {"component": "deployment-controller"},
            "lastTimestamp": now_minus(hours=10),
            "firstTimestamp": now_minus(hours=10),
        },
    ]

    secrets = [
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {
                "name": "regcred",
                "namespace": "default",
                "uid": "uid-sec-regcred",
                "creationTimestamp": "2026-10-01T00:00:00Z",
            },
            "type": "kubernetes.io/dockerconfigjson",
            "data": {"password": base64.b64encode(b"hunter2").decode()},
        },
        helm3_release_secret(
            "wordpress",
            1,
            "superseded",
            "default",
            {"name": "wordpress", "version": "15.1.0", "appVersion": "6.0.0"},
            {"replicaCount": 1},
        ),
        helm3_release_secret(
            "wordpress",
            2,
            "deployed",
            "default",
            {"name": "wordpress", "version": "15.2.1", "appVersion": "6.1.1"},
            {"replicaCount": 2, "blogName": "dev"},
        ),
        helm3_release_secret(
            "grafana",
            1,
            "deployed",
            "prod",
            {"name": "grafana", "version": "8.5.0", "appVersion": "11.1.0"},
            {"persistence": {"enabled": False}},
        ),
    ]

    configmaps = [
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": "app-config",
                "namespace": "default",
                "uid": "uid-cm-app",
                "creationTimestamp": "2026-10-01T00:00:00Z",
            },
            "data": {"config.yaml": "key: value\nmode: dev\n", "big.txt": "x" * 5000},
        },
    ]

    services = [
        {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": "web",
                "namespace": "default",
                "uid": "uid-svc-web",
                "creationTimestamp": "2026-10-31T09:58:00Z",
            },
            "spec": {"type": "ClusterIP", "clusterIP": "10.96.7.10", "ports": [{"port": 80, "protocol": "TCP"}]},
        },
    ]

    externalsecrets = [
        {
            "apiVersion": "external-secrets.io/v1beta1",
            "kind": "ExternalSecret",
            "metadata": {
                "name": "my-secret",
                "namespace": "default",
                "uid": "uid-es-1",
                "creationTimestamp": "2026-10-15T00:00:00Z",
            },
            "spec": {
                "secretStoreRef": {"name": "vault", "kind": "SecretStore"},
                "refreshInterval": "1h",
                "target": {"name": "target-secret"},
            },
            "status": {
                "conditions": [
                    {"type": "Ready", "status": "True", "reason": "SecretSynced", "message": "Secret was synced"}
                ]
            },
        },
        {
            "apiVersion": "external-secrets.io/v1beta1",
            "kind": "ExternalSecret",
            "metadata": {
                "name": "broken-es",
                "namespace": "default",
                "uid": "uid-es-2",
                "creationTimestamp": now_minus(minutes=30),
            },
            "spec": {
                "secretStoreRef": {"name": "vault", "kind": "SecretStore"},
                "refreshInterval": "1h",
                "target": {"name": "broken-target"},
            },
            "status": {
                "conditions": [
                    {
                        "type": "Ready",
                        "status": "False",
                        "reason": "StoreError",
                        "message": "could not get secret: connection refused",
                    }
                ]
            },
        },
    ]

    secretstores = [
        {
            "apiVersion": "external-secrets.io/v1beta1",
            "kind": "SecretStore",
            "metadata": {
                "name": "vault",
                "namespace": "default",
                "uid": "uid-ss-1",
                "creationTimestamp": "2026-10-15T00:00:00Z",
            },
            "spec": {"provider": {"vault": {"server": "https://vault:8200"}}},
            "status": {"conditions": [{"type": "Ready", "status": "True", "reason": "ValidStore"}]},
        },
    ]

    clustersecretstores = [
        {
            "apiVersion": "external-secrets.io/v1beta1",
            "kind": "ClusterSecretStore",
            "metadata": {"name": "cluster-vault", "uid": "uid-css-1", "creationTimestamp": "2026-10-15T00:00:00Z"},
            "spec": {"provider": {"vault": {"server": "https://vault:8200"}}},
            "status": {"conditions": [{"type": "Ready", "status": "False", "reason": "InvalidStore"}]},
        },
    ]

    return {
        "pods": pods,
        "replicasets": replicasets,
        "deployments": deployments,
        "nodes": nodes,
        "namespaces": namespaces,
        "events": events,
        "secrets": secrets,
        "configmaps": configmaps,
        "services": services,
        "externalsecrets": externalsecrets,
        "secretstores": secretstores,
        "clustersecretstores": clustersecretstores,
    }


def build_discovery() -> dict:
    def res(name, kind, namespaced, singular="", short=None, verbs=None):
        r = {"name": name, "kind": kind, "namespaced": namespaced, "verbs": verbs or ["get", "list"]}
        if singular:
            r["singularName"] = singular
        if short:
            r["shortNames"] = short
        return r

    core_v1 = {
        "kind": "APIResourceList",
        "groupVersion": "v1",
        "resources": [
            res("pods", "Pod", True, "pod", ["po"]),
            res("pods/log", "Pod", True),  # subresource; must be skipped
            res("namespaces", "Namespace", False, "namespace", ["ns"]),
            res("nodes", "Node", False, "node", ["no"]),
            res("secrets", "Secret", True, "secret"),
            res("configmaps", "ConfigMap", True, "configmap", ["cm"]),
            res("events", "Event", True, "event", ["ev"]),
            res("services", "Service", True, "service", ["svc"]),
            res("persistentvolumeclaims", "PersistentVolumeClaim", True, "persistentvolumeclaim", ["pvc"]),
        ],
    }
    apps_v1 = {
        "kind": "APIResourceList",
        "groupVersion": "apps/v1",
        "resources": [
            res("deployments", "Deployment", True, "deployment", ["deploy"]),
            res("replicasets", "ReplicaSet", True, "replicaset", ["rs"]),
            res("statefulsets", "StatefulSet", True, "statefulset", ["sts"]),
            res("daemonsets", "DaemonSet", True, "daemonset", ["ds"]),
        ],
    }
    eso_v1beta1 = {
        "kind": "APIResourceList",
        "groupVersion": "external-secrets.io/v1beta1",
        "resources": [
            res("externalsecrets", "ExternalSecret", True, "externalsecret", ["es"]),
            res("secretstores", "SecretStore", True, "secretstore"),
            res("clustersecretstores", "ClusterSecretStore", False, "clustersecretstore"),
        ],
    }
    return {
        "/api": {"kind": "APIVersions", "versions": ["v1"]},
        "/api/v1": core_v1,
        "/apis": {
            "kind": "APIGroupList",
            "groups": [
                {
                    "name": "apps",
                    "versions": [{"groupVersion": "apps/v1"}],
                    "preferredVersion": {"groupVersion": "apps/v1"},
                },
                {
                    "name": "external-secrets.io",
                    "versions": [{"groupVersion": "external-secrets.io/v1beta1"}],
                    "preferredVersion": {"groupVersion": "external-secrets.io/v1beta1"},
                },
            ],
        },
        "/apis/apps/v1": apps_v1,
        "/apis/external-secrets.io/v1beta1": eso_v1beta1,
        "/version": {"major": "1", "minor": "31", "gitVersion": "v1.31.1", "platform": "linux/arm64"},
    }
