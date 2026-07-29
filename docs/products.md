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
| [AI Dataset](product-yolo.md) | An already-local dataset in YOLO training format | Available |
| [Software Application](product-software.md) | A git repository, cloned via its URL | Available |
| YOLO-based AI models | Trained model weights/checkpoints produced from a YOLO dataset | 🔜 Coming soon |

- **[Camtrap DP](product-camtrapdp.md)** — camera-trap deployments, media, and species
  observations, in the [Camtrap DP](https://camtrap-dp.tdwg.org/) standard. Comes from a
  Trapper classification project, with any media marked private filtered out before
  anything is published anywhere.
- **[AI Dataset](product-yolo.md)** — an object-detection training dataset in
  [YOLO](https://docs.ultralytics.com/datasets/)'s standard layout: images split into
  training/validation/test sets, each paired with its bounding-box labels.
- **[Software Application](product-software.md)** — source code archived as its own
  citable artifact. Comes from a `git clone` of a repository URL you provide.
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
standard, is the only one GBIF (the global biodiversity data network) ever registers.
Unlike the other three, GBIF doesn't host the package itself: `gbif register` only
points GBIF's Registry at a URL where the Camtrap DP is already hosted (e.g. Hugging
Face Hub). YOLO training datasets/models are machine-learning artifacts, and a software
application is source code — neither is biodiversity occurrence data, so GBIF isn't a
fit for either. Conversely, a software application has no media/dataset content of its
own, so Hugging Face Hub isn't a fit for it either — only Zenodo/B2SHARE, which mint a
DOI for the code itself.

| Repository | Camtrap DP | AI Dataset | Software Application | YOLO-based AI models |
|---|:---:|:---:|:---:|:---:|
| [Hugging Face Hub](publishing-hfh.md) | ✅ | ✅ | ❌ | 🔜 |
| [Zenodo](publishing-zenodo.md) | ✅ | ✅ | ✅ | 🔜 |
| [B2SHARE (EUDAT)](publishing-b2share.md) 🇪🇺 | ✅ | ✅ | ✅ | 🔜 |
| [GBIF](publishing-gbif.md) | ✅ | ❌ | ❌ | ❌ |

✅ available today · 🔜 planned · ❌ not applicable

!!! note "The web wizard narrows Camtrap DP further, to Hugging Face Hub + GBIF only"
    The table above reflects what each repository integration actually supports — the
    CLI's `hfh`/`zenodo`/`b2share`/`gbif` commands stay generic across product types (see
    the [Developer Guide](developer-guide.md)). The web app's own wizard, however, only
    lets a Camtrap DP package be published to Hugging Face Hub and GBIF, keeping
    Zenodo/B2SHARE reserved for AI Datasets and software applications in that flow. GBIF
    is **mandatory** there — pre-selected and not deselectable, so a Camtrap DP dataset
    always ends up registered with GBIF (Hugging Face Hub stays optional alongside it).

See the [Publishing Guide](publishing-guide.md) for how the publishing process itself
works, and each repository's own guide (linked above) for what publishing a given
product there actually involves.
