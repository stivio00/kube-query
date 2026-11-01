# SKILL.md — kube-query (kq) for AI agents

name: kube-query
description: Read-only Kubernetes triage CLI. Use kq to capture cluster state and diagnose problems (pods, deployments, events, logs, helm, CRDs). Fixing happens with other tools — kq can never mutate the cluster.

## What this tool is for

kq answers "what is the state of the cluster and why is it unhealthy?" — nothing else.
It only sends GET requests to the API server. There is no create/update/delete/apply/exec.
Diagnosis with kq, remediation elsewhere (kubectl, gitops, helm, IaC).

## The 5-move triage loop

```
1. kq overview                 # snapshot: problem pods, nodes, deployments, warnings
2. kq p desc <pod> -n <ns>     # status, restarts, waiting reasons, last errors + events
3. kq logs <pod> -n <ns> -c <container> --tail 50   # crash output (add --previous)
4. kq tree deploy/<name> -n <ns>                    # ownership chain + per-pod health
5. kq ev -A --type Warning --since 2h               # cluster-wide warning events
```

When you don't know the namespace: add `-A` to any list command.
When the resource is unusual (CRD): `kq api` to discover, then `kq get <plural> -A`.

## Command map (aliases in parens)

| Command | Purpose |
|---|---|
| `kq overview` (`ov`, `o`) | cluster snapshot, problems first |
| `kq p l` (`pod`, `po`) | list pods (`-A`, `-n NS`, regex arg, `-l selector`) |
| `kq p NAME` / `kq p desc NAME` | one pod: full yaml / diagnosis bundle |
| `kq logs POD [-c C] [--previous] [--tail N]` | container logs, plain text |
| `kq d l` (`deploy`, `dep`) | deployments; same flags as pods |
| `kq n l`, `kq no l`, `kq svc l`, `kq sec l`, `kq cm l` | namespaces, nodes, services, secrets, configmaps |
| `kq sec NAME --reveal` | decode a secret's values (explicit opt-in) |
| `kq ev` (`events`, `e`) | events: `--type Warning --since 2h --for pod/NAME` |
| `kq tree deploy/NAME` (`t`) | ownership tree with health per node |
| `kq get RESOURCE[/NAME]` (`g`) | any resource incl. CRDs; `kq api` lists all types |
| `kq helm ls -A` (`h`) / `kq helm show NAME` | helm releases, chart + effective values |
| `kq eso -A` / `--stores` | ExternalSecret / SecretStore sync status |
| `kq ctx ls` (`c l`) | which cluster am I on? (kubeconfig contexts) |
| `kq ver` | client + server version |

## Output contract

- Default: **compact yaml** (managedFields, uid, resourceVersion, empty values stripped).
- `-o json` machine-parseable · `-o rich` human tables · `-o md` markdown tables · `-o tree` ownership view.
- `-v` keeps system metadata; `-vv` raw object. Logs are always plain text.
- Exit codes: 0 ok, 1 error, 2 usage. Errors are one actionable sentence, often with a hint.
- Stderr carries `#`-prefixed commentary; stdout stays parseable.

## Agent rules of engagement

1. Always `kq ctx ls` (or check `overview.context`) before interpreting anything.
2. Prefer `overview` → `desc` → `logs` over dumping full object lists into context.
3. Use `-A` + a regex instead of guessing namespaces: `kq p l '^api-' -A`.
4. Read secrets only when strictly needed (`--reveal` is explicit for a reason).
5. Report findings with evidence (status, reasons, events, log lines) and propose the fix
   for a human/other tool to apply — kq will not apply it.

## Common failure signatures

| You see | Likely cause | Next step |
|---|---|---|
| `CrashLoopBackOff` | app exiting/crashing | `kq logs POD --previous` |
| `ImagePullBackOff` | wrong tag/registry/auth | `kq p show POD` (image), check `sec` for pull secret |
| `Pending` + `FailedScheduling` | no capacity/taints | `kq no l`, `kq ev --for pod/POD` |
| Deployment READY x<y | rollout stuck | `kq tree deploy/NAME`, `kq d desc NAME` |
| Node `NotReady`/pressure | node trouble | `kq no show NODE`, node events |
| ExternalSecret not Ready | store/permission issue | `kq eso -A`, `kq eso --stores` |
