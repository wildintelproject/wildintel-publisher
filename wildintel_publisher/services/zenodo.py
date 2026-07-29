"""Preparación y publicación en Zenodo del mismo producto que 'hfh prepare'
usa para HuggingFace Hub — pero sin imágenes sueltas: Zenodo solo aloja
ficheros pequeños de metadatos (más un zip autocontenido si se elige
--self-contained), a cambio de un DOI permanente para citar el dataset. Ver
services.product.ProductAdapter para lo específico de cada tipo de producto.

API de Zenodo: token por cabecera 'Authorization: Bearer', nunca por query
param. sandbox.zenodo.org para pruebas (sin DOI real), zenodo.org para
producción.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
import yaml
from rich.console import Console

from wildintel_publisher.config import REPO_ROOT, ZenodoSettings
from wildintel_publisher.services import common, product

console = Console()

DEFAULT_VERSION = "1.0"

# Used by the generic services.doi_populate to know which repos are
# candidate DOI *sources* — see hfh.py's own PROVIDES_DOI (always False).
PROVIDES_DOI = True

COMMON_TEMPLATES_DIR = REPO_ROOT / "templates" / "common"
LICENSE_TEMPLATE_FILE = COMMON_TEMPLATES_DIR / "LICENSE.j2"
CITATION_TEMPLATE_FILE = COMMON_TEMPLATES_DIR / "CITATION.cff.j2"

README_FILENAME = "README.md"
CITATION_FILENAME = "CITATION.cff"
RECORD_FILENAME = "zenodo_record.json"

SANDBOX_DOI_DESCRIPTION = "Zenodo Sandbox DOI for workflow testing only"

# Zip autocontenido de --self-contained: a diferencia de camtrapdp-local.zip
# (hfh), que asume que la carpeta images/ ya vive físicamente al lado del
# zip, este empaqueta también las imágenes DENTRO del propio zip — Zenodo no
# aloja estructuras de carpetas, solo ficheros sueltos, así que el zip tiene
# que bastarse solo.
SELF_CONTAINED_ZIP_FILENAME = "camtrapdp.zip"


def _self_contained_zip_filename(product_type: str) -> str:
    """Named per product type — SELF_CONTAINED_ZIP_FILENAME is only the
    Camtrap DP name; other product types (e.g. yolo) get their own
    type-named zip instead of a filename that only makes sense for
    Camtrap DP."""
    return SELF_CONTAINED_ZIP_FILENAME if product_type == product.CAMTRAPDP else f"{product_type}.zip"

# Marcador del CITATION.cff/README.md de --self-contained (link mode ya
# apunta a una URL real, la de HuggingFace Hub) — sustituido por la URL del
# resolver del DOI en cuanto upload_to_zenodo lo consigue (Zenodo lo
# reserva gratis en la propia respuesta de update_deposition_metadata, ver
# extract_reserved_doi/_patch_readme_with_doi), o si no, al publicar (ver
# release_on_zenodo). En sandbox nunca se sustituye — el DOI de prueba no es
# citable de verdad (ver _patch_citation_with_doi).
PLACEHOLDER_CITATION_URL = "(DOI assigned by Zenodo upon publication)"


def prepare_zenodo_export(
    *,
    input_dir: Path,
    output_dir: Path,
    metadata: ZenodoSettings,
    hfh_repo_id: Optional[str] = None,
    self_contained: bool = False,
    version: str = DEFAULT_VERSION,
    image_timeout: int = common.DEFAULT_IMAGE_TIMEOUT,
    overwrite: bool = False,
) -> Path:
    """Copia el producto de `input_dir` a `output_dir` (vía el ProductAdapter
    de su tipo, leído de `input_dir`/metadata.json) y escribe README.md,
    CITATION.cff, LICENSE y checksums-sha256.txt.

    Tres modos, mutuamente excluyentes, para la referencia a la media:

    - `self_contained=True`: hace que el adapter descargue/copie la media a
      `output_dir`/images/ y genera `camtrapdp.zip` (todo el producto + la
      propia carpeta images/, dentro del zip) — un único fichero
      autocontenido, sin depender de red ni de ningún otro repositorio.
      Tiene prioridad sobre `hfh_repo_id` si ambos se indican.
    - `hfh_repo_id` (sin `self_contained`): no descarga nada — hace que el
      adapter reescriba la referencia a la media a la URL predecible de
      HuggingFace Hub (asumiendo que ya está, o va a estar, subida allí vía
      'hfh upload').
    - Ninguno de los dos: la referencia se deja tal cual traía `input_dir`,
      sin modificar.

    title/description/version/licencia/autores salen siempre de
    metadata.json, igual que en 'hfh prepare' — sin fallback aquí (ya se
    validaron una vez al generarlo).

    Returns:
        `output_dir`, listo para subir a Zenodo.

    Raises:
        RuntimeError: si `input_dir` no existe, si `output_dir` ya existe y
        tiene contenido (y `overwrite` es False), si `input_dir` no tiene
        metadata.json, o si el producto no pasa la validación de su propio
        ProductAdapter.
    """
    if not input_dir.is_dir():
        raise RuntimeError(
            f"{input_dir} does not exist — generate the package first with 'trapper download' "
            "(or pass --input-dir pointing to where you downloaded it)."
        )
    if self_contained and hfh_repo_id:
        console.print(
            "[yellow]⚠ Both --self-contained and --hfh-repo-id were given — --self-contained "
            "takes precedence, --hfh-repo-id is ignored for the filePath rewrite (it's still "
            "used to link the HuggingFace Hub dataset from README.md).[/yellow]"
        )

    common.ensure_output_dir(output_dir, overwrite=overwrite)

    product_meta = product.read_metadata_json(input_dir)
    adapter = product.get_adapter(product_meta["product_type"])

    console.print(f"Copying the product from {input_dir} to {output_dir} ...")
    adapter.prepare(input_dir, output_dir, mirror=self_contained, image_timeout=image_timeout)
    product.copy_metadata_json(input_dir, output_dir)

    if not self_contained and hfh_repo_id:
        rewritten = adapter.link_media_to_hfh(output_dir, hfh_repo_id)
        console.print(f"  {rewritten} media reference(s) now pointing to HuggingFace Hub.")

    title = product_meta["title"]
    description = product_meta["description"]
    resolved_version = product_meta.get("version") or version
    license = product_meta["license"]
    authors = product_meta["authors"]
    date_released = datetime.now().date().isoformat()

    write_readme(
        output_dir, metadata, resolved_version, adapter,
        title=title, description=description, license_id=license["id"],
        authors=authors, date_released=date_released, hfh_repo_id=hfh_repo_id,
        homepage=product_meta.get("homepage"), self_contained=self_contained,
    )
    common.write_license(
        LICENSE_TEMPLATE_FILE, output_dir,
        license_id=license["id"], license_name=license["name"], license_url=license["url"],
    )
    common.write_citation(
        CITATION_TEMPLATE_FILE, output_dir,
        title=title, message="If you use this dataset, please cite it as below.",
        authors=authors, version=resolved_version, date_released=date_released,
        license_id=license["id"],
        repository_code="https://github.com/wildintelproject/wildintel-publisher",
    )
    if self_contained:
        zip_filename = _self_contained_zip_filename(adapter.product_type)
        adapter.bundle_local_zip(input_dir, output_dir, output_dir / zip_filename, embed_images=True)
        common.cleanup_self_contained_sources(output_dir, adapter, product_meta, zip_filename)
    common.write_checksums(output_dir)

    console.print(f"[green]✔  Zenodo record prepared in {output_dir}[/green]")
    return output_dir


def write_readme(
    output_dir: Path, metadata: ZenodoSettings, version: str, adapter: product.ProductAdapter, *,
    title: str, description: str, license_id: str, authors: list, date_released: str,
    hfh_repo_id: Optional[str], homepage: Optional[str] = None, self_contained: bool,
) -> Path:
    """Renders templates/common/README-{product_type}-body.md.j2 (shared
    with hfh.py/b2share.py for the same product_type) with Zenodo's own
    format fragment slotted in (see
    templates/zenodo/_readme-format-{product_type}.md.j2 — it folds its own
    "where this lives" bit in directly, so no location_template here,
    unlike HFH).

    The citation URL (and, via `homepage`, the format fragment's own "where
    this lives" text) falls back through: self-contained -> placeholder
    (patched with the real DOI once reserved); hfh_repo_id -> Hugging Face
    Hub (Camtrap DP/YOLO's usual link-mode target); homepage -> wherever
    metadata.json says the product's own source lives (Software's only
    option, since it has no HFH target at all — see
    REPOS_BY_PRODUCT_TYPE.software); else the same HFH placeholder text
    used when self-contained (nothing better to point at)."""
    path = output_dir / README_FILENAME
    hfh_repo_id_display = hfh_repo_id or "REPLACE_WITH_HF_USER/dataset"
    if self_contained:
        citation_url = PLACEHOLDER_CITATION_URL
    elif hfh_repo_id:
        citation_url = f"https://huggingface.co/datasets/{hfh_repo_id}"
    elif homepage:
        citation_url = homepage
    else:
        citation_url = f"https://huggingface.co/datasets/{hfh_repo_id_display}"
    body_template = COMMON_TEMPLATES_DIR / f"README-{adapter.product_type}-body.md.j2"
    text = common.render_text_template(
        body_template,
        dataset_name=title,
        version=version,
        description=description,
        hfh_repo_id=hfh_repo_id_display,
        homepage=homepage,
        self_contained=self_contained,
        zip_filename=_self_contained_zip_filename(adapter.product_type),
        license_id=license_id,
        repository_code="https://github.com/wildintelproject/wildintel-publisher",
        record_noun="record",
        format_template=f"zenodo/_readme-format-{adapter.product_type}.md.j2",
        location_template=None,
        apa_citation=common.format_apa_citation(
            authors=authors, title=title, version=version, date_released=date_released,
            publisher="Zenodo", url=citation_url,
        ),
        **adapter.readme_context(output_dir),
    )
    path.write_text(text, encoding="utf-8")
    return path


# ── API de Zenodo ────────────────────────────────────────────────────────────

def _base_url(environment: str) -> str:
    return "https://sandbox.zenodo.org" if environment == "sandbox" else "https://zenodo.org"


def _api_base_url(environment: str) -> str:
    return f"{_base_url(environment)}/api"


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _binary_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/octet-stream"}


def _check_response(response: httpx.Response, expected: tuple, context: str) -> None:
    if response.status_code in expected:
        return
    try:
        body = response.json()
    except Exception:
        body = response.text
    raise RuntimeError(f"{context} failed. HTTP status={response.status_code}. Response={body}")


def create_deposition(api_base_url: str, token: str) -> dict:
    response = httpx.post(f"{api_base_url}/deposit/depositions", headers=_headers(token), json={}, timeout=60)
    _check_response(response, (200, 201), "Create Zenodo deposition")
    return response.json()


def get_deposition(api_base_url: str, token: str, deposition_id: int) -> dict:
    url = f"{api_base_url}/deposit/depositions/{deposition_id}"
    response = httpx.get(url, headers=_headers(token), timeout=60)
    _check_response(response, (200,), "Fetch Zenodo deposition")
    return response.json()


def update_deposition_metadata(api_base_url: str, token: str, deposition_id: int, metadata: dict) -> dict:
    url = f"{api_base_url}/deposit/depositions/{deposition_id}"
    response = httpx.put(url, headers=_headers(token), json={"metadata": metadata}, timeout=60)
    _check_response(response, (200, 201), "Update Zenodo deposition metadata")
    return response.json()


def upload_file_to_bucket(bucket_url: str, token: str, file_path: Path, remote_filename: str) -> dict:
    url = f"{bucket_url}/{remote_filename}"
    response = httpx.put(url, headers=_binary_headers(token), content=file_path.read_bytes(), timeout=300)
    _check_response(response, (200, 201), f"Upload file to Zenodo: {remote_filename}")
    return response.json()


def publish_deposition(api_base_url: str, token: str, deposition_id: int) -> dict:
    url = f"{api_base_url}/deposit/depositions/{deposition_id}/actions/publish"
    response = httpx.post(url, headers=_headers(token), timeout=60)
    _check_response(response, (200, 201, 202), "Publish Zenodo deposition")
    return response.json()


def extract_reserved_doi(deposition: dict) -> Optional[str]:
    """Prioridad: metadata.prereserve_doi.doi (draft con prereserve_doi=True) ->
    metadata.doi (ya publicado) -> doi de nivel superior (también solo tras publicar)."""
    metadata = deposition.get("metadata", {})
    if isinstance(metadata, dict):
        prereserve = metadata.get("prereserve_doi")
        if isinstance(prereserve, dict) and prereserve.get("doi"):
            return str(prereserve["doi"])
        if metadata.get("doi"):
            return str(metadata["doi"])
    if deposition.get("doi"):
        return str(deposition["doi"])
    return None


def is_already_published(deposition: dict) -> bool:
    if deposition.get("submitted") is True:
        return True
    if str(deposition.get("state", "")).lower() in {"done", "published"}:
        return True
    links = deposition.get("links", {})
    if isinstance(links, dict) and not links.get("publish"):
        if deposition.get("record_id") or deposition.get("doi"):
            return True
    return False


def build_zenodo_metadata(*, title: str, description: str, authors: list, license_id: str, communities: Optional[str], related_identifier_url: Optional[str]) -> dict:
    creators = []
    for author in authors:
        if author.get("given_names"):
            name = f"{author.get('family_names', '')}, {author.get('given_names', '')}"
        else:
            name = author.get("name", "")
        creator = {"name": name}
        if author.get("affiliation"):
            creator["affiliation"] = author["affiliation"]
        creators.append(creator)

    metadata = {
        "title": title,
        "upload_type": "dataset",
        "description": description,
        "creators": creators,
        "access_right": "open",
        "license": license_id.lower(),
        "prereserve_doi": True,
    }
    if related_identifier_url:
        metadata["related_identifiers"] = [
            {"identifier": related_identifier_url, "relation": "isSupplementTo", "resource_type": "dataset", "scheme": "url"}
        ]
    if communities:
        community_slugs = [c.strip() for c in communities.split(",") if c.strip()]
        if community_slugs:
            metadata["communities"] = [{"identifier": slug} for slug in community_slugs]

    return metadata


def _read_record(output_dir: Path) -> dict:
    record_path = output_dir / RECORD_FILENAME
    if not record_path.is_file():
        raise RuntimeError(
            f"{record_path} not found — run 'zenodo upload' before 'zenodo release'/'zenodo sync-doi'."
        )
    return json.loads(record_path.read_text(encoding="utf-8"))


def _write_record(output_dir: Path, record: dict) -> None:
    (output_dir / RECORD_FILENAME).write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")


def upload_to_zenodo(
    output_dir: Path, *, token: str, environment: str, communities: Optional[str], hfh_repo_id: Optional[str],
) -> dict:
    """Crea (o reutiliza, si ya existe zenodo_record.json) un depósito en
    Zenodo, le pone los metadatos (título/descripción/autores/licencia,
    enlazando al dataset de HuggingFace Hub vía related_identifiers) — lo
    que además reserva el DOI gratis en la propia respuesta (prereserve_doi,
    ver build_zenodo_metadata/extract_reserved_doi) —, y solo ENTONCES sube
    todos los ficheros de `output_dir` (menos zenodo_record.json): si el DOI
    ya se reservó, CITATION.cff/README.md se parchean con él justo antes de
    subirlos, para que ya lleguen a Zenodo con el DOI real dentro en vez de
    solo tras 'zenodo release' (en sandbox, CITATION.cff sí se parchea, pero
    en identifiers/notes, no en el doi/url principal — y README.md nunca,
    igual que hace _patch_citation_with_doi al publicar).

    Returns:
        El registro local {"deposition_id", "environment", "doi", ...} — ya
        guardado en `output_dir`/zenodo_record.json.

    Raises:
        RuntimeError: si falla cualquier llamada a la API de Zenodo.
    """
    api_base_url = _api_base_url(environment)
    record_path = output_dir / RECORD_FILENAME

    product_meta = product.read_metadata_json(output_dir)
    license = product_meta["license"]
    authors = product_meta["authors"]
    related_identifier_url = f"https://huggingface.co/datasets/{hfh_repo_id}" if hfh_repo_id else None

    zenodo_metadata = build_zenodo_metadata(
        title=product_meta["title"],
        description=product_meta["description"],
        authors=authors,
        license_id=license["id"],
        communities=communities,
        related_identifier_url=related_identifier_url,
    )

    if record_path.is_file():
        record = json.loads(record_path.read_text(encoding="utf-8"))
        deposition_id = record["deposition_id"]
        console.print(f"Reusing the existing Zenodo deposition: {deposition_id}")
        deposition = get_deposition(api_base_url, token, deposition_id)
        if is_already_published(deposition):
            raise RuntimeError(
                f"Deposition {deposition_id} is already published — it cannot be modified. "
                "For a new version, delete zenodo_record.json and run 'zenodo upload' again "
                "(this will create a new deposition, unrelated to the already-published one)."
            )
    else:
        console.print("Creating a new deposition on Zenodo...")
        deposition = create_deposition(api_base_url, token)
        deposition_id = deposition["id"]

    deposition = update_deposition_metadata(api_base_url, token, deposition_id, zenodo_metadata)

    bucket_url = deposition.get("links", {}).get("bucket")
    if not bucket_url:
        raise RuntimeError("Zenodo's response does not include links.bucket — files cannot be uploaded.")

    doi = extract_reserved_doi(deposition)
    record_url = deposition.get("links", {}).get("html") or f"{_base_url(environment)}/deposit/{deposition_id}"
    if doi:
        _patch_citation_with_doi(output_dir / CITATION_FILENAME, doi=doi, record_url=record_url, environment=environment)
        if environment != "sandbox":
            _patch_readme_with_doi(output_dir / README_FILENAME, f"https://doi.org/{doi}")
        common.write_checksums(output_dir)
        console.print(f"[green]✔  DOI reserved ahead of upload: {doi}[/green]")

    # metadata.json is internal pipeline bookkeeping (product_type,
    # publish_history...), kept locally for chaining/re-reading — never
    # meant to be part of the published record itself.
    files = sorted(
        p for p in output_dir.iterdir()
        if p.is_file() and p.name not in (RECORD_FILENAME, product.METADATA_FILENAME)
    )
    console.print(f"Uploading {len(files)} file(s) to deposition {deposition_id} ...")
    for file_path in files:
        upload_file_to_bucket(bucket_url, token, file_path, file_path.name)
        console.print(f"  [green]✓[/green] {file_path.name}")

    record = {
        "deposition_id": deposition_id,
        "environment": environment,
        "doi": doi,
        "record_url": record_url,
        "published": False,
    }
    _write_record(output_dir, record)

    console.print(f"[green]✔  Deposition {deposition_id} prepared (reserved DOI: {doi or 'not yet available'}).[/green]")
    return record


def release_on_zenodo(output_dir: Path, *, token: str) -> dict:
    """Publica el depósito de Zenodo referenciado en
    `output_dir`/zenodo_record.json (si aún no estaba publicado), y refleja
    el DOI real en el propio CITATION.cff/checksums de `output_dir`.

    Returns:
        El registro local actualizado (con "doi"/"record_url"/"published").

    Raises:
        RuntimeError: si no hay zenodo_record.json, o si falla la publicación.
    """
    record = _read_record(output_dir)
    api_base_url = _api_base_url(record["environment"])
    deposition_id = record["deposition_id"]

    deposition = get_deposition(api_base_url, token, deposition_id)
    if is_already_published(deposition):
        console.print(f"Deposition {deposition_id} was already published.")
    else:
        console.print(f"Publishing deposition {deposition_id} ...")
        publish_deposition(api_base_url, token, deposition_id)
        deposition = get_deposition(api_base_url, token, deposition_id)

    doi = extract_reserved_doi(deposition)
    if not doi:
        raise RuntimeError(f"Zenodo did not return a DOI for deposition {deposition_id}.")

    record.update({
        "doi": doi,
        "record_url": deposition.get("links", {}).get("record_html") or deposition.get("links", {}).get("html") or record["record_url"],
        "published": True,
    })
    _write_record(output_dir, record)

    _patch_citation_with_doi(output_dir / CITATION_FILENAME, doi=doi, record_url=record["record_url"], environment=record["environment"])
    common.write_checksums(output_dir)

    console.print(f"[green]✔  Published — DOI: {doi} ({record['record_url']})[/green]")
    return record


def _patch_readme_with_doi(readme_path: Path, doi_url: str) -> None:
    """Sustituye PLACEHOLDER_CITATION_URL (solo aparece en modo
    --self-contained — link mode ya cita la URL real de HuggingFace Hub) por
    la URL del resolver del DOI en el README.md ya renderizado — mismo
    patrón de parcheo-de-texto-plano que hfh.py's
    _patch_readme_with_repo_id/b2share.py's _patch_readme_with_doi, en vez
    de volver a renderizar la plantilla. Solo se llama con un DOI de
    producción (ver upload_to_zenodo) — nunca con uno de sandbox."""
    if not readme_path.is_file():
        return
    text = readme_path.read_text(encoding="utf-8")
    readme_path.write_text(text.replace(PLACEHOLDER_CITATION_URL, doi_url), encoding="utf-8")


def _patch_citation_with_doi(citation_path: Path, *, doi: str, record_url: str, environment: str) -> None:
    """Escribe el DOI en un CITATION.cff (vía common.patch_citation_with_identifier).
    En producción, en el campo doi/url de nivel superior. En sandbox (sin
    DOI real), en la lista identifiers, marcado explícitamente como "solo
    para pruebas" — para no confundirlo nunca con una cita formal (y con
    un "notes" propio explicándolo, que la función genérica no conoce)."""
    if environment == "sandbox":
        changed = common.patch_citation_with_identifier(
            citation_path, value=doi, kind="doi", url=None,
            description=SANDBOX_DOI_DESCRIPTION, allow_as_primary=False,
        )
        if changed and citation_path.is_file():
            citation = yaml.safe_load(citation_path.read_text(encoding="utf-8")) or {}
            citation["notes"] = (
                "This CITATION.cff contains a Zenodo Sandbox DOI for workflow testing only. "
                "Do not use the Sandbox DOI for formal citation."
            )
            citation_path.write_text(yaml.safe_dump(citation, sort_keys=False, allow_unicode=True), encoding="utf-8")
    else:
        common.patch_citation_with_identifier(
            citation_path, value=doi, kind="doi", url=record_url, description="Zenodo DOI",
        )


def sync_doi_to_hfh(*, zenodo_output_dir: Path, hfh_output_dir: Path) -> str:
    """Lee el DOI ya publicado en `zenodo_output_dir`/zenodo_record.json, y lo
    refleja en el CITATION.cff (y, en producción, la sección "## Citation"
    de su README.md — ver common.patch_readme_citation_url) de
    `hfh_output_dir` (el export ya preparado para HuggingFace Hub) —
    regenerando también sus checksums. El paso recomendado después es
    volver a subir con 'hfh upload'.

    Returns:
        El DOI sincronizado.

    Raises:
        RuntimeError: si el depósito de Zenodo todavía no está publicado
        (sin DOI), o si `hfh_output_dir`/CITATION.cff no existe.
    """
    record = _read_record(zenodo_output_dir)
    doi = record.get("doi")
    if not doi or not record.get("published"):
        raise RuntimeError(
            f"The Zenodo deposition in {zenodo_output_dir} is not published yet — "
            "run 'zenodo release' first."
        )

    hfh_citation_path = hfh_output_dir / CITATION_FILENAME
    if not hfh_citation_path.is_file():
        raise RuntimeError(f"{hfh_citation_path} not found — run 'hfh prepare' first.")

    _patch_citation_with_doi(hfh_citation_path, doi=doi, record_url=record["record_url"], environment=record["environment"])
    if record["environment"] != "sandbox":
        # Sandbox DOIs are never cited as primary (see _patch_citation_with_doi) —
        # the README's own citation stays as-is (its own repo URL) either way.
        common.patch_readme_citation_url(hfh_output_dir / README_FILENAME, record["record_url"])
    common.write_checksums(hfh_output_dir)

    console.print(f"[green]✔  DOI {doi} reflected in {hfh_citation_path}.[/green]")
    console.print("   Re-upload with [bold]hfh upload[/bold] to publish the change.")
    return doi
