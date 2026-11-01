# kube-query

**`kq` — read-only Kubernetes queries for humans and AI agents.**

kubectl is a loaded gun in an agent's hands. kube-query is the safe scope:
it **captures cluster state and diagnoses problems**, and *cannot* create,
update or delete anything — the HTTP layer implements `GET` and nothing else.
Compact YAML by default, with rich tables, markdown, JSON and ownership
trees on request. Built-ins, shortnames, CRDs, Helm releases and External
Secrets Operator — one small, fast binary-ish CLI.

```
kq p l -A                    # all pods, all namespaces
kq p desc web-5d9c6 -n prod  # status + reasons + restarts + events, one doc
kq logs web-5d9c6 -n prod -c app --previous
kq tree deploy/web -n prod   # Deployment -> ReplicaSet -> Pods, health per node
kq overview                  # whole-cluster snapshot, problems first
```

> kq is the **diagnosis** half of the loop. The **fix** half belongs to other
> tools (kubectl apply, gitops, helm) — by design.

## Why

| Problem with `kubectl` for agents | kube-query |
|---|---|
| can `delete`/`scale`/`apply` — one hallucinated flag away from an incident | GET-only; no mutating code path exists |
| `-o yaml` dumps managedFields/uid/annotations noise into context | compact by default, `-v`/`-vv` for more |
| output shaped for terminals, not reasoning | yaml/json data, md reports, tree views |
| 100+ verbs to misuse | ~15 read verbs with aliases (`kq p l`, `kq d l`, `kq c l`) |
| helm/ESO/CRD troubleshooting needs extra tools | helm releases, ESO status and CRDs built in |

## Install

Requires Python 3.13+.

```bash
pipx install kubeq              # or: uv tool install kubeq / uvx kubeq
kq ctx ls                        # verify — reads your existing kubeconfig
```

From source:

```bash
git clone <repo> && cd kube-query
make setup                       # .venv (py3.13) + dev deps
.venv/bin/kq overview
```

No cluster to try it on? `make demo` boots a fake API server with broken
pods, a stuck deployment, helm releases and ESO resources to poke at.

## Commands

| Command (aliases) | Purpose |
|---|---|
| `kq overview` (`ov`, `o`, `health`) | cluster snapshot: problem pods, nodes, deployments, PVCs, warnings |
| `kq pod` (`pods`, `p`, `po`) | `l [REGEX] [-A\|-n\|-l\|--field-selector]` · `NAME` · `desc NAME` · `logs NAME` |
| `kq deploy` (`deployments`, `dep`, `d`) | same shape for deployments |
| `kq ns` (`n`) · `kq node` (`no`) · `kq svc` · `kq cm` | namespaces, nodes, services, configmaps |
| `kq secret` (`sec`) | values hidden; `kq sec NAME --reveal` decodes (explicit opt-in) |
| `kq ev` (`events`, `e`) | events, newest first: `--type Warning --since 2h --for pod/NAME` |
| `kq get RESOURCE[/NAME]` (`g`) | any resource incl. CRDs; `kq api` lists all types |
| `kq describe` (`desc`) | diagnosis bundle: summary + object + children + events |
| `kq tree RESOURCE/NAME` (`t`) | ownership tree (`deploy/web`, `cronjob/x`, `node/y`) |
| `kq helm` (`h`) | releases read-only from Helm's release Secrets; `show NAME` adds values |
| `kq eso` | ExternalSecret sync status (`--stores` for SecretStores) |
| `kq ctx` (`c`) | kubeconfig contexts (`kq c l`), no API calls |
| `kq ver` | client + server version (which cluster am I on?) |

Shared flags: `-n NS` · `-A` · `-l SELECTOR` · `--field-selector` · `-f/--filter REGEX`
· `-o yaml|json|rich|md|tree` (default yaml, `KQ_OUTPUT` env) · `-v`/`-vv`.

## Output

```bash
kq overview -o rich      # aligned, colored tables (humans)
kq p l -A -o md          # markdown tables (tickets, chat, agent reports)
kq p web-5d9c6 -o json   # machine-readable
kq d l -o tree           # ownership view
```

Stdout is always the payload (parseable); commentary goes to stderr as
`#`-prefixed notes. Exit codes: `0` ok, `1` error (one actionable sentence),
`2` usage.

## For AI agents

Give your agent (Claude Code, opencode, codex, …) the one-file skill:
[`SKILL.md`](SKILL.md) — command map, the 5-move triage loop, output
contract, failure-signature table, and rules of engagement. Suggested
system-prompt line:

> Use `kq` (read-only) to inspect the Kubernetes cluster: start with
> `kq overview`, then `kq p desc <pod>`, `kq logs`, `kq tree`, `kq ev`.
> Never attempt cluster changes with kq; propose them for kubectl instead.

## Documentation

| Doc | Contents |
|---|---|
| [docs/usage.md](docs/usage.md) | full manual: every command, flag, format, exit code |
| [docs/tutorial.md](docs/tutorial.md) | hands-on: debugging a broken deployment end-to-end |
| [docs/architecture.md](docs/architecture.md) | module map + data flow diagrams |
| [docs/extending.md](docs/extending.md) | add commands, columns, formats (with examples) |
| [docs/roadmap.md](docs/roadmap.md) | what's next + explicit non-goals |
| [CHANGELOG.md](CHANGELOG.md) | releases |

## Development

```bash
make setup          # venv + deps
make check          # the full gate: ruff lint + format check + pytest + build
make demo           # fake-cluster playground
make tag            # run the gate, then create v<version> tag
git push origin vX.Y.Z   # CI publishes to PyPI (trusted publishing)
```

Pipeline: `make check` mirrors CI exactly; pushing a `v*` tag runs the same
gate, builds sdist+wheel, verifies tag/version match, and publishes via
GitHub Actions to PyPI — no stored secrets (OIDC trusted publishing).

Tests are network-free: unit suites plus smoke tests that drive the real CLI
against an in-process fake Kubernetes API server.

## Safety model

1. `kube_query/http.py` exposes `raw_get` only — there is no verb parameter anywhere.
2. `kube_query/access.py` builds list/get/log paths only.
3. Secret values are redacted unless `--reveal` is passed explicitly.
4. Your RBAC still applies — kq reads exactly what your credentials allow.

## License

MIT — see [LICENSE](LICENSE).
