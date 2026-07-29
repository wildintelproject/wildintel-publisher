"""Conexión a Trapper y descarga del paquete Camtrap DP de un proyecto de clasificación.

Usa `wildintel-trapper-sdk` (repo hermano, ver [tool.uv.sources] en pyproject.toml):
``/media_classification/api/package/{project_pk}/`` genera (o reutiliza un
paquete ya cacheado) y devuelve una URL de descarga absoluta en
``data.package`` — esa URL ya lleva su propio token de un solo uso
(``?rt=...``), así que se descarga tal cual con ``client.make_request()``,
sin pasar por la cabecera Authorization del cliente.
"""
import gzip
import json
from pathlib import Path
from typing import Optional
from zipfile import ZipFile

import httpx
from rich.console import Console
from trapper_client import TrapperClient, err
from trapper_client.schemas import ClassificationProject

console = Console()

CAMTRAPDP_ZIP_FILENAME = "camtrapdp.zip"
DATAPACKAGE_FILENAME = "datapackage.json"
PRIVATE_LICENSE_PLACEHOLDER = "private"
LICENSE_SCOPES = ("data", "media")

# TrapperClient por defecto usa timeout=30s (pensado para llamadas normales de
# la API) — generar un paquete Camtrap DP nuevo (sin caché) puede tardar bastante
# más en proyectos grandes, así que aquí el default es mucho más generoso.
# Configurable con --timeout si aun así no basta.
DEFAULT_TIMEOUT = 300


def fetch_camtrapdp_package(
    *,
    trapper_url: str,
    trapper_user: str,
    trapper_password: str,
    project_id: int,
    deployment_id: str,
    output_dir: Path,
    clear_cache: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
    title: Optional[str] = None,
    description: Optional[str] = None,
    version: Optional[str] = None,
    license_id: Optional[str] = None,
    license_name: Optional[str] = None,
    license_url: Optional[str] = None,
    include_events: bool = True,
) -> Path:
    """Genera (o reutiliza) el paquete Camtrap DP del proyecto de clasificación
    `project_id` en el servidor Trapper `trapper_url`, lo descarga y lo
    extrae en `output_dir`.

    Args:
        deployment_id: Limita el paquete a este despliegue. A pesar de lo que
            documenta trapper-client ("Comma-separated deployment PKs"), el
            servidor filtra con un simple `icontains` sobre el campo de texto
            `deployment_id` (ej. "r0007-dona_0018"), no un PK numérico — así
            que aquí solo se admite un único string, no una lista.
        timeout: Timeout de red (segundos) para generar y descargar el
            paquete. La generación (sobre todo con clear_cache=True o
            proyectos grandes) puede tardar bastante en el propio servidor.
        title, description, version: Metadatos que Trapper escribe dentro de
            datapackage.json (mismos parámetros que ResultsDataPackageGenerator.
            get_package_metadata() en el servidor). Deliberadamente NO se pasa
            aquí 'licenses'/'keywords' (también soportados por la API): el
            parseo de parámetros tipo lista de Trapper (AbstractParams.
            from_query_params, que hace `f.type(val)` sobre un valor de query
            string plano) no está verificado como fiable para listas — mejor
            no arriesgarse a que la petición falle en el servidor.
        license_id, license_name, license_url: Si se indican, se usan para
            parchear en sitio los scopes ("data"/"media") de
            datapackage.json["licenses"] que Trapper haya dejado como
            "private" (o vacíos) — ver _fix_datapackage_license. Arregla el
            paquete en la fuente, en vez de dejar que cada consumidor
            (ej. 'hfh prepare') tenga que hacer su propio fallback.
        include_events: Si el paquete generado incluye observations.csv a
            nivel de evento (agregado), además de las de nivel media —
            parámetro `include_events` de la API. A diferencia de esta,
            aquí el valor por defecto es True (la API por su cuenta usa
            False), así que siempre se envía explícito, nunca se omite.

    Returns:
        `output_dir`, con el paquete ya extraído dentro (datapackage.json,
        deployments.csv, media.csv, events.csv...) y el .zip original
        (`camtrapdp.zip`) conservado junto a él.

    Raises:
        RuntimeError: si Trapper no pudo generar el paquete, si se agota el
        tiempo de espera, o si el servidor es inalcanzable.
    """
    client = TrapperClient(
        base_url=trapper_url, user_name=trapper_user, user_password=trapper_password, timeout=timeout,
    )

    console.print(
        "  Using Trapper's own defaults for: approved_only=True, exclude_blank=False, "
        "trapper_url_token=True, release=False, private_human=True, private_vehicle=True "
        "(not yet configurable from wildintel-publisher)."
    )

    package_kwargs = {"include_events": include_events}
    if title:
        package_kwargs["title"] = title
    if description:
        package_kwargs["description"] = description
    if version:
        package_kwargs["version"] = version

    console.print(f"Generating (or reusing) the Camtrap DP package for project {project_id}...")
    try:
        response = client.classification_package.get_project_package(
            project_pk=project_id, clear_cache=clear_cache,
            all_deployments=False, filter_deployments=deployment_id,
            **package_kwargs,
        )
    except httpx.TimeoutException as exc:
        raise RuntimeError(
            f"Timed out ({timeout}s) generating the Camtrap DP package for project "
            f"{project_id}. If the project is large, try a higher --timeout."
        ) from exc
    except httpx.ConnectError as exc:
        raise RuntimeError(f"Could not connect to {trapper_url}: {exc}") from exc

    if response.data is None or not response.data.package:
        message = response.data.message if response.data else "No response from the server."
        errors = response.data.errors if response.data else None
        raise RuntimeError(f"Could not generate the Camtrap DP package: {message}" + (f"\n{errors}" if errors else ""))

    console.print(response.data.message)
    console.print(f"Downloading from {response.data.package} ...")
    try:
        file_response = client.make_request(endpoint=response.data.package, method="GET")
    except httpx.TimeoutException as exc:
        raise RuntimeError(
            f"Timed out ({timeout}s) downloading the Camtrap DP package. "
            "Try a higher --timeout."
        ) from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / CAMTRAPDP_ZIP_FILENAME
    zip_path.write_bytes(file_response.content)

    console.print(f"Extracting to {output_dir} ...")
    with ZipFile(zip_path) as zf:
        zf.extractall(output_dir)

    _decompress_gzipped_tables(output_dir)
    if license_id:
        _fix_datapackage_license(output_dir, license_id=license_id, license_name=license_name, license_url=license_url)

    console.print(f"[green]✔  Camtrap DP for project {project_id} ready in {output_dir}[/green]")
    return output_dir


