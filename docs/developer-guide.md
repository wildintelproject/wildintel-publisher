# Developer Guide

This page is for anyone extending `wildintel-publisher` itself — adding a new product
type or a new repository integration — rather than someone just publishing a dataset.
If you only want to publish something, see the [Products](products.md) and
[Publishing Guide](publishing-guide.md) pages instead.

---

## Commit messages

Commits follow [Conventional Commits](https://www.conventionalcommits.org/): a single
type prefix, a colon, and a short imperative description.

1. Pick **one** type prefix — don't combine two:
   - `feat` — new functionality (a new command, adapter, UI feature...).
   - `fix` — a bug fix.
   - `docs` — documentation only (`docs/`, `README.md`, docstrings).
   - `chore` — maintenance with no behavior change (deps, formatting, config).
   - `ci` — GitHub Actions workflows or other CI/CD setup.
   - `refactor` — restructuring code with no behavior change.
   - `test` — adding or fixing tests only.
2. Write the summary line in the imperative mood ("add", "fix", "trigger" — not "added"/
   "fixes"/"triggered"), lower case after the colon, no trailing period, ideally under
   ~70 characters:
   ```
   ci: run docs workflow also on push to development
   ```
3. If the change needs more explanation than the summary allows, add a blank line and a
   short body explaining *why*, not what (the diff already shows what).
4. Note that `.github/workflows/docs.yml` only runs on pushes to `main`/`development`
   that touch `docs/**`, `mkdocs.yml`, or `README.md` (plus `v*.*.*` tags) — a `docs`/`ci`
   commit that doesn't touch those paths won't trigger it.

---

## Changelog

`CHANGELOG.md` follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Add an
entry under `## Upcoming release` for any user-facing change (new feature, bug fix,
behavior change) as part of the same commit/PR that makes the change — not as a separate
step afterwards.

- The CLI and the web app are tagged and released independently (`vX.Y.Z` vs.
  `web-vX.Y.Z`), so once a release is cut, its entries move from `## Upcoming release`
  into a dated section headed `### [CLI vX.Y.Z](...)` or `### [Web vX.Y.Z](...)` — see the
  existing entries for the exact link format.
- `.github/workflows/release-cli.yml` and `release-web.yml` read straight from
  `CHANGELOG.md` (via `awk`) to populate GitHub Release notes: the stable-release step
  matches the `### [CLI vX.Y.Z]`/`### [Web vX.Y.Z]` header for the tag being released, and
  the dev-build step matches `## Upcoming release`. A change that isn't logged in the
  changelog won't show up in the release notes, even if it's in the diff.

---

## Project layout

```
wildintel_publisher/                  ← the CLI package
├── commands/                         ← Typer command groups (trapper, product, hfh, zenodo, b2share)
└── services/
    ├── product.py                    ← ProductAdapter protocol + metadata.json envelope
    ├── camtrapdp_adapter.py           ← ProductAdapter for Camtrap DP
    ├── yolo_adapter.py                ← ProductAdapter for YOLO
    ├── common.py                     ← shared helpers (README/CITATION.cff rendering, checksums, zip bundling...)
    ├── doi_populate.py               ← cross-repository DOI reflection (web app only)
    ├── hfh.py / zenodo.py / b2share.py  ← one module per repository integration
    └── trapper.py                    ← Trapper API client (Camtrap DP fetching only)

wildintel_publisher_web/              ← the web app (FastAPI backend + React frontend)
├── backend/src/services/             ← thin wrappers around wildintel_publisher.services.*
│   └── publish_orchestrator.py       ← multi-repo upload-all → populate → lock-all sequencing
└── frontend/src/                     ← the wizard UI
```

The web backend does not reimplement any publishing logic — it depends on
`wildintel_publisher` as an editable path dependency and calls straight into
`wildintel_publisher.services.*`, wrapping each blocking call in `asyncio.to_thread` so
the CLI's own synchronous functions can run from FastAPI's async routes. A new product
type or repository integration written in `wildintel_publisher/services/` is
automatically available to both the CLI and the web app — there is nothing to
duplicate on the web side beyond a router/schema/UI form for it.

---

## Adding a new product type

A **product type** (`camtrapdp`, `yolo`, ...) is anything `wildintel-publisher` can turn
into a publishable export. Every repository integration (`hfh.py`/`zenodo.py`/
`b2share.py`) is written against the generic `metadata.json` envelope described in
`wildintel_publisher/services/product.py` — it never inspects the raw product's own
format directly. This is what lets `hfh prepare --product-type yolo` and
`hfh prepare --product-type camtrapdp` share the exact same command implementation.

### 1. Implement the `ProductAdapter` protocol

A `ProductAdapter` (see the `Protocol` class in `services/product.py`) is one class with
a fixed set of methods, implemented once per product type
(`camtrapdp_adapter.CamtrapDPAdapter`, `yolo_adapter.YoloAdapter`):

| Method | Responsibility |
|---|---|
| `validate(input_dir)` | Raise `RuntimeError` if `input_dir` doesn't look like a valid product of this type. |
| `extract_metadata(input_dir)` | Best-effort read `title`/`description`/`version`/`license`/`authors`/`homepage` from the raw product — return `None`/`[]` for anything it can't determine, rather than raising (the UI collects the rest from the user afterwards). |
| `prepare(input_dir, output_dir, *, mirror, image_timeout)` | Copy/generate this product type's own files into `output_dir`. |
| `extract_core_files(output_dir, target_dir)` | Copy just this product type's own files (not a repository's generated extras) out of an already-prepared export — used when chaining one repository's output into the next repository's input. |
| `link_media_to_hfh(output_dir, hfh_repo_id)` | Rewrite wherever this product type references its media to a Hugging Face Hub URL — return `0` (no-op) if the product type has no such reference to rewrite. |
| `bundle_local_zip(output_dir, zip_path, *, embed_images)` | Write a single self-contained zip of this product's own files, for repositories (Zenodo/B2SHARE) that don't host folder structures. |
| `readme_context(output_dir)` | Extra template variables specific to this product type, merged into the generic README context — `{}` if nothing extra is needed. |

