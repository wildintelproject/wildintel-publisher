# YOLO Dataset

This guide describes the **YOLO** product type — what it is, how it's obtained, and
what gets published. See the [Products](products.md) page for an index of every product
type, and the [Publishing Guide](publishing-guide.md) (plus the per-repository guides it
links to) for how the publishing process itself works.

---

## 1. What is a YOLO dataset

[YOLO](https://docs.ultralytics.com/datasets/) (You Only Look Once) is a widely used
family of object-detection models, and its own dataset format — plain image files
organised into `train`/`val`/`test` splits, each image paired with a `.txt` label file
of normalised bounding boxes — has become a de-facto standard beyond YOLO itself, read
directly by most modern object-detection training frameworks.

Unlike Camtrap DP, this project doesn't fetch YOLO datasets from any external service —
a YOLO dataset is expected to already exist as a local directory (produced by whatever
annotation/export tool you use) and is published directly from there.

## 2. Raw dataset layout

```
.
├── images/
│   ├── train/         ← training images (required, at least one file)
│   ├── val/           ← validation images (required, at least one file)
│   └── test/          ← test images (optional)
└── data.yaml           ← standard Ultralytics/YOLO config
```

`data.yaml` is the standard YOLO training config (split paths, number of classes, class
id → name mapping). It can additionally carry a handful of optional descriptive keys —
harmless to any YOLO trainer, which simply ignores keys it doesn't recognise:

```yaml
train: images/train
val: images/val
test: images/test
nc: 8
names: [red_deer, fallow_deer, wild_boar, iberian_lynx, red_fox, mongoose, rabbit, badger]

# Optional, read by wildintel-publisher only:
title: My YOLO Dataset
description: A camera-trap object-detection dataset.
version: "1.0"
license: CC-BY-4.0                 # a bare string id, or {id, name, url}
authors:
  - name: Jane Doe
    affiliation: My Institution
homepage: https://example.org
```

Unlike Camtrap DP, there is no `filePublic`/privacy concept — every image under
`images/` is treated as publishable, and no media-reference URL needs rewriting: the
images themselves either travel with the export (mirror mode) or are simply left out
of that particular publish (link mode) — see
[Publishing modes](publishing-guide.md#publishing-modes) in the Publishing Guide.

## 3. What gets published

Before a YOLO dataset can be published anywhere, it's given a common description — the
same envelope every product type carries, regardless of its own underlying format:

| Description field | Derived from `data.yaml` |
|---|---|
| Title, description, version, homepage | same-named top-level keys |
| License (id, name, URL) | the license key — a bare string id, or an id/name/URL mapping |
| Authors (name, affiliation) | the authors list |

Title, description, version, license, and authors are **required** — if `data.yaml`
didn't provide one of them, it needs to be added by hand (or via the web app's wizard,
which prompts for whatever's missing) before publishing can proceed.

From there, publishing a YOLO dataset copies `data.yaml` (and, in mirror mode, the whole
`images/` tree), and generates a `README.md`, a machine-readable `CITATION.cff`, a
`LICENSE` file, and a checksums manifest covering everything — the README's dataset
format section is rendered specifically for YOLO (split layout, class count and names),
distinct from Camtrap DP's own wording.

!!! note "Mirror mode always bundles the full `images/` tree"
    For Camtrap DP, mirror mode downloads remote images that otherwise wouldn't exist
    locally. For YOLO, the images are already local — mirror mode simply means bundling
    everything (`data.yaml` plus the whole `images/` tree) together, rather than leaving
    `images/` out of that particular publish.

## 4. Where it can be published

| Repository | Availability |
|---|---|
| [Hugging Face Hub](publishing-hfh.md) | ✅ Available |
| [Zenodo](publishing-zenodo.md) | ✅ Available |
| [B2SHARE (EUDAT)](publishing-b2share.md) 🇪🇺 | ✅ Available |
| [GBIF](https://www.gbif.org/) | ❌ Not applicable |

YOLO datasets are machine-learning training data rather than biodiversity occurrence
records, so GBIF isn't a fit for them — see
[Products](products.md#where-products-can-be-published) for how this compares to the
other product types.
