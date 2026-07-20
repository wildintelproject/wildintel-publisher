"""ProductAdapter for Camtrap DP packages — wraps the existing camtrapdp-
specific logic in services.common (validation, datapackage.json reading,
private-media filtering, image mirroring, local zip bundling) behind the
generic ProductAdapter interface (see services.product), so hfh/zenodo/
b2share no longer need to know any of this directly.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from wildintel_publisher.services import common, product


class CamtrapDPAdapter:
    product_type = product.CAMTRAPDP

    def validate(self, input_dir: Path) -> None:
        common.validate_camtrap_dp(input_dir)

    def extract_metadata(self, input_dir: Path) -> dict:
        """Best-effort: never raises for a missing title/description/
        license/authors — returns None/[] for whatever datapackage.json
        doesn't provide, so generate_metadata_json can still write
        metadata.json and let the user fill the gaps afterwards (see
        product.missing_required_fields)."""
        datapackage_meta = common.read_datapackage_metadata(input_dir)
        try:
            license_info = common.resolve_license(datapackage_meta.get("licenses", []))
        except RuntimeError:
            license_info = None
        try:
            authors = common.resolve_authors(datapackage_meta.get("contributors", []))
        except RuntimeError:
            authors = []
        return {
            "title": datapackage_meta.get("title"),
            "description": datapackage_meta.get("description"),
            "version": datapackage_meta.get("version"),
            "license": license_info,
            "authors": authors,
            "homepage": datapackage_meta.get("homepage"),
        }

    def prepare(self, input_dir: Path, output_dir: Path, *, mirror: bool, image_timeout: int) -> None:
        for filename in common.CORE_CAMTRAPDP_FILES:
            source = input_dir / filename
            if source.is_file():
                shutil.copy2(source, output_dir / filename)

        self.validate(output_dir)

        public_media_ids = common.keep_only_public_media(output_dir)
        common.drop_observations_of_removed_media(output_dir, public_media_ids)
        if mirror:
            common.download_public_images(output_dir, timeout=image_timeout)

    def extract_core_files(self, output_dir: Path, target_dir: Path) -> None:
        target_dir.mkdir(parents=True, exist_ok=True)
        for filename in common.CORE_CAMTRAPDP_FILES:
            source = output_dir / filename
            if source.is_file():
                shutil.copy2(source, target_dir / filename)

    def link_media_to_hfh(self, output_dir: Path, hfh_repo_id: str) -> int:
        return common.rewrite_media_filepaths_to_hfh(output_dir, hfh_repo_id)

    def bundle_local_zip(self, output_dir: Path, zip_path: Path, *, embed_images: bool) -> None:
        common.write_local_zip(output_dir, zip_filename=zip_path.name, embed_images=embed_images)

    def readme_context(self, output_dir: Path) -> dict:
        return {}  # Camtrap DP's README fragments (see templates/*/_readme-format-camtrapdp.md.j2) need nothing extra


product.register_adapter(CamtrapDPAdapter())
