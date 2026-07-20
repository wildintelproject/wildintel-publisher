# Publishing to GBIF

This guide explains what **GBIF** is, its main characteristics as a publishing target,
and what can be published to it — see the [CLI User Guide](guide-cli.md#7-register-it-on-gbif)
for the exact command-line steps, or the [Web App User Guide](guide-web.md#4-choose-repositories-and-publish-order)
for the same thing from the wizard.

---

## 1. What is GBIF

[GBIF](https://www.gbif.org/) (the Global Biodiversity Information Facility) is the
world's largest network and data infrastructure for biodiversity occurrence data,
aggregating records from thousands of publishers. GBIF also runs a **sandbox** instance
(`gbif-test.org`) with an identical Registry API, used for testing without touching a
real, publicly-visible dataset — note it requires its own separate account and
organization, not shared with production `gbif.org`.

## 2. Main characteristics

Unlike Hugging Face Hub, Zenodo, and B2SHARE, **GBIF never hosts a copy of the
package** — it only registers, in its [Registry](https://www.gbif.org/developer/registry),
a dataset whose `CAMTRAP_DP` endpoint points at a URL where the Camtrap DP is already
publicly hosted (typically one of this project's other repositories, or anywhere else
public). GBIF's own crawler then fetches and indexes it as biodiversity occurrence data
within a few hours — this project never talks to that crawler directly.

Because there's nothing to host, there is no `prepare`/`upload`/`release` sequence and
no [publishing mode](publishing-guide.md#publishing-modes) to choose — a single
`gbif register --archive-url <url>` command creates the dataset the first time and
updates it (replacing its `CAMTRAP_DP` endpoint) on every later run, so re-running it
after publishing a new version is always safe.

Publishing through GBIF requires an **organization** endorsed by a GBIF Participant
Node, and an **installation** registered under it — both created by hand on `gbif.org`
(or its sandbox), since this is a manual review process that cannot be automated via
API. See the [CLI User Guide](guide-cli.md#before-you-start) for how to obtain and
configure `publishing_organization_key`/`installation_key`; `gbif register` prints
step-by-step guidance itself if either is missing. Unlike Zenodo/B2SHARE's single
access token, the Registry API authenticates with your gbif.org account's
username/password (`GBIF_USERNAME`/`GBIF_PASSWORD`).

!!! note "No separate 'locking' step"
    There's no equivalent to Zenodo's irreversible `release` or B2SHARE's moderator
    review here — every `register` run is immediately live. This also means it's the
    only repository in this project where re-publishing a corrected URL later is
    completely safe by design.

## 3. How to publish

For the exact steps — first-time account/organization/installation setup and a full
example — see the [CLI User Guide](guide-cli.md#7-register-it-on-gbif) or the [Web App
User Guide](guide-web.md#4-choose-repositories-and-publish-order).

## 4. What can I publish here?

| Product type | Availability |
|---|---|
| Camtrap DP | ✅ Available |
| YOLO Dataset | ❌ Not applicable |
| YOLO-based AI models | ❌ Not applicable |

Camtrap DP is a biodiversity data standard GBIF/TDWG recognize natively — YOLO training
datasets and models are machine-learning artifacts, not occurrence records, so they
aren't a fit for GBIF (see [Products](products.md#where-products-can-be-published)).
Unlike Zenodo/B2SHARE, this is the only product type GBIF will ever support, so — unlike
their per-product-type pages — one page is enough to cover it.
