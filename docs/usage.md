# kube-query usage manual

`kube-query` (PyPI package: `kube-query`) is a **read-only** Kubernetes query CLI.
It answers *what is the state of the cluster and why is it unhealthy*, in
compact formats designed for both humans and AI agents. It only ever sends
`GET` requests to the API server.

- Binary: `kube-query` (there is deliberately no short `kq` executable — that
  name on PyPI belongs to an unrelated Kafka library; `alias kq=kube-query`
  if you want it short)
- Install: `uv tool install kube-query` (permanent) or `uvx kube-query` (one-off)
- Output default: **compact YAML**; `-o json | rich | md | tree`
- Cluster selection: standard kubeconfig (`KUBECONFIG` env), `--kubeconfig`, `--ctx`
- RBAC: whatever your user/service-account can read, kube-query can show — nothing more

---

## 1. Global options

```
kube-query [GLOBAL OPTIONS] COMMAND [ARGS...]

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

## 2. Triage: `kube-query overview`

One command, whole cluster, problems first. Covers nodes, problem pods,
unavailable deployments, unbound PVCs and recent warning events. Tolerates
partial RBAC (missing sections are reported as `unavailable`).

```bash
kube-query overview                    # all namespaces (default)
kube-query overview -n prod            # one namespace
kube-query overview --since 4h -o rich # wider event window, human table
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
kube-query <group> [l] [REGEX] [flags]     list (default when no subcommand)
kube-query <group> NAME                    show one object, full compact YAML
kube-query <group> desc NAME               diagnosis bundle (summary+object+children+events)
kube-query <group> logs NAME               pods only: container logs
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
`-f/--filter REGEX`, `--show-labels`, positional `REGEX` (matches object names), `-o`, `-v`.

```bash
kube-query p l                          # pods in current namespace
kube-query p l -A                       # everywhere
kube-query p l '^api-' -n prod          # regex filter
kube-query p l -l app=web,tier=fe       # label selector
kube-query p l --field-selector status.phase=Pending -A
kube-query p web-5d9c6 -n prod          # single pod, compact YAML
kube-query p desc web-5d9c6 -n prod     # + events, restarts, waiting reasons
kube-query p logs web-5d9c6 -c app --tail 50
kube-query p logs web-5d9c6 --previous  # crashed instance logs
kube-query sec l -A                     # secrets (values not shown)
kube-query sec show regcred --reveal    # decoded values (explicit opt-in)
kube-query cm show app-config           # data shown, long values capped
kube-query ctx ls                       # which cluster am I on?
kube-query --ctx staging p l            # quick context switch for one query
```

### Verbosity

| Level | Behavior |
|---|---|
| default | strips `managedFields`, `uid`, `resourceVersion`, `generation`, `selfLink`, noisy annotations, empty values |
| `-v` | keeps system metadata, still strips `managedFields` + last-applied annotation |
| `-vv` | raw object, nothing stripped |

## 4. Any resource incl. CRDs: `kube-query get`

```bash
kube-query get pods -A                      # same as p l -A
kube-query get pod/web-5d9c6 -n prod        # RESOURCE/NAME form
kube-query get deployments.apps -n prod     # group-qualified
kube-query get apps/v1/deployments -n prod  # apiVersion-qualified
kube-query get externalsecrets -A           # CRDs just work (discovery-driven)
kube-query crd ls                           # CRDs installed in this cluster
kube-query crd show externalsecrets.external-secrets.io
kube-query api                              # all resource types incl. CRDs
kube-query api external-secrets             # regex filter
```

CRD-first rendering: kinds without built-in table columns get a smart
**STATUS** column derived from a `Ready`/`Healthy`/`Succeeded`/`Established`/
`Available` condition (or `status.phase`) — so `kube-query get widgets -o rich`
is informative for any operator's CRDs. Columns that end up empty for every
row are omitted. `kube-query crd ls` shows GROUP, KIND, scope and the
`Established` condition per CRD.

