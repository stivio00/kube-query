"""End-to-end smoke tests against a fake Kubernetes API server."""

from __future__ import annotations

import json

import yaml


def parse_yaml(text):
    return yaml.safe_load(text)


# -- contexts (no API calls) ---------------------------------------------------


def test_ctx_ls_yaml(run):
    out = run("ctx", "ls").output
    doc = parse_yaml(out)
    names = {c["name"] for c in doc}
    assert names == {"fake", "fake2"}
    current = [c for c in doc if c["current"]]
    assert current[0]["name"] == "fake"
    assert current[0]["namespace"] == "default"


def test_ctx_ls_aliases_and_rich(out):
    text = out("c", "l", "-o", "rich")
    assert "fake" in text and "fake2" in text and "*" in text


def test_ctx_show(run):
    doc = parse_yaml(run("ctx", "show", "fake2").output)
    assert doc["namespace"] == "prod"
    # implicit-name dispatch on resource groups is exercised via pods below


# -- pods ------------------------------------------------------------------------


def test_pod_ls_default_ns_json(run):
    doc = json.loads(run("p", "l", "-o", "json").output)
    assert [p["metadata"]["name"] for p in doc] == ["web-7f9c6-a", "web-7f9c6-b", "web-7f9c6-c"]


def test_pod_ls_all_namespaces(run):
    doc = json.loads(run("-o", "json", "p", "l", "-A").output)
    assert len(doc) == 6
    nss = {p["metadata"].get("namespace") for p in doc}
    assert nss == {"default", "prod", "kube-system"}


def test_pod_ls_pattern_and_filter(run):
    doc = json.loads(run("p", "l", "web-7f9c6-c$", "-o", "json").output)
    assert len(doc) == 1 and doc[0]["metadata"]["name"] == "web-7f9c6-c"
    doc = json.loads(run("p", "l", "-f", "web-7f9c6-[ab]", "-o", "json").output)
    assert len(doc) == 2


def test_pod_ls_label_selector(run):
    doc = json.loads(run("p", "l", "-l", "app=web", "-o", "json").output)
    assert len(doc) == 3


def test_pod_ls_compacted_by_default(run):
    doc = json.loads(run("p", "l", "-o", "json").output)
    pod = doc[0]
    assert "managedFields" not in pod["metadata"]
    assert "uid" not in pod["metadata"]
    assert "resourceVersion" not in pod["metadata"]


def test_pod_ls_verbose_keeps_system_meta(run):
    doc = json.loads(run("p", "l", "-o", "json", "-v").output)
    assert "uid" in doc[0]["metadata"]


def test_pod_group_level_options(run):
    doc = json.loads(run("p", "-o", "json", "-A").output)  # options before implicit default ls
    assert len(doc) == 6


def test_pod_show_implicit_name(run):
    doc = parse_yaml(run("p", "web-7f9c6-b").output)
    assert doc["kind"] == "Pod"
    assert doc["metadata"]["name"] == "web-7f9c6-b"
    assert doc["status"]["containerStatuses"][0]["state"]["waiting"]["reason"] == "CrashLoopBackOff"


def test_pod_ls_rich_and_md(out):
    rich = out("p", "l", "-o", "rich")
    assert "CrashLoopBackOff" in rich and "web-7f9c6-a" in rich and "RESTARTS" in rich
    md = out("p", "l", "-o", "md")
    assert "| NAME" in md and "web-7f9c6-b" in md


def test_pod_ls_o_tree(out):
    text = out("p", "l", "-o", "tree")
    assert "Pod web-7f9c6-a" in text
    assert "CrashLoopBackOff" in text


def test_pod_not_found_error(run):
    res = run("p", "show", "nope", check=False)
    assert res.exit_code == 1
    text = res.output + getattr(res, "stderr", "")
    assert "not found" in text
    assert "kq get pods" in text


def test_unknown_resource_suggests(run):
    res = run("get", "podz", check=False)
    assert res.exit_code == 1
    text = res.output + getattr(res, "stderr", "")
    assert "Did you mean" in text and "pods" in text


