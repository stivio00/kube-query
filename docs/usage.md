# kube-query usage manual

`kq` (PyPI package: `kubeq`; also runnable as `kube-query`/`kubeq`) is a **read-only** Kubernetes query CLI.
It answers *what is the state of the cluster and why is it unhealthy*, in
compact formats designed for both humans and AI agents. It only ever sends
`GET` requests to the API server.

- Binary names: `kq` / `kube-query` / `kubeq` (same program)
- Output default: **compact YAML**; `-o json | rich | md | tree`
- Cluster selection: standard kubeconfig (`KUBECONFIG` env), `--kubeconfig`, `--ctx`
- RBAC: whatever your user/service-account can read, kq can show — nothing more

---

## 1. Global options

```
kq [GLOBAL OPTIONS] COMMAND [ARGS...]

--ctx, --context NAME    kubeconfig context for this invocation
--kubeconfig PATH        explicit kubeconfig file
-n, --ns, --namespace    default namespace for this invocation
-A, --all-namespaces     all namespaces (where applicable)
-o, --output FORMAT      yaml (default) | json | rich | md | tree   [env: KQ_OUTPUT]
-v / -vv                 verbosity: keep system metadata / raw object
--version                print version
```

Options can be given before or after the subcommand; the most specific one wins.
Useful environment variables: `KUBECONFIG`, `KQ_OUTPUT`, `KQ_TIMEOUT` (request timeout seconds, default 30).

Exit codes: `0` success · `1` runtime error (message on stderr, one actionable sentence) · `2` usage error.

## 2. Triage: `kq overview`

One command, whole cluster, problems first. Covers nodes, problem pods,
unavailable deployments, unbound PVCs and recent warning events. Tolerates
partial RBAC (missing sections are reported as `unavailable`).

```bash
kq overview                    # all namespaces (default)
kq overview -n prod            # one namespace
kq overview --since 4h -o rich # wider event window, human table
```

YAML output shape (trimmed):

```yaml
context: arn:aws:eks:us-east-1:123456789:cluster/prod
scope: all namespaces
nodes:
  total: 3
  healthy: 2
  problems:
    - name: ip-10-0-4-12.ec2.internal
      status: NotReady
      problems: [DiskPressure]
pods:
  total: 58
  healthy: 55
  problems:
    - name: web-7f9c6-b
      namespace: default
      status: CrashLoopBackOff
      restarts: 7
      node: ip-10-0-4-12.ec2.internal
deployments:
  total: 12
  unavailable:
    - name: web
      namespace: default
      desired: 3
      ready: 1
warningEvents:
  window: 1h
  count: 14
  recent: [...]
summary:
  issues: 4
  healthy: false
```

## 3. Resource groups (the sugar commands)

Every group follows the same shape:

```
kq <group> [l] [REGEX] [flags]     list (default when no subcommand)
kq <group> NAME                    show one object, full compact YAML
kq <group> desc NAME               diagnosis bundle (summary+object+children+events)
kq <group> logs NAME               pods only: container logs
```

| Group | Aliases | Notes |
|---|---|---|
| `pod` | `pods`, `p`, `po` | + `logs` subcommand |
| `deploy` | `deployments`, `deployment`, `dep`, `d` | |
| `ns` | `namespaces`, `namespace`, `n` | |
| `node` | `nodes`, `no` | cluster-scoped |
| `svc` | `service`, `services` | |
| `secret` | `secrets`, `sec` | values hidden; `--reveal` to decode |
| `cm` | `configmap`, `configmaps` | long values capped at 2000 chars (`-v` for full) |
| `ctx` | `contexts`, `context`, `c` | kubeconfig only, no API calls |
| `helm` | `h` | `ls`, `show NAME` |
| `ev` | `events`, `event`, `e` | see §6 |

`ls` flags (all groups): `-n NS`, `-A`, `-l LABEL_SELECTOR`, `--field-selector FS`,
`-f/--filter REGEX`, positional `REGEX` (matches object names), `-o`, `-v`.

