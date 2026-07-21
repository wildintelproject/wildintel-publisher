# Web App User Guide — GBIF

!!! note
    See [Publishing to GBIF](publishing-gbif.md) for what this repository is: unlike
    Hugging Face Hub, Zenodo, and B2SHARE, it never hosts a copy of the package — it only
    registers, in its Registry, a dataset whose endpoint points at a URL where the
    Camtrap DP is already publicly hosted.

Every time you publish a Camtrap DP to GBIF, a page similar to this one appears, asking
you to fill in the following fields:

![Configure GBIF](img/web/gbif-configure.png)

## Fields

- **Archive URL** — the public URL where the Camtrap DP is already hosted; GBIF will
  crawl it from there. If Hugging Face Hub precedes GBIF in the publish order, this is
  pre-filled automatically (`https://huggingface.co/datasets/<repo>/resolve/main/datapackage.json`,
  fully derived from what you typed into the Hugging Face Hub form) — still editable if
  you'd rather point at somewhere else.
- **Environment** — **Sandbox** (`gbif-test.org`, testing — its own separate account) or
  **Production** (`gbif.org`).
- **Registry language** — ISO 639-2/T code the Registry API requires (defaults to
  `eng`).
- **Publishing organization UUID** / **Installation UUID** — both come from an
  organization endorsed by a GBIF Participant Node and an installation registered under
  it, created by hand at
  [gbif.org/become-a-publisher](https://www.gbif.org/become-a-publisher) (manual review,
  cannot be automated — see the [CLI User Guide](guide-cli.md#before-you-start) for the
  full process). Just want to smoke-test the sandbox first? GBIF's own shared demo
  organization/installation (shown filled in above) works with the demo login below.
- **GBIF username** / **GBIF password** — your gbif.org account (or gbif-test.org's, a
  separate account, for the sandbox). Sign up at
  [gbif.org/user/profile](https://www.gbif.org/user/profile). **Test credentials**
  verifies them immediately. Testing the sandbox only? GBIF publishes a shared demo
  login for exactly that — no signup needed: username `ws_client_demo`, password
  `Demo123` (pairs with the demo organization/installation above).

GBIF has no separate locking step — every registration (create or update) is immediately
live, so re-running it later (e.g. after publishing a new version elsewhere) is always
safe; it replaces the dataset's endpoint in place rather than creating a duplicate. There
is no "Sync" section for GBIF — it doesn't provide a DOI/PID of its own to reflect
anywhere else. See step 8 of the [walkthrough](guide-web-camtrapdp.md#8-when-its-done) for
where its registration shows up once publishing finishes.