# -- describe -------------------------------------------------------------------


def test_pod_describe(run):
    doc = parse_yaml(run("p", "desc", "web-7f9c6-b").output)
    assert doc["summary"]["status"] == "CrashLoopBackOff"
    assert doc["summary"]["restarts"] == 7
    assert doc["summary"]["containers"][0]["name"] == "app"
    reasons = {e["reason"] for e in doc["events"]}
    assert "BackOff" in reasons
    assert doc["object"]["kind"] == "Pod"


def test_deploy_describe_children(run):
    doc = parse_yaml(run("desc", "deploy/web").output)
    kinds = [c["kind"] for c in doc.get("children", [])]
    assert "ReplicaSet" in kinds
    assert doc["summary"]["healthy"] is False


def test_describe_generic_two_args(run):
    doc = parse_yaml(run("describe", "deployment", "web").output)
    assert doc["summary"]["kind"] == "Deployment"


# -- logs -----------------------------------------------------------------------


def test_logs_single_container(run):
    text = run("logs", "web-7f9c6-a").output
    assert "fake log line 1" in text


def test_logs_previous(run):
    text = run("logs", "web-7f9c6-b", "--previous").output
    assert "previous crash log line A" in text


def test_logs_via_pod_group(run):
    text = run("p", "logs", "web-7f9c6-a", "-c", "app").output
    assert "fake log line 2" in text


def test_logs_bad_container(run):
    res = run("logs", "web-7f9c6-a", "-c", "nope", check=False)
    assert res.exit_code == 1
    text = res.output + getattr(res, "stderr", "")
    assert "Containers:" in text and "app" in text


# -- tree -----------------------------------------------------------------------


def test_tree_deploy(out, run):
    text = out("tree", "deploy/web")
    assert "Deployment web" in text
    assert "web-7f9c6" in text  # ReplicaSet
    assert "web-7f9c6-b" in text  # child pod


def test_tree_yaml(run):
    doc = parse_yaml(run("tree", "deploy/web", "-o", "yaml").output)
    assert doc["kind"] == "Deployment"
    child = doc["children"][0]
    assert child["kind"] == "ReplicaSet" and child["name"] == "web-7f9c6"
    grandchild = child["children"][0]
    assert grandchild["kind"] == "Pod"
    unhealthy = [c for c in child["children"] if c.get("status") == "CrashLoopBackOff"]
    assert unhealthy and unhealthy[0]["restarts"] == 7


def test_tree_node(run):
    text = run("tree", "node/node-1", "-o", "tree").output
    assert "Node node-1" in text
    assert "web-7f9c6-a" in text


# -- events ---------------------------------------------------------------------


def test_events_default_ns(run):
    doc = json.loads(run("ev", "-o", "json").output)
    reasons = {e["reason"] for e in doc}
    assert reasons == {"BackOff", "Pulled", "FailedScheduling"}
    # newest first
    assert doc[0]["reason"] == "BackOff"


def test_events_warning_since(run):
    doc = json.loads(run("ev", "-A", "--type", "Warning", "--since", "1h", "-o", "json").output)
    assert {e["reason"] for e in doc} == {"BackOff", "FailedScheduling"}


def test_events_for_object(run):
    doc = json.loads(run("ev", "--for", "pod/web-7f9c6-b", "-o", "json").output)
    assert len(doc) == 1 and doc[0]["reason"] == "BackOff"
    assert doc[0]["object"] == "Pod/web-7f9c6-b"


def test_events_pattern(run):
    doc = json.loads(run("ev", "BackOff", "-o", "json").output)
    assert len(doc) == 1


def test_events_rich(out):
    text = out("ev", "-A", "--type", "Warning", "-o", "rich")
    assert "BackOff" in text and "REASON" in text


# -- secrets / configmaps ----------------------------------------------------------


def test_secret_ls(run):
    doc = json.loads(run("sec", "l", "-o", "json").output)
    names = {s["metadata"]["name"] for s in doc}
    assert "regcred" in names
    assert "sh.helm.release.v1.wordpress.v2" in names


