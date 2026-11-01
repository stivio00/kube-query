"""Helm release discovery — read-only, decoded from Helm's release Secrets.

Helm 3 stores releases as Secrets named ``sh.helm.release.v1.<name>.v<rev>``
with labels ``owner=helm, name=<release>, status=<status>, version=<rev>``
and a ``data.release`` payload of base64(gzip(protobuf)).

kube-query never talks to Tiller/the helm binary; everything here is plain
API reads plus a best-effort protobuf walk for chart metadata and values.
"""

from __future__ import annotations

import base64
import gzip
import json
import re

from .access import list_objects
from .discovery import resolve
from .errors import KqError
from .summarize import age, dig

HELM_SELECTOR = "owner=helm"
_SECRET_NAME_RE = re.compile(r"^sh\.helm\.release\.v\d+\.(.+)\.v(\d+)$")
_SEMVER = re.compile(r"^\d+(\.\d+){0,3}([-+][\w.\-+]*)?$")


# -- payload decoding ---------------------------------------------------------


def _payload(secret: dict) -> bytes | None:
    raw = dig(secret, "data", "release") or {}
    if not isinstance(raw, str) or not raw:
        return None
    try:
        blob = base64.b64decode(raw)
    except Exception:
        return None
    if blob[:2] == b"\x1f\x8b":
        try:
            blob = gzip.decompress(blob)
        except Exception:
            return None
    return blob