### 2. Register it

At the bottom of your new adapter module:

```python
product.register_adapter(MyNewAdapter())
```

and make sure that module gets imported somewhere on startup (see how
`camtrapdp_adapter.py`/`yolo_adapter.py` are imported) — `get_adapter()`/
`registered_product_types()` only see adapters that have actually run their
`register_adapter()` call.

### 3. That's it for repository integrations

Every repository's `prepare`/`upload`/`release` command already works purely in terms of
`get_adapter(product_type)` and the generic `metadata.json` fields — adding a new product
type does not require touching `hfh.py`, `zenodo.py`, or `b2share.py` at all.

### 4. Write the docs and tests

- A `docs/product-<name>.md` page (see `product-camtrapdp.md`/`product-yolo.md` for the
  expected shape: what it is, raw layout, turning it into a publishable product,
  publishing it), linked from `docs/products.md`'s table and `mkdocs.yml`'s nav.
  `docs/products.md` marks each type's row "Available" — flip a type from
  "🔜 Coming soon" once the adapter is registered and the CLI actually accepts it.
- `tests/unit/test_<name>_adapter.py`, following `test_camtrapdp_adapter.py`/
  `test_yolo_adapter.py`.

---

## Adding a new repository integration

A **repository integration** (`hfh.py`, `zenodo.py`, `b2share.py`) is one module per
external service, each exposing the same shape of commands
(`prepare_*_export`/`upload_to_*`/`release_on_*`) so the CLI's `commands/*.py` and the
web backend's orchestrator can drive any of them identically.

### Conventions every repository module follows

- **`prepare_<repo>_export(input_dir, output_dir, *, product_type, ...)`** — resolves the
  adapter via `product.get_adapter(product_type)`, calls its `prepare()`, then generates
  that repository's own `README.md`/`CITATION.cff`/`LICENSE`/`checksums-sha256.txt` on
  top (each module has its own `write_readme`, rendered via
  `common.render_text_template`; see `common.write_citation`/`write_checksums`).
- **`upload_to_<repo>(output_dir, *, token, ...)`** — creates the remote repository/
  draft/deposition if it doesn't exist yet, uploads every file, and writes a local
  record file (`RECORD_FILENAME`, e.g. `zenodo_record.json`/`b2share_record.json`) into
  `output_dir` so a later step (release, `sync-doi`, cross-repo DOI reflection) can find
  the remote id again without re-deriving it.
