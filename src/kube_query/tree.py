"""Ownership trees (Deployment -> ReplicaSet -> Pods, CronJob -> Jobs -> Pods)."""

from __future__ import annotations

from rich.text import Text
from rich.tree import Tree

from .access import list_objects
from .discovery import resolve
from .errors import KqError
from .summarize import (
    age,
    conditions_brief,
    deployment_brief,
    deployment_is_healthy,
    dig,
    node_is_healthy,
    node_status,
    pod_is_healthy,
    pod_ready_ratio,
    pod_restarts,
    pod_status,
)

# Resources searched for ownership children (kept cheap: one list call each).
CHILD_CANDIDATES = ("pods", "replicasets", "jobs")


class Node:
    __slots__ = ("children", "entry", "obj")

    def __init__(self, entry, obj: dict) -> None:
        self.entry = entry
        self.obj = obj
        self.children: list[Node] = []


def child_index(ctx, namespace: str) -> dict:
    """uid -> [(entry, obj)] for workload children within a namespace."""
    idx: dict = {}
    for plural in CHILD_CANDIDATES:
        try:
            entry = resolve(ctx, plural)
            items = list_objects(ctx, entry, namespace=namespace)
        except KqError:
            continue  # tree stays useful even if one candidate is missing/forbidden
        for it in items:
            for ref in dig(it, "metadata", "ownerReferences", default=[]) or []:
                uid = ref.get("uid")
                if uid:
                    idx.setdefault(uid, []).append((entry, it))
    return idx


def build_forest(ctx, root_entry, root_obj: dict) -> list[Node]:
    """A one-root forest for a single object."""
    root = Node(root_entry, root_obj)
    if root_entry.kind.lower() == "node":
        try:
            pods_entry = resolve(ctx, "pods")
            name = dig(root_obj, "metadata", "name")
            pods = list_objects(ctx, pods_entry, field_selector=f"spec.nodeName={name}")
        except KqError:
            pods = []
        for p in pods:
            root.children.append(Node(pods_entry, p))
        return [root]
    ns = dig(root_obj, "metadata", "namespace")
    if ns:
        _attach(root, child_index(ctx, ns), depth=0)
    return [root]


def forest_for_items(ctx, entry, items: list[dict]) -> list[Node]:
    """Forest over a list of items (e.g. `kq get deployments -o tree`)."""
    by_ns: dict = {}
    for it in items:
        by_ns.setdefault(dig(it, "metadata", "namespace") or "", []).append(it)
    cache: dict = {}
    roots = []
    for ns, its in by_ns.items():
        if ns not in cache:
            cache[ns] = child_index(ctx, ns)
        for it in its:
            n = Node(entry, it)
            _attach(n, cache[ns], depth=0)
            roots.append(n)
    return roots


def _attach(node: Node, idx: dict, depth: int) -> None:
    if depth > 10:
        return
    uid = dig(node.obj, "metadata", "uid")
    for entry, obj in idx.get(uid, []):
        child = Node(entry, obj)
        node.children.append(child)
        _attach(child, idx, depth + 1)


def node_dict(node: Node, *, with_children: bool = True) -> dict:
    entry, obj = node.entry, node.obj
    k = entry.kind.lower()
    d: dict = {
        "kind": entry.kind,
        "name": dig(obj, "metadata", "name", default="") or "",
        "age": age(dig(obj, "metadata", "creationTimestamp")),
    }
    ns = dig(obj, "metadata", "namespace")
    if ns:
        d["namespace"] = ns
    if k == "pod":
        d["status"] = pod_status(obj)
        d["ready"] = pod_ready_ratio(obj)
        d["healthy"] = pod_is_healthy(obj)
        r = pod_restarts(obj)
        if r:
            d["restarts"] = r
    elif k == "deployment":
        d["replicas"] = "{ready}/{desired}".format(**deployment_brief(obj))
        d["healthy"] = deployment_is_healthy(obj)
    elif k == "replicaset":
        desired = int(dig(obj, "spec", "replicas", default=0) or 0)
        ready = int(dig(obj, "status", "readyReplicas", default=0) or 0)
        d["replicas"] = f"{ready}/{desired}"
        d["healthy"] = ready >= desired
    elif k == "job":
        failed = int(dig(obj, "status", "failed", default=0) or 0)
        succeeded = int(dig(obj, "status", "succeeded", default=0) or 0)
        d["status"] = "Failed" if failed else ("Complete" if succeeded else "Running")
        d["healthy"] = not failed
    elif k == "node":
        d["status"], problems = node_status(obj)
        d["healthy"] = node_is_healthy(obj)
        if problems:
            d["problems"] = problems
    else:
        conds = conditions_brief(obj)
        if conds:
            d["conditions"] = conds
    if with_children and node.children:
        d["children"] = [node_dict(c) for c in node.children]
    return d


def _node_label(d: dict) -> str:
    bits = []
    if d.get("status"):
        bits.append(str(d["status"]))
    if d.get("replicas"):
        bits.append(d["replicas"])
    if d.get("ready"):
        bits.append(f"ready {d['ready']}")
    if d.get("restarts"):
        bits.append(f"{d['restarts']} restarts")
    if d.get("problems"):
        bits.append(",".join(d["problems"]))
    bits.append(d["age"])
    return f"{d['kind']} {d['name']} - " + " - ".join(bits)


def _styled_label(d: dict) -> Text:
    label = Text(_node_label(d))
    style = "green" if d.get("healthy") is True else ("red" if d.get("healthy") is False else "dim")
    label.stylize(style)
    return label


def rich_forest(roots: list[Node]) -> Tree:
    if not roots:
        return Tree("")
    if len(roots) == 1:
        tree = Tree(_styled_label(node_dict(roots[0], with_children=False)))
        _add_children(roots[0], tree)
        return tree
    tree = Tree("")
    for r in roots:
        branch = tree.add(_styled_label(node_dict(r, with_children=False)))
        _add_children(r, branch)
    return tree


def _add_children(node: Node, branch: Tree) -> None:
    for c in node.children:
        sub = branch.add(_styled_label(node_dict(c, with_children=False)))
        _add_children(c, sub)


def md_forest(roots: list[Node]) -> str:
    lines: list[str] = []

    def walk(nodes: list[Node], depth: int) -> None:
        for n in nodes:
            d = node_dict(n, with_children=False)
            bits = [
                b
                for b in (
                    d.get("status"),
                    d.get("replicas"),
                    f"ready {d.get('ready')}" if d.get("ready") else None,
                    f"{d['restarts']} restarts" if d.get("restarts") else None,
                    d["age"],
                )
                if b
            ]
            lines.append("  " * depth + f"- **{d['kind']}** `{d['name']}` - " + ", ".join(str(b) for b in bits))
            walk(n.children, depth + 1)

    walk(roots, 0)
    return "\n".join(lines) + "\n"
