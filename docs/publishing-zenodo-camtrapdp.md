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

- **Self-contained** — the four core tables (`datapackage.json`, `deployments.csv`,
  `media.csv`, `observations.csv`) and the downloaded `images/` folder are bundled
  together into a single `camtrapdp.zip`, with `media.csv`'s `filePath` rewritten to a
  **local, relative path** (`images/<file>`) rather than any URL. The loose copies are
  deleted once the zip is built, so the record itself ends up with just that one zip
  alongside the documentation files — never one file per image.
- **Link** (`--hfh-repo-id`) — no images are downloaded, and the four core tables stay
  loose (not zipped). `media.csv`'s `filePath` is rewritten to the real Hugging Face Hub
  URL of each image, assuming that repository is (or will be) published there. The
  Zenodo record itself never holds any image — just the tables plus a pointer to where
  the images actually live.
- **Plain** — same as link mode, but `filePath` is left as Trapper's own one-shot URL,
  which expires — not meant for a lasting, citable record.

This is the opposite of how [Hugging Face Hub](publishing-hfh-camtrapdp.md) stores the
same product: there, public images travel one by one, as real files in the repository,
with `media.csv` pointing at real per-file URLs. Here, self-contained publishing
compresses everything into one zip and the media reference becomes a path *inside* that
zip, not a URL at all.
