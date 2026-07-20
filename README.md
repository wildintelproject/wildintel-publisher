# <img src="docs/img/wildIntel_logo.webp" alt="WildINTEL Logo" height="60"> wildintel-publisher

![License](https://img.shields.io/badge/license-GPLv3-blue.svg)
[![WildINTEL](https://img.shields.io/badge/WildINTEL-v1.0-blue)](https://wildintel.eu/)
[![Trapper](https://img.shields.io/badge/Trapper-Server-green)](https://gitlab.com/trapper-project/trapper)

<hr>

## Publishes WildINTEL project products to HuggingFace Hub, Zenodo, and B2SHARE

**wildintel-publisher** publishes products generated within the
[WildINTEL](https://wildintel.eu/) project — currently [Camtrap DP](https://camtrap-dp.tdwg.org/)
camera-trap packages, fetched from a [Trapper](https://gitlab.com/trapper-project/trapper)
classification project, and [YOLO](https://docs.ultralytics.com/datasets/) training datasets,
already prepared locally, with more product types planned — to a range of open-data
repositories: [HuggingFace Hub](https://huggingface.co/), [Zenodo](https://zenodo.org/),
[B2SHARE (EUDAT)](https://b2share.eudat.eu/) 🇪🇺, and — for Camtrap DP —
[GBIF](https://www.gbif.org/), rewriting the media references inside the package to point
wherever it actually ends up hosted.

## 🚀 Setup

```bash
./setup.sh
source .venv/bin/activate
```

## 📚 Documentation

**https://wildintelproject.github.io/wildintel-publisher/**

## 🏛️ Funding

This work is part of the [WildINTEL project](https://wildintel.eu/), funded by the
[Biodiversa+](https://www.biodiversa.eu/) Joint Research Call 2022–2023
*"Improved transnational monitoring of biodiversity and ecosystem change for science and society (BiodivMon)"*.

## 📝 License

[GNU General Public License v3.0](https://www.gnu.org/licenses/gpl-3.0.html)
