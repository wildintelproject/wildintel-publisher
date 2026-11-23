# <img src="docs/img/wildIntel_logo.webp" alt="WildINTEL Logo" height="60"> wildintel-publisher

![License](https://img.shields.io/badge/license-GPLv3-blue.svg)
[![WildINTEL](https://img.shields.io/badge/WildINTEL-v1.0-blue)](https://wildintel.eu/)
[![TRAPPER](https://img.shields.io/badge/TRAPPER-Server-green)](https://gitlab.com/trapper-project/trapper)

<hr>

## Publishes WildINTEL project products to open-data repositories

**wildintel-publisher** is an open-source tool that publishes products generated within the
[WildINTEL](https://wildintel.eu/) project — currently [Camtrap DP](https://camtrap-dp.tdwg.org/)
camera-trap packages, fetched from a [TRAPPER](https://gitlab.com/trapper-project/trapper)
classification project, and [YOLO](https://docs.ultralytics.com/datasets/) training datasets,
already prepared locally, with more product types planned — to a range of open-data
repositories: [Hugging Face Hub](https://huggingface.co/), [Zenodo](https://zenodo.org/),
[B2SHARE (EUDAT)](https://b2share.eudat.eu/) 🇪🇺, and — for Camtrap DP — [GBIF](https://www.gbif.org/).

Each product goes through the same pipeline regardless of its type or destination: metadata is
generated, the files are prepared and validated, uploaded with a dry run first, and the media
references inside the package are rewritten to point wherever it actually ends up hosted. A CLI
and a web app share the same core and settings.

## 🚀 Quick start

```bash
git clone https://github.com/wildintelproject/wildintel-publisher.git
cd wildintel-publisher
./setup.sh
source .venv/bin/activate
```

```bash
# Fetch a Camtrap DP package from a Trapper classification project
wildintel-publisher trapper download --deployment-id <deployment-id>

# Generate metadata.json for it, then prepare/upload/release to your repository of choice
wildintel-publisher product generate-metadata \
  --input-dir <trapper-output-dir> --product-type camtrapdp
```

See the [Publishing Guide](https://wildintelproject.github.io/wildintel-publisher/publishing-guide/)
for the full prepare → upload → release process, and each repository's own guide for the exact
commands to publish there.

## ✨ Features

**Product types**

- [**Camtrap DP**](https://camtrap-dp.tdwg.org/) camera-trap packages, fetched straight from a
  TRAPPER classification project
- [**YOLO**](https://docs.ultralytics.com/datasets/) training datasets, prepared locally
- More product types planned, on the same pipeline

**Repository integrations**

- [**Hugging Face Hub**](https://huggingface.co/), [**Zenodo**](https://zenodo.org/) and
  [**B2SHARE (EUDAT)**](https://b2share.eudat.eu/) 🇪🇺 for every product type
- [**GBIF**](https://www.gbif.org/) registration for Camtrap DP packages

**Publishing pipeline**

- A shared **prepare → upload → release** flow across repositories, with a **dry run** before
  anything is actually uploaded
- **Locking** a publish once it is released, so a product is not accidentally republished or
  overwritten
- Media references inside each package are rewritten to point to wherever it actually ends up
  hosted

**CLI and web app**

- A guided **web app** and a scriptable **command line** (`wildintel-publisher`), on the same core
  and settings
- A development CLI (`wpcli`) for maintainers of the tool itself

## 📋 Requirements

**To run it**

- Python 3.11+ with [uv](https://docs.astral.sh/uv/)
- Node.js / npm (to build the web app's frontend)
- Access to a [TRAPPER](https://gitlab.com/trapper-project/trapper) server to fetch Camtrap DP
  packages from, and an account on the repositories you publish to

**Technology stack**

| Layer | Technologies |
|---|---|
| Backend | [FastAPI](https://fastapi.tiangolo.com/) served by [Uvicorn](https://www.uvicorn.org/), [Pydantic](https://docs.pydantic.dev/) 2, [Dynaconf](https://www.dynaconf.com/) (settings), [HTTPX](https://www.python-httpx.org/), [tenacity](https://tenacity.readthedocs.io/) (retries) |
| Command line | [Typer](https://typer.tiangolo.com/) and [Rich](https://rich.readthedocs.io/) |
| Products and packaging | [Frictionless](https://framework.frictionlessdata.io/) (Camtrap DP), [Pillow](https://python-pillow.org/) (images), [Jinja2](https://jinja.palletsprojects.com/) (templated READMEs) |
| Integrations | [WildINTEL's Trapper SDK](https://github.com/wildintelproject/wildintelproject-trapper-sdk), [huggingface-hub](https://huggingface.co/docs/huggingface_hub), [boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html) (S3-compatible storage) |
| Frontend | [React](https://react.dev/), [TypeScript](https://www.typescriptlang.org/), [Vite](https://vite.dev/) |
| Packaging and docs | [PyInstaller](https://pyinstaller.org/) (executables), [MkDocs Material](https://squidfunk.github.io/mkdocs-material/) with mike, GitHub Actions |

## 📚 Documentation

Full documentation, in English and Spanish, is available at
**https://wildintelproject.github.io/wildintel-publisher/**

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

To report a bug or request a new feature, please open an
[issue](https://github.com/wildintelproject/wildintel-publisher/issues).

## 🏛️ Funding

This work is part of the [WildINTEL project](https://wildintel.eu/), funded by the
[Biodiversa+](https://www.biodiversa.eu/) Joint Research Call 2022-2023 "Improved
transnational monitoring of biodiversity and ecosystem change for science and society (BiodivMon)". Biodiversa+ is the
European co-funded biodiversity partnership supporting excellent research on biodiversity with an impact for policy and
society. Biodiversa+ is part of the European Biodiversity Strategy for 2030 that aims to put Europe's biodiversity on a
path to recovery by 2030 and is co-funded by the European Commission.

WildINTEL has been co-funded by the [European Commission](https://commission.europa.eu/) (GA No. 101052342) and the following funding organisations: [Agencia Estatal de Investigación](https://www.aei.gob.es/) (Spain, PCI2023-145963-2, PCI2024-153489), [National Science Centre](https://www.ncn.gov.pl/?language=en) (Poland, UMO-2023/05/Y/NZ8/00104), the [Research Council of Norway](https://www.forskningsradet.no/en/) (Norway, NFR350962) and the [German Research Foundation](https://www.dfg.de/en/) (Germany).

## 📝 License

This project is licensed under the GNU General Public License v3.0 or later - see the [LICENSE](LICENSE) file for details.

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License
as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
