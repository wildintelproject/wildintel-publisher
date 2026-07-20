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
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from rich.console import Console

console = Console()

GBIF_ENDPOINT_TYPE = "CAMTRAP_DP"

GBIF_REGISTRY_BASE_URLS = {
    "sandbox": "https://api.gbif-test.org",
    "production": "https://api.gbif.org",
}
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
    license_url: str, registry_language: str,
) -> dict:
    return {
        "publishingOrganizationKey": publishing_organization_key,
        "installationKey": installation_key,
        "type": "OCCURRENCE",
        "title": title,
        "description": description,
        "language": registry_language,
        "license": license_url,
    }


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
        "dataset_page_url", "registered_at_utc"} — ya guardado en
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

    dataset_page_url = GBIF_DATASET_PAGE_URL_TEMPLATES[environment].format(key=dataset_key)
    record = {
        "dataset_key": dataset_key,
        "environment": environment,
        "archive_url": archive_url,
        "dataset_page_url": dataset_page_url,
        "registered_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    _write_record(output_dir, record)

    console.print(f"[green]✔  GBIF dataset registered: {dataset_page_url}[/green]")
    console.print("   GBIF crawls new/updated endpoints within a few hours — check back at the link above.")
    return record
