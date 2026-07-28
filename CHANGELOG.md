# Changelog

WildINTEL project provides up-to-date release notes for `wildintel-publisher` (CLI and web
app). This document contains information about recent changes, including new features, bug
fixes, and improvements. It is intended to help users and developers understand the
evolution of the project over time.

You can download the latest CLI/web app binaries from the
[releases page](https://github.com/wildintelproject/wildintel-publisher/releases).

To report a bug or request a new feature, please open an
[issue](https://github.com/wildintelproject/wildintel-publisher/issues).

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html). The CLI and
the web app are versioned and released independently — `vX.Y.Z` tags for the CLI, `web-vX.Y.Z`
tags for the web app — so released entries below are labelled `CLI` or `Web` accordingly.

## Upcoming release

### Added
- Web: publish Camtrap DP to GBIF from the wizard, alongside Hugging Face Hub, Zenodo, and
  B2SHARE — previously CLI-only.
- CLI/Web: add a new "software application" product type, now also selectable in the web
  wizard — its source is a git repository, fetched via `git clone`, and it publishes to
  Zenodo/B2SHARE only. The repository must have a
  [`CITATION.cff`](https://citation-file-format.github.io/) at its root — it's the sole
  source of the product's own title/description/version/license/authors (same standard
  this project's own generated exports use for every product type). Zenodo is mandatory
  for it in the wizard — pre-selected and not deselectable, since its DOI is always the
  one used to cite the software.
- CLI/Web: `gbif register`/the wizard's GBIF form send the product's `homepage` (when
  known) to the GBIF Registry.
- Web: a **Validate archive** button on the GBIF form downloads the archive URL upfront,
  checks it's a real zip, and validates it against the official Camtrap DP schema —
  catches the exact failure GBIF's own `CAMTRAP_DP` crawler otherwise hits silently (a
  crawl that finishes with no records and no error visible anywhere in this project).
- CLI/Web: Camtrap DP can now also be obtained from a **Public URL** — a third source
  alongside Trapper and a local directory — pointing at an already-published zip archive,
  downloaded and validated against the official schema on the way in. That same URL is
  then directly reusable as GBIF's own archive URL, already confirmed public and valid,
  without the local-copy-vs-archive-URL distinction the other two sources have.
- CLI/Web: `gbif register` now also fetches and stores the dataset's DOI — some
  organizations have their own DataCite arrangement configured with GBIF, which makes it
  auto-mint one on registration (entirely GBIF/organization-side, not something this tool
  requests). New `gbif sync-doi` command/web endpoint reflects it into an already-prepared
  Hugging Face Hub export's `CITATION.cff`, same as `zenodo sync-doi`/`b2share sync-pid`.
  When the web wizard publishes Hugging Face Hub and GBIF together in the same run, this
  sync now happens automatically — unlike Zenodo/B2SHARE's DOI/PID (already known before
  Hugging Face Hub gets tagged, so it's cross-referenced for free), GBIF's own DOI is only
  known after its registration call, which always runs after Hugging Face Hub's own publish
  — the "All done!" screen's "Sync DOI" section now only shows up as a manual fallback, for
  whenever GBIF was registered standalone (without Hugging Face Hub in the same run) or the
  automatic attempt itself failed.
- CLI/Web: a DOI/PID cross-referenced into a Hugging Face Hub export — whether from the
  same run's `doi_populate` step, or a later `zenodo sync-doi`/`b2share sync-pid`/
  `gbif sync-doi` — now also updates its `README.md`'s own "## Citation" section (which
  cites the export's own repo URL by default), not just `CITATION.cff` as before.

### Fixed
- CLI/Web: `camtrapdp-remote.zip` (built for GBIF's own `--archive-url`) packed its four
  files loose at the zip's own root — GBIF's `CAMTRAP_DP` crawler unpacks the archive and
  requires exactly one root directory in the result (`org.gbif.utils.file.CompressionUtil`
  errors with "More than one root directory" otherwise), so the crawl finished `NORMAL`
  but indexed zero records — no images, no occurrences, no error visible anywhere in this
  project (a *different*, later failure mode than the earlier `finishReason: ABORT` one).
  The four files now nest inside a single top-level folder inside the zip.
  `gbif.validate_camtrap_dp_archive`/the **Public URL** source
  (`camtrapdp_source.fetch_camtrap_dp_archive`) now locate `datapackage.json` correctly
  either way (see `common.find_camtrap_dp_root`).
- CLI/Web: even past that fix, GBIF's own Camtrap DP -> Darwin Core conversion (the
  `camtrapdp`/`camtraptor` R packages it runs internally) only keeps observations whose
  `observationLevel` matches a `gbifIngestion.observationLevel` field in `datapackage.json`
  — defaulting to `"event"` when that field is absent. Trapper's own exports (and every
  example bundled with this project) are always media-level (`observationLevel: "media"`
  on every row), so every dataset published so far got silently filtered down to zero
  occurrences at GBIF, with no error surfaced anywhere in this project, the GBIF Registry
  API, or the dataset's own page. `camtrapdp-remote.zip` now sets that field automatically,
  detected from `observations.csv` itself (see `common.write_remote_zip`).
