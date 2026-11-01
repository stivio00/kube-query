# Tutorial — debug a broken deployment with kube-query

A hands-on walkthrough of the intended triage loop. Reproduce it against any
cluster (a `kind`/`minikube` cluster works) by deploying something broken, or
just follow along.

## 0. Know where you are

```bash
$ kube-query ctx ls
* fake   fake   http://127.0.0.1:8001   fake   default
  fake2  fake   http://127.0.0.1:8001   fake   prod
```

The `*` marks the active context. Everything below runs there — or pass
`--ctx <name>` per invocation.

## 1. Snapshot the cluster

```bash
$ kube-query overview
context: fake
scope: all namespaces
nodes:
  total: 2
  healthy: 1
  problems:
  - name: node-2
    status: NotReady
    problems:
    - DiskPressure
pods:
  total: 6
  healthy: 4
  problems:
  - name: web-7f9c6-b
    namespace: default
    status: CrashLoopBackOff
    restarts: 7
    node: node-1
    age: 1d
  - name: web-7f9c6-c
    namespace: default
    status: ContainerCreating
    restarts: 0
    node: node-1
    age: 2m
deployments:
  total: 2
  unavailable:
  - name: web
    namespace: default
    desired: 3
    ready: 1
    available: 1
warningEvents:
  window: 1h
  count: 2
  recent:
  - lastSeen: '2026-11-01T10:59:00Z'
    type: Warning
    reason: BackOff
    object: Pod/web-7f9c6-b
    message: Back-off restarting failed container app in pod web-7f9c6-b_default
  - lastSeen: '2026-11-01T10:58:00Z'
    type: Warning
    reason: FailedScheduling
    object: Pod/web-7f9c6-c
    message: '0/2 nodes are available: 1 node(s) had untolerated taint, 1 Insufficient memory.'
summary:
  issues: 4
  healthy: false
```

Two problem pods, one bad node, one stuck deployment, two distinct warning
reasons. In ~40 lines of YAML you already know more than most dashboards
show. Now drill down.

## 2. Diagnose the crashing pod

```bash
$ kube-query p desc web-7f9c6-b
summary:
  kind: Pod
  name: web-7f9c6-b
  age: 1d
  namespace: default
  status: CrashLoopBackOff
  ready: 0/1
  restarts: 7
  healthy: false
  node: node-1
  containers:
  - name: app
    image: nginx:1.27
    ready: false
    restarts: 7
    state: Waiting
    reason: CrashLoopBackOff
    lastReason: Error
object:
  kind: Pod
  metadata:
    name: web-7f9c6-b
    namespace: default
    creationTimestamp: '2026-10-31T10:00:00Z'
    labels:
      app: web
  spec:
    containers:
    - image: nginx:1.27
      name: app
  status:
    containerStatuses:
    - image: nginx:1.27
      lastState:
        terminated:
          reason: Error
          exitCode: 1
      name: app
      ready: false
      restartCount: 7
      state:
        waiting:
          message: back-off 5m0s restarting failed container
          reason: CrashLoopBackOff
events:
- lastSeen: '2026-11-01T10:59:00Z'
  type: Warning
  reason: BackOff
  object: Pod/web-7f9c6-b
  count: 8
  message: Back-off restarting failed container app in pod web-7f9c6-b_default
```

Last termination reason `Error` with exit code 1 — the app is crashing at
startup. Get the crash output:

```bash
$ kube-query p logs web-7f9c6-b --previous
previous crash log line A
previous crash log line B
```

Suppose the log shows `Error: cannot read /etc/web/config.yaml: permission
denied`. Check what the pod actually mounts — the config comes from a
ConfigMap:

```bash
$ kube-query p show web-7f9c6-b -v      # -v keeps uid/volumes details
$ kube-query cm show app-config         # inspect the data (long values are capped)
```

Diagnosis: mount path/config mismatch. The **fix** (edit the ConfigMap or the
deployment spec) belongs to kubectl/gitops — kube-query deliberately can't do it.

## 3. Diagnose the pending pod

```bash
$ kube-query ev --for pod/web-7f9c6-c
- lastSeen: '2026-11-01T10:58:00Z'
  type: Warning
  reason: FailedScheduling
  object: Pod/web-7f9c6-c
  count: 2
  message: '0/2 nodes are available: 1 node(s) had untolerated taint, 1 Insufficient memory.'
$ kube-query no l -o rich
  NAME     STATUS     ROLES           AGE   VERSION
  node-1   Ready      control-plane   8w    v1.31.1
  node-2   NotReady   <none>          8w    v1.31.1
```

One node tainted for control-plane only, the other out of memory and
NotReady. Not a pod problem — a capacity/node problem.

## 4. See the rollout as a whole

```bash
$ kube-query tree deploy/web
Deployment web - 1/3 - 8w
├── ReplicaSet web-7f9c6 - 2/3
│   ├── Pod web-7f9c6-a - Running - ready 1/1 - 1d
│   ├── Pod web-7f9c6-b - CrashLoopBackOff - ready 0/1 - 7 restarts - 1d
│   └── Pod web-7f9c6-c - ContainerCreating - 2m
```

Same story, one picture: 1 healthy, 1 crash-looping, 1 unschedulable.

## 5. Markdown report for the ticket

```bash
kube-query overview -o md > incident.md
kube-query p desc web-7f9c6-b -o md >> incident.md
```

`-o md` renders headings + tables + fenced YAML blocks — paste straight into
a GitHub issue or a chat with a human.

## 6. Helm and CRDs in the same loop

```bash
$ kube-query helm ls -A
  NAME         NAMESPACE   REVISION   STATUS     CHART              UPDATED
  wordpress    default     2          deployed   wordpress-15.2.1   3h
  grafana      prod        1          deployed   grafana-8.5.0      2d

$ kube-query helm show grafana -n prod      # effective values — is persistence off by accident?

$ kube-query eso -A                         # ExternalSecrets failing to sync?
  NAME         NAMESPACE   STORE            TARGET           READY   REASON
  my-secret    default     SecretStore/vault target-secret    True    SecretSynced
  broken-es    default     SecretStore/vault broken-target    False   StoreError
```

## Takeaways

1. `overview` first — it tells you where to look.
2. `desc` gives you the full picture of one object in a single document.
3. `logs --previous` is the crash message; events explain scheduling.
4. `tree` shows rollout shape; `-o md` writes the report.
5. kube-query stops at *diagnosis* — the fix goes through kubectl/gitops/helm, on purpose.
