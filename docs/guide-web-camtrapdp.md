# Web App User Guide — Camtrap DP

A step-by-step walkthrough of publishing a Camtrap DP package using the web app's wizard —
screen by screen, with no commands involved. See the [Publishing
Guide](publishing-guide.md) for the concepts referenced along the way (media modes,
locking, the generic pipeline). Before starting, make sure every repository account you
plan to use is ready — see [Before you start](guide-web.md#before-you-start).

---

## 1. Choose what to publish

On the wizard's first screen, pick **Camtrap DP**.

![Choosing what to publish](img/web/product-selection.png)

## 2. Choose where it comes from

Pick **Trapper Instance** to fetch a package from a Trapper classification project,
**Local Directory** if you already have one on this machine, or **Public URL** to fetch
an already-published Camtrap DP zip archive from a public URL (validated against the
official schema on the way in — the same URL is then reusable as-is for
[GBIF](publishing-gbif.md)'s own archive URL, since it's already confirmed public).

![Choosing where the package comes from](img/web/source-selection.png)

## 3. Confirm the package and its description

Once the package is ready (downloaded, or already local), the wizard shows where it
lives. If its common description is missing something required (title, description,
version, license, authors), a form prompts for exactly what's missing; once complete, a
summary card shows the title, version, license, authors, and homepage.

![Confirming the package's description](img/web/confirm-package.png)

![Confirming the package's description](img/web/confirm-package.png)

## 4. Choose repositories and publish order

For Camtrap DP, the wizard only offers **Hugging Face Hub** and **GBIF** (Zenodo/B2SHARE
stay available for it via the CLI only). **GBIF is mandatory** here — pre-selected and
not deselectable, so a Camtrap DP dataset always ends up registered with GBIF; Hugging
Face Hub is optional alongside it.

If both are selected, Hugging Face Hub always publishes first — this isn't a choice you
make (there's no manual reordering for this pair): GBIF's own configuration form depends
on knowing what Hugging Face Hub already did. Its **Archive URL** field auto-fills and
locks to Hugging Face Hub's own `camtrapdp-remote.zip`, but only when Hugging Face Hub is
configured to publish in **Mirror** mode — that file is never generated in **Link** mode,
so in that case (or when GBIF is the only one selected) the field is left unlocked
instead, with a note that you need to provide a separate, already-public archive URL by
hand (see [GBIF](guide-web-gbif.md)).

![Choosing repositories and publish order](img/web/repo-selection.png)

## 5. Configure each selected repository

The wizard walks through your selected repositories one at a time, each with its own
configuration form — see that repository's own page for the full form, field-by-field,
with a screenshot: [Hugging Face Hub](guide-web-hfh.md), [Zenodo](guide-web-zenodo.md),
[B2SHARE](guide-web-b2share.md), [GBIF](guide-web-gbif.md).

## 6. Choose the primary DOI (only if HFH, Zenodo and B2SHARE are all selected)

If Hugging Face Hub, Zenodo, and B2SHARE are all selected together, you're asked which
of Zenodo's or B2SHARE's DOI should be treated as *primary* in Hugging Face Hub's own
citation file — Hugging Face Hub never has a DOI of its own, so this only comes up when
there's more than one candidate to choose from.

![Choosing the primary DOI](img/web/primary-doi-choice.png)

## 7. Confirm and publish

After a final summary screen, **Publish** runs the whole sequence on its own: uploading
to every selected repository, cross-referencing whatever DOIs Zenodo/B2SHARE obtained
into each other's (and Hugging Face Hub's) citation file, then locking each repository —
with a single live progress view showing every repository's status as it goes. GBIF has
no upload/lock of its own to speak of — it's registered with a single Registry API call
during this same automated sequence, using the archive URL from step 5 (see [Publishing
to GBIF](publishing-gbif.md#2-main-characteristics)).

## 8. When it's done

![All repositories published](img/web/all-done.png)

The wizard confirms which repositories were published, but doesn't print each one's
resulting URL/DOI/PID directly on this screen — check the repository itself, or the
record file its own output directory holds (`zenodo_record.json`,
`b2share_record.json`, `gbif_linked_dataset_record.json`). If Zenodo and/or B2SHARE were
published, you can also use the **Sync DOI**/**Sync PID** sections shown here — besides
reflecting the DOI/PID into an already-published Hugging Face Hub export, they confirm
success with a direct link back to it (see [Zenodo](guide-web-zenodo.md#sync-doi-to-hugging-face-hub)/
[B2SHARE](guide-web-b2share.md#sync-piddoi-to-hugging-face-hub)). If B2SHARE is still
pending moderator review, that's shown too — its final PID/DOI won't be known until a
moderator approves the submission, which happens outside this wizard run.

If GBIF was published alongside Hugging Face Hub in the same run and came back with a
DOI, it's already synced into Hugging Face Hub's `CITATION.cff` automatically — this
screen just confirms it, with a link back to the export, no extra step needed. GBIF's own
**Sync DOI** section only shows up as something to fill in by hand when that couldn't
happen automatically (GBIF published on its own, without Hugging Face Hub in the same
run) — see [Publishing to GBIF](publishing-gbif.md).
