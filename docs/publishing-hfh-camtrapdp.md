# Hugging Face Hub — Camtrap DP

This publishes what's described in Camtrap DP's
[What gets published](product-camtrapdp.md#3-what-gets-published) — its common
description, the public images, and the generated documentation — to
[Hugging Face Hub](publishing-hfh.md). Here's exactly what ends up stored there.

---

## What gets stored

Regardless of publishing mode, the repository always ends up with the four core Camtrap DP
tables (`datapackage.json`, `deployments.csv`, `media.csv`, `observations.csv` — private
rows already filtered out), the common description (`metadata.json`), and the generated
documentation (`README.md`, `LICENSE`, `CITATION.cff`, `checksums-sha256.txt`).

- **Mirror mode (the default)** — every public image is downloaded and uploaded to the
  repository as its own individual file, under `images/`, preserving the original file
  arrangement: one file per image, never a zip. `media.csv`'s `filePath` is rewritten,
  once the destination repository is known, to the real, permanent Hugging Face Hub URL
  of each image. An additional `camtrapdp-local.zip` is also generated for convenience —
  the same tables with `filePath` made relative to `images/`, meant to be used together
  with the already-downloaded `images/` folder without needing network access to resolve
  each file again.
- **Link mode** — no images are downloaded or uploaded at all. The repository still gets
  the four core tables, but `media.csv`'s `filePath` is left exactly as Trapper
  delivered it: a temporary, one-shot URL that expires. This only really makes sense for
  a quick, throwaway inspection, since Hugging Face Hub is the one repository in this
  project actually meant to host the media itself.

This is the one repository where images travel one by one, as real files in the
repository — Zenodo and B2SHARE, in contrast, bundle them into a single zip when hosting
them at all (see [Zenodo](publishing-zenodo-camtrapdp.md) /
[B2SHARE](publishing-b2share-camtrapdp.md)).
