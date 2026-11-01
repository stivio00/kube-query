# Changelog

All notable changes to kube-query are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows SemVer.

## [0.1.1] — 2026-11-01

### Changed
- **PyPI distribution renamed to `kubeq`** so `uvx kubeq` / `pipx install kubeq`
  work directly (the short `kq` project name on PyPI belongs to an unrelated
  Kafka library). The CLI is unchanged; the wheel now provides three
  equivalent entry points: `kq`, `kube-query`, `kubeq`.
- The original `kube-query` 0.1.0 release remains on PyPI as the first
  published artifact; `kubeq` is the canonical distribution going forward.

### Added
- `kubeq` console script (alias of `kq`).
- CI smoke-checks all three installed entry points.

## [0.1.0] — 2026-11-01

First public release (published to PyPI as `kube-query`).

### Added
- Read-only core (GET-only HTTP layer) with kubeconfig/in-cluster auth:
  bearer tokens, basic auth, TLS client certs, exec plugin (EKS-style).
- Discovery-driven resource resolution: plurals, singulars, kinds,
  shortnames, group-qualified (`deployments.apps`) and apiVersion-qualified
  (`apps/v1/deployments`) forms, with close-match suggestions; CRDs included.
- Output: compact YAML (default), JSON, rich tables/trees, markdown,
  ownership-tree view; verbosity levels (`-v` system metadata, `-vv` raw).
- Commands: `overview`, `pod` (`p`, `po`), `deploy` (`dep`, `d`), `ns` (`n`),
  `node` (`no`), `svc`, `secret` (`sec`, with `--reveal`), `cm`, `ev`
  (`events`), `logs`, `describe` (`desc`), `tree` (`t`), `get` (`g`),
  `helm` (`h`), `eso`, `ctx` (`c`), `api` (`api-resources`), `version` (`ver`).
- Sugar groups accept `kq p NAME` (implicit show) and run `ls` by default;
  options accepted before or after the subcommand.
- Helm releases decoded read-only from release Secrets (gzip+protobuf
  best-effort: chart metadata + effective values, helm2 JSON fallback).
- External Secrets Operator views: ExternalSecrets and SecretStores.
- Ownership trees: Deployment→ReplicaSet→Pod, CronJob→Job→Pod, Node→pods.
- Events with `--type`, `--since`, `--for KIND/NAME`, regex, limit.
- Cluster `overview` snapshot with fault-tolerant sections (RBAC holes
  reported, not fatal).
- Secret redaction by default; ConfigMap value capping; agent notes on
  stderr keeping stdout parseable.
- `SKILL.md` agent skill file; docs: usage, tutorial, architecture,
  extending, roadmap.
- Pipeline: Makefile staged gates, GitHub Actions CI + tag-driven PyPI
  release (trusted publishing), `make demo` fake-cluster playground.
- Tests: unit suites + end-to-end smoke tests against a fake API server.

### Security
- No mutating verbs exist in the codebase; secrets are redacted unless
  `--reveal` is passed explicitly.