def _read_varint(buf: bytes, i: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        if i >= len(buf):
            raise ValueError("truncated varint")
        b = buf[i]
        i += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, i
        shift += 7
        if shift > 63:
            raise ValueError("varint too long")


def _fields(buf: bytes) -> list[tuple[int, int, object]]:
    """Parse a protobuf message into (field_number, wire_type, value) triples."""
    out, i, n = [], 0, len(buf)
    while i < n:
        try:
            key, i = _read_varint(buf, i)
        except ValueError:
            break
        field, wire = key >> 3, key & 7
        try:
            if wire == 0:
                v, i = _read_varint(buf, i)
                out.append((field, wire, v))
            elif wire == 2:
                ln, i = _read_varint(buf, i)
                if i + ln > n:
                    break
                out.append((field, wire, buf[i : i + ln]))
                i += ln
            elif wire == 5:
                out.append((field, wire, buf[i : i + 4]))
                i += 4
            elif wire == 1:
                out.append((field, wire, buf[i : i + 8]))
                i += 8
            else:
                break
        except ValueError:
            break
    return out


def _is_text(b) -> str | None:
    try:
        s = b.decode("utf-8")
    except (UnicodeDecodeError, AttributeError):
        return None
    if not s or not all(ch.isprintable() or ch in "\n\r\t" for ch in s):
        return None
    return s


def _looks_like_chart_meta(buf: bytes) -> dict | None:
    """ChartMeta heuristic: printable field-1 + semver-ish field-4 (+ appVersion field-9)."""
    fields = _fields(buf)
    f1 = next((v for f, w, v in fields if f == 1 and w == 2), None)
    f4 = next((v for f, w, v in fields if f == 4 and w == 2), None)
    if f1 is None or f4 is None:
        return None
    name, ver = _is_text(f1), _is_text(f4)
    if not name or not ver or " " in name or not _SEMVER.match(ver.strip()):
        return None
    meta = {"name": name, "version": ver.strip()}
    f9 = next((v for f, w, v in fields if f == 9 and w == 2), None)
    if f9 is not None:
        t = _is_text(f9)
        if t:
            meta["appVersion"] = t
    return meta


def extract_chart_meta(payload: bytes) -> dict | None:
    """Walk the release protobuf for a ChartMeta-like submessage."""
    found: list[tuple[int, dict]] = []

    def walk(buf: bytes, depth: int) -> None:
        if depth > 3:
            return
        for _field, wire, val in _fields(buf):
            if wire != 2 or not isinstance(val, bytes):
                continue
            meta = _looks_like_chart_meta(val)
            if meta:
                found.append((depth, meta))
            walk(val, depth + 1)

    walk(payload, 0)
    if not found:
        return None
    found.sort(key=lambda x: x[0])  # shallowest = most likely the real ChartMeta
    return found[0][1]


def extract_values(payload: bytes) -> dict | None:
    """User-supplied values: a Config message whose field-1 raw bytes are JSON.

    Prefers the top-level Release.config (field 3) over chart defaults.
    """
    candidates: list[tuple[int, dict]] = []
    for field, wire, val in _fields(payload):
        if wire != 2 or not isinstance(val, bytes):
            continue
        for f, w, v in _fields(val):
            if f == 1 and w == 2 and isinstance(v, bytes):
                txt = _is_text(v)
                if txt and txt.lstrip()[:1] == "{":
                    try:
                        data = json.loads(txt)
                    except Exception:
                        continue
                    if isinstance(data, dict):
                        candidates.append((field, data))
    if not candidates:
        return None
    for f, data in candidates:
        if f == 3:  # Release.config — the effective user values
            return data
    return candidates[-1][1]


# -- release model ---------------------------------------------------------------


def parse_release_secret(secret: dict) -> dict:
    labels = dig(secret, "metadata", "labels", default={}) or {}
    sname = dig(secret, "metadata", "name", default="") or ""
    m = _SECRET_NAME_RE.match(sname)
    name = labels.get("name") or (m.group(1) if m else sname)
    rev = labels.get("version") or (m.group(2) if m else "")
    meta: dict | None = None
    values: dict | None = None
    payload = _payload(secret)
    if payload:
        try:
            doc = json.loads(payload.decode("utf-8"))
            if isinstance(doc, dict):  # helm 2 (JSON payload)
                chart = doc.get("chart") or {}
                meta = {"name": chart.get("name") or "", "version": chart.get("version") or ""}
                if chart.get("appVersion"):
                    meta["appVersion"] = chart["appVersion"]
                cfg = doc.get("config")
                if isinstance(cfg, dict):
                    values = cfg
        except Exception:
            meta = extract_chart_meta(payload)
            values = extract_values(payload)
    out = {
        "name": name,
        "namespace": dig(secret, "metadata", "namespace", default="") or "",
        "revision": int(rev) if str(rev).isdigit() else rev,
        "status": labels.get("status") or "unknown",
        "updated": dig(secret, "metadata", "creationTimestamp", default="") or "",
        "_age": age(dig(secret, "metadata", "creationTimestamp")),
    }
    if meta:
        out["chart"] = meta
    if values:
        out["values"] = values
    return out


def _revision(rel: dict):
    try:
        return int(rel.get("revision") or 0)
    except (TypeError, ValueError):
        return 0


def _is_helm_secret(s: dict) -> bool:
    return dig(s, "metadata", "labels", default={}).get("owner") == "helm"


def list_releases(ctx, *, namespace: str | None = None) -> list[dict]:
    """Latest revision of every Helm release, sorted by (namespace, name)."""
    entry = resolve(ctx, "secrets")
    secrets = list_objects(ctx, entry, namespace=namespace, label_selector=HELM_SELECTOR)
    latest: dict = {}
    for s in secrets:
        if not _is_helm_secret(s):
            continue
        rel = parse_release_secret(s)
        key = (rel["name"], rel["namespace"])
        if key not in latest or _revision(rel) > _revision(latest[key]):
            latest[key] = rel
    return sorted(latest.values(), key=lambda r: (r["namespace"], r["name"]))


def show_release(ctx, name: str, *, namespace: str | None = None) -> dict:
    entry = resolve(ctx, "secrets")
    secrets = list_objects(ctx, entry, namespace=namespace, label_selector=f"{HELM_SELECTOR},name={name}")
    cands = [s for s in secrets if _is_helm_secret(s) and dig(s, "metadata", "labels", default={}).get("name") == name]
    if not cands:
        where = f" in namespace '{namespace}'" if namespace else ""
        raise KqError(
            f"helm release '{name}' not found{where}.\n"
            "  Hint: list releases with 'kq helm ls' (add -A for all namespaces)."
        )
    latest = max(cands, key=lambda s: _revision(parse_release_secret(s)))
    rel = parse_release_secret(latest)
    rel.pop("_age", None)
    rel["revisionsAvailable"] = len({dig(s, "metadata", "name", default="") for s in cands}) and len(cands)
    return rel


def chart_str(rel: dict) -> str:
    meta = rel.get("chart")
    if not meta or not meta.get("name"):
        return "?"
    return f"{meta['name']}-{meta.get('version', '')}"
