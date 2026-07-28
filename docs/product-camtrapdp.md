# Camtrap DP

This guide describes the **Camtrap DP** product type — what it is, how it's obtained, and
what gets published. See the [Products](products.md) page for an index of every product
type, and the [Publishing Guide](publishing-guide.md) (plus the per-repository guides it
links to) for how the publishing process itself works.

---

## 1. What is Camtrap DP

[Camtrap DP](https://camtrap-dp.tdwg.org/) (Camera Trap Data Package) is a community
data exchange standard for structuring and sharing camera-trap data, maintained under
[Frictionless Data](https://frictionlessdata.io/) and the
[TDWG](https://www.tdwg.org/) biodiversity-informatics community. It describes camera
deployments, the media (images/videos) they captured, and the observations
(species/individual identifications) derived from that media, as a small set of
tabular files tied together by one JSON metadata descriptor.

In this project, a Camtrap DP package is obtained one of three ways before anything is
published: fetched from a [Trapper](https://gitlab.com/trapper-project/trapper)
classification project (the platform researchers use to manage camera-trap deployments
and classify the media they capture — an export of a given project, optionally scoped
to a single deployment, is generated, downloaded, and extracted locally), pointed at an
already-local directory, or fetched from a **public URL** to a zip archive of an
already-published Camtrap DP (downloaded and validated against the official schema the
same way a real publish would validate it — useful when re-registering an
already-hosted package with [GBIF](publishing-gbif.md), since the same URL used to fetch
it is then directly reusable as GBIF's own `--archive-url`, already confirmed public and
valid).

## 2. Raw package layout

A Camtrap DP package is four files at the root of a directory:

```
.
├── datapackage.json    ← metadata descriptor (title, license, contributors, resource schemas)
├── deployments.csv     ← one row per camera deployment (location, start/end dates)
├── media.csv           ← one row per media file (deployment, timestamp, filePath, filePublic)
└── observations.csv    ← one row per observation (media/deployment reference, taxonomic id)
```

The original archive Trapper generated is kept alongside the extracted files, and any
compressed table Trapper delivered is transparently decompressed.

### Private media

Not every row in `media.csv` is meant to be published: `filePublic` marks whether a
given media file may be shared publicly (e.g. camera-trap images sometimes capture
people, and Trapper's own privacy rules decide whether a given file counts as public).
The publishing process filters `media.csv` down to public rows only, and drops any
observation that referenced a now-removed media file — private media never leaves your
machine.

### Coordinate anonymization

`deployments.csv`'s `latitude`/`longitude` are exact GPS coordinates by default — fine
for most datasets, but a real concern for sensitive sites (poaching risk, protected
species, private land). An optional **anonymize coordinates** setting rounds every
deployment's coordinates to a fixed number of decimal places (2 by default, ≈ 1.1 km
at the equator) — deliberately deterministic rather than a random offset, so the same
deployment ends up with identical rounded coordinates on every repository it's
published to.

This is a **product-level preprocessing step**, applied once — as part of
[generating `metadata.json`](publishing-guide.md), right after the raw package is
obtained, in `--input-dir` itself — rather than something each repository's own
prepare step decides independently. Every repository that later prepares its own
export from that same `--input-dir` (directly, or chained from another repository's
own already-prepared output) inherits the already-anonymized coordinates
automatically, with nothing extra to pass at that point. In the web app's wizard, the
option appears once a Camtrap DP source is picked (Step 1); on the CLI, it's
`--anonymize-coordinates`/`--coordinate-decimals` on `product generate-metadata`. It's
off by default — coordinates are published exactly as provided unless explicitly
enabled.

Because it mutates `--input-dir` in place, enabling it against a **Local Directory**
source rounds the coordinates in that directory's own `deployments.csv` directly —
there's no separate "raw" copy kept anywhere with the original precision.

### `filePath` — a one-shot token URL, or already local

`media.csv`'s `filePath`, as delivered by Trapper, is a temporary, one-time-use signed
URL — it resolves once (or for a limited time) and then expires. This is why the
publishing process rewrites it before publishing anywhere permanent — to a predictable
Hugging Face Hub URL, to a self-contained bundle with a relative path, or, for a quick,
throwaway local inspection rather than anything meant to stay citable, left as-is — see
[Publishing modes](publishing-guide.md#publishing-modes) in the Publishing Guide.

An already-local, self-contained Camtrap DP package (the standard's own alternative to
an absolute URL) instead has `filePath` values as paths *relative to the package
itself* — e.g. `images/<file>.jpg`, resolving against a sibling `images/` folder next to
`datapackage.json` (the same convention this project's own `camtrapdp-local.zip`
generates — see this repository's own `examples/camtrapdp/` for a working example you
can point **Local Directory** at). Publishing in mirror mode picks either one up
transparently — an absolute `http(s)://` URL is downloaded, anything else is copied
straight from the local package.

## 3. What gets published

Before a Camtrap DP package can be published anywhere, it's given a common description —
the same envelope every product type carries, regardless of its own underlying format:

| Description field | Derived from |
|---|---|
| Title, description, version, homepage | `datapackage.json`'s own fields |
| License (id, name, URL) | `datapackage.json`'s license entry |
| Authors (name, affiliation) | `datapackage.json`'s contributors |

Title, description, version, license, and authors are **required** — if Trapper's own
`datapackage.json` didn't provide one of them, it needs to be filled in by hand (or via
the web app's wizard, which prompts for whatever's missing) before publishing can
proceed.

The public images and videos themselves — whatever `media.csv` still lists after
private media is filtered out — are also part of what gets published, alongside the
four core files. Whether they travel as actual image files or stay a reference to
wherever they already live depends on which [publishing mode](publishing-guide.md#publishing-modes)
is used: they can be bundled into the publish itself, left as a pointer to an existing
Hugging Face Hub copy, or (for a quick, throwaway inspection only) left out entirely.

From there, publishing a Camtrap DP package generates, on top of its own files, a
`README.md`, a machine-readable `CITATION.cff`, a `LICENSE` file, and a checksums
manifest covering everything — so every published copy is self-describing and citable,
independent of the repository it ends up in.

## 4. Where it can be published

| Repository | Availability |
|---|---|
| [Hugging Face Hub](publishing-hfh.md) | ✅ Available |
| [Zenodo](publishing-zenodo.md) | ✅ Available |
| [B2SHARE (EUDAT)](publishing-b2share.md) 🇪🇺 | ✅ Available |
| [GBIF](publishing-gbif.md) | ✅ Available (registration only, no upload) |

Camtrap DP, being a biodiversity data standard, is the one product type that reaches
every repository this tool supports, including GBIF — which doesn't host the package
itself, just registers wherever you've already published it (see
[Publishing to GBIF](publishing-gbif.md)). See
[Products](products.md#where-products-can-be-published) for how this compares
to the other product types.
