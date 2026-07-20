# CLI User Guide

A step-by-step walkthrough of publishing each product type to all three repositories
using the `wildintel-publisher` command line. See the [Publishing Guide](publishing-guide.md)
for the concepts referenced along the way (publishing modes, locking, the generic pipeline),
and each repository's own "What can I publish here?" page for exactly what ends up
stored — this guide is about the commands themselves.

For the same walkthrough without the command line, see the
[Web App User Guide](guide-web.md).

---

## Before you start

### Installing

```bash
./setup.sh
source .venv/bin/activate
```

### Repository credentials

Set these up for whichever repositories you actually plan to use — each is independent.

**Hugging Face Hub**

1. Create an account at [huggingface.co](https://huggingface.co).
2. Get an access token with **write** permission at
   [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens):
   ```bash
   wildintel-publisher hfh config set token
   ```
3. Optionally remember your username, or the full `repo_id` you tend to publish to:
   ```bash
   wildintel-publisher hfh config set repo_id=your-user/your-dataset
   ```

**Zenodo**

1. Create an account at [zenodo.org](https://zenodo.org) (use `sandbox.zenodo.org`
   first to test the whole flow without minting a real DOI).
2. Create a personal access token (**Applications → Personal access tokens**):
   ```bash
   wildintel-publisher zenodo config set token
   ```
3. Optionally, set which communities every deposition gets submitted to:
   ```bash
   wildintel-publisher zenodo config set communities=camera-traps,biodiversity
   ```

**B2SHARE (EUDAT)**

1. Create an account at [b2share.eudat.eu](https://b2share.eudat.eu) (use
   `trng-b2share.eudat.eu` first to test without touching a real community/DOI).
2. Get a personal access token (**Account → Applications → Personal access tokens**):
   ```bash
   wildintel-publisher b2share config set token
   ```
3. Set which community every draft requests to join — the generic EUDAT community
   works if you don't have a more specific one:
   ```bash
   wildintel-publisher b2share config set community_id=e9b9792e-79fb-4b07-b6b4-b9c2bd06d095
   ```

**Trapper** (Camtrap DP only)

```bash
wildintel-publisher trapper config set base_url=https://trapper.example.org
wildintel-publisher trapper config set user_name
wildintel-publisher trapper config set project_id=<classification-project-id>
```

---

## Camtrap DP

### 1. Fetch the package from Trapper

```bash
wildintel-publisher trapper download --deployment-id <deployment-id>
```

### 2. Generate its common description

```bash
wildintel-publisher product generate-metadata \
  --input-dir <trapper-output-dir> --product-type camtrapdp
```

Fill in any required field it reports as missing (edit `metadata.json` directly) before
moving on.

### 3. Publish to Hugging Face Hub

```bash
export HF_TOKEN='hf_xxxxxxxxxxxxxxxxxxxxxxxxx'

wildintel-publisher hfh prepare \
  --input-dir <trapper-output-dir> --output-dir <hfh-export-dir>

wildintel-publisher hfh upload --output-dir <hfh-export-dir> --repo-id <your-user>/<dataset-slug>
wildintel-publisher hfh release --output-dir <hfh-export-dir> --repo-id <your-user>/<dataset-slug>
```

Or, in one call (`prepare` → `upload` → `release`):

```bash
wildintel-publisher hfh pipeline --repo-id <your-user>/<dataset-slug>
```

### 4. Publish to Zenodo, linked to Hugging Face Hub

```bash
export ZENODO_TOKEN='xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'

wildintel-publisher zenodo prepare \
  --input-dir <trapper-output-dir> --output-dir <zenodo-export-dir> \
  --hfh-repo-id <your-user>/<dataset-slug>

wildintel-publisher zenodo upload --output-dir <zenodo-export-dir>
wildintel-publisher zenodo release --output-dir <zenodo-export-dir>   # irreversible
```

Prefer a fully self-contained record instead (no link to Hugging Face Hub)? Use
`--self-contained` instead of `--hfh-repo-id` at the `prepare` step.

### 5. Publish to B2SHARE, linked to Hugging Face Hub

```bash
export B2SHARE_TOKEN='xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'

wildintel-publisher b2share prepare \
  --input-dir <trapper-output-dir> --output-dir <b2share-export-dir> \
  --hfh-repo-id <your-user>/<dataset-slug>

wildintel-publisher b2share upload \
  --output-dir <b2share-export-dir> --community-id <community-uuid>
wildintel-publisher b2share release --output-dir <b2share-export-dir>   # submits for review, not immediate
```

Same `--self-contained` alternative as Zenodo is available here too.

### 6. Cross-reference the DOIs back into Hugging Face Hub

Once Zenodo/B2SHARE have a DOI/PID (B2SHARE's may take a while — a moderator has to
approve it first), reflect it into the Hugging Face Hub export's `CITATION.cff` and
re-upload:

```bash
wildintel-publisher zenodo sync-doi \
  --zenodo-output-dir <zenodo-export-dir> --hfh-output-dir <hfh-export-dir>
wildintel-publisher b2share sync-pid \
  --b2share-output-dir <b2share-export-dir> --hfh-output-dir <hfh-export-dir>

wildintel-publisher hfh upload --output-dir <hfh-export-dir> --repo-id <your-user>/<dataset-slug>
```

If `sync-pid` reports nothing to sync yet, the B2SHARE moderator hasn't approved the
submission yet — check back later and re-run it.

---

## YOLO Dataset

Identical shape to Camtrap DP — just a different `--product-type`, and no Trapper step
(a YOLO dataset is already a local directory).

### 1. Generate its common description

```bash
wildintel-publisher product generate-metadata \
  --input-dir <yolo-dataset-dir> --product-type yolo
```

### 2. Publish to Hugging Face Hub

```bash
export HF_TOKEN='hf_xxxxxxxxxxxxxxxxxxxxxxxxx'

wildintel-publisher hfh prepare \
  --input-dir <yolo-dataset-dir> --output-dir <hfh-export-dir>

wildintel-publisher hfh upload --output-dir <hfh-export-dir> --repo-id <your-user>/<dataset-slug>
wildintel-publisher hfh release --output-dir <hfh-export-dir> --repo-id <your-user>/<dataset-slug>
```

### 3. Publish to Zenodo

```bash
export ZENODO_TOKEN='xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'

wildintel-publisher zenodo prepare \
  --input-dir <yolo-dataset-dir> --output-dir <zenodo-export-dir> --self-contained

wildintel-publisher zenodo upload --output-dir <zenodo-export-dir>
wildintel-publisher zenodo release --output-dir <zenodo-export-dir>   # irreversible
```

YOLO images have nowhere else to link to, so a linked Zenodo record for YOLO would carry
no images at all — `--self-contained` is the meaningful choice here.

### 4. Publish to B2SHARE

```bash
export B2SHARE_TOKEN='xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'

wildintel-publisher b2share prepare \
  --input-dir <yolo-dataset-dir> --output-dir <b2share-export-dir> --self-contained

wildintel-publisher b2share upload \
  --output-dir <b2share-export-dir> --community-id <community-uuid>
wildintel-publisher b2share release --output-dir <b2share-export-dir>   # submits for review, not immediate
```

### 5. Cross-reference the DOIs back into Hugging Face Hub

```bash
wildintel-publisher zenodo sync-doi \
  --zenodo-output-dir <zenodo-export-dir> --hfh-output-dir <hfh-export-dir>
wildintel-publisher b2share sync-pid \
  --b2share-output-dir <b2share-export-dir> --hfh-output-dir <hfh-export-dir>

wildintel-publisher hfh upload --output-dir <hfh-export-dir> --repo-id <your-user>/<dataset-slug>
```
