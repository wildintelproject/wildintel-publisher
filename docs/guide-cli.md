# CLI User Guide

A step-by-step walkthrough of publishing each product type to all three repositories
using the `wildintel-publisher` command line. See the [Publishing Guide](publishing-guide.md)
for the concepts referenced along the way (publishing modes, locking, the generic pipeline),
and each repository's own "What can I publish here?" page for exactly what ends up
stored — this guide is about the commands themselves.

For the same walkthrough without the command line, see the
[Web App User Guide](guide-web.md).

---

## Getting the CLI

Prebuilt binaries — no Python installation required.

1. Go to the [Releases page](https://github.com/wildintelproject/wildintel-publisher/releases)
   and pick the latest stable release (or the `cli-dev` pre-release for the latest
   development build).
2. Download the asset for your OS:
   - **Linux**: `wildintel-publisher-X.Y.Z-linux-x86_64`
   - **macOS** (Apple Silicon): `wildintel-publisher-X.Y.Z-macos-arm64`
   - **Windows**: `wildintel-publisher-X.Y.Z-windows-x64.exe`
3. Run it.

   Linux/macOS — make it executable first:

   <div class="termy">

   ```console
   $ chmod +x wildintel-publisher-X.Y.Z-linux-x86_64
   $ ./wildintel-publisher-X.Y.Z-linux-x86_64 --help

    Usage: wildintel-publisher [OPTIONS] COMMAND [ARGS]...

   ╭─ Commands ─────────────────────────────────────────────────────────────╮
   │ trapper    Fetch Camtrap DP packages from a Trapper project.           │
   │ product    Generate/inspect a product's metadata.json.                 │
   │ hfh        Prepare, upload, and release to Hugging Face Hub.           │
   │ zenodo     Prepare, upload, and release to Zenodo.                     │
   │ b2share    Prepare, upload, and release to B2SHARE.                    │
   │ gbif       Register a Camtrap DP already hosted elsewhere on GBIF.     │
   ╰──────────────────────────────────────────────────────────────────────╯
   ```

   </div>

   Windows — run it from a terminal (or double-click):
   ```powershell
   .\wildintel-publisher-X.Y.Z-windows-x64.exe --help
   ```

Rename the binary to `wildintel-publisher` (`wildintel-publisher.exe` on Windows) and
move it to a directory on your `PATH` so you can invoke it as plain `wildintel-publisher`,
matching every command in the rest of this guide.

---

## Before you start

### Repository credentials

Set these up for whichever repositories you actually plan to use — each is independent.

**Hugging Face Hub**

1. Create an account at [huggingface.co](https://huggingface.co).
2. Get an access token with **write** permission at
   [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens):

   <div class="termy">

   ```console
   $ wildintel-publisher hfh config set token
   Value of token:
   ✔  hfh.token = ••••••••
   ```

   </div>

3. Optionally remember your username, or the full `repo_id` you tend to publish to:

   <div class="termy">

   ```console
   $ wildintel-publisher hfh config set repo_id=your-user/your-dataset
   ✔  hfh.repo_id = your-user/your-dataset
   ```

   </div>

**Zenodo**

1. Create an account at [zenodo.org](https://zenodo.org) (use `sandbox.zenodo.org`
   first to test the whole flow without minting a real DOI).
2. Create a personal access token (**Applications → Personal access tokens**):

   <div class="termy">

   ```console
   $ wildintel-publisher zenodo config set token
   Value of token:
   ✔  zenodo.token = ••••••••
   ```

   </div>

3. Optionally, set which communities every deposition gets submitted to:

   <div class="termy">

   ```console
   $ wildintel-publisher zenodo config set communities=camera-traps,biodiversity
   ✔  zenodo.communities = camera-traps,biodiversity
   ```

   </div>

**B2SHARE (EUDAT)**

1. Create an account at [b2share.eudat.eu](https://b2share.eudat.eu) (use
   `trng-b2share.eudat.eu` first to test without touching a real community/DOI).
2. Get a personal access token (**Account → Applications → Personal access tokens**):

   <div class="termy">

   ```console
   $ wildintel-publisher b2share config set token
   Value of token:
   ✔  b2share.token = ••••••••
   ```

   </div>

3. Set which community every draft requests to join — the generic EUDAT community
   works if you don't have a more specific one:

   <div class="termy">

   ```console
   $ wildintel-publisher b2share config set community_id=e9b9792e-79fb-4b07-b6b4-b9c2bd06d095
   ✔  b2share.community_id = e9b9792e-79fb-4b07-b6b4-b9c2bd06d095
   ```

   </div>

**GBIF** (Camtrap DP only — registration only, no upload)

1. Sign up at [gbif.org](https://www.gbif.org) (use [gbif-test.org](https://www.gbif-test.org)
   first to test without touching a real dataset), and export your credentials — the
   Registry API uses Basic Auth, not a token:

   <div class="termy">

   ```console
   $ export GBIF_USERNAME='your-gbif-username'
   $ export GBIF_PASSWORD='your-gbif-password'
   ```

   </div>

2. Request organization endorsement at
   [gbif.org/become-a-publisher](https://www.gbif.org/become-a-publisher) — a manual
   review by a GBIF Participant Node (days, not instant), so do this well ahead of time
   (see [endorsement guidelines](https://www.gbif.org/endorsement-guidelines) for what
   the node looks at). Once endorsed, set its UUID (from its `gbif.org/publisher/<uuid>`
   page) and add an installation under it (any technical type, e.g. a plain IPT),
   setting its UUID the same way:

   <div class="termy">

   ```console
   $ wildintel-publisher gbif config set publishing_organization_key=<organization-uuid>
   ✔  gbif.publishing_organization_key = <organization-uuid>
   $ wildintel-publisher gbif config set installation_key=<installation-uuid>
   ✔  gbif.installation_key = <installation-uuid>
   ```

   </div>

**Trapper** (Camtrap DP only)

<div class="termy">

```console
$ wildintel-publisher trapper config set base_url=https://trapper.example.org
✔  trapper.base_url = https://trapper.example.org
$ wildintel-publisher trapper config set user_name
Value of user_name:
✔  trapper.user_name = ••••••••
$ wildintel-publisher trapper config set project_id=<classification-project-id>
✔  trapper.project_id = <classification-project-id>
```

</div>

---

## Camtrap DP

### 1. Fetch the package from Trapper

<div class="termy">

```console
$ wildintel-publisher trapper download --deployment-id <deployment-id>
Generating (or reusing) the Camtrap DP package for project <project-id>...
Downloading from https://trapper.example.org/media/packages/camtrapdp_<project-id>.zip ...
Extracting to <trapper-output-dir> ...
✔  Camtrap DP for project <project-id> ready in <trapper-output-dir>
```

</div>

### 2. Generate its common description

<div class="termy">

```console
$ wildintel-publisher product generate-metadata --input-dir <trapper-output-dir> --product-type camtrapdp
✔  metadata.json written to <trapper-output-dir> (camtrapdp):
   title: <package title>
   license: CC-BY-4.0
   authors: <author 1>, <author 2>
```

</div>

Fill in any required field it reports as missing (edit `metadata.json` directly) before
moving on.

### 3. Publish to Hugging Face Hub

<div class="termy">

```console
$ export HF_TOKEN='hf_xxxxxxxxxxxxxxxxxxxxxxxxx'
$ wildintel-publisher hfh prepare --input-dir <trapper-output-dir> --output-dir <hfh-export-dir>
Copying the product from <trapper-output-dir> to <hfh-export-dir> ...
✔  HuggingFace Hub export prepared in <hfh-export-dir>
$ wildintel-publisher hfh upload --output-dir <hfh-export-dir> --repo-id <your-user>/<dataset-slug>
Repository <your-user>/<dataset-slug> does not exist — creating it (private)...
Uploading <hfh-export-dir> to <your-user>/<dataset-slug> ...
✔  Uploaded to https://huggingface.co/datasets/<your-user>/<dataset-slug> (not tagged yet — see 'hfh release').
$ wildintel-publisher hfh release --output-dir <hfh-export-dir> --repo-id <your-user>/<dataset-slug>
  Tagged <your-user>/<dataset-slug> as 'v1.0.0'.
✔  Published at https://huggingface.co/datasets/<your-user>/<dataset-slug>
Making repository <your-user>/<dataset-slug> public ...
✔  <your-user>/<dataset-slug> is publicly accessible without a token: https://huggingface.co/datasets/<your-user>/<dataset-slug>
```

</div>

Or, in one call (`prepare` → `upload` → `release`):

<div class="termy">

```console
$ wildintel-publisher hfh pipeline --repo-id <your-user>/<dataset-slug>
── Step 1/3: prepare ──
✔  HuggingFace Hub export prepared in <hfh-export-dir>
── Step 2/3: upload ──
✔  Uploaded to https://huggingface.co/datasets/<your-user>/<dataset-slug> (not tagged yet — see 'hfh release').
── Step 3/3: release ──
✔  Published at https://huggingface.co/datasets/<your-user>/<dataset-slug>
✔  Pipeline completed.
```

</div>

### 4. Publish to Zenodo, linked to Hugging Face Hub

<div class="termy">

```console
$ export ZENODO_TOKEN='xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
$ wildintel-publisher zenodo prepare --input-dir <trapper-output-dir> --output-dir <zenodo-export-dir> --hfh-repo-id <your-user>/<dataset-slug>
Copying the product from <trapper-output-dir> to <zenodo-export-dir> ...
✔  Zenodo export prepared in <zenodo-export-dir>
$ wildintel-publisher zenodo upload --output-dir <zenodo-export-dir>
Creating a new deposition on Zenodo...
✔  DOI reserved ahead of upload: 10.5281/zenodo.1234567
Uploading 6 file(s) to deposition 1234567 ...
✔  Deposition 1234567 prepared (reserved DOI: 10.5281/zenodo.1234567).
$ wildintel-publisher zenodo release --output-dir <zenodo-export-dir>   # irreversible
Publishing deposition 1234567 ...
✔  Published — DOI: 10.5281/zenodo.1234567 (https://zenodo.org/records/1234567)
```

</div>

Prefer a fully self-contained record instead (no link to Hugging Face Hub)? Use
`--self-contained` instead of `--hfh-repo-id` at the `prepare` step — for Camtrap DP,
this is already the default whenever `--hfh-repo-id` isn't given, so leaving both flags
out has the same effect; pass `--no-self-contained` if you want the old "leave
`media.csv` untouched" (Plain) behavior instead.

### 5. Publish to B2SHARE, linked to Hugging Face Hub

<div class="termy">

```console
$ export B2SHARE_TOKEN='xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
$ wildintel-publisher b2share prepare --input-dir <trapper-output-dir> --output-dir <b2share-export-dir> --hfh-repo-id <your-user>/<dataset-slug>
Copying the product from <trapper-output-dir> to <b2share-export-dir> ...
✔  B2SHARE record prepared in <b2share-export-dir> (linked).
$ wildintel-publisher b2share upload --output-dir <b2share-export-dir> --community-id <community-uuid>
Creating a new draft on B2SHARE...
Requesting inclusion in community <community-uuid> ...
✔  Draft 9f8e7d6c prepared (DOI not reserved yet — 'b2share release' will assign one, possibly pending approval by a moderator of the EUDAT community).
$ wildintel-publisher b2share release --output-dir <b2share-export-dir>   # submits for review, not immediate
Submitting B2SHARE record 9f8e7d6c for community review (may require approval by a moderator of the EUDAT community)...
⚠  Record submitted for publication, but B2SHARE has not returned any PID/DOI yet. Check https://b2share.eudat.eu/records/9f8e7d6c later and run 'b2share sync-pid'.
```

</div>

Same `--self-contained` alternative as Zenodo is available here too.

### 6. Cross-reference the DOIs back into Hugging Face Hub

Once Zenodo/B2SHARE have a DOI/PID (B2SHARE's may take a while — a moderator has to
approve it first), reflect it into the Hugging Face Hub export's `CITATION.cff` and
re-upload:

<div class="termy">

```console
$ wildintel-publisher zenodo sync-doi --zenodo-output-dir <zenodo-export-dir> --hfh-output-dir <hfh-export-dir>
✔  DOI 10.5281/zenodo.1234567 reflected in <hfh-export-dir>/CITATION.cff.
   Re-upload with hfh upload to publish the change.
$ wildintel-publisher b2share sync-pid --b2share-output-dir <b2share-export-dir> --hfh-output-dir <hfh-export-dir>
✔  Nothing to sync yet — B2SHARE has not returned a PID/DOI (still pending moderator approval).
$ wildintel-publisher hfh upload --output-dir <hfh-export-dir> --repo-id <your-user>/<dataset-slug>
Uploading <hfh-export-dir> to <your-user>/<dataset-slug> ...
✔  Uploaded to https://huggingface.co/datasets/<your-user>/<dataset-slug> (not tagged yet — see 'hfh release').
```

</div>

If `sync-pid` reports nothing to sync yet, the B2SHARE moderator hasn't approved the
submission yet — check back later and re-run it.

### 7. Register it on GBIF

`gbif register` doesn't upload anything — it points GBIF's Registry at a URL where the
Camtrap DP is already hosted (here, the Hugging Face Hub export from step 3).

!!! warning "The URL must point to `camtrapdp-remote.zip`, not `datapackage.json` or `camtrapdp-local.zip`"
    GBIF's `CAMTRAP_DP` crawler expects `--archive-url` to point to a **zip archive**
    containing the whole Camtrap DP package, resolvable once extracted in isolation — it
    downloads whatever's at that URL and decompresses it itself. A bare `datapackage.json`
    URL downloads fine but then fails to decompress (silently, as an `ABORT` with no
    records crawled), since it isn't an archive at all. `camtrapdp-local.zip` *is* a real
    zip, but its `media.csv` uses paths relative to a sibling `images/` folder (meant for
    local/offline use, not standalone extraction) — GBIF can't resolve those in isolation
    either. Use `camtrapdp-remote.zip` instead: generated after `hfh upload` has already
    rewritten `media.csv` to real Hugging Face Hub URLs, so every image resolves correctly
    once GBIF extracts it on its own.

<div class="termy">

```console
$ wildintel-publisher gbif register --input-dir <trapper-output-dir> --archive-url https://huggingface.co/datasets/<your-user>/<dataset-slug>/resolve/main/camtrapdp-remote.zip
Registering new GBIF dataset (sandbox)...
Created GBIF dataset: 3a2f9c1e-...
Adding CAMTRAP_DP endpoint: https://huggingface.co/datasets/<your-user>/<dataset-slug>/resolve/main/camtrapdp-remote.zip
✔  GBIF dataset registered: https://registry.gbif-test.org/dataset/3a2f9c1e-...
   GBIF crawls new/updated endpoints within a few hours — check back at the link above.
```

</div>

Re-running `gbif register` (e.g. after publishing a new version) updates the same
dataset and replaces its `CAMTRAP_DP` endpoint, rather than creating a duplicate. See
[Publishing to GBIF](publishing-gbif.md) for what `environment=production` involves.

---

## AI Dataset

Identical shape to Camtrap DP — just a different `--product-type`, and no Trapper step
(an AI Dataset, in YOLO training format, is already a local directory).

### 1. Generate its common description

<div class="termy">

```console
$ wildintel-publisher product generate-metadata --input-dir <yolo-dataset-dir> --product-type yolo
✔  metadata.json written to <yolo-dataset-dir> (yolo):
   title: <dataset title>
   license: CC-BY-4.0
   authors: <author 1>, <author 2>
```

</div>

### 2. Publish to Hugging Face Hub

<div class="termy">

```console
$ export HF_TOKEN='hf_xxxxxxxxxxxxxxxxxxxxxxxxx'
$ wildintel-publisher hfh prepare --input-dir <yolo-dataset-dir> --output-dir <hfh-export-dir>
Copying the product from <yolo-dataset-dir> to <hfh-export-dir> ...
✔  HuggingFace Hub export prepared in <hfh-export-dir>
$ wildintel-publisher hfh upload --output-dir <hfh-export-dir> --repo-id <your-user>/<dataset-slug>
Repository <your-user>/<dataset-slug> does not exist — creating it (private)...
Uploading <hfh-export-dir> to <your-user>/<dataset-slug> ...
✔  Uploaded to https://huggingface.co/datasets/<your-user>/<dataset-slug> (not tagged yet — see 'hfh release').
$ wildintel-publisher hfh release --output-dir <hfh-export-dir> --repo-id <your-user>/<dataset-slug>
  Tagged <your-user>/<dataset-slug> as 'v1.0.0'.
✔  Published at https://huggingface.co/datasets/<your-user>/<dataset-slug>
```

</div>

### 3. Publish to Zenodo

<div class="termy">

```console
$ export ZENODO_TOKEN='xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
$ wildintel-publisher zenodo prepare --input-dir <yolo-dataset-dir> --output-dir <zenodo-export-dir> --self-contained
Copying the product from <yolo-dataset-dir> to <zenodo-export-dir> ...
✔  Zenodo export prepared in <zenodo-export-dir>
$ wildintel-publisher zenodo upload --output-dir <zenodo-export-dir>
Creating a new deposition on Zenodo...
✔  DOI reserved ahead of upload: 10.5281/zenodo.7654321
Uploading 4 file(s) to deposition 7654321 ...
✔  Deposition 7654321 prepared (reserved DOI: 10.5281/zenodo.7654321).
$ wildintel-publisher zenodo release --output-dir <zenodo-export-dir>   # irreversible
Publishing deposition 7654321 ...
✔  Published — DOI: 10.5281/zenodo.7654321 (https://zenodo.org/records/7654321)
```

</div>

YOLO images have nowhere else to link to, so a linked Zenodo record for YOLO would carry
no images at all — `--self-contained` is the meaningful choice here.

### 4. Publish to B2SHARE

<div class="termy">

```console
$ export B2SHARE_TOKEN='xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
$ wildintel-publisher b2share prepare --input-dir <yolo-dataset-dir> --output-dir <b2share-export-dir> --self-contained
Copying the product from <yolo-dataset-dir> to <b2share-export-dir> ...
✔  B2SHARE record prepared in <b2share-export-dir> (self-contained).
$ wildintel-publisher b2share upload --output-dir <b2share-export-dir> --community-id <community-uuid>
Creating a new draft on B2SHARE...
Requesting inclusion in community <community-uuid> ...
✔  Draft 3c2b1a0f prepared (DOI not reserved yet — 'b2share release' will assign one, possibly pending approval by a moderator of the EUDAT community).
$ wildintel-publisher b2share release --output-dir <b2share-export-dir>   # submits for review, not immediate
Submitting B2SHARE record 3c2b1a0f for community review (may require approval by a moderator of the EUDAT community)...
⚠  Record submitted for publication, but B2SHARE has not returned any PID/DOI yet. Check https://b2share.eudat.eu/records/3c2b1a0f later and run 'b2share sync-pid'.
```

</div>

### 5. Cross-reference the DOIs back into Hugging Face Hub

<div class="termy">

```console
$ wildintel-publisher zenodo sync-doi --zenodo-output-dir <zenodo-export-dir> --hfh-output-dir <hfh-export-dir>
✔  DOI 10.5281/zenodo.7654321 reflected in <hfh-export-dir>/CITATION.cff.
   Re-upload with hfh upload to publish the change.
$ wildintel-publisher b2share sync-pid --b2share-output-dir <b2share-export-dir> --hfh-output-dir <hfh-export-dir>
✔  Nothing to sync yet — B2SHARE has not returned a PID/DOI (still pending moderator approval).
$ wildintel-publisher hfh upload --output-dir <hfh-export-dir> --repo-id <your-user>/<dataset-slug>
Uploading <hfh-export-dir> to <your-user>/<dataset-slug> ...
✔  Uploaded to https://huggingface.co/datasets/<your-user>/<dataset-slug> (not tagged yet — see 'hfh release').
```

</div>
