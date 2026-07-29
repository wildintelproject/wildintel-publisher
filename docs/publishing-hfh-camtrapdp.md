# Hugging Face Hub — Camtrap DP

This publishes what's described in Camtrap DP's
[What gets published](product-camtrapdp.md#3-what-gets-published) — its common
description, the public images, and the generated documentation — to
[Hugging Face Hub](publishing-hfh.md). Here's exactly what ends up stored there.

---

## What gets stored

Regardless of publishing mode, the repository always ends up with the four core Camtrap DP
tables (`datapackage.json`, `deployments.csv`, `media.csv`, `observations.csv` — private
rows already filtered out), the common description (`metadata.json`), the generated
documentation (`README.md`, `LICENSE`, `CITATION.cff`, `checksums-sha256.txt`), and
`camtrapdp-remote.zip` — the same four tables, packed as-is into a zip. This is the one
to register as [GBIF](publishing-gbif.md)'s `--archive-url` — GBIF's `CAMTRAP_DP` crawler
downloads and decompresses whatever URL it's given, so it needs a real zip archive, unlike
a bare `datapackage.json` (not an archive at all). The zip itself lives at a permanent
Hugging Face Hub URL regardless of mode; only what its own `filePath` entries point at
differs between the two:

- **Mirror mode (the default)** — every public image is downloaded and uploaded to the
  repository as its own individual file, under `images/`, preserving the original file
  arrangement: one file per image, never a zip. `media.csv`'s `filePath` is rewritten,
  once the destination repository is known, to the real, permanent Hugging Face Hub URL
  of each image — `camtrapdp-remote.zip`'s own `filePath` entries carry these same
  permanent URLs, so GBIF's crawler can resolve every image directly once it extracts the
  zip in isolation. An additional `camtrapdp-local.zip` is also generated — the same
  tables with `filePath` made relative to `images/` instead, meant to be used together
  with the already-downloaded `images/` folder without needing network access to resolve
  each file again (meaningless once extracted on its own, unlike `camtrapdp-remote.zip`).
- **Link mode** — no images are downloaded or uploaded at all, and no
  `camtrapdp-local.zip` either (there's no local `images/` folder for it to reference).
  `media.csv`'s `filePath` — and therefore `camtrapdp-remote.zip`'s own copy of it too —
  is left exactly as the source gave it: Trapper's temporary, one-shot URL (expires), a
  local path (meaningless to an external crawler), or an already-public URL if the
  product's own source was a [Public URL](product-camtrapdp.md#1-what-is-camtrap-dp)
  archive (in which case the reference stays valid). The zip archive itself is still
  fetchable and decompressible by GBIF either way — only whether its *internal* media
  references stay resolvable afterwards depends on the source.

This is the one repository where images travel one by one, as real files in the
repository — Zenodo and B2SHARE, in contrast, bundle them into a single zip when hosting
them at all (see [Zenodo](publishing-zenodo-camtrapdp.md) /
[B2SHARE](publishing-b2share-camtrapdp.md)).
