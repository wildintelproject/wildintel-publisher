# Software Application

This guide describes the **Software Application** product type — what it is, how it's
obtained, and what gets published. See the [Products](products.md) page for an index of
every product type, and the [Publishing Guide](publishing-guide.md) (plus the
per-repository guides it links to) for how the publishing process itself works.

---

## 1. What is a software application product

A software application in this sense is source code that lives in its own git
repository — a WildINTEL tool, script, or library that's worth archiving as its own
citable artifact, separately from any dataset it might produce or consume.

Unlike YOLO's local-directory pick, this project fetches a software application by
running `git clone` against a repository URL you provide — the web app's wizard clones a
shallow copy locally before anything else happens, the same way it fetches a Camtrap DP
package from Trapper.

## 2. Raw layout

```
.
├── .git/               ← removed before publishing — never part of the export
├── CITATION.cff         ← required — the source of title/description/version/license/authors
└── ...                  ← the rest of the repository's own files
```

Beyond having actually come from a `git clone` (i.e. having a `.git/` directory), a
[`CITATION.cff`](https://citation-file-format.github.io/) file at the repository root is
**required** — it's the sole source of the product's own description, the same standard
this project's own generated exports already use for every product type:

```yaml
cff-version: 1.2.0
title: my-tool
abstract: A WildINTEL command-line tool.
version: 1.0.0
license: MIT
authors:
  - given-names: Jane
    family-names: Doe
    affiliation: WildINTEL project
repository-code: https://github.com/wildintelproject/my-tool
```

Authors can also be an "entity" (an organization, with just a `name`) instead of a
"person" (`given-names`/`family-names`). Whatever field `CITATION.cff` itself doesn't
provide is asked for by hand — the web app's wizard prompts for whatever's still
missing, same as every other product type. The repository's own git remote URL is used
as a fallback homepage when `CITATION.cff` has neither `repository-code` nor `url`.

## 3. What gets published

Before a software application can be published anywhere, it's given a common
description — the same envelope every product type carries, regardless of its own
underlying format:

| Description field | Derived from |
|---|---|
| Title, description, version | `CITATION.cff`'s own `title`/`abstract`/`version` |
| License (id, name, URL) | `CITATION.cff`'s own `license` (a bare SPDX identifier) |
| Authors (name, affiliation) | `CITATION.cff`'s own `authors` list |
| Homepage | `CITATION.cff`'s own `repository-code`/`url`, else the repository's own git remote URL |

Title, description, version, license, and authors are **required** — if `CITATION.cff`
didn't provide one of them, it needs to be added by hand before publishing can proceed.

From there, publishing a software application copies the whole cloned tree (minus
`.git/`) and generates a `README.md`, a machine-readable `CITATION.cff`, a `LICENSE`
file, and a checksums manifest covering everything. If the repository already had its
own `README.md`/`LICENSE`/`CITATION.cff`, those are kept alongside the generated ones
under a `SOURCE_` prefix (e.g. `SOURCE_README.md`) rather than being silently
overwritten.

## 4. Where it can be published

| Repository | Availability |
|---|---|
| [Hugging Face Hub](publishing-hfh.md) | ❌ Not applicable |
| [Zenodo](publishing-zenodo.md) | ✅ Available |
| [B2SHARE (EUDAT)](publishing-b2share.md) 🇪🇺 | ✅ Available |
| [GBIF](https://www.gbif.org/) | ❌ Not applicable |

A software application has no media or biodiversity occurrence content, so neither
Hugging Face Hub nor GBIF is a fit for it — only Zenodo and B2SHARE, which mint a DOI for
the code itself. In the web app's wizard, Zenodo is **mandatory** for this product
type — pre-selected and not deselectable, since its DOI is always the one used to cite
the software (B2SHARE stays optional, alongside it or on its own via the CLI). See
[Products](products.md#where-products-can-be-published) for how this compares to the
other product types.