- CLI/Web: Camtrap DP mirror mode (`hfh prepare`'s default, and the wizard's own
  **Mirror** option) only ever tried to download `media.csv`'s `filePath` as an absolute
  `http(s)://` URL — the right behavior for Trapper-sourced (or **Public URL**-fetched)
  media, but for an already-local, self-contained package whose `filePath` is instead a
  path *relative to the package itself* (the standard's own alternative form, and what
  `examples/camtrapdp/` uses), every row silently failed to download with no image ever
  reaching `images/`, and mirror mode ended up behaving exactly like link mode — no error
  surfaced anywhere in the wizard. Mirror mode now copies these straight from the local
  package instead of attempting a network fetch.
- CLI/Web: the archive URL suggested for GBIF registration (and the CLI guide's own
  example) pointed at a bare `datapackage.json` — GBIF's `CAMTRAP_DP` crawler downloads
  that URL and decompresses it itself, so a bare descriptor silently fails to crawl
  (`finishReason: ABORT`, nothing ever indexed, no error visible anywhere in this
  project). `hfh upload` (mirror mode) now also generates `camtrapdp-remote.zip` — built
  right after `media.csv` gets rewritten to real Hugging Face Hub URLs, so it's both a
  real, decompressible zip archive *and* has media references GBIF can resolve once
  extracted on its own. (The existing `camtrapdp-local.zip` isn't a fit either — its
  `media.csv` uses paths relative to a sibling `images/` folder, meaningless once
  extracted in isolation.) Every archive-URL suggestion/example now points at
  `camtrapdp-remote.zip`.
- Web: `POST /api/software/clone` was a plain (non-`async`) route calling code that
  scheduled a background `asyncio` task — with no event loop running in the worker
  thread FastAPI runs sync routes in, the clone silently never started and the status
  poll would hang forever. Now `async def`, matching every other background-task route.

### Changed
- Web: restrict the Camtrap DP wizard to Hugging Face Hub and GBIF only (Zenodo and
  B2SHARE remain available for Camtrap DP via the CLI).
- Web: show each successfully published repository's real URL in the wizard's publish
  progress/summary screens, and let a partial failure retry only the repositories that
  didn't finish, instead of re-running the whole selection (which could otherwise fail a
  retry outright for an already-tagged/released Hugging Face Hub repo).
- Web: let the user go Back while configuring repositories one at a time (e.g. from
  "Configure GBIF" to "Configure Hugging Face Hub") without losing what was already typed
  — previously the only way back was reloading the whole wizard. The GBIF form also warns
  when Hugging Face Hub is scheduled to publish later in the same run, since its archive
  URL won't actually exist yet, so **Validate archive** failing at that point doesn't read
  as something being misconfigured.
- Web: temporarily narrow the wizard to a single, thoroughly-tested flow — Camtrap DP
  (YOLO Dataset/Software Application marked "Coming soon") published to Hugging Face Hub
  and GBIF only (Zenodo/B2SHARE marked "Coming soon" too, for every product type). All
  four are still fully implemented and available via the CLI; this only trims what the
  wizard currently offers.
- Web: when both Hugging Face Hub and GBIF are selected, Hugging Face Hub always
  publishes first (no longer manually reorderable for this pair) and GBIF's Archive URL
  becomes read-only, fixed to Hugging Face Hub's own `camtrapdp-remote.zip` — there's no
  other valid value once both are picked together. When GBIF is selected on its own, its
  form now explains that the locally fetched copy (from "Where is it located?") was only
  used for metadata, and the Archive URL must point to a separate, already-public copy.

## Released

**Note:** The information in past release notes may have been superseded by newer releases.
Please refer to the latest release for the most up-to-date information.
