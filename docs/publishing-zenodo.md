# Publishing to Zenodo

This guide explains what **Zenodo** is, its main characteristics as a publishing target,
and what can be published to it — see the
[CLI](guide-cli.md)/[Web App](guide-web-zenodo.md) User Guides for the exact steps.

---

## 1. What is Zenodo

[Zenodo](https://zenodo.org) is an open-access research data repository operated by
CERN. Researchers use it to archive and share research output — datasets, software,
papers — and it assigns a permanent **DOI** to every published record. Zenodo also runs
a **Sandbox** instance (`sandbox.zenodo.org`) with an identical API, used for testing
without minting real DOIs.

## 2. Main characteristics

A Zenodo record can hold files of any type, including large binary data — but this
project gives you the choice (see [Publishing modes](publishing-guide.md#publishing-modes)):
either a **linked record** (metadata and evidence only, the media stays wherever it
already lives — typically Hugging Face Hub) or a genuinely **self-contained** record
(the media bundled into the record itself, as a single zip).

`zenodo prepare` never talks to Zenodo — it only builds the export locally, exactly
like `hfh prepare`. `zenodo upload` is the command that actually creates (or reuses) a
deposition, **reserves a DOI** as a side effect of setting its metadata (before any file
is even uploaded), and pushes files to it; `zenodo release` is the one that publishes it
for real.

Every export carries a generated dataset description (`README.md`), a **license file**,
a machine-readable **`CITATION.cff`** (patched with the reserved DOI as soon as one
exists), a **checksums manifest**, and a local `zenodo_record.json` recording the
deposition id and DOI so later commands (`upload` re-run, `release`, `sync-doi`) know
which deposition to work with. The exact product files alongside them — loose files or
a single self-contained zip — depends on the product type and publishing mode; see
[What can I publish here?](#4-what-can-i-publish-here) below.

!!! warning "`release` is the only step that publishes"
    `prepare` and `upload` only create/update a **draft** deposition — re-run them as
    many times as you need. Once `release` succeeds, that version's files can never be
    edited or removed; only a new version (a new deposition, a new DOI) can supersede it.

## 3. How to publish

For the exact steps — first-time account/token setup, the full sequence, and one
example per product type — see:

- **[CLI User Guide](guide-cli.md)** — the `zenodo prepare`/`upload`/`release`/
  `sync-doi` commands (there is no combined `pipeline` command for Zenodo — each step
  is run on its own).
- **[Web App User Guide](guide-web-zenodo.md)** — the same flow through the wizard, no
  commands involved.

## 4. What can I publish here?

| Product type | Availability |
|---|---|
| [Camtrap DP](publishing-zenodo-camtrapdp.md) | ✅ Available |
| [AI Dataset](publishing-zenodo-yolo.md) | ✅ Available |
| YOLO-based AI models | 🔜 Coming soon |

Each link details exactly what ends up stored in the Zenodo record for that product
type, and how the choice of [publishing mode](publishing-guide.md#publishing-modes) changes it.

!!! note "Mandatory in the web wizard"
    The CLI's own `zenodo prepare`/`upload`/`release` sequence is entirely opt-in, like
    every other repository command. The web wizard, however, makes Zenodo **mandatory**
    for both AI Dataset and Software Application — pre-selected and not deselectable,
    since its DOI is always the one used to cite the dataset/software (Hugging Face Hub
    and B2SHARE stay optional alongside it for AI Dataset; only B2SHARE does for
    Software Application, which has no Hugging Face Hub target at all — see
    [Products](products.md#where-products-can-be-published),
    [guide-web-yolo.md](guide-web-yolo.md#4-choose-repositories-and-publish-order), and
    [guide-web-software.md](guide-web-software.md#4-choose-repositories)).