def test_secret_show_hidden_by_default(run):
    doc = parse_yaml(run("sec", "show", "regcred").output)
    assert "hidden" in doc["data"]["password"]
    assert "hunter2" not in run("sec", "show", "regcred").output


def test_secret_show_reveal(run):
    doc = parse_yaml(run("sec", "show", "regcred", "--reveal").output)
    assert doc["data"]["password"] == "hunter2"


def test_configmap_capped(run):
    doc = parse_yaml(run("cm", "show", "app-config").output)
    assert doc["data"]["config.yaml"] == "key: value\nmode: dev\n"
    assert "truncated" in doc["data"]["big.txt"]
    doc_full = parse_yaml(run("cm", "show", "app-config", "-v").output)
    assert doc_full["data"]["big.txt"] == "x" * 5000


# -- helm -----------------------------------------------------------------------


def test_helm_ls_namespace(run):
    doc = json.loads(run("helm", "ls", "-o", "json").output)
    assert len(doc) == 1  # latest revision only
    rel = doc[0]
    assert rel["name"] == "wordpress" and rel["revision"] == 2 and rel["status"] == "deployed"
    assert rel["chart"] == {"name": "wordpress", "version": "15.2.1", "appVersion": "6.1.1"}


def test_helm_ls_all_namespaces(out, run):
    text = out("h", "ls", "-A", "-o", "rich")
    assert "wordpress" in text and "grafana" in text and "deployed" in text


def test_helm_show(run):
    doc = parse_yaml(run("helm", "show", "wordpress").output)
    assert doc["values"] == {"replicaCount": 2, "blogName": "dev"}
    assert doc["chart"]["appVersion"] == "6.1.1"


def test_helm_implicit_show(run):
    doc = parse_yaml(run("helm", "wordpress").output)
    assert doc["name"] == "wordpress"


def test_helm_ls_md(out):
    text = out("helm", "ls", "-A", "-o", "md")
    assert "| NAME" in text and "grafana-8.5.0" in text


# -- ESO ------------------------------------------------------------------------


def test_eso_rows(run):
    doc = json.loads(run("eso", "-o", "json").output)
    by_name = {r["name"]: r for r in doc}
    assert by_name["my-secret"]["ready"] == "True"
    assert by_name["my-secret"]["healthy"] is True
    assert by_name["broken-es"]["reason"] == "StoreError"


def test_eso_rich(out):
    text = out("eso", "-o", "rich")
    assert "my-secret" in text and "StoreError" in text


def test_eso_stores(run):
    doc = json.loads(run("eso", "--stores", "-A", "-o", "json").output)
    names = {r["name"] for r in doc}
    assert names == {"vault", "cluster-vault"}


# -- overview -------------------------------------------------------------------


def test_overview_json(run):
    doc = json.loads(run("overview", "-o", "json").output)
    assert doc["context"] == "fake"
    assert doc["nodes"]["total"] == 2
    assert doc["nodes"]["problems"][0]["name"] == "node-2"
    assert doc["nodes"]["problems"][0]["status"] == "NotReady"
    problem_pods = {p["name"] for p in doc["pods"]["problems"]}
    assert problem_pods == {"web-7f9c6-b", "web-7f9c6-c"}
    assert doc["deployments"]["unavailable"][0]["name"] == "web"
    assert doc["warningEvents"]["count"] >= 2
    assert doc["summary"]["issues"] == 4
    # PVC section tolerates a 404 list endpoint
    assert "unavailable" in doc["persistentVolumeClaims"]


def test_overview_rich_and_md(out):
    rich = out("ov", "-o", "rich")
    assert "problem pods" in rich and "node-2" in rich and "NotReady" in rich
    md = out("overview", "-o", "md")
    assert "## " in md and "web-7f9c6-b" in md


def test_overview_namespace_scoped(run):
    doc = json.loads(run("overview", "-n", "prod", "-o", "json").output)
    assert doc["scope"] == "namespace: prod"
    assert doc["pods"]["problems"] == []


