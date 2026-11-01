# SKILL.md — kube-query for AI agents

name: kube-query
description: Read-only Kubernetes triage CLI. Use kube-query to capture cluster state and diagnose problems (pods, deployments, events, logs, helm, CRDs). Fixing happens with other tools — kube-query can never mutate the cluster.

Install (PyPI project `kube-query`; there is no short `kq` executable — that
name on PyPI is an unrelated Kafka lib):
`uv tool install kube-query` (permanent) or `uvx kube-query` (one-off).
Optional short form in your shell: `alias kq=kube-query`.

## What this tool is for

kube-query answers "what is the state of the cluster and why is it unhealthy?" — nothing else.
It only sends GET requests to the API server. There is no create/update/delete/apply/exec.
Diagnosis with kube-query, remediation elsewhere (kubectl, gitops, helm, IaC).

## The 5-move triage loop

```
1. kube-query overview                 # snapshot: problem pods, nodes, deployments, warnings
2. kube-query p desc <pod> -n <ns>     # status, restarts, waiting reasons, last errors + events
3. kube-query logs <pod> -n <ns> -c <container> --tail 50   # crash output (add --previous)
4. kube-query tree deploy/<name> -n <ns>                    # ownership chain + per-pod health
5. kube-query ev -A --type Warning --since 2h               # cluster-wide warning events
```

When you don't know the namespace: add `-A` to any list command.
When the resource is unusual (CRD): `kube-query api` to discover, then `kube-query get <plural> -A`.

## Command map (aliases in parens)

| Command | Purpose |
|---|---|
| `kube-query overview` (`ov`, `o`) | cluster snapshot, problems first |
| `kube-query p l` (`pod`, `po`) | list pods (`-A`, `-n NS`, regex arg, `-l selector`) |
| `kube-query p NAME` / `kube-query p desc NAME` | one pod: full yaml / diagnosis bundle |
| `kube-query logs POD [-c C] [--previous] [--tail N]` | container logs, plain text |
| `kube-query d l` (`deploy`, `dep`) | deployments; same flags as pods |
| `kube-query n l`, `kube-query no l`, `kube-query svc l`, `kube-query sec l`, `kube-query cm l` | namespaces, nodes, services, secrets, configmaps |
| `kube-query sec NAME --reveal` | decode a secret's values (explicit opt-in) |
| `kube-query ev` (`events`, `e`) | events: `--type Warning --since 2h --for pod/NAME` |
| `kube-query tree deploy/NAME` (`t`) | ownership tree with health per node |
| `kube-query get RESOURCE[/NAME]` (`g`) | any resource incl. CRDs; `kube-query api` lists all types |
| `kube-query crd ls` | CRDs installed in this cluster (group, kind, Established) |
| `kube-query argo -A` (`argocd`) | Argo CD Applications: health + sync |
| `kube-query svc desc NAME` | service ports + backing endpoints (ready/notReady IPs) |
| `kube-query helm ls -A` (`h`) / `kube-query helm show NAME` | helm releases, chart + effective values |
| `kube-query eso -A` / `--stores` | ExternalSecret / SecretStore sync status |
| `kube-query ctx ls` (`c l`) | which cluster am I on? (kubeconfig contexts) |
| `kube-query ver` | client + server version |

## Output contract

- Default: **compact yaml** (managedFields, uid, resourceVersion, empty values stripped).
- `-o json` machine-parseable · `-o rich` human tables · `-o md` markdown tables · `-o tree` ownership view.
- `-v` keeps system metadata; `-vv` raw object. Logs are always plain text.
- Exit codes: 0 ok, 1 error, 2 usage. Errors are one actionable sentence, often with a hint.
- Stderr carries `#`-prefixed commentary; stdout stays parseable.

## Agent rules of engagement

1. Always `kube-query ctx ls` (or check `overview.context`) before interpreting anything.
2. Prefer `overview` → `desc` → `logs` over dumping full object lists into context.
3. Use `-A` + a regex instead of guessing namespaces: `kube-query p l '^api-' -A`.
4. Read secrets only when strictly needed (`--reveal` is explicit for a reason).
5. Report findings with evidence (status, reasons, events, log lines) and propose the fix
   for a human/other tool to apply — kube-query will not apply it.

## Common failure signatures

| You see | Likely cause | Next step |
|---|---|---|
| `CrashLoopBackOff` | app exiting/crashing | `kube-query logs POD --previous` |
| `ImagePullBackOff` | wrong tag/registry/auth | `kube-query p show POD` (image), check `sec` for pull secret |
| `Pending` + `FailedScheduling` | no capacity/taints | `kube-query no l`, `kube-query ev --for pod/POD` |
| Deployment READY x<y | rollout stuck | `kube-query tree deploy/NAME`, `kube-query d desc NAME` |
| Node `NotReady`/pressure | node trouble | `kube-query no show NODE`, node events |
| ExternalSecret not Ready | store/permission issue | `kube-query eso -A`, `kube-query eso --stores` |
