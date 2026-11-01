"""Output compaction: strip agent-irrelevant noise from Kubernetes objects.

Verbosity levels::

    0  (default)  drop managedFields, uid, resourceVersion, generation,
                  selfLink, noisy annotations, and all empty values
    1  (-v)       drop managedFields and noisy annotations only
    2  (-vv)      raw object, nothing is stripped
"""

from __future__ import annotations

import base64

NOISY_META = ("managedFields", "selfLink", "resourceVersion", "uid", "generation")
NOISY_ANNOTATIONS = (
    "kubectl.kubernetes.io/last-applied-configuration",
    "deployment.kubernetes.io/revision",
    "deprecated.daemonset.template.generation",
)
_EMPTY = ("", {}, [], None)


def compact(obj: dict | list, verbose: int = 0) -> dict | list:
    if verbose >= 2:
        return obj
    obj = _strip_noisy(obj)
    if verbose == 0:
        obj = _drop_empty(obj)
    return obj


def _strip_noisy(node):
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k == "metadata" and isinstance(v, dict):
                v = {mk: mv for mk, mv in v.items() if mk != "managedFields"}
                ann = v.get("annotations")
                if isinstance(ann, dict):
                    ann = {a: b for a, b in ann.items() if a not in NOISY_ANNOTATIONS}
                    if ann:
                        v["annotations"] = ann
                    else:
                        v.pop("annotations", None)
                out[k] = _strip_noisy(v)
                continue
            out[k] = _strip_noisy(v)
        return out
    if isinstance(node, list):
        return [_strip_noisy(x) for x in node]
    return node


def _drop_empty(node):
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k == "metadata" and isinstance(v, dict):
                v = {mk: mv for mk, mv in v.items() if mk not in NOISY_META}
            v = _drop_empty(v)
            if v in _EMPTY:
                continue
            out[k] = v
        return out
    if isinstance(node, list):
        return [_drop_empty(x) for x in node]
    return node


# -- display helpers for ConfigMaps / Secrets ------------------------------


def cap_map_values(obj: dict, limit: int = 2000) -> dict:
    """Cap long string values in data maps (ConfigMap display) in place."""
    for key in ("data", "stringData", "binaryData"):
        m = obj.get(key)
        if not isinstance(m, dict):
            continue
        for k, v in list(m.items()):
            if isinstance(v, str) and len(v) > limit:
                m[k] = v[:limit] + f" ...[truncated {len(v) - limit} of {len(v)} chars; -v to see full]"
    return obj


def redact_map_values(obj: dict) -> dict:
    """Hide secret values in place; keys and sizes stay visible."""
    for key in ("data", "stringData", "binaryData"):
        m = obj.get(key)
        if not isinstance(m, dict):
            continue
        obj[key] = {k: (f"<{len(v)} chars hidden -- use --reveal>" if isinstance(v, str) else v) for k, v in m.items()}
    return obj


def reveal_map_values(obj: dict) -> dict:
    """Base64-decode secret data values in place (binary values stay encoded)."""
    m = obj.get("data")
    if isinstance(m, dict):
        out = {}
        for k, v in m.items():
            if not isinstance(v, str):
                out[k] = v
                continue
            try:
                raw = base64.b64decode(v)
            except Exception:
                out[k] = v
                continue
            try:
                out[k] = raw.decode("utf-8")
            except UnicodeDecodeError:
                out[k] = f"<{len(raw)} bytes binary; base64: {v[:100]}>"
        obj["data"] = out
    return obj