def _fix_datapackage_license(
    output_dir: Path, *, license_id: str, license_name: Optional[str], license_url: Optional[str],
) -> None:
    """Parchea datapackage.json in situ: para cada scope ("data"/"media")
    sin una licencia real (ausente, o el placeholder "private" que Trapper
    añade en get_package_metadata() cuando no le llega ninguna — ver
    apps/media_classification/tasks/data_packages.py:290-294 del servidor),
    añade la licencia indicada. Los scopes que ya tengan una licencia real
    no se tocan."""
    datapackage_path = output_dir / DATAPACKAGE_FILENAME
    if not datapackage_path.is_file():
        return

    try:
        data = json.loads(datapackage_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return

    licenses = data.get("licenses")
    if not isinstance(licenses, list):
        licenses = []

    real_scopes = {
        licence.get("scope") for licence in licenses
        if isinstance(licence, dict) and licence.get("name") and licence.get("name") != PRIVATE_LICENSE_PLACEHOLDER
    }
    missing_scopes = [scope for scope in LICENSE_SCOPES if scope not in real_scopes]
    if not missing_scopes:
        return

    licenses = [
        licence for licence in licenses
        if not (isinstance(licence, dict) and licence.get("name") == PRIVATE_LICENSE_PLACEHOLDER and licence.get("scope") in missing_scopes)
    ]
    for scope in missing_scopes:
        licenses.append({"name": license_id, "path": license_url, "title": license_name, "scope": scope})

    data["licenses"] = licenses
    datapackage_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    console.print(f"  datapackage.json: license '{license_id}' added for scope(s) {', '.join(missing_scopes)}.")


def _decompress_gzipped_tables(output_dir: Path) -> None:
    """Descomprime en sitio las tablas del paquete que vienen comprimidas
    (export_filetype='csv.gz' por defecto en Trapper, ej. media.csv.gz,
    deployments.csv.gz, observations.csv.gz), elimina el .gz para quedarse
    solo con el .csv en claro, y limpia la marca de compresión en
    datapackage.json (ver _clear_datapackage_resource_compression) — si no,
    cualquier lector/validador del paquete (incluido frictionless) seguiría
    intentando hacer gunzip sobre un CSV que ya está en claro."""
    decompressed_names = set()
    for gz_path in output_dir.rglob("*.gz"):
        csv_path = gz_path.with_suffix("")
        with gzip.open(gz_path, "rb") as f_in, open(csv_path, "wb") as f_out:
            f_out.write(f_in.read())
        gz_path.unlink()
        console.print(f"  Decompressed {gz_path.name} -> {csv_path.name}")
        decompressed_names.add(csv_path.relative_to(output_dir).as_posix())

    if decompressed_names:
        _clear_datapackage_resource_compression(output_dir, decompressed_names)


def _clear_datapackage_resource_compression(output_dir: Path, decompressed_names: set) -> None:
    """Quita "compression" de los resources de datapackage.json cuyo fichero
    ya se descomprimió.

    Trapper declara "path" con el nombre YA descomprimido (ej.
    "deployments.csv") aunque el fichero físico dentro del zip fuera
    "deployments.csv.gz" — es el "compression": "gz" el que le dice a quien
    lea el paquete que descomprima, no el nombre en "path". Por si esa
    convención cambiase, también se cubre el caso de que "path" siguiera
    terminando en ".gz"."""
    datapackage_path = output_dir / DATAPACKAGE_FILENAME
    if not datapackage_path.is_file():
        return

    try:
        data = json.loads(datapackage_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return

    resources = data.get("resources")
    if not isinstance(resources, list):
        return

    changed = False
    for resource in resources:
        if not isinstance(resource, dict):
            continue
        path = resource.get("path")
        if path in decompressed_names:
            if resource.pop("compression", None) is not None:
                changed = True
        elif isinstance(path, str) and path.endswith(".gz") and path[:-3] in decompressed_names:
            resource["path"] = path[:-3]
            resource.pop("compression", None)
            changed = True

    if changed:
        datapackage_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        console.print("  datapackage.json: removed the compression marker from the already-decompressed resources.")


def test_connection(
    *,
    trapper_url: str,
    trapper_user: str,
    trapper_password: str,
    project_id: int,
) -> ClassificationProject:
    """Comprueba que se puede conectar al servidor Trapper `trapper_url` con
    estas credenciales, y que el usuario tiene acceso al proyecto de
    clasificación `project_id`.

    Returns:
        El proyecto de clasificación, si la conexión y el acceso son correctos.

    Raises:
        RuntimeError: con un mensaje explicando qué ha fallado (servidor
        inalcanzable, credenciales inválidas, o sin acceso al proyecto).
    """
    client = TrapperClient(base_url=trapper_url, user_name=trapper_user, user_password=trapper_password)

    try:
        return client.classification_projects.find(pk=project_id)
    except httpx.ConnectError as exc:
        raise RuntimeError(f"Could not connect to {trapper_url}: {exc}") from exc
    except httpx.TimeoutException as exc:
        raise RuntimeError(f"Timed out connecting to {trapper_url}: {exc}") from exc
    except err.UnauthorizedError as exc:
        raise RuntimeError("Incorrect Trapper username or password.") from exc
    except err.ForbiddenError as exc:
        raise RuntimeError(f"The user does not have permission to access classification project {project_id}.") from exc
    except err.NotFoundError as exc:
        raise RuntimeError(f"Classification project {project_id} does not exist on {trapper_url}.") from exc
    except err.APIError as exc:
        raise RuntimeError(f"Trapper API error: {exc}") from exc
