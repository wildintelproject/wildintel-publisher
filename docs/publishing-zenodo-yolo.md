# Zenodo — YOLO Dataset

This publishes what's described in YOLO's
[What gets published](product-yolo.md#3-what-gets-published) — its common description,
the dataset itself, and the generated documentation — to
[Zenodo](publishing-zenodo.md). Here's exactly what ends up stored there.

---

## What gets stored

The record always carries the common description (`metadata.json`), the generated
documentation (`README.md`, `LICENSE`, `CITATION.cff`, `checksums-sha256.txt`), and,
once uploaded, a local `zenodo_record.json`.

- **Self-contained** — `data.yaml` and the whole `images/` tree are bundled together
  into a single self-contained zip archive, the same "everything in one file" approach
  used for Camtrap DP's own self-contained mode — just without any path rewriting, since
  a YOLO dataset has no media-reference column to begin with.
- **Link/plain** — only `data.yaml` and the documentation travel; the images aren't part
  of this particular publish at all. Unlike Camtrap DP, there's no external URL a YOLO
  dataset's images can point to instead — the `--hfh-repo-id` link option only affects
  Camtrap DP's `media.csv`, not YOLO.
