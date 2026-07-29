# Publishing to Hugging Face Hub

This guide explains what **Hugging Face Hub** is, its main characteristics as a
publishing target, and what can be published to it — see the
[CLI](guide-cli.md)/[Web App](guide-web-hfh.md) User Guides for the exact steps.

---

## 1. What is Hugging Face Hub

[Hugging Face Hub](https://huggingface.co) is the leading platform for sharing machine
learning models and datasets. It provides git-based versioning for every repository, a
built-in dataset viewer so anyone can browse files without downloading anything, and
public or private visibility that can be switched at any time.

In this project's publishing flow, Hugging Face Hub is the repository that actually
**hosts the media** (images, in mirror mode) — Zenodo and B2SHARE, by default, only
link back to it rather than duplicating the images themselves. It's also the only
repository here with no DOI of its own: it's built for hosting and versioning data, not
for formal citation.

## 2. Main characteristics

A Hugging Face **dataset repository** can hold any file, of any size — there's no split
between "data" and "metadata" platforms the way Zenodo/B2SHARE are used in this
project. Everything (images, tables, documentation) lives in one git-versioned
repository, and `upload` pushes the *entire* prepared export to it in one go.

Every export also carries a generated **dataset card** (`README.md`, rendered from a
shared template with Hugging Face-specific formatting), a **license file**, a
machine-readable **`CITATION.cff`**, and a **checksums manifest** covering everything —
so the record is self-describing and citable regardless of which product ended up in
it. The exact product files alongside them — and whether images travel as individual
files, get linked elsewhere, or are left out — depends on the product type and media
mode; see [What can I publish here?](#4-what-can-i-publish-here) below.

## 3. How to publish

For the exact steps — first-time account/token setup, the full sequence, and one
example per product type — see:

- **[CLI User Guide](guide-cli.md)** — the `hfh prepare`/`upload`/`release` (and
  one-shot `pipeline`) commands.
- **[Web App User Guide](guide-web-hfh.md)** — the same flow through the wizard, no
  commands involved.

## 4. What can I publish here?

| Product type | Availability |
|---|---|
| [Camtrap DP](publishing-hfh-camtrapdp.md) | ✅ Available |
| [AI Dataset](publishing-hfh-yolo.md) | ✅ Available |
| YOLO-based AI models | 🔜 Coming soon |

Each link details exactly what ends up stored on Hugging Face Hub for that product type,
and how the choice of [publishing mode](publishing-guide.md#publishing-modes) changes it.
