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
- CLI/Web: an opt-in **anonymize coordinates** option for Camtrap DP rounds
  `deployments.csv`'s `latitude`/`longitude` to a fixed number of decimal places
  (2 by default, ≈ 1.1 km) — a privacy option for sensitive camera-trap
  locations (poaching risk, protected species, private land). Deterministic
  (not a random offset), so the same deployment gets identical rounded
  coordinates on every repository it's published to. Applied once, as a
  product-level preprocessing step when `metadata.json` is first generated
  (`product generate-metadata --anonymize-coordinates --coordinate-decimals`
  on the CLI; the option appears once a Camtrap DP source is picked, Step 1,
  in the web wizard) — every repository that later prepares its own export
  from that same input inherits the already-anonymized coordinates
  automatically, with nothing extra to configure per repository.
- CLI/Web: a DOI/PID cross-referenced into a Hugging Face Hub export — whether from the
  same run's `doi_populate` step, or a later `zenodo sync-doi`/`b2share sync-pid`/
  `gbif sync-doi` — now also updates its `README.md`'s own "## Citation" section (which
  cites the export's own repo URL by default), not just `CITATION.cff` as before.
- CLI/Web: a software application's raw source now switches to the git tag matching
  `CITATION.cff`'s own `version` (trying `1.2.0`, then `v1.2.0`), once, right after
  `metadata.json` is generated — previously only the default branch's current commit was
  ever used, so an export could end up citing one version while actually shipping a
  different (possibly unreleased) one. Falls back to today's behavior (the default
  branch's latest commit) when neither tag exists, e.g. a repository that doesn't tag
  releases.
- CLI/Web: an opt-in **randomize media IDs** option for Camtrap DP replaces every
  `mediaID` in `media.csv` that isn't already a UUID with a freshly generated one,
  keeping `observations.csv`'s own `mediaID` references in sync — keeps published
  mediaIDs from leaking the original export's own numbering convention, and collision-free
  if this data is later merged with another project's/repository's. Same "applied once,
  as a product-level preprocessing step when `metadata.json` is first generated" shape as
  **anonymize coordinates** (`product generate-metadata --randomize-media-ids` on the CLI;
  a checkbox next to "Anonymize deployment coordinates" in the web wizard, Step 1).
- CLI/Web: `trapper download`/the wizard's Trapper source form can now include
  event-level (aggregated) observations in the fetched Camtrap DP package, alongside the
  media-level ones already included — Trapper's own API defaults this off
  (`include_events=false`); wildintel-publisher now always sends it explicitly, defaulting
  it **on** instead (`--include-events/--no-include-events` on the CLI; an "Include
  events" checkbox, checked by default, once a deployment is selected in the web wizard).
- Web: a Software Application git clone with no `CITATION.cff` at its root (or any other
  `ProductAdapter.validate` failure) now shows the actual error message on the package
  confirmation screen — it used to fail silently, leaving **Next** permanently disabled
  with no indication why.
- CLI/Web: whether the git tag matching `CITATION.cff`'s own `version` was actually found
  (see the "Which commit gets published" entry above) is no longer CLI-only — the web
  wizard now shows the same outcome as a note on the package confirmation screen: a green
  confirmation naming the tag if one matched, or an amber warning if it didn't (publishing
  from the default branch's latest commit instead).
- CLI/Web: a Software Application published in **Mirror** mode's self-contained zip
  (`zenodo prepare --self-contained`/`b2share prepare --self-contained`) now bundles the
  clone's own files under their real names (e.g. the repository's own `README.md`),
  instead of a `SOURCE_`-renamed copy sitting alongside a newly-generated file of the same
  original name — `SoftwareAdapter.bundle_local_zip` now reads directly from the untouched
  clone, since a whole-repo mirror has nothing product-specific for `prepare()` to
  transform first (unlike Camtrap DP's private-media filtering/image download, which must
  still run before anything gets zipped there).
- CLI: `zenodo prepare --self-contained`/`b2share prepare --self-contained` now produce a
  Camtrap DP archive directly usable as GBIF's own `--archive-url`, without needing
  Hugging Face Hub published in the same run — the self-contained `camtrapdp.zip` nests
  its files inside a single root folder and gets `gbifIngestion.observationLevel`
  injected into its own copy of `datapackage.json` (the same two fixes
  `camtrapdp-remote.zip` already has for Hugging Face Hub). Their own **Link** mode
  (`--hfh-repo-id`) now also generates a `camtrapdp-remote.zip` alongside the loose
  tables — no images embedded, since `media.csv` already points at real Hugging Face Hub
  URLs by that point.