def test_overview_render_tolerates_unavailable_sections():
    """Sections blocked by RBAC become error strings; rendering must not crash."""
    from kube_query.commands.overview import _md_sections, _print_rich
    from kube_query.output import console

    report = {
        "context": "x",
        "scope": "all namespaces",
        "nodes": {"unavailable": "403"},
        "pods": {"unavailable": "403"},
        "deployments": {"unavailable": "403 forbidden"},  # used to crash rich/md render
        "persistentVolumeClaims": {"unavailable": "403"},
        "warningEvents": {"unavailable": "403"},
        "generatedAt": "now",
        "summary": {"issues": 0, "healthy": True},
    }
    _print_rich(console(), report)
    assert _md_sections(report)


# -- generic get / api / version ----------------------------------------------------


def test_get_crd_resource(run):
    doc = json.loads(run("get", "externalsecrets", "-A", "-o", "json").output)
    assert len(doc) == 2
    assert doc[0]["kind"] == "ExternalSecret"


def test_get_single_object(run):
    doc = parse_yaml(run("get", "deploy/web").output)
    assert doc["kind"] == "Deployment" and doc["metadata"]["name"] == "web"


def test_get_deployment_all_namespaces_rich(out):
    text = out("get", "deployments", "-A", "-o", "rich")
    assert "NAMESPACE" in text and "web" in text and "api" in text


def test_get_api_version_form(run):
    doc = json.loads(run("get", "apps/v1/deployments", "-o", "json").output)
    assert [d["metadata"]["name"] for d in doc] == ["web"]  # default namespace, like kubectl
    doc = json.loads(run("get", "apps/v1/deployments", "-A", "-o", "json").output)
    assert len(doc) == 2


def test_api_lists_crds(run):
    doc = json.loads(run("api", "-o", "json").output)
    names = {e["name"] for e in doc}
    assert {"pods", "deployments", "externalsecrets"} <= names
    # subresources are skipped
    assert "pods/log" not in names


def test_api_pattern(out):
    text = out("api", "external", "-o", "rich")
    assert "externalsecrets" in text


def test_version(run):
    doc = json.loads(run("ver", "-o", "json").output)
    assert doc["server"]["version"] == "v1.31.1"
    assert doc["context"] == "fake"


# -- other sugar groups ---------------------------------------------------------------


def test_ns_ls(run):
    doc = json.loads(run("n", "l", "-o", "json").output)
    assert {n["metadata"]["name"] for n in doc} == {"default", "prod", "kube-system"}


def test_node_ls(out, run):
    text = out("no", "l", "-o", "rich")
    assert "node-1" in text and "NotReady" in text and "control-plane" in text
    doc = parse_yaml(run("no", "show", "node-2").output)
    assert doc["kind"] == "Node"


def test_deploy_ls(run):
    doc = json.loads(run("d", "l", "-o", "json").output)
    assert [d["metadata"]["name"] for d in doc] == ["web"]  # default ns only
    doc = json.loads(run("d", "l", "-A", "-o", "json").output)
    assert len(doc) == 2


def test_svc_ls(out):
    text = out("svc", "l", "-o", "rich")
    assert "10.96.7.10" in text and "80/TCP" in text


def test_root_namespace_flag(run):
    doc = json.loads(run("--ns", "prod", "p", "l", "-o", "json").output)
    assert {p["metadata"]["name"] for p in doc} == {"api-6d4d9", "db-0"}


def test_context_flag(run):
    doc = json.loads(run("--ctx", "fake2", "p", "l", "-o", "json").output)
    assert {p["metadata"]["name"] for p in doc} == {"api-6d4d9", "db-0"}


def test_bad_context_error(run):
    res = run("--ctx", "nope", "p", "l", check=False)
    assert res.exit_code == 1


def test_invalid_output_format(run):
    res = run("p", "l", "-o", "xml", check=False)
    assert res.exit_code == 2  # click choice validation
