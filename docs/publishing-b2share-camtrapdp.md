# B2SHARE (EUDAT) — Camtrap DP

This publishes what's described in Camtrap DP's
[What gets published](product-camtrapdp.md#3-what-gets-published) — its common
description, the public images, and the generated documentation — to
[B2SHARE](publishing-b2share.md). Here's exactly what ends up stored there.

---

## What gets stored

The record always carries the common description (`metadata.json`), the generated
documentation (`README.md`, `LICENSE`, `CITATION.cff`, `checksums-sha256.txt`), and,
once uploaded, a local `b2share_record.json`. Storage of the Camtrap DP tables and
images themselves works exactly like [Zenodo](publishing-zenodo-camtrapdp.md), with one
difference driven by B2SHARE's own **100-files-per-record cap**:

!!! note "Self-contained is the default for Camtrap DP"
    `b2share prepare` defaults `--self-contained` to enabled for Camtrap DP whenever
    `--hfh-repo-id` isn't also given — pass `--no-self-contained` explicitly for the old
    "leave `media.csv` untouched" (Plain) behavior instead. This default doesn't apply to
    other product types (e.g. YOLO), which still default to `--no-self-contained`.

- **Self-contained** (the default) — the four core tables (`datapackage.json`, `deployments.csv`,
  `media.csv`, `observations.csv`) and the downloaded `images/` folder are bundled
  together into a single `camtrapdp.zip`, with `media.csv`'s `filePath` rewritten to a
  **local, relative path** (`images/<file>`) rather than any URL. The loose copies are
  deleted once the zip is built. This isn't just a style choice here: uploading more
  files than B2SHARE's per-record cap allows would fail outright, so bundling into one
  zip is what makes publishing any camera-trap dataset with more than a handful of
  images possible at all.

  Same as Zenodo's own `camtrapdp.zip`, this one is also nested inside a single
  top-level root folder and has `gbifIngestion.observationLevel` injected into its own
  copy of `datapackage.json` — see [Zenodo](publishing-zenodo-camtrapdp.md) — so it's
  directly usable as GBIF's `--archive-url` too, without needing Hugging Face Hub in the
  same run.
- **Link** (`--hfh-repo-id`) — no images are downloaded, and the four core tables stay
  loose (not zipped). `media.csv`'s `filePath` is rewritten to the real Hugging Face Hub
  URL of each image, assuming that repository is (or will be) published there. The
  B2SHARE record itself never holds any image — just the tables plus a pointer to where
  the images actually live. A `camtrapdp-remote.zip` is generated alongside the loose
  tables too — see [Zenodo](publishing-zenodo-camtrapdp.md) — so this record is also
  directly usable as GBIF's `--archive-url` on its own.
- **Plain** — same as link mode, but `filePath` is left as Trapper's own one-shot URL,
  which expires — not meant for a lasting, citable record.

Like Zenodo, this is the opposite of how [Hugging Face Hub](publishing-hfh-camtrapdp.md)
stores the same product: there, public images travel one by one, as real files, with
`media.csv` pointing at real per-file URLs. Here, self-contained publishing compresses
everything into one zip and the media reference becomes a path *inside* that zip.

## Keeping `camtrapdp.zip` under B2SHARE's own size limit

Same mechanism as [Zenodo](publishing-zenodo-camtrapdp.md#keeping-camtrapdpzip-under-zenodos-own-size-limit),
just against B2SHARE's own (lower) real per-file limit — `DEFAULT_MAX_ZIP_BYTES` defaults
to 20 GiB here instead of Zenodo's 50 GiB. Same flags: `--fit-archive-size`/
`--no-fit-archive-size` (default: enabled), `--max-zip-file` (GiB), `--min-image-edge`
(pixels, default 640) — all Camtrap DP + `--self-contained` only.
