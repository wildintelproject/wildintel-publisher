# Web App User Guide

A step-by-step walkthrough of publishing each product type to all three repositories
using the web app's wizard — screen by screen, with no commands involved. See the
[Publishing Guide](publishing-guide.md) for the concepts referenced along the way (media
modes, locking, the generic pipeline), and each repository's own "What can I publish
here?" page for exactly what ends up stored.

For the same walkthrough using the command line instead, see the
[CLI User Guide](guide-cli.md).

---

## Before you start

Start the web app from `wildintel_publisher_web/` (see the project's own `README.md`):

```bash
uv run wildintel-publisher-web dev
```

then open it in your browser. Have your Hugging Face Hub / Zenodo / B2SHARE access
tokens ready — the wizard's own configuration forms are where you enter them, there's
no separate account or config-file setup step. If you've already saved any of them via
the CLI's `config set` commands, the wizard pre-fills its forms with those same saved
values (both share the same `settings.toml`).

---

## Camtrap DP

### 1. Choose what to publish

On the wizard's first screen, pick **Camtrap DP**.

### 2. Choose where it comes from

Pick **Trapper Instance** to fetch a package from a Trapper classification project, or
**Local Directory** if you already have one on this machine.

### 3. Confirm the package and its description

Once the package is ready (downloaded, or already local), the wizard shows where it
lives. If its common description is missing something required (title, description,
version, license, authors), a form prompts for exactly what's missing; once complete, a
summary card shows the title, version, license, authors, and homepage.

### 4. Choose repositories and publish order

Select one or more of **Hugging Face Hub**, **Zenodo**, and **B2SHARE** (GBIF is coming
soon). If you select more than one, a **publish order** list lets you reorder them: the
first repository publishes the fetched package itself, and each next one publishes
whatever the previous one wrote to its own output — so, for example, publishing to
Hugging Face Hub before Zenodo lets Zenodo's record link back to it.

### 5. Configure each selected repository

The wizard walks through your selected repositories one at a time, each with its own
configuration form:

- **Hugging Face Hub** — repository id, token, mirror images or link only, and whether
  to start it private.
- **Zenodo** — token, environment (sandbox or production), communities to submit to,
  and self-contained or linked media.
- **B2SHARE** — token, environment, community, and self-contained or linked media.

### 6. Choose the primary DOI (only if all three are selected)

If Hugging Face Hub, Zenodo, and B2SHARE are all selected together, you're asked which
of Zenodo's or B2SHARE's DOI should be treated as *primary* in Hugging Face Hub's own
citation file — Hugging Face Hub never has a DOI of its own, so this only comes up when
there's more than one candidate to choose from.

### 7. Confirm and publish

After a final summary screen, **Publish** runs the whole sequence on its own: uploading
to every selected repository, cross-referencing whatever DOIs Zenodo/B2SHARE obtained
into each other's (and Hugging Face Hub's) citation file, then locking each repository —
with a single live progress view showing every repository's status as it goes.

### 8. When it's done

Each repository's resulting URL/DOI/PID is shown once publishing finishes. If B2SHARE is
still pending moderator review, that's shown too — its final PID/DOI won't be known
until a moderator approves the submission, which happens outside this wizard run.

---

## YOLO Dataset

Same shape as Camtrap DP, with two differences: at step 2, only **Local Directory** is
offered (a YOLO dataset is never fetched from Trapper), and its images always travel
together with `data.yaml` in self-contained/mirror mode — there's no external repository
for YOLO images to link to instead.
