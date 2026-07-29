"""Registro (o actualización) de un dataset en el Registry de GBIF, apuntando
a un camtrapdp ya alojado en cualquier otra parte (HuggingFace Hub, Zenodo,
B2SHARE, un servidor propio...).

A diferencia de hfh.py/zenodo.py/b2share.py, este módulo no prepara ni sube
ningún fichero — GBIF no aloja nada por sí mismo. Solo habla con la Registry
API (https://www.gbif.org/developer/registry) usando Basic Auth (no un
token), creando o actualizando un dataset de tipo OCCURRENCE y su endpoint
de tipo CAMTRAP_DP, que es lo que hace que el crawler de GBIF vaya a buscar
el paquete a esa URL y lo indexe. Requiere una organización e instalación ya
registradas y endosadas a mano en gbif.org (o su sandbox, gbif-test.org) —
ver commands/gbif.py para el mensaje que explica cómo conseguirlas.
"""
import json
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from rich.console import Console

from wildintel_publisher.services import common

console = Console()

GBIF_ENDPOINT_TYPE = "CAMTRAP_DP"

GBIF_REGISTRY_BASE_URLS = {
    "sandbox": "https://api.gbif-test.org",
    "production": "https://api.gbif.org",
}
CITATION_FILENAME = "CITATION.cff"
README_FILENAME = "README.md"

GBIF_DATASET_PAGE_URL_TEMPLATES = {
    "sandbox": "https://registry.gbif-test.org/dataset/{key}",
    "production": "https://www.gbif.org/dataset/{key}",
}

RECORD_FILENAME = "gbif_linked_dataset_record.json"


def _check_response(response: httpx.Response, expected: tuple, context: str) -> None:
    if response.status_code in expected:
        return
    try:
        body = response.json()
    except Exception:
        body = response.text
    raise RuntimeError(f"{context} failed. HTTP status={response.status_code}. Response={body}")


def _read_record(output_dir: Path) -> Optional[dict]:
    record_path = output_dir / RECORD_FILENAME
    if not record_path.is_file():
        return None
    return json.loads(record_path.read_text(encoding="utf-8"))


def _write_record(output_dir: Path, record: dict) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / RECORD_FILENAME).write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")


def build_dataset_payload(
    *, publishing_organization_key: str, installation_key: str, title: str, description: str,
    license_url: str, registry_language: str, homepage: Optional[str] = None,
) -> dict:
    payload = {
        "publishingOrganizationKey": publishing_organization_key,
        "installationKey": installation_key,
        "type": "OCCURRENCE",
        "title": title,
        "description": description,
        "language": registry_language,
        "license": license_url,
    }
    # Omitted entirely rather than sent as "" — homepage is a URI-typed
    # field on GBIF's side, and an empty string is not a valid URI.
    if homepage:
        payload["homepage"] = homepage
    return payload


