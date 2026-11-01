# Extending kube-query

The core is deliberately small and generic. Most extensions touch exactly one
layer.

## Where things live

| You want to add... | Touch... |
|---|---|
| a new sugar group (`kube-query sts l`, `kube-query job l`) | `commands/groups.py` — one `make_resource_group(...)` call + registration in `commands/__init__.py` |
| smart table columns for a kind | `summarize.COLUMNS` (and `summary_for` for describe) |
| a new output format (`-o csv`) | `output.py`: add to `FORMATS`, an emitter, and branch in `render_list`/`render_single` |
| a new triage section in overview | `commands/overview.py::build_overview` (wrap in `_section` for RBAC tolerance) |
| ownership children for new workload types | `tree.CHILD_CANDIDATES` |
| a new CRD-aware view (like `eso`) | a small module like `eso.py` + thin command in `commands/` |

## Example: add a StatefulSet group

```python
# commands/groups.py (bottom of file)
STATEFULSETS = make_resource_group(
    name="sts",
    plural="statefulsets",
    group_help="StatefulSets: ls | NAME | desc NAME | tree sts/NAME.",
)
```

```python
# commands/__init__.py, inside register()
main.add_command(STATEFULSETS, "sts")
main.add_command(STATEFULSETS, "statefulsets", alias=True)
main.add_command(STATEFULSETS, "statefulset", alias=True)
```

That's the whole change — the group automatically gets `ls` (with `-A/-n/-l/-f/-o`),
`show`, `desc`, tree support and CRD-grade name resolution, because it rides
the generic core.

## Example: better columns for a kind

```python
# summarize.py
COLUMNS["statefulset"] = [
    ("NAME", _name),
    (
        "READY",
        lambda o: f"{dig(o, 'status', 'readyReplicas', default=0) or 0}/{dig(o, 'spec', 'replicas', default=0) or 0}",
    ),
    ("AGE", _age),
]
```

Columns are `(header, fn)` pairs shared by the `rich` and `md` renderers;
status-like headers (`STATUS`, `READY`, `TYPE`) get automatic coloring.

## Example: a new output format

1. Add the name to `output.FORMATS` (the click `Choice` updates everywhere).
2. Implement the renderer (mirroring `md_table` / `print_object`).
3. Branch on it in `_impl.render_list` / `render_single` / command-specific
   renderers.

Format resolution order is: command flag → group flag → root flag →
`KQ_OUTPUT` env → default. All of that comes free from
`Settings.effect()`.

## Rules for extensions

- **Never add mutating verbs.** `http.py` must stay GET-only; this is the
  product's core promise.
- Errors: raise `KqError` with one actionable sentence (+ `Hint:` line).
- Every new command gets: the shared option decorators from `cli_kit`
  (`list_options` / `show_options`), `Settings.effect()` for option
  resolution, and at least one smoke test against the fake API server.
- Prefer adding data to `summarize.summary_for` (describe) over inventing new
  document shapes.
- Keep unit tests network-free; anything needing a cluster goes in
  `test_smoke.py` with fixtures in `tests/fixtures.py`.

## Testing checklist for a new command

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest
uv run kube-query <your command> --help      # help text stays one scannable line
```
