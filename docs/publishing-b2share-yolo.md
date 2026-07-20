# B2SHARE (EUDAT) — YOLO Dataset

This publishes what's described in YOLO's
[What gets published](product-yolo.md#3-what-gets-published) — its common description,
the dataset itself, and the generated documentation — to
[B2SHARE](publishing-b2share.md). Here's exactly what ends up stored there.

---

## What gets stored

The record always carries the common description (`metadata.json`), the generated
documentation (`README.md`, `LICENSE`, `CITATION.cff`, `checksums-sha256.txt`), and,
once uploaded, a local `b2share_record.json`.

- **Self-contained** — `data.yaml` and the whole `images/` tree are bundled together
  into a single self-contained zip archive — the same approach [Zenodo](publishing-zenodo-yolo.md)
  uses, and for the same reason B2SHARE bundles Camtrap DP's images too: B2SHARE's
  100-files-per-record cap would otherwise be hit by any dataset with more than a
  handful of images.
- **Link/plain** — only `data.yaml` and the documentation travel; the images aren't part
  of this particular publish at all. Unlike Camtrap DP, there's no external URL a YOLO
  dataset's images can point to instead — the `--hfh-repo-id` link option only affects
  Camtrap DP's `media.csv`, not YOLO.
