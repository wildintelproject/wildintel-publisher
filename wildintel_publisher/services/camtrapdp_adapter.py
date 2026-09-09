"""ProductAdapter for Camtrap DP packages — wraps the existing camtrapdp-
specific logic in services.common (validation, datapackage.json reading,
private-media filtering, image mirroring, local zip bundling) behind the
generic ProductAdapter interface (see services.product), so hfh/zenodo/
b2share no longer need to know any of this directly.
"""
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from typing import Optional

from wildintel_publisher.services import common, product

# Appended as the closing paragraph of every Camtrap DP's description (see
# extract_metadata below) — regardless of source (Trapper, a public URL, a
# local directory) or whether the user edited datapackage.json's own
# description by hand (e.g. the web wizard's metadata-editing step).
# Attribution wildintel-publisher itself always wants present in what ends
# up in metadata.json, and from there in every publish artifact that reads
# it (README.md, and the description actually sent to GBIF's Registry API —
# see services.gbif.register_gbif_dataset — Zenodo, B2SHARE).
CAMTRAPDP_DESCRIPTION_FOOTER = "Camtrap DP camera-trap dataset, published via the WildINTEL project. https://wildintel.eu/"


def _append_description_footer(description: Optional[str]) -> str:
    description = (description or "").strip()
    if description.endswith(CAMTRAPDP_DESCRIPTION_FOOTER):
        return description  # already there — don't duplicate it
    if not description:
        return CAMTRAPDP_DESCRIPTION_FOOTER
    return f"{description}\n\n{CAMTRAPDP_DESCRIPTION_FOOTER}"


class CamtrapDPAdapter:
    product_type = product.CAMTRAPDP

    def validate(self, input_dir: Path) -> None:
        common.validate_camtrap_dp(input_dir)

    def extract_metadata(self, input_dir: Path) -> dict:
        """Best-effort: never raises for a missing title/description/
        license/authors — returns None/[] for whatever datapackage.json
        doesn't provide, so generate_metadata_json can still write
        metadata.json and let the user fill the gaps afterwards (see
        product.missing_required_fields). description always gets
        CAMTRAPDP_DESCRIPTION_FOOTER appended, on top of whatever
        datapackage.json itself provides (or nothing, if it's blank)."""
        datapackage_meta = common.read_datapackage_metadata(input_dir)
        try:
            license_info = common.resolve_license(datapackage_meta.get("licenses", []))
        except RuntimeError:
            license_info = None
        try:
            authors = common.resolve_authors(datapackage_meta.get("contributors", []))
        except RuntimeError:
            authors = []
        contact = common.resolve_contact(datapackage_meta.get("contributors", []))
        return {
            "title": datapackage_meta.get("title"),
            "description": _append_description_footer(datapackage_meta.get("description")),
            "version": datapackage_meta.get("version"),
            "license": license_info,
            "authors": authors,
            "contact": contact,
            "homepage": datapackage_meta.get("homepage"),
        }

    def checkout_release(self, input_dir: Path, *, version: Optional[str]) -> Optional[str]:
        return None  # Camtrap DP's raw source isn't a git checkout in this pipeline's sense

    def prepare(
        self, input_dir: Path, output_dir: Path, *, mirror: bool, image_timeout: int,
        media_dir: Optional[Path] = None,
    ) -> None:
        common.copy_core_camtrapdp_files(input_dir, output_dir)

        # The PUBLISHED datapackage.json itself must carry the same
        # attribution its description gets in metadata.json (see
        # extract_metadata) — copy_core_camtrapdp_files above only copies
        # input_dir's own datapackage.json byte-for-byte, so without this it
        # would ship without the footer even though metadata.json (and
        # everything generated from it — README.md, GBIF's registered
        # description, Zenodo/B2SHARE) already has it. Patched only on the
        # OUTPUT copy — input_dir (the working copy, or the user's own
        # original) is never touched.
        output_datapackage_meta = common.read_datapackage_metadata(output_dir)
        common.update_datapackage_fields(output_dir, {
            "description": _append_description_footer(output_datapackage_meta.get("description")),
        })

        self.validate(output_dir)

        public_media_ids = common.keep_only_public_media(output_dir)
        common.drop_observations_of_removed_media(output_dir, public_media_ids)
        if mirror:
            common.download_public_images(output_dir, input_dir=media_dir or input_dir, timeout=image_timeout)

    def anonymize_coordinates(self, input_dir: Path, *, decimals: int) -> None:
        common.anonymize_deployment_coordinates(input_dir, decimals=decimals)

    def randomize_media_ids(self, input_dir: Path, *, domain: str = "localhost") -> None:
        common.randomize_media_ids(input_dir, domain=domain)

    def extract_core_files(self, output_dir: Path, target_dir: Path) -> None:
        target_dir.mkdir(parents=True, exist_ok=True)
        if (output_dir / common.DATAPACKAGE_FILENAME).is_file():
            for filename in common.CORE_CAMTRAPDP_FILES:
                source = output_dir / filename
                if source.is_file():
                    shutil.copy2(source, target_dir / filename)
            return

        # --self-contained mode already bundled datapackage.json/deployments.csv/
        # media.csv/observations.csv (and images/, if embedded) into a zip and
        # removed the loose copies (see common.write_local_zip/
        # cleanup_self_contained_sources) — pull them back out of that zip
        # instead, so this repo's own "prepared" output (output_mode='prepared')
        # and whatever repo comes next in the publish order (see
        # services.publish_orchestrator's chaining) still get something usable.
        zip_path = next(output_dir.glob("*.zip"), None)
        if zip_path is None:
            return
        with zipfile.ZipFile(zip_path) as zf:
            names = [name for name in zf.namelist() if not name.endswith("/")]
            # write_local_zip(embed_images=True) nests everything under a
            # single root folder (the zip's own stem) so the same archive
            # also works as GBIF's --archive-url — strip that one common
            # prefix back off here so target_dir ends up flat again, same as
            # every other branch of this method.
            root_prefix = ""
            if names:
                first_root = names[0].split("/", 1)[0] + "/"
                if all(name.startswith(first_root) for name in names):
                    root_prefix = first_root
            for name in names:
                destination = target_dir / name[len(root_prefix):]
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(zf.read(name))

    def link_media_to_hfh(self, output_dir: Path, hfh_repo_id: str) -> int:
        return common.rewrite_media_filepaths_to_hfh(output_dir, hfh_repo_id)

    def bundle_local_zip(self, input_dir: Path, output_dir: Path, zip_path: Path, *, embed_images: bool) -> None:
        common.write_local_zip(output_dir, zip_filename=zip_path.name, embed_images=embed_images)

    def readme_context(self, output_dir: Path) -> dict:
        return {}  # Camtrap DP's README fragments (see templates/*/_readme-format-camtrapdp.md.j2) need nothing extra


product.register_adapter(CamtrapDPAdapter())
