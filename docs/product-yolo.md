# AI Dataset

This guide describes the **AI Dataset** product type — a dataset in YOLO training
format — what it is, how it's obtained, and what gets published. See the
[Products](products.md) page for an index of every product type, and the [Publishing
Guide](publishing-guide.md) (plus the per-repository guides it links to) for how the
publishing process itself works.

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
│   ├── train/         ← training images (required, at least one image)
│   ├── val/           ← validation images (required, at least one image)
│   └── test/          ← test images (optional)
├── labels/            ← optional, one .txt per image, same split layout as images/
│   ├── train/
│   ├── val/
│   └── test/
└── data.yaml           ← standard Ultralytics/YOLO config
```

Only this `images/<split>` layout is supported. The alternative Ultralytics layout
(`train/images`, `train/labels`, …) needs to be reorganised first. Images can be
nested in subfolders inside each split. A label file shares its image's relative
path (`images/train/site-a/0001.jpg` ↔ `labels/train/site-a/0001.txt`).

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
publisher:                         # credited in CITATION.cff's preferred-citation
  name: University of Huelva
  website: https://www.uhu.es/
copyright_holders:                 # "© <year> <names>" in the citation
  - Spanish National Research Council
```

In the web app, the metadata step edits these descriptive keys on a copy of
`data.yaml` kept inside the session — your own dataset directory is never modified.
The publisher and rights holder are picked from the organizations configured in
`settings.toml` (`[[PRODUCT.organizations]]`), the same list Camtrap DP uses. The license
is picked from a list of common ones (CC-BY-NC-4.0 by default, WildINTEL's own policy),
which fills in its id, full name and URL at once; "Other…" lets you type any other.
The authors listed in `data.yaml` are shown as they are; the "Add a saved author…" menu
adds one of the authors saved in the settings page's *Authors* section
(`[[PRODUCT.authors]]` in `settings.toml`) with one click, and each one stays editable.
The *Additional funding text* field is appended to the README's *Funding* section
(saved as `funding` in the copy of `data.yaml`).

Unlike Camtrap DP, there is no `filePublic`/privacy concept — every image under
`images/` is treated as publishable, and no media-reference URL needs rewriting: the
images themselves either travel with the export (mirror mode) or are simply left out
of that particular publish (link mode) — see
[Publishing modes](publishing-guide.md#publishing-modes) in the Publishing Guide.

## 3. Validation

The dataset is validated before anything is published. Errors stop the process;
warnings are only logged.

| Check | Result |
|---|---|
| `data.yaml` exists and is valid YAML | error |
| `train`/`val` (and `test`, if present) point to `images/train`, `images/val`, `images/test` | error |
| `names` lists at least one class; a mapping uses consecutive ids starting at 0 | error |
| `nc`, if present, equals the number of `names` | error |
| `images/train` and `images/val` contain at least one image (`.jpg`, `.png`, `.tif`, `.webp`, …) | error |
| Every line of every `labels/` file is `class x y w h` (box) or `class x1 y1 x2 y2 x3 y3 …` (polygon), with the class id lower than the number of classes and every coordinate between 0 and 1 | error, listing the file and line of the first 10 problems |
| `data.yaml` declares `test` but `images/test` has no images | warning |
| Images with no label file (background images) | warning |
| Label files with no matching image | warning |
| Non-image files inside `images/<split>` | warning (they're published as-is) |

## 4. What gets published

Before a YOLO dataset can be published anywhere, it's given a common description — the
same envelope every product type carries, regardless of its own underlying format:

| Description field | Derived from `data.yaml` |
|---|---|
| Title, description, version, homepage | same-named top-level keys |
| License (id, name, URL) | the license key — a bare string id, or an id/name/URL mapping |
| Authors (name, affiliation) | the authors list |
| Publisher, rights holders | the publisher mapping and copyright_holders list (optional) |

Title, description, version, license, and authors are **required** — if `data.yaml`
didn't provide one of them, it needs to be added by hand (or via the web app's wizard,
which prompts for whatever's missing) before publishing can proceed.

From there, publishing a YOLO dataset copies `data.yaml` (and, in mirror mode, the whole
`images/` tree), and generates a `README.md`, a machine-readable `CITATION.cff`, a
`LICENSE` file, and a checksums manifest covering everything — the README's dataset
format section is rendered specifically for YOLO (split layout, class count and names),
distinct from Camtrap DP's own wording.

!!! note "Mirror and Link are the same for YOLO"
    For Camtrap DP, mirror mode downloads remote images that otherwise wouldn't exist
    locally, and link mode points at a copy hosted elsewhere. A YOLO dataset's images are
    already local and have nowhere else to point at, so every export always includes
    `data.yaml`, `images/` and `labels/`: loose on Hugging Face Hub, bundled into
    `yolo.zip` on Zenodo and B2SHARE.

!!! note "Very large splits on Hugging Face Hub"
    Hugging Face Hub accepts at most 10,000 files per folder. A split over that limit is
    spread, on Hugging Face Hub only, over hash-named subfolders
    (`images/train/3f/img.jpg`, with its label at `labels/train/3f/img.txt`) — still valid
    YOLO, since trainers look for images recursively. Your own dataset, `yolo.zip` and
    the local output folders keep the original layout.

## 5. Where it can be published

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
