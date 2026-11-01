# Roadmap / TODO

## Now (v0.1) — shipped

- [x] Read-only core: discovery-driven get/list for built-ins + CRDs
- [x] Compact YAML default; json / rich / md / tree formats; -v/-vv verbosity
- [x] Sugar groups with aliases (p/pod/po, d/dep/deploy, n/ns, no/node, sec,
      svc, cm) + implicit `show` (`kube-query p NAME`) + default `ls`
- [x] `overview` cluster snapshot with fault-tolerant sections
- [x] `describe` bundles (summary + object + children + events)
- [x] Ownership trees (deploy→rs→pod, cronjob→job→pod, node→pods)
- [x] Events with type/since/object filters
- [x] Pod logs (tail, previous, since, timestamps, all-containers)
- [x] Helm releases (ls + show with chart/values decoding, no helm binary)
- [x] ESO views (ExternalSecrets + SecretStores)
- [x] Contexts, api-resources, version
- [x] Secret redaction + explicit `--reveal`; configmap value capping
- [x] Fake-API-server smoke tests; ruff-clean; SKILL.md for agents

## Next (v0.2)

- [ ] `kube-query explain RESOURCE` — field schema from OpenAPI (agent-friendly)
- [ ] `kube-query top` / metrics in `overview` (metrics.k8s.io, optional + tolerated)
- [ ] `kube-query diff-args`: `--since` on lists (server-side or resourceVersion diff)
- [ ] JSONPath/column selection: `-o custom=NAME:metadata.name,...`
- [ ] `--watch`-style polling helper for agents (`kube-query p l --wait-ready NAME`)
      (poll loop, still read-only)
- [ ] Shell completion (click) for resources and object names
- [ ] `kube-query yaml`/`kube-query manifest` — fetch rendered workload spec with defaults
      filled in (template + PodTemplate spec merged view)
- [ ] Helm: decode `--revision N`, values-only output (`kube-query helm values NAME`)
- [ ] ESO: `--provider` filter, condition history

## Later (v0.3+)

- [ ] MCP server mode exposing the same core (kube-query stays the engine; agents
      gain a typed tool interface)
- [ ] `kube-query snapshot` — tarball of cluster state (yaml bundle) for offline
      debugging / attaching to tickets
- [ ] Multi-cluster overview (iterate contexts, merge reports)
- [ ] Caching layer with TTL for discovery across invocations (`~/.cache/kube-query`)
- [ ] Structured exit codes (e.g. 3 = "found problems" for `overview` in CI)
- [ ] i18n-free plain errors contract documented for agents (stable IDs)

## Non-goals

- Any create/update/delete/patch/exec/port-forward — forever.
- A dashboard/UI — the terminal + agent surfaces are the product.
- Talking to Tiller or requiring the helm binary — release secrets only.