- CLI/Web: GBIF's own **Validate archive** check (`gbif.validate_camtrap_dp_archive`) now
  also rejects a Camtrap DP archive whose `media.csv` has any `filePath` that isn't an
  absolute `http(s)://` URL — a relative or local filesystem path (valid Camtrap DP on its
  own, e.g. a self-contained package) never resolves to anything once GBIF's crawler has
  decompressed and discarded the archive, silently leaving every occurrence record with no
  working media link.
- CLI: `zenodo prepare --self-contained`/`b2share prepare --self-contained` (Camtrap DP
  only) now resize the already-downloaded images uniformly before bundling them into
  `camtrapdp.zip`, whenever their combined size would otherwise exceed the repository's
  own per-file upload cap (50 GiB on Zenodo, 20 GiB on B2SHARE) — a single, upfront scale
  factor keeps the whole dataset at one consistent resolution, never shrinking an image's
  longest edge below `--min-image-edge` (640px by default). `camtrapdp.zip`'s final size
  is still checked against the limit afterwards regardless (`--max-zip-file` to override
  it, `--no-fit-archive-size` to disable resizing) — `prepare` now fails with a clear
  error instead of letting the much later upload silently fail once it hits the platform's
  own cap.

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
- CLI/Web: preparing a software application for Zenodo/B2SHARE (`zenodo prepare`/
  `b2share prepare`, or the wizard's own Zenodo/B2SHARE steps) crashed outright —
  `write_readme` looked for a `README-software-body.md.j2` template that never existed,
  so every attempt failed with an uncaught `TemplateNotFound`. New template (shared by
  Zenodo/B2SHARE) fixes this.
- CLI/Web: even past that fix, software's own **Link** mode (the non-mirror choice on
  Zenodo/B2SHARE's "Mode" section) was broken in two ways: it cited a Hugging Face Hub
  placeholder URL (`REPLACE_WITH_HF_USER/dataset`) that never resolves to anything, since
  software has no Hugging Face Hub target at all; and, since `SoftwareAdapter.prepare`
  ignored the mode entirely and always copied the whole repository loose, any file inside
  a subdirectory (`src/`, `lib/`, ...) silently never reached Zenodo/B2SHARE — both
  services only ever upload files sitting directly at the export's own root, not
  recursively. Relabeled **Reference only**: copies no source code at all, and cites the
  repository directly (`CITATION.cff`'s `repository-code`/`url`, or the git remote) —
  only `README.md`/`CITATION.cff`/`LICENSE`/checksums get published, giving the software
  a citable DOI/PID without duplicating code that already has a canonical home.
- CLI/Web: `metadata.json` — internal pipeline bookkeeping (`product_type`,
  `publish_history`) — was being uploaded verbatim to Hugging Face Hub/Zenodo/B2SHARE
  alongside the actual export, and listed in `checksums-sha256.txt` as if it were part of
  the published record. It still stays in `output_dir` (every repo that later chains off
  of it, or re-reads it during upload/release, still needs it there) but is no longer
  sent to any repository or included in the checksums manifest.
- Web: when Hugging Face Hub and GBIF are both selected, the GBIF form's Archive URL
  used to always lock to Hugging Face Hub's own `camtrapdp-remote.zip` — but that file is
  only ever generated in Hugging Face Hub's **Mirror** mode (see `hfh.
  upload_to_huggingface`); in **Link** mode it's never created, so a locked field would
  point GBIF at a URL that 404s, with no error visible anywhere in the wizard. The field
  now only locks/prefills when Hugging Face Hub is actually publishing in Mirror mode —
  otherwise it behaves exactly like GBIF standalone (no Hugging Face Hub in the run):
  unlocked, with a note that a separate, already-public archive URL must be provided by
  hand.
- Web: GBIF's own registration (`publish_orchestrator._lock_one`) read `metadata.json`
  from the publish task's ORIGINAL input directory, regardless of whether an earlier repo
  in the same run (typically Hugging Face Hub, in Mirror mode) had just updated its
  `homepage` field to its own real dataset URL — so GBIF's Registry entry ended up with a
  stale or missing `homepage` even when the run set a real one. Now reads from this
  repo's own input directory as of its actual turn in the chain, same as every other
  repo already does.
- Web: publishing Hugging Face Hub and GBIF together only worked correctly (predictable
  archive URL, correct `homepage` — see above) when Hugging Face Hub published first; the
  wizard's own `toggleRepo` already enforces this order client-side, but `POST
  /api/publish/start` accepted any order, so a request bypassing the wizard UI could
  silently end up with a stale/wrong GBIF registration. Now rejected with a 400 if GBIF is
  listed before Hugging Face Hub in `repos`.
- CLI/Web: `common.validate_camtrap_dp` silently auto-adds a missing `datapackage.json`
  `"profile"` field wherever it validates a local copy this project actually controls
  (Trapper, Local Directory, or a Public URL source's own persisted copy) — correct there,
  since the patch lands in the exact file that later gets published. GBIF's own **Validate
  archive** check (`gbif.validate_camtrap_dp_archive`), however, downloads an externally
  hosted zip into a throwaway extraction it discards right after — patching that copy only
  "fixed" something nobody would ever see, silently reporting a URL as valid when the real,
  unpatched file (the one GBIF's own crawler will actually fetch) was still missing
  `"profile"`. It now raises instead whenever that field is missing there.

### Changed
- Web: restrict the Camtrap DP wizard to Hugging Face Hub and GBIF only (Zenodo and
  B2SHARE remain available for Camtrap DP via the CLI).
- Web: GBIF is now mandatory for Camtrap DP in the wizard — pre-selected and not
  deselectable, the same mechanism Software Application's own Zenodo already uses, so a
  Camtrap DP dataset always ends up registered with GBIF. Hugging Face Hub stays optional
  alongside it (GBIF registers standalone, with a manually-provided archive URL, when
  it's the only repository selected).
- Web: Zenodo is now mandatory for AI Dataset too, pre-selected and not deselectable —
  same mechanism, and same reasoning, as Software Application's own Zenodo: its DOI is
  always the one used to cite the dataset. Hugging Face Hub and B2SHARE both stay optional
  alongside it.
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
  (AI Dataset/Software Application marked "Coming soon") published to Hugging Face Hub
  and GBIF only (Zenodo/B2SHARE marked "Coming soon" too, for every product type). All
  four are still fully implemented and available via the CLI; this only trims what the
  wizard currently offers.
- Web: when both Hugging Face Hub and GBIF are selected, Hugging Face Hub always
  publishes first (no longer manually reorderable for this pair) and GBIF's Archive URL
  becomes read-only, fixed to Hugging Face Hub's own `camtrapdp-remote.zip` — there's no
  other valid value once both are picked together. When GBIF is selected on its own, its
  form now explains that the locally fetched copy (from "Where is it located?") was only
  used for metadata, and the Archive URL must point to a separate, already-public copy.
- CLI/Web: `camtrapdp-remote.zip` is now generated (and uploaded) for every Hugging Face
  Hub publish of a Camtrap DP package, in both **Mirror** and **Link** mode — previously
  only Mirror mode produced it, so GBIF's Archive URL only auto-filled/locked in that
  case. The zip file itself lives at a permanent Hugging Face Hub URL regardless of mode;
  only its own `media.csv`'s `filePath` entries differ (real Hugging Face Hub URLs in
  Mirror, whatever the original source gave it in Link) — a separate, lesser concern from
  the archive itself existing and being fetchable by GBIF's crawler. The wizard's own
  Archive URL auto-fill/lock now applies whenever Hugging Face Hub is selected at all, no
  longer conditional on its publishing mode.
- CLI: `zenodo prepare`/`b2share prepare` now default `--self-contained` to enabled
  (mirror) for Camtrap DP whenever `--hfh-repo-id` isn't also given, instead of leaving
  `media.csv` untouched (Plain mode) — pass `--no-self-contained` explicitly for the old
  behavior. Other product types (e.g. AI Dataset/Software Application) are unaffected,
  still defaulting to disabled.
- Web: Zenodo and B2SHARE are now selectable for Camtrap DP in the wizard too, alongside
  Hugging Face Hub and GBIF (reversing the earlier "restrict the Camtrap DP wizard to
  Hugging Face Hub and GBIF only" entry above) — the backend already fully supported this
  combination; only the wizard's own repository picker was narrower. GBIF's Archive URL
  still only auto-fills/locks from Hugging Face Hub (its user-chosen repository name is
  known upfront, unlike Zenodo/B2SHARE's own deposition/record id, only assigned once
  they actually upload) — selecting Zenodo/B2SHARE without Hugging Face Hub leaves the
  field blank and editable, with a note explaining why and pointing at registering GBIF
  in a separate run afterward instead.

## Released

**Note:** The information in past release notes may have been superseded by newer releases.
Please refer to the latest release for the most up-to-date information.