def register_gbif_dataset(
    archive_url: str,
    output_dir: Path,
    *,
    environment: str,
    publishing_organization_key: Optional[str],
    installation_key: Optional[str],
    username: Optional[str],
    password: Optional[str],
    title: str,
    description: str,
    license_url: str,
    registry_language: str,
    homepage: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """Registra (primera vez) o actualiza (siguientes) el dataset en el
    Registry de GBIF, y reemplaza su endpoint CAMTRAP_DP por `archive_url` —
    nunca sube ningún fichero, solo le dice a GBIF dónde rastrearlo.

    El dataset_key ya registrado (si lo hay) se lee de
    `output_dir`/gbif_linked_dataset_record.json, escrito por una ejecución
    anterior de esta misma función — así una segunda llamada actualiza el
    dataset existente en vez de crear uno duplicado.

    Returns:
        El registro local {"dataset_key", "environment", "archive_url",
        "dataset_page_url", "doi" (None salvo que la organización tenga su
        propio acuerdo con DataCite — ver el fetch más abajo),
        "registered_at_utc"} — ya guardado en
        `output_dir`/gbif_linked_dataset_record.json.

    Raises:
        RuntimeError: si `archive_url` no es http(s), `environment` no es
        'sandbox'/'production', faltan las claves de organización/
        instalación o las credenciales, o falla cualquier llamada a la
        Registry API.
    """
    if not (archive_url.startswith("http://") or archive_url.startswith("https://")):
        raise RuntimeError(f"--archive-url must be a public http(s) URL, got: {archive_url}")
    if environment not in GBIF_REGISTRY_BASE_URLS:
        raise RuntimeError(f"GBIF.environment must be 'sandbox' or 'production', got: {environment!r}")
    if not publishing_organization_key or not installation_key:
        raise RuntimeError(
            "GBIF.publishing_organization_key and GBIF.installation_key must both be set — "
            "they can't be guessed. Register an organization/installation on gbif.org (or its "
            "sandbox at gbif-test.org) and set them with 'wildintel-publisher gbif config set "
            "publishing_organization_key=...' / 'installation_key=...'."
        )
    if not username or not password:
        raise RuntimeError(
            "No GBIF Registry API credentials found. Set the GBIF_USERNAME/GBIF_PASSWORD "
            "environment variables, or store them with 'wildintel-publisher gbif config set "
            "username' / 'set password'."
        )

    base_url = GBIF_REGISTRY_BASE_URLS[environment]
    auth = (username, password)

    existing_record = _read_record(output_dir) or {}
    dataset_key = existing_record.get("dataset_key")

    dataset_payload = build_dataset_payload(
        publishing_organization_key=publishing_organization_key,
        installation_key=installation_key,
        title=title,
        description=description,
        license_url=license_url,
        registry_language=registry_language,
        homepage=homepage,
    )

    if dry_run:
        console.print(
            f"[yellow]Dry run.[/yellow] Would {'update' if dataset_key else 'create'} the GBIF "
            f"dataset at {base_url} with: {dataset_payload}"
        )
        console.print(f"[yellow]Dry run.[/yellow] Would then point its {GBIF_ENDPOINT_TYPE} endpoint at: {archive_url}")
        return {
            "dataset_key": dataset_key,
            "environment": environment,
            "archive_url": archive_url,
            "dataset_page_url": None,
            "doi": None,
            "registered_at_utc": None,
        }

    if dataset_key:
        console.print(f"Updating existing GBIF dataset: {dataset_key}")
        response = httpx.put(
            f"{base_url}/v1/dataset/{dataset_key}", json={**dataset_payload, "key": dataset_key}, auth=auth, timeout=60,
        )
        _check_response(response, (200, 204), "Update GBIF dataset")
    else:
        console.print(f"Registering new GBIF dataset ({environment})...")
        response = httpx.post(f"{base_url}/v1/dataset", json=dataset_payload, auth=auth, timeout=60)
        _check_response(response, (200, 201), "Register GBIF dataset")
        dataset_key = response.json()
        console.print(f"Created GBIF dataset: {dataset_key}")

    # Elimina cualquier endpoint de nuestro tipo que quedara de una ejecución
    # anterior antes de añadir el actual, para que volver a registrar nunca
    # deje endpoints duplicados apuntando a URLs viejas/renombradas.
    endpoints_response = httpx.get(f"{base_url}/v1/dataset/{dataset_key}/endpoint", auth=auth, timeout=60)
    _check_response(endpoints_response, (200,), "Fetch GBIF dataset endpoints")
    for endpoint in endpoints_response.json():
        if endpoint.get("type") == GBIF_ENDPOINT_TYPE:
            delete_response = httpx.delete(
                f"{base_url}/v1/dataset/{dataset_key}/endpoint/{endpoint['key']}", auth=auth, timeout=60,
            )
            _check_response(delete_response, (200, 204), "Delete stale GBIF dataset endpoint")

    console.print(f"Adding {GBIF_ENDPOINT_TYPE} endpoint: {archive_url}")
    endpoint_response = httpx.post(
        f"{base_url}/v1/dataset/{dataset_key}/endpoint",
        json={"type": GBIF_ENDPOINT_TYPE, "url": archive_url},
        auth=auth, timeout=60,
    )
    _check_response(endpoint_response, (200, 201), "Add GBIF dataset endpoint")

    # Some organizations have their own DataCite arrangement configured
    # with GBIF, which makes it auto-mint a DOI for every dataset registered
    # under them — entirely GBIF/organization-side, never something this
    # tool requests. Fetched here (a plain GET, the POST/PUT responses above
    # don't reliably include it) so sync_doi_to_hfh can reflect it into
    # HFH's own CITATION.cff later, same as Zenodo/B2SHARE's own DOI/PID.
    dataset_response = httpx.get(f"{base_url}/v1/dataset/{dataset_key}", auth=auth, timeout=60)
    _check_response(dataset_response, (200,), "Fetch GBIF dataset")
    doi = dataset_response.json().get("doi") or None

    dataset_page_url = GBIF_DATASET_PAGE_URL_TEMPLATES[environment].format(key=dataset_key)
    record = {
        "dataset_key": dataset_key,
        "environment": environment,
        "archive_url": archive_url,
        "dataset_page_url": dataset_page_url,
        "doi": doi,
        "registered_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    _write_record(output_dir, record)

    console.print(f"[green]✔  GBIF dataset registered: {dataset_page_url}[/green]")
    console.print("   GBIF crawls new/updated endpoints within a few hours — check back at the link above.")
    return record


def validate_camtrap_dp_archive(url: str, *, timeout: int = 60) -> None:
    """Downloads `url` (expected to be a zip archive containing a whole
    Camtrap DP package — what GBIF's own CAMTRAP_DP crawler actually
    expects as --archive-url, NOT a bare datapackage.json, see this
    module's own docstring and docs/publishing-gbif.md) and validates it
    the same way common.validate_camtrap_dp already does before any repo
    publishes — catches upfront the exact failure mode GBIF's crawler hits
    silently otherwise (a crawl that finishes with finishReason=ABORT and
    nothing ever indexed, with no error visible anywhere in this project).

    Calls common.validate_camtrap_dp with patch_missing_profile=False —
    `url` is hosted externally, in a throwaway extraction this function
    discards once done, so silently patching a missing "profile" here (the
    default elsewhere) would only fix a copy nobody ever sees, while
    reporting a false "valid" for the real, unpatched file GBIF will
    actually crawl.

    Raises:
        RuntimeError: if `url` isn't http(s), can't be downloaded, isn't a
        real zip archive, or the extracted content doesn't pass Camtrap DP
        validation (frictionless, including a missing "profile") — the
        message identifies which.
    """
    if not (url.startswith("http://") or url.startswith("https://")):
        raise RuntimeError(f"Archive URL must be a public http(s) URL, got: {url}")

    with tempfile.TemporaryDirectory(prefix="gbif-archive-validate-") as tmp:
        tmp_dir = Path(tmp)
        zip_path = tmp_dir / "archive.zip"
        try:
            with httpx.stream("GET", url, follow_redirects=True, timeout=timeout) as response:
                if response.status_code != 200:
                    raise RuntimeError(f"Could not download {url}: HTTP {response.status_code}.")
                with zip_path.open("wb") as f:
                    for chunk in response.iter_bytes():
                        f.write(chunk)
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Could not download {url}: {exc}") from exc

        if not zipfile.is_zipfile(zip_path):
            raise RuntimeError(
                f"{url} is not a valid zip archive. GBIF's CAMTRAP_DP crawler downloads this URL "
                "and tries to decompress it, so it must be a zip containing the whole Camtrap DP "
                "package (e.g. camtrapdp-remote.zip) — not a bare datapackage.json, which downloads "
                "fine but then fails to decompress, silently, with nothing ever crawled."
            )

        extract_dir = tmp_dir / "extracted"
        extract_dir.mkdir()
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)

        common.validate_camtrap_dp(common.find_camtrap_dp_root(extract_dir), patch_missing_profile=False)


def sync_doi_to_hfh(*, gbif_output_dir: Path, hfh_output_dir: Path) -> str:
    """Lee el DOI que GBIF asignó al dataset (si lo hay — solo lo tienen
    organizaciones con su propio acuerdo de DataCite configurado con GBIF,
    ver register_gbif_dataset) desde `gbif_output_dir`/
    gbif_linked_dataset_record.json, y lo refleja en el CITATION.cff (y la
    sección "## Citation" de su README.md — ver
    common.patch_readme_citation_url) de `hfh_output_dir` (el export ya
    preparado para HuggingFace Hub) — regenerando también sus checksums. El
    paso recomendado después es volver a subir con 'hfh upload'.

    A diferencia de Zenodo (que en sandbox emite un DOI de pega para
    pruebas), el DOI de GBIF, cuando existe, viene de la cuenta DataCite
    real de la organización — se trata siempre como definitivo, sin la
    distinción sandbox/producción que sí hace falta en zenodo.py.

    Returns:
        El DOI sincronizado.

    Raises:
        RuntimeError: si el dataset de GBIF no tiene DOI asignado (lo
        normal — no es un fallo, solo no hay nada que sincronizar), o si
        `hfh_output_dir`/CITATION.cff no existe.
    """
    record = _read_record(gbif_output_dir) or {}
    doi = record.get("doi")
    if not doi:
        raise RuntimeError(
            f"The GBIF dataset in {gbif_output_dir} has no DOI — most organizations don't get one "
            "automatically (only those with their own DataCite arrangement configured with GBIF). "
            "There's nothing to sync."
        )

    hfh_citation_path = hfh_output_dir / CITATION_FILENAME
    if not hfh_citation_path.is_file():
        raise RuntimeError(f"{hfh_citation_path} not found — run 'hfh prepare' first.")

    common.patch_citation_with_identifier(
        hfh_citation_path, value=doi, kind="doi", url=record.get("dataset_page_url"), description="GBIF DOI",
    )
    if record.get("dataset_page_url"):
        common.patch_readme_citation_url(hfh_output_dir / README_FILENAME, record["dataset_page_url"])
    common.write_checksums(hfh_output_dir)

    console.print(f"[green]✔  DOI {doi} reflected in {hfh_citation_path}.[/green]")
    console.print("   Re-upload with [bold]hfh upload[/bold] to publish the change.")
    return doi
