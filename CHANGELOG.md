# Changelog

All notable changes to kube-query are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows SemVer.

## [0.1.1] — 2026-11-01

### Changed
- **Single executable: `kube-query`.** The short `kq` console script was
  dropped — the `kq` name on PyPI belongs to an unrelated Kafka library and
  PyPI's similarity rules block close variants (`kubeq`), so shipping a `kq`
  binary only invited confusion. Want it short? `alias kq=kube-query`.
- Version is now single-sourced from `kube_query.__version__` (pyproject pulls
  it dynamically), so the release gate's tag↔version check can't diverge.
- CI actions bumped to Node 24 majors (checkout v7, setup-python v7,
  upload-artifact v7, gh-release v3).
- Docs standardized on `uvx kube-query` / `uv tool install kube-query`.

### Notes
- The distribution briefly moved to the name `kubeq`; reverted because PyPI's
  name-similarity guard rejects it (one letter from the existing `kube`
  library). The package remains **`kube-query`**.

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
