# Zenodo — Camtrap DP

This publishes what's described in Camtrap DP's
[What gets published](product-camtrapdp.md#3-what-gets-published) — its common
description, the public images, and the generated documentation — to
[Zenodo](publishing-zenodo.md). Here's exactly what ends up stored there.

---

## What gets stored

The record always carries the common description (`metadata.json`), the generated
documentation (`README.md`, `LICENSE`, `CITATION.cff`, `checksums-sha256.txt`), and,
once uploaded, a local `zenodo_record.json`. How the Camtrap DP tables and images
themselves end up stored depends entirely on the publishing mode:

!!! note "Self-contained is the default for Camtrap DP"
    `zenodo prepare` defaults `--self-contained` to enabled for Camtrap DP whenever
    `--hfh-repo-id` isn't also given — pass `--no-self-contained` explicitly for the old
    "leave `media.csv` untouched" (Plain) behavior instead. This default doesn't apply to
    other product types (e.g. YOLO), which still default to `--no-self-contained`.

- **Self-contained** (the default) — the four core tables (`datapackage.json`, `deployments.csv`,
  `media.csv`, `observations.csv`) and the downloaded `images/` folder are bundled
  together into a single `camtrapdp.zip`, with `media.csv`'s `filePath` rewritten to a
  **local, relative path** (`images/<file>`) rather than any URL. The loose copies are
  deleted once the zip is built, so the record itself ends up with just that one zip
  alongside the documentation files — never one file per image.

  This zip is nested inside a single top-level root folder (its own stem, `camtrapdp/`)
  and has `gbifIngestion.observationLevel` injected into its own copy of
  `datapackage.json` — the same two fixes [`camtrapdp-remote.zip`](publishing-hfh-camtrapdp.md)
  needs for GBIF (see [Publishing to GBIF](publishing-gbif.md)) — so this same zip is
  also directly usable as GBIF's `--archive-url` when publishing to Zenodo without
  Hugging Face Hub in the same run.
- **Link** (`--hfh-repo-id`) — no images are downloaded, and the four core tables stay
  loose (not zipped). `media.csv`'s `filePath` is rewritten to the real Hugging Face Hub
  URL of each image, assuming that repository is (or will be) published there. The
  Zenodo record itself never holds any image — just the tables plus a pointer to where
  the images actually live. A `camtrapdp-remote.zip` is generated alongside the loose
  tables too — the same shape [Hugging Face Hub's own](publishing-hfh-camtrapdp.md)
  generates, with no images embedded (since `filePath` already points at real URLs) —
  so this record is also directly usable as GBIF's `--archive-url` on its own, without
  needing Hugging Face Hub published in the same run.
- **Plain** — same as link mode, but `filePath` is left as Trapper's own one-shot URL,
  which expires — not meant for a lasting, citable record.

This is the opposite of how [Hugging Face Hub](publishing-hfh-camtrapdp.md) stores the
same product: there, public images travel one by one, as real files in the repository,
with `media.csv` pointing at real per-file URLs. Here, self-contained publishing
compresses everything into one zip and the media reference becomes a path *inside* that
zip, not a URL at all.

## Keeping `camtrapdp.zip` under Zenodo's own size limit

Zenodo caps how big a single uploaded file can be (`DEFAULT_MAX_ZIP_BYTES`, 50 GiB by
default — matches Zenodo's own real limit). Once the images are already downloaded to
`output_dir/images/`, and only for Camtrap DP, `zenodo prepare --self-contained` checks
their combined size before bundling them into `camtrapdp.zip`:

- If they already fit comfortably, nothing changes.
- Otherwise every image is downscaled **uniformly** (same scale factor for all of them,
  computed once from how much over budget they are — not a "build, measure, halve,
  rebuild" loop) so the whole dataset ends up at one consistent resolution, rather than
  some images sharper than others depending on download order. An image's longest edge
  is never shrunk below `--min-image-edge` (640px by default) — past that point,
  shrinking further trades away more identifiability (species, individual markings) than
  it saves in bytes. Non-image files (e.g. video, if any) are never touched.
- `camtrapdp.zip`'s final size is checked against the limit regardless — even with
  `--no-fit-archive-size` — and `prepare` fails with a clear error instead of letting the
  much later upload to Zenodo fail on its own.

Flags: `--fit-archive-size`/`--no-fit-archive-size` (default: enabled), `--max-zip-file`
(the budget itself, in GiB — defaults to Zenodo's real 50 GiB cap; only useful to lower,
e.g. for a stricter personal quota), `--min-image-edge` (the floor, in pixels, default
640). All three are ignored outside `--self-contained` Camtrap DP.
