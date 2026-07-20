# Hugging Face Hub — YOLO Dataset

This publishes what's described in YOLO's
[What gets published](product-yolo.md#3-what-gets-published) — its common description,
the dataset itself, and the generated documentation — to
[Hugging Face Hub](publishing-hfh.md). Here's exactly what ends up stored there.

---

## What gets stored

Regardless of publishing mode, the repository always ends up with `data.yaml`, the common
description (`metadata.json`), and the generated documentation (`README.md`, `LICENSE`,
`CITATION.cff`, `checksums-sha256.txt`).

- **Mirror mode (the default)** — the whole `images/train`/`images/val`/`images/test`
  tree is uploaded to the repository as individual files, preserving the split folders.
  No rewriting is needed here (unlike Camtrap DP), since a YOLO dataset has no
  media-reference column pointing anywhere — the images are simply part of the
  repository itself.
- **Link mode** — only `data.yaml` and the documentation are uploaded; the images aren't
  part of this particular publish at all. Unlike Camtrap DP, there's no external URL for
  YOLO images to point to instead — "link" mode here just means leaving the images out,
  not pointing at somewhere else they already live.
