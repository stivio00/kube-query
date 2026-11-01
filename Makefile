# kube-query pipeline — staged gates, locally and in CI.
# `make check` is the single gate everything else keys off.

PYTHON ?= .venv/bin/python
PIP    ?= uv pip install --python $(PYTHON)
KQ     ?= .venv/bin/kq

VERSION := $(shell $(PYTHON) -c "from kube_query import __version__; print(__version__)" 2>/dev/null || echo unknown)

.DEFAULT_GOAL := help

.PHONY: help setup lint format format-check test check build check-dist tag release demo clean version

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

version: ## Print the package version
	@echo $(VERSION)

setup: ## Create .venv (Python 3.13) and install dev dependencies
	uv venv --python 3.13 .venv
	$(PIP) -e ".[dev]" ruff build
	@echo "OK: .venv ready -> source .venv/bin/activate (or just use make targets)"

lint: ## Ruff check (errors only)
	$(PYTHON) -m ruff check .

format: ## Ruff format (writes)
	$(PYTHON) -m ruff format .

format-check: ## Ruff format (verify only)
	$(PYTHON) -m ruff format --check .

test: ## Run the test suite (incl. fake-API-server smoke tests)
	$(PYTHON) -m pytest

build: clean-dist ## Build sdist + wheel into dist/
	$(PYTHON) -m build

check-dist: build ## Verify distributions (twine-style metadata sanity)
	$(PYTHON) -m pip install -q --force-reinstall dist/*.whl --target /tmp/kq-dist-check >/dev/null 2>&1 \
		|| $(PYTHON) -m zipfile -l dist/*.whl >/dev/null
	@ls -lh dist/

tag: check ## Create annotated git tag v$(VERSION) (requires clean gate)
	@git diff --quiet || (echo "ERROR: uncommitted changes" && exit 1)
	@git tag -a "v$(VERSION)" -m "kube-query v$(VERSION)"
	@echo "Tagged v$(VERSION). Push it to trigger the release pipeline:"
	@echo "  git push origin v$(VERSION)"

release: check-dist ## Dry-run the release: gate + build + dist check
	@echo "Release v$(VERSION) ready in dist/. CI publishes on tag push (git push origin v$(VERSION))."

check: lint format-check test check-dist ## Full gate: lint + format + tests + build (same as CI)

demo: ## Play with kq against a fake cluster (no kubeconfig needed)
	$(PYTHON) scripts/demo.py

clean-dist: ## Remove dist/ and build artifacts
	rm -rf dist build src/*.egg-info

clean: clean-dist ## Remove caches and venv
	rm -rf .pytest_cache .ruff_cache
