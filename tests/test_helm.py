"""Helm release payload decoding unit tests (handcrafted protobuf)."""

from __future__ import annotations

import base64
import gzip
import json

from fixtures import helm3_release_secret, pb_msg, pb_str
from kube_query.helm import (
    _payload,
    extract_chart_meta,
    extract_values,
    parse_release_secret,
)


def test_extract_chart_meta_and_values():
    chart_meta = pb_str(1, "wordpress") + pb_str(4, "15.2.1") + pb_str(9, "6.1.1")
    config = pb_str(1, json.dumps({"replicaCount": 2, "blogName": "dev"}))
    release = pb_msg(2, chart_meta) + pb_msg(3, config) + pb_str(5, "default")

    meta = extract_chart_meta(release)
    assert meta == {"name": "wordpress", "version": "15.2.1", "appVersion": "6.1.1"}

    values = extract_values(release)
    assert values == {"replicaCount": 2, "blogName": "dev"}


def test_extract_values_prefers_release_config_over_chart_defaults():
    chart_defaults = pb_str(1, json.dumps({"replicaCount": 1, "defaultsOnly": True}))
    user_values = pb_str(1, json.dumps({"replicaCount": 5}))
    chart_meta = pb_str(1, "app") + pb_str(4, "1.0.0")
    # chart message (field 2) embeds its own defaults; release config (field 3) wins
    chart = pb_msg(1, chart_meta) + pb_msg(9, chart_defaults)
    release = pb_msg(2, chart) + pb_msg(3, user_values)
    assert extract_values(release) == {"replicaCount": 5}


def test_parse_release_secret_helm3():
    secret = helm3_release_secret(
        "wordpress",
        2,
        "deployed",
        "default",
        {"name": "wordpress", "version": "15.2.1", "appVersion": "6.1.1"},
        {"replicaCount": 2},
    )
    rel = parse_release_secret(secret)
    assert rel["name"] == "wordpress"
    assert rel["namespace"] == "default"
    assert rel["revision"] == 2
    assert rel["status"] == "deployed"
    assert rel["chart"] == {"name": "wordpress", "version": "15.2.1", "appVersion": "6.1.1"}
    assert rel["values"] == {"replicaCount": 2}


def test_parse_release_secret_helm2_json():
    doc = {
        "name": "legacy",
        "chart": {"name": "leg", "version": "0.1.0", "appVersion": "1.0"},
        "config": {"a": 1},
    }
    payload = gzip.compress(json.dumps(doc).encode())
    secret = {
        "metadata": {
            "name": "sh.helm.release.v1.legacy.v3",
            "namespace": "prod",
            "creationTimestamp": "2026-10-01T00:00:00Z",
            "labels": {"owner": "helm", "name": "legacy", "status": "deployed", "version": "3"},
        },
        "data": {"release": base64.b64encode(payload).decode()},
    }
    rel = parse_release_secret(secret)
    assert rel["name"] == "legacy"
    assert rel["revision"] == 3
    assert rel["chart"]["name"] == "leg"
    assert rel["values"] == {"a": 1}


def test_undecodable_payload_still_lists():
    secret = {
        "metadata": {
            "name": "sh.helm.release.v1.weird.v1",
            "namespace": "default",
            "creationTimestamp": "2026-10-01T00:00:00Z",
            "labels": {"owner": "helm", "name": "weird", "status": "failed", "version": "1"},
        },
        "data": {"release": base64.b64encode(b"not-gzip-not-proto").decode()},
    }
    rel = parse_release_secret(secret)
    assert rel["name"] == "weird"
    assert rel["status"] == "failed"
    assert "chart" not in rel
    assert "values" not in rel


def test_payload_gunzip():
    secret = helm3_release_secret("x", 1, "deployed", "default", {"name": "x", "version": "1.0.0"}, {})
    blob = _payload(secret)
    assert blob is not None and blob[:1] != b"\x1f"  # already gunzipped protobuf
