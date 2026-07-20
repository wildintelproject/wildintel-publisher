# wildintel-publisher

![WildINTEL](img/wildIntel_logo.webp){ style="display: block; margin: 0 auto;" }

**wildintel-publisher** publishes products generated within the
[WildINTEL](https://wildintel.eu/) project — currently [Camtrap DP](https://camtrap-dp.tdwg.org/)
camera-trap packages, fetched from a [Trapper](https://gitlab.com/trapper-project/trapper)
classification project, and [YOLO](https://docs.ultralytics.com/datasets/) training datasets,
already prepared locally, with more product types planned — to a range of open-data
repositories: [Hugging Face Hub](https://huggingface.co/), [Zenodo](https://zenodo.org/),
[B2SHARE (EUDAT)](https://b2share.eudat.eu/) 🇪🇺, and — for Camtrap DP —
[GBIF](https://www.gbif.org/).

---

## Documentation Map

**[Products](products.md)**

What each supported product type is, how it's obtained, and what turning it into a
publishable export involves: [Camtrap DP](product-camtrapdp.md) ·
[YOLO Dataset](product-yolo.md).

**[Publishing Guide](publishing-guide.md)**

The publishing process shared by every repository: the generic prepare → upload →
release pipeline, the three publishing modes, what "locking" a publish means per
repository, and the CLI vs. web-app ways of running it.

**Publishing to each repository**

Every uploaded file explained, and the exact commands to publish either product type:
[Hugging Face Hub](publishing-hfh.md) · [Zenodo](publishing-zenodo.md) ·
[B2SHARE (EUDAT)](publishing-b2share.md) 🇪🇺.

**[Features](features.md)**

What makes this tool and its CLI/web app stand out — product types, repository
integrations, and capabilities.

**[Developer Guide](developer-guide.md)**

For anyone extending the tool itself: adding a new product type or a new repository
integration.

**[About](about.md)**

Background on the project, WildINTEL, and funding.

---

## Quick start

```bash
# 1. Set up the environment
./setup.sh
source .venv/bin/activate

# 2. Fetch a Camtrap DP package from Trapper
wildintel-publisher trapper download --deployment-id <deployment-id>

# 3. Generate metadata.json, then prepare/upload/release to your repository of choice
wildintel-publisher product generate-metadata \
  --input-dir <trapper-output-dir> --product-type camtrapdp
```

See the [Publishing Guide](publishing-guide.md) for the full process, and each
repository's own guide for the exact commands to publish there.