Name resolution accepts plurals, singulars, kinds and shortnames
(case-insensitive): `deployments` = `deployment` = `Deployment` = `deploy`.
Ambiguous names prefer core, then common groups. Unknown names produce
suggestions: *“unknown resource type 'podz'. Did you mean: pods?”*

## 5. Diagnosis helpers

### `kube-query describe` (alias `desc`)

`summary` (computed status/health) + `object` (compact) + `children`
(ownership) + `events` (related, 20 most recent) in one document.

```bash
kube-query describe pod web-5d9c6 -n prod
kube-query desc deploy/web -n prod
```

### `kube-query describe` extras

- **Services** get an `endpoints` section: ready / notReady backing IPs and
  ports — the fastest answer to "is traffic actually reaching pods?".
- **Pods** show per-container ports (`80/http`) in the summary.
- Unknown/CRD kinds show their conditions in the summary.

### `kube-query tree` (alias `t`)

Ownership chains with health per node:

```bash
kube-query tree deploy/web -n prod          # Deployment -> ReplicaSet -> Pods
kube-query tree cronjob/backup -n prod      # CronJob -> Jobs -> Pods
kube-query tree node/worker-1               # pods scheduled on a node
kube-query tree deploy/web -o yaml          # nested structure as data
kube-query p l -o tree                      # forest view of any list
```

## 6. Argo CD: `kube-query argo`

Applications across the cluster with health + sync (read-only, via the
`applications.argoproj.io` CRD; friendly error if Argo CD isn't installed):

```bash
kube-query argo -A                      # NAME NAMESPACE PROJECT HEALTH SYNC DESTINATION AGE
kube-query argo -A -o rich
kube-query argo '^payments' -n argocd
kube-query get applications -A          # raw CRD objects (smart STATUS column)
```

## 7. Events: `kube-query ev`

```bash
kube-query ev                               # current namespace, newest first, 50 max
kube-query ev -A --type Warning --since 2h  # cluster warnings in a window
kube-query ev --for pod/web-5d9c6 -n prod   # events about one object
kube-query ev 'BackOff' -A                  # regex on reason/object/message
kube-query ev --limit 200                   # more rows
```

Compact event shape: `lastSeen, type, reason, object (Kind/name), namespace, count, source, message`.

## 8. Helm (read-only): `kube-query helm`

Helm 3 stores releases as Secrets (`sh.helm.release.v1.<name>.v<rev>`,
label `owner=helm`). kube-query lists them without the helm binary and best-effort
decodes chart metadata + effective values from the payload.

```bash
kube-query helm ls -A               # name, revision, status, chart, updated
kube-query helm show wordpress      # + chart meta and effective values
kube-query helm show grafana -n monitoring -o json
```

If a payload can't be decoded (very old/hand-modified releases), the release
still lists with `chart: ?`.

## 9. External Secrets Operator: `kube-query eso`

```bash
kube-query eso -A                    # ExternalSecrets: store, target, Ready, reason
kube-query eso --stores -A           # SecretStores + ClusterSecretStores
```

Missing ESO CRDs produce a clear message instead of a stack trace.

## 10. Output formats

| `-o` | What you get | Best for |
|---|---|---|
| `yaml` (default) | compact YAML, key order preserved | agents, diffs, humans |
| `json` | same data, JSON | programmatic use |
| `rich` | aligned, colored tables (auto-detects TTY) | interactive terminal |
| `md` | markdown tables; objects as fenced yaml blocks | chat/PR comments, agent reports |
| `tree` | ownership tree view | workload chains |

`KQ_OUTPUT=rich` in your shell profile gives you tables by default while
agents (no env) keep YAML.

## 11. Safety model

- kube-query contains **no code path** that issues POST/PUT/PATCH/DELETE — the HTTP
  layer only implements `GET`.
- Secrets values are redacted unless `--reveal` is passed explicitly.
- RBAC still applies: kube-query shows exactly what your credentials can read.
- Fixing things is deliberately out of scope: use kubectl/gitops/helm for that.
