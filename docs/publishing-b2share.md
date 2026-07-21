# Publishing to B2SHARE (EUDAT)

This guide explains what **B2SHARE** is, its main characteristics as a publishing
target, and what can be published to it — see the
[CLI](guide-cli.md)/[Web App](guide-web-b2share.md) User Guides for the exact steps.

---

## 1. What is B2SHARE

[B2SHARE](https://b2share.eudat.eu) is [EUDAT](https://www.eudat.eu/)'s research-data
repository — a European alternative/complement to Zenodo, built on the same
[InvenioRDM](https://inveniosoftware.org/products/rdm/) platform, and also assigning a
permanent DOI to every published record. B2SHARE also runs a **sandbox** instance
(`trng-b2share.eudat.eu`) for testing.

The key difference from Zenodo: **every B2SHARE record must belong to a community**,
and every submission to a community is reviewed by one of that community's moderators
before it actually publishes — there is no self-service "publish" the way Zenodo has.
The generic **EUDAT** community (open to anyone, UUID
`e9b9792e-79fb-4b07-b6b4-b9c2bd06d095` on both the sandbox and production instances) is
a reasonable default if no other community suits your data better.

## 2. Main characteristics

Same choice as [Zenodo](publishing-zenodo.md): a **linked record** (metadata only, the
media stays wherever it already lives) or a **self-contained** one (the media bundled
into the record). Unlike Zenodo, though, B2SHARE's API **caps every record at 100
files** — this is why self-contained publishing here always bundles the media into a
single zip rather than uploading it file by file, regardless of how many images the
dataset actually has.

Same `prepare`/`upload`/`release` split as Zenodo — `prepare` never talks to B2SHARE,
`upload` creates/reuses a draft, requests inclusion in a community, and — best-effort —
**reserves a DOI/PID** ahead of time via a dedicated InvenioRDM endpoint; `release`
submits the draft for community review rather than publishing it outright.

Every export carries a generated dataset description (`README.md`), a **license file**,
a machine-readable **`CITATION.cff`** (patched with the reserved DOI/PID as soon as one
exists), a **checksums manifest**, and a local `b2share_record.json` recording the draft
id and PID (which may end up being a DOI or an EUDAT ePIC handle) so later commands
(`upload` re-run, `release`, `sync-pid`) know which draft to work with. The exact
product files alongside them — loose files or a single self-contained zip — depends on
the product type and publishing mode; see
[What can I publish here?](#4-what-can-i-publish-here) below.

!!! warning "`release` doesn't publish by itself"
    Unlike Zenodo, submitting for review doesn't guarantee — or immediately produce —
    a public, citable record. A moderator of the community you requested has to approve
    it first; until then, `sync-pid` will keep reporting there's nothing to sync yet.

## 3. How to publish

For the exact steps — first-time account/token setup, the full sequence, and one
example per product type — see:

- **[CLI User Guide](guide-cli.md)** — the `b2share prepare`/`upload`/`release`/
  `sync-pid` commands (there is no combined `pipeline` command for B2SHARE — each step
  is run on its own).
- **[Web App User Guide](guide-web-b2share.md)** — the same flow through the wizard, no
  commands involved.

## 4. What can I publish here?

| Product type | Availability |
|---|---|
| [Camtrap DP](publishing-b2share-camtrapdp.md) | ✅ Available |
| [YOLO Dataset](publishing-b2share-yolo.md) | ✅ Available |
| YOLO-based AI models | 🔜 Coming soon |

Each link details exactly what ends up stored in the B2SHARE record for that product
type, and how the choice of [publishing mode](publishing-guide.md#publishing-modes) changes it.
