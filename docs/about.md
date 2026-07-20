# About

## wildintel-publisher & WildINTEL

**wildintel-publisher** is a publishing tool developed as part of the
[WildINTEL project](https://wildintel.eu/), an initiative dedicated to the automated
monitoring of wildlife through artificial intelligence and camera-trap imagery. It
publishes products generated within WildINTEL — currently
[Camtrap DP](https://camtrap-dp.tdwg.org/) camera-trap packages, fetched from a
[Trapper](https://gitlab.com/trapper-project/trapper) classification project, and
[YOLO](https://docs.ultralytics.com/datasets/) training datasets, already prepared
locally, with more product types planned — to a range of open-data repositories:
[Hugging Face Hub](https://huggingface.co/), [Zenodo](https://zenodo.org/),
[B2SHARE (EUDAT)](https://b2share.eudat.eu/) 🇪🇺, and — for Camtrap DP —
[GBIF](https://www.gbif.org/), giving WildINTEL's own data and models
a consistent, repeatable path from Trapper (or a local export) to citable, publicly
hosted repositories.

It exists as its own general-purpose tool — rather than one-off publishing scripts per
project — precisely so that any WildINTEL product built on top of Camtrap DP or YOLO
data can reuse the same pipeline, repository integrations, and command-line/web
interfaces, instead of every project reinventing them.

---

## Funding

This work is part of the [WildINTEL project](https://wildintel.eu/), funded by the
[Biodiversa+](https://www.biodiversa.eu/) Joint Research Call 2022–2023 *"Improved
transnational monitoring of biodiversity and ecosystem change for science and society
(BiodivMon)"*.

Biodiversa+ is the European co-funded biodiversity partnership supporting excellent
research on biodiversity with an impact for policy and society. Biodiversa+ is part of
the European Biodiversity Strategy for 2030 that aims to put Europe's biodiversity on a
path to recovery by 2030 and is co-funded by the European Commission.
