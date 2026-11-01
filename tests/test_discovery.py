"""Discovery + resolution unit tests (no HTTP)."""

from __future__ import annotations

import pytest

from kube_query.config import Ctx
from kube_query.discovery import ApiResource, parse_target, resolve
from kube_query.errors import KqError


def make_ctx(entries):
    ctx = Ctx()
    ctx.resources = entries  # pre-seed the discovery cache
    return ctx


ENTRIES = [
    ApiResource(
        api_version="v1",
        group="",
        version="v1",
        plural="pods",
        singular="pod",
        kind="Pod",
        namespaced=True,
        short_names=("po",),
    ),
    ApiResource(
        api_version="v1", group="", version="v1", plural="events", singular="event", kind="Event", namespaced=True
    ),
    ApiResource(
        api_version="v1",
        group="",
        version="v1",
        plural="nodes",
        singular="node",
        kind="Node",
        namespaced=False,
        short_names=("no",),
    ),
    ApiResource(
        api_version="apps/v1",
        group="apps",
        version="v1",
        plural="deployments",
        singular="deployment",
        kind="Deployment",
        namespaced=True,
        short_names=("deploy",),
    ),
    ApiResource(
        api_version="batch/v1",
        group="batch",
        version="v1",
        plural="cronjobs",
        singular="cronjob",
        kind="CronJob",
        namespaced=True,
        short_names=("cj",),
    ),
    ApiResource(
        api_version="events.k8s.io/v1",
        group="events.k8s.io",
        version="v1",
        plural="events",
        singular="event",
        kind="Event",
        namespaced=True,
    ),
    ApiResource(
        api_version="external-secrets.io/v1beta1",
        group="external-secrets.io",
        version="v1beta1",
        plural="externalsecrets",
        singular="externalsecret",
        kind="ExternalSecret",
        namespaced=True,
    ),
]


@pytest.mark.parametrize(
    "name,expected_plural,expected_group",
    [
        ("pods", "pods", ""),
        ("pod", "pods", ""),
        ("Pod", "pods", ""),
        ("PODS", "pods", ""),
        ("po", "pods", ""),
        ("deployments", "deployments", "apps"),
        ("deployment", "deployments", "apps"),
        ("Deployment", "deployments", "apps"),
        ("deploy", "deployments", "apps"),
        ("deployments.apps", "deployments", "apps"),
        ("events", "events", ""),  # core preferred over events.k8s.io
        ("externalsecrets", "externalsecrets", "external-secrets.io"),
    ],
)
def test_resolve_common_forms(name, expected_plural, expected_group):
    entry = resolve(make_ctx(ENTRIES), name)
    assert entry.plural == expected_plural
    assert entry.group == expected_group


def test_resolve_with_api_version():
    entry = resolve(make_ctx(ENTRIES), "events", api_version="events.k8s.io/v1")
    assert entry.group == "events.k8s.io"


def test_resolve_unknown_gives_suggestions():
    with pytest.raises(KqError) as ei:
        resolve(make_ctx(ENTRIES), "podz")
    msg = str(ei.value.message)
    assert "unknown resource type 'podz'" in msg
    assert "pods" in msg
    assert "kube-query api" in msg


def test_resolve_bad_api_version():
    with pytest.raises(KqError):
        resolve(make_ctx(ENTRIES), "pods", api_version="apps/v9")


@pytest.mark.parametrize(
    "resource,name,expected",
    [
        ("pods", None, (None, "pods", None)),
        ("deploy/web", None, (None, "deploy", "web")),
        ("apps/v1/deployments", None, ("apps/v1", "deployments", None)),
        ("apps/v1/deployments/web", None, ("apps/v1", "deployments", "web")),
        ("deployments", "web", (None, "deployments", "web")),
    ],
)
def test_parse_target(resource, name, expected):
    assert parse_target(resource, name) == expected
