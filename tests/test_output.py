"""Output-layer unit tests: format resolution, YAML/JSON/markdown rendering."""

from __future__ import annotations

import datetime

import pytest

from kube_query.errors import KqError
from kube_query.output import as_json, as_yaml, md_table, resolve_format


def test_resolve_format_defaults(monkeypatch):
    monkeypatch.delenv("KQ_OUTPUT", raising=False)
    assert resolve_format(None) == "yaml"
    assert resolve_format("json") == "json"
    assert resolve_format("RICH") == "rich"


def test_resolve_format_env(monkeypatch):
    monkeypatch.setenv("KQ_OUTPUT", "md")
    assert resolve_format(None) == "md"
    assert resolve_format("json") == "json"  # explicit beats env


def test_resolve_format_rejects_garbage(monkeypatch):
    monkeypatch.delenv("KQ_OUTPUT", raising=False)
    with pytest.raises(KqError):
        resolve_format("xml")


def test_as_yaml_handles_datetime_and_order():
    doc = {"z": 1, "a": datetime.datetime(2026, 11, 1, 12, 0, 0), "nested": {"k": ["v", 2]}}
    text = as_yaml(doc)
    assert text.index("z: 1") < text.index("a: '2026-11-01T12:00:00'")  # key order preserved; timestamp stays a string
    assert "- v" in text


def test_as_json():
    assert json_ok(as_json({"a": [1, 2]}))


def json_ok(s):
    import json

    json.loads(s)
    return True


def test_md_table_escapes_pipes_and_newlines():
    rows = [{"M": "has | pipe", "X": "line1\nline2"}]
    text = md_table(["M", "X"], rows)
    assert "has \\| pipe" in text
    assert "line1 line2" in text
    assert text.count("|") >= 6
