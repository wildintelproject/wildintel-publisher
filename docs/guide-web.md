# Web App User Guide

A step-by-step walkthrough of publishing each product type to all three repositories
using the web app's wizard — screen by screen, with no commands involved. See the
[Publishing Guide](publishing-guide.md) for the concepts referenced along the way (media
modes, locking, the generic pipeline), and each repository's own "What can I publish
here?" page for exactly what ends up stored.

For the same walkthrough using the command line instead, see the
[CLI User Guide](guide-cli.md).

---

## Getting the web app

Prebuilt binaries — no Python or Node installation required.

1. Go to the [Releases page](https://github.com/wildintelproject/wildintel-publisher/releases)
   and pick the latest stable release (or the `web-dev` pre-release for the latest
   development build).
2. Download the asset for your OS:
   - **Linux**: `wildintel-publisher-web-X.Y.Z-linux-x86_64`
   - **macOS** (Apple Silicon): `wildintel-publisher-web-X.Y.Z-macos-arm64`
   - **Windows**: `wildintel-publisher-web-X.Y.Z-windows-x64.exe`
3. Run it.

   Linux/macOS — make it executable first:
   ```bash
   chmod +x wildintel-publisher-web-X.Y.Z-linux-x86_64
   ./wildintel-publisher-web-X.Y.Z-linux-x86_64
   ```

   Windows — run it from a terminal (or double-click):
   ```powershell
   .\wildintel-publisher-web-X.Y.Z-windows-x64.exe
   ```

It starts a local server and opens your default browser automatically (falling back to
the next free port if its default one is busy) — no separate step needed.

---

## Before you start

Have your Hugging Face Hub / Zenodo / B2SHARE access tokens ready — the wizard's own
configuration forms are where you enter them, there's no separate account or config-file
setup step. If you've already saved any of them via the CLI's `config set` commands, the
wizard pre-fills its forms with those same saved values (both share the same
`settings.toml`).

Publishing to GBIF additionally needs a gbif.org username/password and an organization/
installation UUID pair, obtained in advance by hand — see [Publishing to
GBIF](publishing-gbif.md#2-main-characteristics) for how to get them (the wizard's own
GBIF form links to the same pages).

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

Select one or more of **Hugging Face Hub**, **Zenodo**, **B2SHARE**, and — Camtrap DP
only, see [Publishing to GBIF](publishing-gbif.md#4-what-can-i-publish-here) — **GBIF**.
If you select more than one, a **publish order** list lets you reorder them: the first
repository publishes the fetched package itself, and each next one publishes whatever the
previous one wrote to its own output — so, for example, publishing to Hugging Face Hub
before Zenodo lets Zenodo's record link back to it. GBIF doesn't take part in this
chaining (it never hosts a copy of the package — see the next step), but ordering it
after whichever repository will host the package still lets its configuration form
prefill the archive URL automatically.

### 5. Configure each selected repository

The wizard walks through your selected repositories one at a time, each with its own
configuration form:

- **Hugging Face Hub** — repository id, token, mirror images or link only, and whether
  to start it private.
- **Zenodo** — token, environment (sandbox or production), communities to submit to,
  and self-contained or linked media.
- **B2SHARE** — token, environment, community, and self-contained or linked media.
- **GBIF** — the archive URL (prefilled if Hugging Face Hub precedes it in the publish
  order — see the previous step), environment, publishing organization/installation UUID,
  registry language, and username/password. No mirror/link choice: GBIF never hosts a
  copy of anything.

### 6. Choose the primary DOI (only if all three are selected)

If Hugging Face Hub, Zenodo, and B2SHARE are all selected together, you're asked which
of Zenodo's or B2SHARE's DOI should be treated as *primary* in Hugging Face Hub's own
citation file — Hugging Face Hub never has a DOI of its own, so this only comes up when
there's more than one candidate to choose from.

### 7. Confirm and publish

After a final summary screen, **Publish** runs the whole sequence on its own: uploading
to every selected repository, cross-referencing whatever DOIs Zenodo/B2SHARE obtained
into each other's (and Hugging Face Hub's) citation file, then locking each repository —
with a single live progress view showing every repository's status as it goes. GBIF has
no upload/lock of its own to speak of — it's registered with a single Registry API call
during this same automated sequence, using the archive URL from step 5 (see [Publishing
to GBIF](publishing-gbif.md#2-main-characteristics)).

### 8. When it's done

Each repository's resulting URL/DOI/PID is shown once publishing finishes — for GBIF,
its Registry dataset page. If B2SHARE is still pending moderator review, that's shown
too — its final PID/DOI won't be known until a moderator approves the submission, which
happens outside this wizard run.

---

## YOLO Dataset

Same shape as Camtrap DP, with two differences: at step 2, only **Local Directory** is
offered (a YOLO dataset is never fetched from Trapper), and its images always travel
together with `data.yaml` in self-contained/mirror mode — there's no external repository
for YOLO images to link to instead.