- **`release_on_<repo>(output_dir, *, token)`** — the "lock" step; see
  [Locking a publish](publishing-guide.md#locking-a-publish) for how differently this
  behaves per repository.

### DOI capability: `PROVIDES_DOI`

Each module declares a module-level `PROVIDES_DOI: bool` — `True` for Zenodo/B2SHARE
(both mint their own DOI/PID), `False` for Hugging Face Hub (it never does). This is what
lets generic, repository-agnostic code (`doi_populate.py`) ask "which of the repositories
in this publish can ever be a DOI *source*?" without hardcoding repository names.

If your new repository *does* provide its own DOI/PID:

1. Set `PROVIDES_DOI = True`.
2. Reserve the DOI as early as possible — ideally as a side effect of creating the
   draft/deposition, before any file upload (see `zenodo.update_deposition_metadata` and
   `b2share.reserve_doi`) — and immediately patch it into `CITATION.cff` via
   `common.patch_citation_with_identifier(citation_path, value=doi, kind="doi", url=doi_url, description="<Repo> DOI")`.
   This is what lets `doi_populate.populate()` run once, after every repository has
   uploaded, with every DOI already known.
3. Write the reserved id into your own `RECORD_FILENAME` (e.g.
   `<repo>_record.json`) so `doi_populate._read_identifier` can find it — add your
   repository to `doi_populate.REPO_MODULES`/`REPO_LABELS`.
4. Optionally define `PLACEHOLDER_CITATION_URL`, a string your `write_readme` leaves in
   the README when no DOI is known yet — `doi_populate.populate()` replaces it with the
   real DOI URL once one becomes available from another repository.

If it doesn't provide a DOI (like Hugging Face Hub), leave `PROVIDES_DOI = False` and
skip all of the above — `doi_populate.populate()` treats your repository purely as a DOI
*destination*, cross-referencing others' DOIs into your `CITATION.cff`, and (if it's the
only repository without its own DOI) asking the user which one should be primary.

### `common.py` helpers to reuse rather than reimplement

- `render_text_template` — Jinja2 rendering used by every repository's own
  `write_readme`, merging the generic context with the product adapter's own
  `readme_context()`.
- `write_citation` — writes `CITATION.cff` from a shared template.
- `patch_citation_with_identifier(citation_path, *, value, kind, url, description, allow_as_primary)` —
  the single primitive behind every DOI/PID patch: writes to `CITATION.cff`'s top-level
  `doi`/`url` fields when allowed and appropriate, otherwise appends/replaces an entry in
  its `identifiers` list. Returns whether the file actually changed, so callers know
  whether to regenerate checksums and re-upload.
- `write_checksums` — regenerates `checksums-sha256.txt` for a whole `output_dir`; call
  this any time a later step patches a file that's already been checksummed.
- `zip_directory` / `write_local_zip` — generic zip bundling for self-contained exports.

### Wiring it into the CLI and web app

- **CLI**: add `wildintel_publisher/commands/<repo>.py`, following `hfh.py`/`zenodo.py`/
  `b2share.py` for the `prepare`/`upload`/`release` (and `sync-doi`-equivalent, if your
  repository provides a DOI) command shape, and register the Typer app in `main.py`.
- **Web app**: add `wildintel_publisher_web/backend/src/services/<repo>_service.py`
  (thin `asyncio.to_thread` wrappers) and `api/routers/<repo>.py`, then add the
  repository to `publish_orchestrator.py`'s upload/populate/lock phases and
  `schemas/requests.py`'s `RepoPublishConfig`, and add a config form on the frontend
  (see `HFHPublishForm.tsx`/`ZenodoPublishForm.tsx`/`B2SharePublishForm.tsx`).

### Write the docs and tests

- A `docs/publishing-<repo>.md` page (see the existing three for the expected shape:
  what gets uploaded, prepare/upload/release commands for every product type, locking
  semantics), linked from `publishing-guide.md`'s repository table and `mkdocs.yml`'s
  nav.
- Unit tests mocking the repository's HTTP API (see `tests/unit/test_zenodo_service.py`/
  `test_b2share_service.py`), plus integration-style CLI tests (see
  `tests/integration/test_hfh_cli.py`).