```bash
kq p l                          # pods in current namespace
kq p l -A                       # everywhere
kq p l '^api-' -n prod          # regex filter
kq p l -l app=web,tier=fe       # label selector
kq p l --field-selector status.phase=Pending -A
kq p web-5d9c6 -n prod          # single pod, compact YAML
kq p desc web-5d9c6 -n prod     # + events, restarts, waiting reasons
kq p logs web-5d9c6 -c app --tail 50
kq p logs web-5d9c6 --previous  # crashed instance logs
kq sec l -A                     # secrets (values not shown)
kq sec show regcred --reveal    # decoded values (explicit opt-in)
kq cm show app-config           # data shown, long values capped
kq ctx ls                       # which cluster am I on?
kq --ctx staging p l            # quick context switch for one query
```

### Verbosity

| Level | Behavior |
|---|---|
| default | strips `managedFields`, `uid`, `resourceVersion`, `generation`, `selfLink`, noisy annotations, empty values |
| `-v` | keeps system metadata, still strips `managedFields` + last-applied annotation |
| `-vv` | raw object, nothing stripped |

## 4. Any resource incl. CRDs: `kq get`

```bash
kq get pods -A                      # same as p l -A
kq get pod/web-5d9c6 -n prod        # RESOURCE/NAME form
kq get deployments.apps -n prod     # group-qualified
kq get apps/v1/deployments -n prod  # apiVersion-qualified
kq get externalsecrets -A           # CRDs just work (discovery-driven)
kq get crds                         # what CRDs exist?
kq api                              # all resource types incl. CRDs
kq api external-secrets             # regex filter
```

Name resolution accepts plurals, singulars, kinds and shortnames
(case-insensitive): `deployments` = `deployment` = `Deployment` = `deploy`.
Ambiguous names prefer core, then common groups. Unknown names produce
suggestions: *“unknown resource type 'podz'. Did you mean: pods?”*

## 5. Diagnosis helpers

### `kq describe` (alias `desc`)

`summary` (computed status/health) + `object` (compact) + `children`
(ownership) + `events` (related, 20 most recent) in one document.

```bash
kq describe pod web-5d9c6 -n prod
kq desc deploy/web -n prod
```

### `kq tree` (alias `t`)

Ownership chains with health per node:

```bash
kq tree deploy/web -n prod          # Deployment -> ReplicaSet -> Pods
kq tree cronjob/backup -n prod      # CronJob -> Jobs -> Pods
kq tree node/worker-1               # pods scheduled on a node
kq tree deploy/web -o yaml          # nested structure as data
kq p l -o tree                      # forest view of any list
```

## 6. Events: `kq ev`

```bash
kq ev                               # current namespace, newest first, 50 max
kq ev -A --type Warning --since 2h  # cluster warnings in a window
kq ev --for pod/web-5d9c6 -n prod   # events about one object
kq ev 'BackOff' -A                  # regex on reason/object/message
kq ev --limit 200                   # more rows
```

Compact event shape: `lastSeen, type, reason, object (Kind/name), namespace, count, source, message`.

## 7. Helm (read-only): `kq helm`

Helm 3 stores releases as Secrets (`sh.helm.release.v1.<name>.v<rev>`,
label `owner=helm`). kq lists them without the helm binary and best-effort
decodes chart metadata + effective values from the payload.

```bash
kq helm ls -A               # name, revision, status, chart, updated
kq helm show wordpress      # + chart meta and effective values
kq helm show grafana -n monitoring -o json
```

If a payload can't be decoded (very old/hand-modified releases), the release
still lists with `chart: ?`.

## 8. External Secrets Operator: `kq eso`

```bash
kq eso -A                    # ExternalSecrets: store, target, Ready, reason
kq eso --stores -A           # SecretStores + ClusterSecretStores
```

Missing ESO CRDs produce a clear message instead of a stack trace.

## 9. Output formats

| `-o` | What you get | Best for |
|---|---|---|
| `yaml` (default) | compact YAML, key order preserved | agents, diffs, humans |
| `json` | same data, JSON | programmatic use |
| `rich` | aligned, colored tables (auto-detects TTY) | interactive terminal |
| `md` | markdown tables; objects as fenced yaml blocks | chat/PR comments, agent reports |
| `tree` | ownership tree view | workload chains |

`KQ_OUTPUT=rich` in your shell profile gives you tables by default while
agents (no env) keep YAML.

## 10. Safety model

- kq contains **no code path** that issues POST/PUT/PATCH/DELETE — the HTTP
  layer only implements `GET`.
- Secrets values are redacted unless `--reveal` is passed explicitly.
- RBAC still applies: kq shows exactly what your credentials can read.
- Fixing things is deliberately out of scope: use kubectl/gitops/helm for that.
