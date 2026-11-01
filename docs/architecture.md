# Architecture

## Design goals

1. **Read-only by construction** — the HTTP layer implements `GET` only; there
   is no code path that can mutate a cluster.
2. **Agent-first output** — compact, structured, lossless-enough YAML by
   default; progressive disclosure via formats and verbosity.
3. **One core, many surfaces** — everything (pods, CRDs, helm, ESO) flows
   through the same discovery → resolve → fetch → summarize → render pipeline.
4. **Fast, boring dependencies** — click, rich, pyyaml + the official
   `kubernetes` client's transport. No operator, no daemon, no cluster-side
   install.

## Module map

```
src/kube_query/
├── cli.py              root click group, global flags, epilog, registration
├── cli_kit.py          KqGroup (alias-hiding), ResourceGroup (implicit show,
│                       default ls), shared option decorators
├── config.py           Settings (per-invocation options) + Ctx (lazy cluster
│                       connection, kubeconfig introspection, discovery cache)
├── http.py             raw GET transport (modern + legacy kubernetes client),
│                       auth (bearer/basic fallback), timeouts, error mapping
├── discovery.py        /api + /apis discovery -> ApiResource list; name
│                       resolution (plural/singular/kind/shortname/group-
│                       qualified) with suggestions; RESOURCE[/NAME] parsing
├── access.py           URL building per ApiResource; list_objects /
│                       get_object / pod_logs / server_version
├── cleanup.py          compaction (verbosity levels), configmap capping,
│                       secret redaction/reveal
├── summarize.py        status/health computation (pods, deployments, nodes,
│                       services), ages, table columns, describe summaries
├── output.py           format resolution (flag > KQ_OUTPUT > yaml), YAML/JSON
│                       emitters, rich tables, markdown tables, status colors
├── events.py           event listing/filtering/compaction (shared by 3 cmds)
├── tree.py             ownership graph (child index by ownerRef uid) + rich/md
│                       tree renderers
├── helm.py             helm release secrets: label scan, gzip+protobuf
│                       best-effort decode (chart meta, values)
├── eso.py              ExternalSecret / SecretStore status rows
└── commands/           thin click commands over the core
    ├── _impl.py        shared list/show renderers, namespace + filter logic
    ├── groups.py       sugar-group factory (pod/ns/deploy/svc/sec/cm/node)
    ├── get.py describe.py logs.py tree_cmd.py events_cmd.py overview.py
    ├── helm_cmd.py eso_cmd.py contexts.py api_resources.py version.py
    └── __init__.py     command registry + aliases
```

Dependency rule: `commands → core modules → {http, errors}`. Core modules
never import from `commands`, and `http.py` is the only module that touches
the network.

## Data flow

```
                      ┌────────────────────────────────────────────────┐
                      │  CLI layer (click)                             │
                      │  kube-query p l web -n prod -o rich                    │
                      └───────────────┬────────────────────────────────┘
                                      │  Settings → Eff (resolved ns/format/verbosity)
                                      ▼
        ┌──────────────────┐   resolve("pods")   ┌──────────────────────┐
        │ config.Ctx       │────────────────────▶│ discovery            │
        │ lazy ApiClient   │   cached list of    │ GET /api, /api/v1,   │
        │ kubeconfig loaded│   ApiResource       │ /apis, /apis/<g>/<v> │
        │ on first use     │◀────────────────────│ (preferred versions) │
        └────────┬─────────┘                     └──────────────────────┘
                 │ resource_path(entry, ns) → /api/v1/namespaces/prod/pods
                 ▼
        ┌──────────────────┐    only GET, auth from kubeconfig (bearer,
        │ http.raw_get     │    basic fallback, TLS client certs, exec
        └────────┬─────────┘    tokens via the official client's transport)
                 │ JSON bytes
                 ▼
        ┌───────────────────────────────────────────────────────────────┐
        │ pipeline per command                                           │
        │                                                                │
        │  list:  items ─▶ filter(regex) ─▶ sort(ns,name) ─▶ render      │
        │  show:  object ─▶ compact(verbosity) ─▶ [secret/cm transform]  │
        │  desc:  object ─▶ summary_for ─▶ children(ownerRef index)      │
        │               ─▶ related_events ─▶ document                    │
        │  tree:  root ─▶ child_index(ns: pods+rs+jobs) ─▶ forest        │
        │  helm:  secrets(owner=helm) ─▶ latest rev ─▶ gunzip+protobuf   │
        │               ─▶ chart meta + values                           │
        └───────────────────────────┬───────────────────────────────────┘
                                    ▼
        ┌───────────────────────────────────────────────────────────────┐
        │ output.emit / render                                          │
        │  yaml, json → stdout (parseable)                              │
        │  rich → colored tables/trees (TTY-aware)                      │
        │  md   → markdown tables + fenced yaml                         │
        │  tree → rich ownership view                                   │
        │  notes → stderr with '# ' prefix                              │
        └───────────────────────────────────────────────────────────────┘
```

### Request budget

- `kube-query <group> ls`: 1 discovery pass (≈ 2 + #groups GETs, cached per process)
  + 1 list call.
- `desc`: get object + (pods, replicasets, jobs) in the namespace + events.
- `overview`: nodes + pods + deployments + pvcs + events — each section
  independently fault-tolerant (RBAC holes become `unavailable`).
- `helm ls`: one secrets list (`labelSelector=owner=helm`) + payload decode
  of only the latest revision per release.

### Error model

Everything user-facing is a `KqError` (a `click.ClickException`): one
actionable sentence + optional `Hint:` line, exit code 1. 404s include the
command that would list candidates. Unknown resources include close-match
suggestions. HTTP/transport failures suggest checking `kube-query ctx` and network.

## The read-only guarantee

Two mechanisms, one intent:

1. `http.py` exposes exactly `raw_get` / `get_json` / `get_text`. No verb
   parameter exists anywhere in the codebase.
2. `access.py` is the only URL builder and only builds list/get/log paths.

Enforced socially too: the repo README and SKILL.md state that remediation
belongs to other tools.

## Testing strategy

- **Unit tests** (`tests/test_*.py`): discovery resolution, compaction,
   status computation, helm protobuf decoding, output rendering — no network.
- **Smoke tests** (`tests/test_smoke.py`): a threaded fake API server
  (`tests/conftest.py`) serving realistic fixtures (discovery documents,
  objects, subresources, label/field selectors, 404s) with a generated
  kubeconfig; the full CLI is driven via `click.testing.CliRunner` —
  context→discovery→http→render, end to end, in milliseconds.

## Performance notes

Discovery is cached per invocation (a `Ctx` attribute), so multi-section
commands pay it once. Lists are unpaginated single GETs (complete results,
one round trip). Age strings and tables are computed lazily at render time.
