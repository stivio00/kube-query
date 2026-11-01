"""Status/health computation, table columns and describe summaries."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from .errors import KqError


def dig(obj, *path, default=None):
    cur = obj
    for p in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(p)
        if cur is None:
            return default
    return cur


# -- time ------------------------------------------------------------------


def parse_ts(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError:
        return None


def now_utc() -> datetime:
    return datetime.now(UTC)


def age(value, *, now: datetime | None = None) -> str:
    """Humanized age: '45s', '12m', '3h', '5d', '2w', '3mo'."""
    ts = parse_ts(value)
    if not ts:
        return "n/a"
    secs = max(0, ((now or now_utc()) - ts).total_seconds())
    if secs < 60:
        return f"{int(secs)}s"
    if secs < 3600:
        return f"{int(secs // 60)}m"
    if secs < 86400:
        return f"{int(secs // 3600)}h"
    d = int(secs // 86400)
    if d < 14:
        return f"{d}d"
    if d < 90:
        return f"{d // 7}w"
    return f"{d // 30}mo"


def parse_since(value) -> timedelta | None:
    """Parse '45s', '10m', '2h', '3d', '1w' (plain integers are seconds)."""
    if value is None:
        return None
    s = str(value).strip().lower()
    m = re.fullmatch(r"(\d+)\s*(s|m|h|d|w)?", s)
    if not m:
        raise KqError(f"invalid duration '{value}' (examples: 30s, 5m, 2h, 1d)")
    n = int(m.group(1))
    mult = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}[m.group(2) or "s"]
    return timedelta(seconds=n * mult)


# -- pods --------------------------------------------------------------------


def container_rows(pod: dict) -> list[dict]:
    """All containers (regular + init) with their status info."""
    out = []
    for spec_key, st_key, is_init in (
        ("containers", "containerStatuses", False),
        ("initContainers", "initContainerStatuses", True),
    ):
        statuses = {c.get("name"): c for c in dig(pod, "status", st_key, default=[]) or []}
        for c in dig(pod, "spec", spec_key, default=[]) or []:
            st = statuses.get(c.get("name")) or {}
            state, reason = _container_state(st)
            row = {
                "name": c.get("name"),
                "image": c.get("image"),
                "init": is_init,
                "ready": bool(st.get("ready")),
                "restarts": int(st.get("restartCount") or 0),
                "state": state,
                "reason": reason,
                "ports": [
                    f"{p.get('containerPort')}" + (f"/{p['name']}" if p.get("name") else "")
                    for p in c.get("ports") or []
                ],
            }
            last = _last_termination_reason(st)
            if last:
                row["lastReason"] = last
            out.append(row)
    return out


def _container_state(st: dict) -> tuple[str, str]:
    s = st.get("state") or {}
    if "running" in s:
        return "Running", ""
    if "waiting" in s:
        w = s.get("waiting") or {}
        return "Waiting", w.get("reason") or ""
    if "terminated" in s:
        t = s.get("terminated") or {}
        return "Terminated", t.get("reason") or ""
    return "Unknown", ""


def _last_termination_reason(st: dict) -> str:
    t = (st.get("lastState") or {}).get("terminated") or {}
    return t.get("reason") or ""


def pod_status(pod: dict) -> str:
    phase = dig(pod, "status", "phase") or "Unknown"
    waiting = [r for r in container_rows(pod) if r["state"] == "Waiting" and r["reason"]]
    if phase == "Running":
        return waiting[0]["reason"] if waiting else "Running"
    if phase == "Succeeded":
        return "Completed"
    if phase == "Failed":
        return "Error"
    if phase == "Pending":
        return waiting[0]["reason"] if waiting else "Pending"
    return phase


def pod_ready_ratio(pod: dict) -> str:
    rows = [r for r in container_rows(pod) if not r["init"]]
    if not rows:
        return "0/0"
    return f"{sum(1 for r in rows if r['ready'])}/{len(rows)}"


def pod_restarts(pod: dict) -> int:
    return sum(r["restarts"] for r in container_rows(pod))


def pod_is_healthy(pod: dict) -> bool:
    phase = dig(pod, "status", "phase")
    if phase == "Succeeded":
        return True
    if phase != "Running":
        return False
    rows = container_rows(pod)
    return all(r["ready"] for r in rows if not r["init"]) and not any(r["state"] == "Waiting" for r in rows)


# -- deployments ---------------------------------------------------------------


def deployment_brief(dep: dict) -> dict:
    spec_r = dig(dep, "spec", "replicas")
    desired = spec_r if spec_r is not None else int(dig(dep, "status", "replicas", default=0) or 0)
    return {
        "desired": desired,
        "ready": int(dig(dep, "status", "readyReplicas", default=0) or 0),
        "updated": int(dig(dep, "status", "updatedReplicas", default=0) or 0),
        "available": int(dig(dep, "status", "availableReplicas", default=0) or 0),
        "unavailable": int(dig(dep, "status", "unavailableReplicas", default=0) or 0),
    }


def deployment_is_healthy(dep: dict) -> bool:
    b = deployment_brief(dep)
    conds = {c.get("type"): c.get("status") for c in dig(dep, "status", "conditions", default=[]) or []}
    if conds.get("Available") == "False":
        return False
    if b["unavailable"]:
        return False
    return b["available"] >= b["desired"]


# -- nodes ---------------------------------------------------------------------


def node_status(node: dict) -> tuple[str, list[str]]:
    conds = {c.get("type"): c for c in dig(node, "status", "conditions", default=[]) or []}
    ready = (conds.get("Ready") or {}).get("status") == "True"
    problems = []
    for t, c in conds.items():
        if t == "Ready":
            continue
        if c.get("status") == "True":  # DiskPressure, MemoryPressure, PIDPressure, ...
            problems.append(t)
    return ("Ready" if ready else "NotReady"), problems


def node_is_healthy(node: dict) -> bool:
    status, problems = node_status(node)
    return status == "Ready" and not problems


def node_roles(node: dict) -> str:
    labels = dig(node, "metadata", "labels", default={}) or {}
    roles = [k.split("node-role.kubernetes.io/", 1)[1] for k in labels if k.startswith("node-role.kubernetes.io/")]
    roles = sorted(r for r in roles if r)
    return ",".join(roles) or "<none>"


# -- services --------------------------------------------------------------------


def svc_ports(svc: dict) -> str:
    parts = []
    for p in dig(svc, "spec", "ports", default=[]) or []:
        s = str(p.get("port"))
        if p.get("nodePort"):
            s += f":{p['nodePort']}"
        s += f"/{p.get('protocol') or 'TCP'}"
        parts.append(s)
    return ",".join(parts) or "<none>"


def svc_cluster_ip(svc: dict) -> str:
    return dig(svc, "spec", "clusterIP") or "<none>"


def svc_external_ip(svc: dict) -> str:
    ing = [i.get("ip") or i.get("hostname") for i in dig(svc, "status", "loadBalancer", "ingress", default=[]) or []]
    ext = dig(svc, "spec", "externalIPs", default=[]) or []
    vals = [x for x in (ing + ext) if x]
    return ",".join(vals) or "<none>"


# -- conditions --------------------------------------------------------------------


def conditions_brief(obj: dict) -> list[dict]:
    out = []
    for c in dig(obj, "status", "conditions", default=[]) or []:
        row = {"type": c.get("type"), "status": c.get("status")}
        if c.get("reason"):
            row["reason"] = c.get("reason")
        if c.get("message"):
            row["message"] = c.get("message")
        out.append(row)
    return out


# -- table columns -----------------------------------------------------------------


def _name(o: dict) -> str:
    return dig(o, "metadata", "name", default="") or ""


def _ns(o: dict) -> str:
    return dig(o, "metadata", "namespace", default="") or ""


def _age(o: dict) -> str:
    return age(dig(o, "metadata", "creationTimestamp"))


NS_COLUMN = ("NAMESPACE", _ns)

COLUMNS: dict[str, list] = {
    "pod": [
        ("NAME", _name),
        ("READY", pod_ready_ratio),
        ("STATUS", pod_status),
        ("RESTARTS", pod_restarts),
        ("AGE", _age),
        ("IP", lambda o: dig(o, "status", "podIP") or ""),
        ("NODE", lambda o: dig(o, "spec", "nodeName") or ""),
    ],
    "deployment": [
        ("NAME", _name),
        (
            "READY",
            lambda d: (
                f"{dig(d, 'status', 'readyReplicas', default=0) or 0}/{dig(d, 'spec', 'replicas', default=0) or 0}"
            ),
        ),
        ("UP-TO-DATE", lambda d: dig(d, "status", "updatedReplicas", default=0) or 0),
        ("AVAILABLE", lambda d: dig(d, "status", "availableReplicas", default=0) or 0),
        ("AGE", _age),
    ],
    "node": [
        ("NAME", _name),
        ("STATUS", lambda o: node_status(o)[0]),
        ("ROLES", node_roles),
        ("AGE", _age),
        ("VERSION", lambda o: dig(o, "status", "nodeInfo", "kubeletVersion") or ""),
    ],
    "service": [
        ("NAME", _name),
        ("TYPE", lambda o: dig(o, "spec", "type") or ""),
        ("CLUSTER-IP", svc_cluster_ip),
        ("EXTERNAL-IP", svc_external_ip),
        ("PORTS", svc_ports),
        ("AGE", _age),
    ],
    "secret": [
        ("NAME", _name),
        ("TYPE", lambda o: dig(o, "type") or "Opaque"),
        ("DATA", lambda o: len(dig(o, "data", default={}) or dig(o, "stringData", default={}) or {})),
        ("AGE", _age),
    ],
    "configmap": [
        ("NAME", _name),
        ("DATA", lambda o: len(dig(o, "data", default={}) or {})),
        ("AGE", _age),
    ],
    "namespace": [
        ("NAME", _name),
        ("STATUS", lambda o: dig(o, "status", "phase") or ""),
        ("AGE", _age),
    ],
}

# Condition types that read as "the object's overall status" (CRD-friendly).
_STATUS_CONDITIONS = ("Ready", "Healthy", "Succeeded", "Established", "Available")


def generic_status(obj: dict) -> str:
    """Best-effort status for unknown/CRD kinds: a Ready-ish condition,
    Argo-style ``status.health.status``, ``status.phase``/``status.state``."""
    conds = dig(obj, "status", "conditions", default=[]) or []
    if conds:
        by_type = {c.get("type"): c for c in conds}
        for t in _STATUS_CONDITIONS:
            c = by_type.get(t)
            if c:
                return str(c.get("status") or "")
        first = conds[0]
        return f"{first.get('type')}={first.get('status')}"
    health = dig(obj, "status", "health", "status")  # Argo CD applications
    if isinstance(health, str) and health:
        return health
    for key in ("phase", "state"):
        v = dig(obj, "status", key)
        if isinstance(v, str) and v:
            return v
    return ""


GENERIC_COLUMNS = [("NAME", _name), ("STATUS", generic_status), ("AGE", _age)]


def _crd_established(o: dict) -> str:
    for c in dig(o, "status", "conditions", default=[]) or []:
        if c.get("type") == "Established":
            return str(c.get("status") or "")
    return ""


COLUMNS["customresourcedefinition"] = [
    ("NAME", _name),
    ("GROUP", lambda o: dig(o, "spec", "group") or ""),
    ("KIND", lambda o: dig(o, "spec", "names", "kind") or ""),
    ("NAMESPACED", lambda o: "namespaced" if dig(o, "spec", "scope") == "Namespaced" else "cluster"),
    ("ESTABLISHED", _crd_established),
    ("AGE", _age),
]


def columns_for(kind: str) -> list:
    return COLUMNS.get((kind or "").lower(), GENERIC_COLUMNS)


# -- describe summaries ---------------------------------------------------------------


def summary_for(entry, obj: dict) -> dict:
    k = (entry.kind or "").lower()
    s: dict = {"kind": entry.kind, "name": _name(obj), "age": _age(obj)}
    if _ns(obj):
        s["namespace"] = _ns(obj)
    if k == "pod":
        s["status"] = pod_status(obj)
        s["ready"] = pod_ready_ratio(obj)
        s["restarts"] = pod_restarts(obj)
        s["healthy"] = pod_is_healthy(obj)
        for key, val in (
            ("node", dig(obj, "spec", "nodeName")),
            ("ip", dig(obj, "status", "podIP")),
            ("qos", dig(obj, "status", "qosClass")),
        ):
            if val:
                s[key] = val
        s["conditions"] = conditions_brief(obj)
        s["containers"] = [_container_summary(r) for r in container_rows(obj)]
    elif k == "node":
        status, problems = node_status(obj)
        s["status"] = status
        s["healthy"] = node_is_healthy(obj)
        s["problems"] = problems
        s["version"] = dig(obj, "status", "nodeInfo", "kubeletVersion") or ""
        s["conditions"] = conditions_brief(obj)
    elif k == "deployment":
        s["replicas"] = deployment_brief(obj)
        s["healthy"] = deployment_is_healthy(obj)
        s["strategy"] = dig(obj, "spec", "strategy", "type") or ""
        s["conditions"] = conditions_brief(obj)
    elif k == "service":
        s["type"] = dig(obj, "spec", "type") or ""
        s["clusterIP"] = svc_cluster_ip(obj)
        s["externalIP"] = svc_external_ip(obj)
        s["ports"] = svc_ports(obj)
    elif k == "secret":
        data = dig(obj, "data", default={}) or {}
        s["type"] = dig(obj, "type") or "Opaque"
        s["keys"] = sorted(data or (dig(obj, "stringData", default={}) or {}))
        s["dataBytes"] = sum(len(v) for v in data.values() if isinstance(v, str))
    elif k == "configmap":
        data = dig(obj, "data", default={}) or {}
        s["keys"] = sorted(data)
        s["dataBytes"] = sum(len(v) for v in data.values() if isinstance(v, str))
    else:
        conds = conditions_brief(obj)
        if conds:
            s["conditions"] = conds
    return s


def _container_summary(r: dict) -> dict:
    out = {k: r[k] for k in ("name", "image", "ready", "restarts", "state") if r.get(k) is not None}
    if r.get("ports"):
        out["ports"] = r["ports"]
    if r.get("reason"):
        out["reason"] = r["reason"]
    if r.get("lastReason"):
        out["lastReason"] = r["lastReason"]
    if r.get("init"):
        out["init"] = True
    return out
