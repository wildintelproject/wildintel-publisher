# Products

A **product** is a dataset or model generated within the WildINTEL project that
`wildintel-publisher` can turn into a publishable, citable export. This page is an index
of every product type — what it contains, where it comes from, and which repositories
it can be published to.

---

## Supported product types

| Product type | Source | Availability |
|---|---|---|
| [Camtrap DP](product-camtrapdp.md) | A [Trapper](https://gitlab.com/trapper-project/trapper) classification project | Available |
| [YOLO Dataset](product-yolo.md) | An already-local YOLO training dataset | Available |
| YOLO-based AI models | Trained model weights/checkpoints produced from a YOLO dataset | 🔜 Coming soon |

- **[Camtrap DP](product-camtrapdp.md)** — camera-trap deployments, media, and species
  observations, in the [Camtrap DP](https://camtrap-dp.tdwg.org/) standard. Comes from a
  Trapper classification project, with any media marked private filtered out before
  anything is published anywhere.
- **[YOLO Dataset](product-yolo.md)** — an object-detection training dataset in
  [YOLO](https://docs.ultralytics.com/datasets/)'s standard layout: images split into
  training/validation/test sets, each paired with its bounding-box labels.
- **YOLO-based AI models** *(coming soon)* — trained model weights/checkpoints produced
  from a YOLO dataset, published as their own citable artifact rather than as training
  data.

More product types are planned as WildINTEL produces more kinds of data and models to
share. Every product type shares a common description — title, description, version,
license, and authors — so that whichever one you're publishing ends up equally
well-documented and citable. See the
[Developer Guide](developer-guide.md#adding-a-new-product-type) if you're looking to add
support for a new one to this tool.

---

## Where products can be published

Not every repository accepts every product type. Camtrap DP, being a biodiversity data
standard, can be published to all of them — including GBIF, the global biodiversity data
network. YOLO training datasets and models are machine-learning artifacts rather than
biodiversity occurrence records, so they aren't a fit for GBIF.

| Repository | Camtrap DP | YOLO Dataset | YOLO-based AI models |
|---|:---:|:---:|:---:|
| [Hugging Face Hub](publishing-hfh.md) | ✅ | ✅ | 🔜 |
| [Zenodo](publishing-zenodo.md) | ✅ | ✅ | 🔜 |
| [B2SHARE (EUDAT)](publishing-b2share.md) 🇪🇺 | ✅ | ✅ | 🔜 |
| [GBIF](https://www.gbif.org/) | 🔜 | ❌ | ❌ |

✅ available today · 🔜 planned · ❌ not applicable

See the [Publishing Guide](publishing-guide.md) for how the publishing process itself
works, and each repository's own guide (linked above) for what publishing a given
product there actually involves.
