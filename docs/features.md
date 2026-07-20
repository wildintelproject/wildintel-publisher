# Features

## Product types

- **[Camtrap DP](product-camtrapdp.md)** — fetches a camera-trap package directly from
  a [Trapper](https://gitlab.com/trapper-project/trapper) classification project
  (optionally scoped to a single deployment), automatically filtering out any media
  marked private before anything is ever written to disk or published anywhere.
- **[YOLO](product-yolo.md)** — publishes an already-local YOLO training dataset
  (`images/train,val,test` + `data.yaml`) with no external fetch step.
- **A shared, generic pipeline** underneath both: `product generate-metadata` extracts
  a common `title`/`description`/`version`/`license`/`authors`/`homepage` envelope
  (`metadata.json`) from whichever product type you're publishing, so every
  repository's `prepare`/`upload`/`release` commands work identically regardless of
  product type — see the [Developer Guide](developer-guide.md#adding-a-new-product-type)
  for what adding a new one involves.
- **YOLO-based AI models** *(coming soon)* — trained model weights/checkpoints,
  published as their own citable artifact; see
  [Products](products.md#supported-product-types).

## Repository integrations

- **[Hugging Face Hub](publishing-hfh.md)** — the repository that actually hosts the
  media itself (in mirror mode); creates the dataset repository automatically on first
  upload, tags each published version's commit (refusing to silently re-tag a version
  that's already out), and makes the repository public only once you explicitly ask it
  to.
- **[Zenodo](publishing-zenodo.md)** — a citable, permanent-DOI record, either linked
  to wherever the media already lives or fully self-contained; supports both its
  production and sandbox (`sandbox.zenodo.org`) environments for risk-free testing.
- **[B2SHARE (EUDAT)](publishing-b2share.md)** 🇪🇺 — the European counterpart to Zenodo,
  with the same linked/self-contained choice, community-submission and moderator
  review built in, and a 100-files-per-record limit worked around automatically by
  bundling self-contained media into a single zip.
- **Three consistent [publishing modes](publishing-guide.md#publishing-modes)** across every
  repository — plain, link (point at an existing Hugging Face Hub copy), or
  self-contained/mirror (host the media itself) — so switching how a given repository
  handles media never changes the commands you run.
- **DOI/PID reservation ahead of publishing**, on both Zenodo and B2SHARE — the DOI
  gets written into `CITATION.cff`/`README.md` (and re-uploaded) before the record is
  ever locked, rather than only after the fact.
- **`sync-doi`/`sync-pid`** — reflect an already-obtained Zenodo DOI or B2SHARE PID back
  into an existing Hugging Face Hub export's `CITATION.cff`, so a dataset that lives on
  Hugging Face Hub can still carry a citation pointing at its permanent DOI elsewhere.
- **[GBIF](publishing-gbif.md)** — registers a Camtrap DP already hosted anywhere public
  (Hugging Face Hub, Zenodo, B2SHARE, your own server...) in the GBIF Registry, so its
  crawler indexes it as biodiversity occurrence data. No file is uploaded — only a
  `CAMTRAP_DP` endpoint pointing at that URL — and, like Zenodo/B2SHARE, both a
  production and sandbox (`gbif-test.org`) environment are supported.

## The CLI

- **One command group per repository** — `hfh`, `zenodo`, `b2share` — each with its own
  `prepare`/`upload`/`release` (plus `sync-doi`/`sync-pid` where relevant), so every
  platform can be driven independently, in whatever order suits you.
- **`hfh pipeline`** — the one repository with a combined, one-shot command
  (`prepare` → `upload` → `release`), with an optional `--wizard` mode that prompts for
  every parameter interactively and confirms a summary before running.
- **Built-in configuration management** — `config show`/`config get`/`config set`/
  `config wizard`, per section (`trapper`, `hfh`, `zenodo`, `b2share`), read and write a
  single `settings.toml`. Access tokens are stored as real settings but always masked in
  `show` and entered via hidden input in `set`/`wizard`, never echoed to the terminal.
- **Environment-variable overrides** for every credential (`WILDINTEL_USER_NAME`,
  `HF_TOKEN`, `ZENODO_TOKEN`, `B2SHARE_TOKEN`, ...), so CI or scripted use never has to
  touch `settings.toml` at all.
- **Self-verifying exports** — every `prepare` step writes `checksums-sha256.txt`
  covering its own output, regenerated any time a later step patches a file (e.g. a
  DOI/PID landing in `CITATION.cff`), so the checksums manifest always matches exactly
  what's actually there.

## The web app

- **The same product types and repositories**, through a step-by-step wizard: pick a
  product type, fetch or point at the data, complete any metadata the product itself
  couldn't provide, choose one or more repositories, and configure each one — all
  before anything is published.
- **Automatic multi-repository publishing** — once every selected repository is
  configured, publishing runs on its own: uploading all of them, then locking all of
  them, with a single live progress view per repository.
- **Cross-repository DOI reflection**, unique to the web app — whatever DOI Zenodo
  and/or B2SHARE each manage to reserve gets cross-referenced into the *other's*
  `CITATION.cff` before either one locks, and if all three repositories are selected
  together, you're asked which one Hugging Face Hub (which never has a DOI of its own)
  should treat as primary.
- **"Sync DOI/PID to Hugging Face Hub"** as an in-wizard action right after Zenodo/
  B2SHARE finish, instead of a separate command run later by hand.
