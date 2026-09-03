# Publishing to GBIF

This guide explains what **GBIF** is, its main characteristics as a publishing target,
and what can be published to it — see the [CLI User Guide](guide-cli.md#7-register-it-on-gbif)
for the exact command-line steps, or the [Web App User Guide](guide-web-gbif.md)
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

!!! warning "`--archive-url` must point to `camtrapdp-remote.zip`"
    GBIF's `CAMTRAP_DP` crawler downloads whatever's at this URL and decompresses it
    itself — a bare `datapackage.json` downloads successfully but then fails to
    decompress (silently: the crawl finishes with `finishReason: ABORT` and nothing ever
    gets indexed, with no error visible anywhere in this project), since it isn't an
    archive. Hugging Face Hub's default mirror mode also generates `camtrapdp-local.zip`,
    but its `media.csv` uses paths relative to a sibling `images/` folder — meaningless
    once GBIF extracts the zip on its own, in isolation. Use `camtrapdp-remote.zip`
    instead — built right after the images have real Hugging Face Hub URLs, so
    `media.csv` resolves correctly with nothing else needed alongside it. The web
    wizard's **Validate archive** button checks this upfront (see
    `gbif.validate_camtrap_dp_archive`) — `gbif register` itself never downloads or
    inspects the archive, so this is only ever caught if you run that check first.

    `camtrapdp-remote.zip` also nests its four files inside a single top-level folder,
    rather than at the zip's own root — GBIF's crawler requires exactly one root
    directory once it unpacks the archive (`org.gbif.utils.file.CompressionUtil` errors
    with "More than one root directory" otherwise, and treats the whole dataset as
    empty — the crawl finishes `NORMAL`, but indexes zero records, with no error visible
    anywhere in this project either).

!!! warning "`observationLevel` must match `datapackage.json`'s `gbifIngestion` field"
    Once the archive itself downloads and decompresses correctly, GBIF's own Camtrap DP
    -> Darwin Core conversion (internally, the `camtrapdp`/`camtraptor` R packages) still
    only keeps observations whose own `observationLevel` (`"event"` or `"media"`, per the
    Camtrap DP standard) matches a `gbifIngestion.observationLevel` field in
    `datapackage.json` — **defaulting to `"event"` when that field is absent**. Trapper's
    own exports (and this project's own `examples/camtrapdp/`) are always media-level, so
    without this field every observation gets silently filtered out — the crawl still
    finishes `NORMAL`, `camtraptor` still writes `occurrence.csv`, just with zero rows in
    it, with no error surfaced anywhere (this project, the GBIF Registry API, or the
    dataset's own page). `camtrapdp-remote.zip` sets this field automatically, detected
    from `observations.csv` itself (see `common.write_remote_zip`) — same as the other two
    fixes above, it's only added to this zip, never to the on-disk `datapackage.json`
    every other repository also copies as-is (it's a GBIF-only vendor extension, not part
    of the Camtrap DP standard itself).

!!! warning "Every `media.csv` filePath must already be a public http(s) URL"
    GBIF never hosts the media itself — once its crawler decompresses and discards the
    archive, `media.csv`'s own `filePath` is the only thing left describing where each
    file lives, turned as-is into a Darwin Core Multimedia extension entry. A relative
    path (e.g. `images/m1.jpg`, valid for a self-contained Camtrap DP package on its
    own) or a local filesystem path never resolves to anything once the archive is gone
    — even if the file sits right next to it inside that very same zip — silently
    leaving every occurrence record with no working media link. The web wizard's
    **Validate archive** button now checks this upfront, the same way it already checks
    the archive's structure and `gbifIngestion` field above (see
    `gbif.validate_camtrap_dp_archive`/`gbif._validate_media_filepaths_are_urls`) —
    `gbif register` itself never downloads/inspects the archive, same as the other two
    checks above, so this is only ever caught if you run **Validate archive** first.

Registering an already-published Camtrap DP that this tool didn't just publish itself?
The web wizard's **Public URL** source (see [Camtrap DP](product-camtrapdp.md#1-what-is-camtrap-dp))
fetches and validates that same zip on the way in, so the URL you point it at is
directly reusable here as `--archive-url` — already confirmed public and valid, no
separate check needed.

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

!!! note "DOI — only if your organization has its own DataCite arrangement"
    GBIF never *requests* a DOI on your behalf — but some organizations have their own
    DataCite arrangement configured with GBIF, which makes it auto-mint one on
    registration anyway (entirely GBIF/organization-side, not something this tool
    controls or can predict). `gbif register` fetches and stores it locally
    (`gbif_linked_dataset_record.json`) whenever one comes back. `gbif sync-doi`
    reflects it into an already-published Hugging Face Hub export's `CITATION.cff`,
    same as `zenodo sync-doi`/`b2share sync-pid` — when the web wizard publishes Hugging
    Face Hub and GBIF together in the same run, this happens automatically; the web
    wizard's own **Sync DOI** section is only a manual fallback for whenever GBIF was
    registered standalone (without Hugging Face Hub in the same run).

!!! note "Mandatory in the web wizard"
    The CLI's own `gbif register` is entirely opt-in, like every other repository
    command. The web wizard, however, makes GBIF **mandatory** for Camtrap DP —
    pre-selected and not deselectable, so a Camtrap DP dataset published through it
    always ends up registered with GBIF (Hugging Face Hub stays optional alongside it,
    and always publishes first when both are selected — see
    [Products](products.md#where-products-can-be-published) and
    [GBIF](guide-web-gbif.md)).

## 3. How to publish

For the exact steps — first-time account/organization/installation setup and a full
example — see the [CLI User Guide](guide-cli.md#7-register-it-on-gbif) or the [Web App
User Guide](guide-web-gbif.md).

## 4. What can I publish here?

| Product type | Availability |
|---|---|
| Camtrap DP | ✅ Available |
| AI Dataset | ❌ Not applicable |
| YOLO-based AI models | ❌ Not applicable |

Camtrap DP is a biodiversity data standard GBIF/TDWG recognize natively — YOLO training
datasets and models are machine-learning artifacts, not occurrence records, so they
aren't a fit for GBIF (see [Products](products.md#where-products-can-be-published)).
Unlike Zenodo/B2SHARE, this is the only product type GBIF will ever support, so — unlike
their per-product-type pages — one page is enough to cover it.
