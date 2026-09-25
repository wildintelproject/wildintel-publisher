"""Utilidades compartidas por los distintos servicios de publicación
(wildintel_publisher.services.hfh, .zenodo y .b2share) — hashing,
renderizado de plantillas, y todo lo relacionado con leer/validar/filtrar el
propio camtrapdp (datapackage.json + CSVs) o descargar sus imágenes, que no
depende de a qué repositorio se vaya a publicar después.
"""
import csv
import gzip
import hashlib
import io
import json
import re
import shutil
import uuid
from pathlib import Path
from typing import Any, Optional
from zipfile import ZipFile

import httpx
import yaml
from frictionless import validate as frictionless_validate
from jinja2 import Environment, FileSystemLoader
from PIL import Image
from rich.console import Console
from rich.progress import track

from wildintel_publisher.config import REPO_ROOT
from wildintel_publisher.services import product

console = Console()

TEMPLATES_ROOT = REPO_ROOT / "templates"

DATAPACKAGE_FILENAME = "datapackage.json"
DEPLOYMENTS_CSV_FILENAME = "deployments.csv"
MEDIA_CSV_FILENAME = "media.csv"
OBSERVATIONS_CSV_FILENAME = "observations.csv"
FILE_PUBLIC_COLUMN = "filePublic"
MEDIA_ID_COLUMN = "mediaID"
FILE_PATH_COLUMN = "filePath"
FILE_NAME_COLUMN = "fileName"
LATITUDE_COLUMN = "latitude"
LONGITUDE_COLUMN = "longitude"
TRUTHY_VALUES = {"true", "1", "yes"}

# Placeholder Trapper's own get_package_metadata() writes into a license
# scope ("data"/"media") when the classification project has no real license
# configured for it — see resolve_license/fix_datapackage_license.
PRIVATE_LICENSE_PLACEHOLDER = "private"
LICENSE_SCOPES = ("data", "media")

# ~1.1 km at the equator — coarse enough to obscure the exact deployment
# point, still regionally useful. See anonymize_deployment_coordinates.
DEFAULT_COORDINATE_DECIMALS = 2

IMAGES_DIRNAME = "images"
LOCAL_ZIP_FILENAME = "camtrapdp-local.zip"
REMOTE_ZIP_FILENAME = "camtrapdp-remote.zip"
DEFAULT_IMAGE_TIMEOUT = 60

# Hugging Face Hub rejects a git push with more than 10,000 files in any one
# directory (its own repo-level limit, not ours) — sharding images/ into 256
# subfolders (2 hex chars) keeps up to ~2.56M images under that cap without
# ever needing to grow the scheme. The bucket is a pure hash of the file
# name, so it's computable from media.csv alone (no directory listing
# needed) and stable across runs — see _image_bucket.
IMAGE_SHARD_HEX_CHARS = 2


def _image_bucket(file_name: str) -> str:
    """Deterministic 2-hex-char shard for `file_name`, used to spread
    images/ across subfolders — see IMAGE_SHARD_HEX_CHARS."""
    return hashlib.sha1(file_name.encode("utf-8")).hexdigest()[:IMAGE_SHARD_HEX_CHARS]

# Los 4 ficheros que de verdad componen un camtrapdp (datapackage.json + sus
# 3 tablas) — usado por servicios que copian de un input_dir que puede traer
# de más (ej. si input_dir fuera la salida ya procesada de 'hfh prepare',
# que además tiene images/, camtrapdp-local.zip, su propio README/CITATION...;
# o el input_dir por defecto de 'trapper download', que además guarda el
# camtrapdp.zip original de Trapper, ya obsoleto tras filtrar media privada)
# — evita arrastrar ficheros ajenos o desactualizados al copiar.
CORE_CAMTRAPDP_FILES = [DATAPACKAGE_FILENAME, DEPLOYMENTS_CSV_FILENAME, MEDIA_CSV_FILENAME, OBSERVATIONS_CSV_FILENAME]

# Versión anclada del esquema oficial de Camtrap DP contra la que valida
# frictionless — 1.0.1+ es la primera compatible con frictionless-py 5.17+
# (antes tenía un $ref roto que impedía validar). Ver
# https://github.com/tdwg/camtrap-dp/releases
CAMTRAP_DP_PROFILE_VERSION = "1.0.2"
CAMTRAP_DP_PROFILE_URL = f"https://raw.githubusercontent.com/tdwg/camtrap-dp/{CAMTRAP_DP_PROFILE_VERSION}/camtrap-dp-profile.json"

CHECKSUM_FILENAME = "checksums-sha256.txt"


def ensure_output_dir(output_dir: Path, *, overwrite: bool) -> None:
    """Crea `output_dir` si no existe. Si ya existe y ya tiene contenido, se
    niega a continuar salvo que `overwrite=True` — evita pisar en silencio un
    export/registro ya preparado (o, peor, un directorio que no era el que
    se pretendía usar) de una ejecución anterior.

    Raises:
        RuntimeError: si `output_dir` ya existe y tiene contenido, y
        `overwrite` es False.
    """
    if output_dir.exists() and any(output_dir.iterdir()) and not overwrite:
        raise RuntimeError(
            f"{output_dir} already exists and is not empty — pass --overwrite to reuse it "
            "anyway (existing files will be overwritten), or choose a different --output-dir."
        )
    output_dir.mkdir(parents=True, exist_ok=True)


def copy_core_camtrapdp_files(source_dir: Path, target_dir: Path) -> None:
    """Copia a `target_dir` los CORE_CAMTRAPDP_FILES presentes en
    `source_dir` (datapackage.json + sus 3 tablas) — nada más, en particular
    ninguna imagen/vídeo. Ficheros ausentes en `source_dir` se saltan en
    silencio (mismo criterio que el resto del pipeline: no todo camtrapdp
    trae las 3 tablas).

    Para cada tabla, si no existe la versión sin comprimir pero sí un
    `<fichero>.gz` (p. ej. un export de Trapper descargado y descomprimido a
    mano, cuyas tablas siguen viniendo comprimidas), se copia ese `.gz` tal
    cual — decompress_gzipped_tables (pensada para ejecutarse justo después,
    sobre `target_dir`) es quien luego lo descomprime y limpia la marca de
    compresión en datapackage.json."""
    target_dir.mkdir(parents=True, exist_ok=True)
    for filename in CORE_CAMTRAPDP_FILES:
        source = source_dir / filename
        if source.is_file():
            shutil.copy2(source, target_dir / filename)
            continue
        if filename == DATAPACKAGE_FILENAME:
            continue  # never itself gzip-compressed
        gz_source = source_dir / f"{filename}.gz"
        if gz_source.is_file():
            shutil.copy2(gz_source, target_dir / gz_source.name)


def decompress_gzipped_tables(output_dir: Path) -> None:
    """Descomprime en sitio las tablas del paquete que vienen comprimidas
    (export_filetype='csv.gz' por defecto en Trapper, ej. media.csv.gz,
    deployments.csv.gz, observations.csv.gz), elimina el .gz para quedarse
    solo con el .csv en claro, y limpia la marca de compresión en
    datapackage.json (ver _clear_datapackage_resource_compression) — si no,
    cualquier lector/validador del paquete (incluido frictionless) seguiría
    intentando hacer gunzip sobre un CSV que ya está en claro.

    Usada tanto por 'trapper download' (justo tras extraer el zip) como por
    resolve_local_camtrapdp_source (Local Directory, tras copy_core_camtrapdp_files)
    — un export de Trapper descargado y descomprimido a mano conserva sus
    tablas comprimidas, y sin este paso la validación de Camtrap DP fallaba
    con "No such file or directory: .../deployments.csv.gz" (el fichero
    referenciado en datapackage.json nunca llegó a copiarse/descomprimirse)."""
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
    convención cambiase (algunos exports declaran "path" ya terminado en
    ".gz"), también se cubre ese caso."""
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


_jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_ROOT)),
    trim_blocks=True, lstrip_blocks=True,
)


def render_text_template(template_path: Path, **context: Any) -> str:
    """Renderiza una plantilla .j2 de texto/markdown (README.md.j2,
    LICENSE.j2...), recortando el whitespace que dejarían los tags
    {% for %}/{% if %}. `template_path` debe vivir bajo templates/ — el
    entorno Jinja usa un FileSystemLoader anclado ahí (en vez de
    Environment().from_string(...)) precisamente para que las plantillas
    puedan usar {% include "otro/fichero.j2" %} con rutas relativas a
    templates/ (p. ej. README-camtrapdp-body.md.j2 incluyendo el
    format_template/location_template propio de cada repo — ver
    services.hfh/zenodo/b2share's write_readme)."""
    relative_name = template_path.relative_to(TEMPLATES_ROOT).as_posix()
    template = _jinja_env.get_template(relative_name)
    return template.render(**context)


def sha256_file(path: Path, chunk_size_bytes: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size_bytes), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> tuple[list[str], list[dict]]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_checksums(output_dir: Path) -> Path:
    """Escribe checksums-sha256.txt con el SHA-256 de todos los ficheros del
    export, excluyéndose a sí mismo y a metadata.json — bookkeeping interno
    del pipeline (product_type, publish_history...), nunca subido a ningún
    repositorio (ver upload_to_huggingface/upload_to_zenodo/upload_to_b2share),
    así que tampoco tiene sentido listarlo como si formara parte del
    export publicado."""
    path = output_dir / CHECKSUM_FILENAME
    with path.open("w", encoding="utf-8") as f:
        for file_path in sorted(output_dir.rglob("*")):
            if not file_path.is_file() or file_path == path or file_path.name == product.METADATA_FILENAME:
                continue
            rel = file_path.relative_to(output_dir).as_posix()
            f.write(f"{sha256_file(file_path)}  {rel}\n")
    return path


def update_checksums_entries(checksums_path: Path, updated_files: dict[str, Path]) -> bool:
    """Rewrites just the entries in an ALREADY-PUBLISHED checksums-sha256.txt
    for `updated_files` ({relative_path_as_it_appears_in_the_file: real
    local file to hash now}), leaving every other line untouched —
    services.doi_populate's own populate() uses this instead of
    write_checksums (which needs every file of the export physically
    present locally to re-hash them all) once a repo's own build_dir may
    already be gone by the time a cross-referenced DOI patches its
    CITATION.cff/README.md — see publish_orchestrator's own docstring on
    why only those two (plus this file itself) still need to exist locally
    at that point.

    Unlike write_checksums, this never adds an entry for a file that
    wasn't already listed — every possible caller here is patching a file
    the original export always already had (CITATION.cff, README.md),
    never introducing a new one.

    Returns:
        True if the file actually changed (any of `updated_files`' hashes
        differ from what was already there).
    """
    original_text = checksums_path.read_text(encoding="utf-8")
    new_hashes = {rel: sha256_file(path) for rel, path in updated_files.items()}
    new_lines = []
    for line in original_text.splitlines():
        digest, sep, rel = line.partition("  ")
        if sep and rel in new_hashes:
            new_lines.append(f"{new_hashes[rel]}  {rel}")
        else:
            new_lines.append(line)
    new_text = "\n".join(new_lines) + "\n"
    if new_text == original_text:
        return False
    checksums_path.write_text(new_text, encoding="utf-8")
    return True


def validate_camtrap_dp(output_dir: Path, *, patch_missing_profile: bool = True) -> None:
    """Valida datapackage.json (y los CSV que referencia) contra el esquema
    oficial de Camtrap DP con frictionless — no solo la estructura genérica
    de Data Package, sino los requisitos propios del estándar (campos
    obligatorios, columnas de cada tabla, número de licencias, claves entre
    tablas...).

    Si datapackage.json no declara "profile" (necesario para que frictionless
    sepa que debe aplicar el esquema de Camtrap DP, no solo el genérico de
    Data Package):

    - patch_missing_profile=True (default) — se añade aquí mismo, en
      `output_dir`, y queda así permanentemente en el fichero, que es lo que
      el propio estándar recomienda para que cualquier herramienta lo
      autodetecte. Correcto siempre que `output_dir` sea una copia local que
      este proyecto controla y desde la que luego se construye lo que se
      publica (Trapper, Local Directory, o la copia ya persistida al usar
      Public URL como fuente) — el parche llega a lo que de verdad se sube.
    - patch_missing_profile=False — se lanza un error en su lugar, sin
      tocar nada. Pensado para cuando `output_dir` es la extracción
      *desechable* de un zip alojado en una URL externa que este proyecto no
      controla (ver gbif.validate_camtrap_dp_archive): parchear ahí solo
      arreglaría una copia temporal que se descarta al momento, dando una
      falsa validación — el zip real, tal y como lo rastreará GBIF, seguiría
      sin "profile".

    Raises:
        RuntimeError: si datapackage.json no es JSON válido, si le falta
        "profile" y patch_missing_profile=False, o si la validación de
        Camtrap DP falla (con el detalle de cada error).
    """
    datapackage_path = output_dir / DATAPACKAGE_FILENAME
    if not datapackage_path.is_file():
        raise RuntimeError(f"{datapackage_path} not found — cannot validate the camtrapdp.")

    try:
        data = json.loads(datapackage_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(f"{datapackage_path} is not valid JSON: {exc}") from exc

    if not data.get("profile"):
        if not patch_missing_profile:
            raise RuntimeError(
                f"{datapackage_path} does not declare a \"profile\" — required for GBIF's own "
                f"CAMTRAP_DP crawler (and frictionless) to recognise this as a Camtrap DP package, "
                f"not just a generic Data Package. This archive is hosted externally, so it can't be "
                f'patched from here: add "profile": "{CAMTRAP_DP_PROFILE_URL}" to datapackage.json '
                "at the source and re-publish it there, or fetch/rebuild it through a source this "
                "project controls (Trapper, or a local directory) instead."
            )
        data["profile"] = CAMTRAP_DP_PROFILE_URL
        datapackage_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        console.print(f"  datapackage.json: added \"profile\": \"{CAMTRAP_DP_PROFILE_URL}\" (it didn't have one).")

    console.print("Validating the camtrapdp against the Camtrap DP schema (frictionless)...")
    report = frictionless_validate(str(datapackage_path))

    if report.valid:
        console.print("[green]✔  The camtrapdp is valid according to the Camtrap DP schema.[/green]")
        return

    console.print("[red]✘  The camtrapdp is not valid according to the Camtrap DP schema:[/red]")
    error_lines = []
    for _type, title, message in report.flatten(["type", "title", "message"]):
        line = f"{title}: {message}"
        console.print(f"  [red]•[/red] {line}")
        error_lines.append(line)

    # The errors above are also folded into the exception message itself —
    # not just printed to this console — since some callers (e.g. the web
    # backend's resolve_local_source/fetch_camtrap_dp_archive) only ever
    # surface str(exc) to their own caller (an HTTP response, eventually the
    # wizard's UI), which never sees this process's own stdout. Without this,
    # the web UI showed a generic "review the errors above" pointing at a
    # console the user has no access to, with the actual validation errors
    # visible only in the server's own logs.
    details = "\n".join(f"  - {line}" for line in error_lines) or "  (no details reported by frictionless)"
    raise RuntimeError(
        f"The camtrapdp in {output_dir} does not pass Camtrap DP validation (frictionless):\n{details}"
    )


def read_datapackage_metadata(output_dir: Path) -> dict:
    """Lee name/title/description/version/licenses/contributors/homepage de
    datapackage.json, si existe y es válido."""
    datapackage_path = output_dir / DATAPACKAGE_FILENAME
    if not datapackage_path.is_file():
        return {}
    try:
        data = json.loads(datapackage_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    result = {key: data[key] for key in ("name", "title", "description", "version") if data.get(key)}
    result["licenses"] = data.get("licenses") or []
    result["contributors"] = data.get("contributors") or []
    result["homepage"] = data.get("homepage")
    return result


def update_datapackage_fields(output_dir: Path, updates: dict) -> None:
    """Merges `updates` (only the keys actually present, e.g.
    name/title/description/homepage/version) into datapackage.json,
    preserving everything else already there — same read-mutate-rewrite
    pattern as write_homepage below and trapper._fix_datapackage_license.

    Edited here rather than in metadata.json (see product.update_metadata_json)
    because datapackage.json is the Camtrap DP's own source of truth for
    these fields — CamtrapDPAdapter.extract_metadata re-reads them from here
    every time generate_metadata_json runs, so calling this BEFORE that (see
    the web wizard's own metadata-editing step) is enough for metadata.json,
    and everything generated from it (README.md, CITATION.cff, Zenodo/
    B2SHARE/HFH records), to pick up the new values with no extra syncing."""
    datapackage_path = output_dir / DATAPACKAGE_FILENAME
    data = json.loads(datapackage_path.read_text(encoding="utf-8"))
    data.update({key: value for key, value in updates.items() if value is not None})
    datapackage_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write_homepage(output_dir: Path, url: str) -> None:
    """Sets/overwrites the top-level "homepage" property (standard Data
    Package/Camtrap DP field for "a URL for the home on the web that is
    related to this data package") in datapackage.json — used by
    'hfh upload' in mirror mode to record the HuggingFace Hub dataset the
    images actually got uploaded to, so a later publish step (Zenodo,
    B2SHARE) can detect it instead of asking the user to retype it. Not
    called in link mode: media stays wherever it already was (e.g. Trapper),
    so this HFH repo isn't really the media's home."""
    update_datapackage_fields(output_dir, {"homepage": url})


def resolve_license(licenses: list) -> dict:
    """Busca la primera licencia real en datapackage.json (ignorando los
    placeholders PRIVATE_LICENSE_PLACEHOLDER que Trapper añade cuando no hay
    una real para ese scope — ver get_package_metadata() en el servidor).
    Sin fallback: si no hay ninguna, es que nadie llegó a parchearla todavía
    (ver fix_datapackage_license, que sí lo hace, en cada una de las tres
    fuentes de un Camtrap DP — Trapper, Local Directory, Public URL) — hay
    que arreglar el camtrapdp, no sustituirla aquí.

    Returns:
        {"id": ..., "name": ..., "url": ...} — id es el código corto (ej.
        CC-BY-4.0), name el título completo, url el path/URL de la licencia.

    Raises:
        RuntimeError: si no hay ninguna licencia real.
    """
    for licence in licenses:
        if not isinstance(licence, dict):
            continue
        name = licence.get("name")
        if name and name != PRIVATE_LICENSE_PLACEHOLDER:
            return {"id": name, "name": licence.get("title") or name, "url": licence.get("path") or ""}

    raise RuntimeError(
        f'datapackage.json has no real license (everything is "{PRIVATE_LICENSE_PLACEHOLDER}" '
        "placeholders, or the list is empty) — fill in title/description/license/authors by hand "
        "below, or set one explicitly at the source and regenerate the package."
    )


def fix_datapackage_license(
    output_dir: Path, *, license_id: str, license_name: Optional[str] = None, license_url: Optional[str] = None,
) -> None:
    """Parchea datapackage.json in situ: para cada scope de LICENSE_SCOPES
    ("data"/"media") sin una licencia real (ausente, o el placeholder
    PRIVATE_LICENSE_PLACEHOLDER que Trapper añade en get_package_metadata()
    cuando no le llega ninguna — ver
    apps/media_classification/tasks/data_packages.py:290-294 del servidor),
    añade la licencia indicada. Los scopes que ya tengan una licencia real
    no se tocan.

    Llamada desde las tres fuentes de un Camtrap DP con estos mismos valores
    por defecto (settings.TRAPPER.license_id/license_name/license_url, ver
    config.py) — Trapper (trapper.fetch_camtrapdp_package, con
    --license-id/--license-name/--license-url configurables por si el
    usuario quiere otra cosa), Local Directory
    (camtrapdp_source.resolve_local_camtrapdp_source) y Public URL
    (camtrapdp_source.fetch_camtrap_dp_archive) — un export de Trapper
    (que es de donde viene este placeholder) puede llegar por cualquiera de
    las tres, no solo descargándolo directamente con 'trapper download'."""
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


_CITATION_AUTHOR_ROLES = {"principalInvestigator", "contributor"}


def resolve_authors(contributors: list) -> list:
    """Convierte los contributors de datapackage.json (title/organization,
    nombre completo sin separar en nombre/apellidos — ver get_contributors()
    en el servidor) en autores "entity" de CITATION.cff. Sin fallback: si no
    hay contributors, es que el proyecto de clasificación en Trapper no
    tiene administradores configurados — hay que arreglarlo ahí, no
    sustituirlo aquí por un autor genérico.

    Solo se incluyen los contributors cuyo role sea "principalInvestigator"
    o "contributor" (o no tenga role, el valor por defecto de Camtrap DP
    para "contributor") — "contact" tiene su propio campo en CITATION.cff
    (ver resolve_contact) y "publisher"/"rightsHolder" no tienen ningún
    campo equivalente ahí, así que no tiene sentido citarlos como autores.

    Raises:
        RuntimeError: si no queda ningún contributor con nombre después de
        ese filtro.
    """
    authors = []
    for contributor in contributors:
        if not isinstance(contributor, dict):
            continue
        role = contributor.get("role") or "contributor"
        if role not in _CITATION_AUTHOR_ROLES:
            continue
        name = contributor.get("title")
        if not name:
            continue
        authors.append({"name": name, "affiliation": contributor.get("organization") or ""})

    if authors:
        return authors

    raise RuntimeError(
        "datapackage.json has no 'contributor' with a name and a role of 'principalInvestigator' "
        "or 'contributor' — configure the administrators of the classification project in Trapper "
        "(get_contributors() derives them from there), or adjust contributor roles in the wizard."
    )


def resolve_contact(contributors: list) -> list:
    """Convierte los contributors de datapackage.json cuyo role sea
    exactamente "contact" en entradas "entity" para el campo `contact` de
    CITATION.cff — a diferencia de resolve_authors, estos NO se incluyen
    también como autores (el propio CITATION.cff ya tiene un campo
    específico para esto). Lista vacía (nunca error) si no hay ninguno —
    `contact` es opcional en CITATION.cff, a diferencia de `authors`."""
    contacts = []
    for contributor in contributors:
        if not isinstance(contributor, dict) or contributor.get("role") != "contact":
            continue
        name = contributor.get("title")
        if not name:
            continue
        contacts.append({"name": name, "affiliation": contributor.get("organization") or ""})
    return contacts


def resolve_publisher(contributors: list) -> Optional[dict]:
    """Convierte el (primer) contributor de datapackage.json cuyo role sea
    "publisher" en una entidad CFF (name/website/email) — CITATION.cff no
    tiene ningún campo "publisher" a nivel raíz (verificado contra el
    schema oficial: solo existe dentro de un objeto "reference", el mismo
    que usa preferred-citation/references), así que write_citation lo
    coloca dentro de un bloque preferred-citation en vez de excluirlo sin
    más (como antes). Si hubiera más de un contributor con role
    "publisher" (no debería, con el editor del wizard — ver
    CAMTRAPDP_PUBLISHER en WizardPage.tsx, la única fila fija con ese rol),
    se usa el primero. None si no hay ninguno."""
    for contributor in contributors:
        if not isinstance(contributor, dict) or contributor.get("role") != "publisher":
            continue
        name = contributor.get("title")
        if not name:
            continue
        publisher: dict = {"name": name}
        if contributor.get("path"):
            publisher["website"] = contributor["path"]
        if contributor.get("email"):
            publisher["email"] = contributor["email"]
        return publisher
    return None


def resolve_copyright_holders(contributors: list) -> list[str]:
    """Nombres de los contributors de datapackage.json cuyo role sea
    "rightsHolder" — CFF's "copyright" (igual que "publisher", solo existe
    dentro de un "reference") es un string libre, no una lista de
    entidades, así que write_citation combina estos nombres con el año de
    date_released ("© <año> <nombre(s)>") una vez conocido, en vez de
    hacerlo aquí. Lista vacía si no hay ninguno."""
    return [
        contributor["title"] for contributor in contributors
        if isinstance(contributor, dict) and contributor.get("role") == "rightsHolder" and contributor.get("title")
    ]


def keep_only_public_media(output_dir: Path) -> set:
    """Reescribe media.csv dejando solo las filas con filePublic=true.

    Returns:
        El conjunto de mediaID que se han conservado (público), para poder
        arrastrar el filtro a observations.csv.

    Raises:
        RuntimeError: si no hay media.csv, o le falta la columna filePublic.
    """
    media_csv = output_dir / MEDIA_CSV_FILENAME
    if not media_csv.is_file():
        raise RuntimeError(f"{media_csv} not found inside the copied Camtrap DP package.")

    fieldnames, rows = read_csv(media_csv)
    if FILE_PUBLIC_COLUMN not in fieldnames:
        raise RuntimeError(
            f"{media_csv} does not have the '{FILE_PUBLIC_COLUMN}' column — cannot "
            "distinguish public from non-public media."
        )

    public_rows = [row for row in rows if row.get(FILE_PUBLIC_COLUMN, "").strip().lower() in TRUTHY_VALUES]
    removed = len(rows) - len(public_rows)

    write_csv(media_csv, fieldnames, public_rows)
    console.print(f"  {MEDIA_CSV_FILENAME}: {removed} non-public media row(s) removed, {len(public_rows)} remain.")

    if MEDIA_ID_COLUMN in fieldnames:
        return {row[MEDIA_ID_COLUMN] for row in public_rows}
    return set()


def drop_observations_of_removed_media(output_dir: Path, public_media_ids: set) -> None:
    """Reescribe observations.csv quitando las filas que referencian un
    mediaID que ya no está en media.csv (media no pública eliminada). Las
    filas sin mediaID (observaciones no ligadas a un fichero, ej. basadas en
    evento) no se tocan."""
    observations_csv = output_dir / OBSERVATIONS_CSV_FILENAME
    if not observations_csv.is_file() or not public_media_ids:
        return

    fieldnames, rows = read_csv(observations_csv)
    if MEDIA_ID_COLUMN not in fieldnames:
        return

    kept_rows = [
        row for row in rows
        if not row.get(MEDIA_ID_COLUMN) or row[MEDIA_ID_COLUMN] in public_media_ids
    ]
    removed = len(rows) - len(kept_rows)
    if removed:
        write_csv(observations_csv, fieldnames, kept_rows)
        console.print(f"  {OBSERVATIONS_CSV_FILENAME}: {removed} non-public media row(s) removed, {len(kept_rows)} remain.")


def anonymize_deployment_coordinates(output_dir: Path, *, decimals: int = DEFAULT_COORDINATE_DECIMALS) -> int:
    """Redondea latitude/longitude en deployments.csv a `decimals`
    decimales — un difuminado determinista (la misma coordenada da siempre
    el mismo resultado, a diferencia de un desplazamiento aleatorio), para
    que Zenodo/B2SHARE/HFH publiquen exactamente las mismas coordenadas
    difuminadas para un mismo deployment sin importar cuántas veces (o en
    qué combinación de repos) se prepare.

    No-op si deployments.csv no existe o no tiene esas columnas — nunca
    lanza, y las filas con latitude/longitude vacías o no numéricas se
    dejan tal cual.

    Returns:
        Cuántas filas se han redondeado.
    """
    deployments_csv = output_dir / DEPLOYMENTS_CSV_FILENAME
    if not deployments_csv.is_file():
        return 0

    fieldnames, rows = read_csv(deployments_csv)
    if LATITUDE_COLUMN not in fieldnames or LONGITUDE_COLUMN not in fieldnames:
        return 0

    rounded = 0
    for row in rows:
        try:
            latitude = float(row[LATITUDE_COLUMN])
            longitude = float(row[LONGITUDE_COLUMN])
        except (KeyError, TypeError, ValueError):
            continue
        row[LATITUDE_COLUMN] = str(round(latitude, decimals))
        row[LONGITUDE_COLUMN] = str(round(longitude, decimals))
        rounded += 1

    if rounded:
        write_csv(deployments_csv, fieldnames, rows)
        console.print(f"  {DEPLOYMENTS_CSV_FILENAME}: {rounded} deployment(s) coordinates rounded to {decimals} decimal(s).")
    return rounded


def randomize_media_ids(output_dir: Path, *, domain: str = "localhost") -> int:
    """Reemplaza en media.csv cualquier mediaID que no sea ya un UUID válido
    por uno determinista — uuid.uuid5(uuid.NAMESPACE_URL, f"{domain}:{old_id}") —,
    y actualiza toda referencia coincidente en observations.csv para que el
    enlace entre ambas tablas siga intacto — así los mediaID publicados no
    delatan la convención de numeración original (ids secuenciales, o
    derivados del propio id interno de Trapper).

    `domain` es lo que de verdad garantiza que dos fuentes DISTINTAS con el
    mismo mediaID numérico original no colisionen (el propio mediaID
    original, sin más, no lo garantiza — dos repositorios distintos pueden
    asignar "1", "2", "3"...) — normalmente el dominio del servidor Trapper o
    de la URL pública de origen (ver el campo "Media ID domain" del wizard
    web). Por ser determinista, además, volver a procesar la MISMA fuente
    (mismo domain + mismo mediaID original) reproduce siempre el mismo UUID
    — a diferencia de un uuid4() puramente aleatorio, que cambiaría en cada
    pasada aunque la foto real sea la misma.

    Solo toca los mediaID que aún NO son un UUID válido — de ahí que sea
    idempotente (una segunda pasada no vuelve a generar otros distintos, a
    diferencia de regenerar incondicionalmente cada vez), la misma garantía
    que ya ofrece anonymize_deployment_coordinates y de la que depende, por
    ejemplo, el wizard web al volver a llamar a esto tras pulsar "Back".

    No-op si media.csv no existe o no tiene esa columna — nunca lanza. Las
    filas de observations.csv sin mediaID (basadas en evento, no en un
    fichero) no se tocan, igual que en drop_observations_of_removed_media.

    Returns:
        Cuántos mediaID se han sustituido.
    """
    media_csv = output_dir / MEDIA_CSV_FILENAME
    if not media_csv.is_file():
        return 0

    fieldnames, rows = read_csv(media_csv)
    if MEDIA_ID_COLUMN not in fieldnames:
        return 0

    id_map = {}
    for row in rows:
        old_id = row.get(MEDIA_ID_COLUMN)
        if not old_id:
            continue
        try:
            uuid.UUID(old_id)
            continue  # already a valid UUID — leave it as-is
        except ValueError:
            pass
        new_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{domain}:{old_id}"))
        id_map[old_id] = new_id
        row[MEDIA_ID_COLUMN] = new_id

    if not id_map:
        return 0

    write_csv(media_csv, fieldnames, rows)
    console.print(f"  {MEDIA_CSV_FILENAME}: {len(id_map)} mediaID(s) replaced with UUIDs derived from {domain!r}.")

    observations_csv = output_dir / OBSERVATIONS_CSV_FILENAME
    if observations_csv.is_file():
        obs_fieldnames, obs_rows = read_csv(observations_csv)
        if MEDIA_ID_COLUMN in obs_fieldnames:
            updated = 0
            for row in obs_rows:
                old_id = row.get(MEDIA_ID_COLUMN)
                if old_id in id_map:
                    row[MEDIA_ID_COLUMN] = id_map[old_id]
                    updated += 1
            if updated:
                write_csv(observations_csv, obs_fieldnames, obs_rows)
                console.print(f"  {OBSERVATIONS_CSV_FILENAME}: {updated} mediaID reference(s) updated to match.")

    return len(id_map)


def format_apa_author(author: dict) -> str:
    """Una entrada de autor de CITATION.cff en formato APA.

    Autores "person" (given_names/family_names) se formatean como
    "Apellidos, I. I."; autores "entity" (solo name, de los contributors de
    Trapper — nombre completo sin separar en nombre/apellidos) se dejan tal
    cual, como hace APA con autores de grupo/organización."""
    if author.get("given_names"):
        initials = " ".join(f"{part[0]}." for part in author["given_names"].split() if part)
        return f"{author.get('family_names', '')}, {initials}".strip(", ")
    return author.get("name", "")


def format_apa_citation(
    *, authors: list, title: str, version: str, date_released: str, publisher: str, url: str,
    copyright_holders: list[str] | None = None,
) -> str:
    """Cita en formato APA (7ª ed.) para un dataset, generada a partir de los
    mismos datos que CITATION.cff — mismo criterio que la tarjeta "Cite this
    repository" de GitHub. `publisher` es quien lo cita como editor (el
    contributor con role "publisher" — ver resolve_publisher —, no el
    nombre del repositorio de destino: cada caller resuelve ese fallback
    por su cuenta, ver hfh.py/zenodo.py/b2share.py's own write_readme).
    copyright_holders (los contributors con role "rightsHolder" — ver
    resolve_copyright_holders) se añade como un "© <año> <nombre(s)>" al
    final, después de la URL — patch_readme_citation_url localiza la URL
    por su propio patrón (http(s)://...), no por ser el último token de la
    línea, precisamente para que esto no la rompa."""
    author_strs = [format_apa_author(a) for a in authors]
    if len(author_strs) == 1:
        authors_part = author_strs[0]
    elif len(author_strs) == 2:
        authors_part = f"{author_strs[0]} & {author_strs[1]}"
    else:
        authors_part = ", ".join(author_strs[:-1]) + f", & {author_strs[-1]}"

    year = date_released.split("-")[0] if date_released else "n.d."

    citation = f"{authors_part} ({year}). *{title}* (Version {version}) [Data set]. {publisher}. {url}"
    if copyright_holders:
        citation += f" © {year} {', '.join(copyright_holders)}"
    return citation


def write_license(template_file: Path, output_dir: Path, *, license_id: str, license_name: str, license_url: str) -> Path:
    path = output_dir / "LICENSE"
    text = render_text_template(
        template_file,
        license_id=license_id,
        license_name=license_name,
        license_url=license_url,
    )
    path.write_text(text, encoding="utf-8")
    return path


def write_citation(
    template_file: Path, output_dir: Path, *,
    title: str, message: str, authors: list, version: str, date_released: str,
    license_id: str, repository_code: str,
    contact: list | None = None,
    publisher: dict | None = None,
    copyright_holders: list[str] | None = None,
    url: str | None = None, doi: str | None = None,
    identifiers: list | None = None, notes: str | None = None,
) -> Path:
    """url/doi/identifiers/notes are never known yet the one time this is
    called (at prepare time, before the destination repo/DOI/PID exists) —
    they're declared here (rather than left as undefined Jinja variables)
    so the fields this file can eventually gain are visible from the
    function signature, not just from CITATION.cff.j2's own comment. They
    get filled in afterwards by patching the already-written YAML directly
    (see hfh.py's _patch_citation_with_repo_id, zenodo.py's
    _patch_citation_with_doi, b2share.py's _patch_citation_with_pid) —
    never through a second call to this function.

    contact (Camtrap DP only — see resolve_contact) is CITATION.cff's own
    "contact" field, distinct from "authors" — empty/None just omits the
    field, since it's optional there.

    publisher/copyright_holders (Camtrap DP only — see resolve_publisher/
    resolve_copyright_holders) come from contributors whose role is
    "publisher"/"rightsHolder". Neither has a top-level field in
    CITATION.cff (verified against the real CFF JSON schema: "publisher"
    and "copyright" only exist inside a "reference" object, additionalProperties
    is false at the root) — so both are rendered inside a preferred-citation
    block instead, which the CFF schema requires to repeat its own authors/
    title/type regardless. copyright_holders becomes a single free-text
    "© <year> <name(s)>" string there, the year taken from date_released.
    The whole preferred-citation block is omitted when neither is given —
    a bare repeat of title/authors/version/date-released adds nothing on
    its own. A contributor can carry more than one role (e.g. a second
    datapackage.json entry for the same person/organization with role
    "publisher" alongside their "principalInvestigator" one) — nothing
    here special-cases that: they simply show up wherever each of their
    own role's entry routes them (authors AND publisher, in that example)."""
    path = output_dir / "CITATION.cff"
    preferred_citation = None
    if publisher or copyright_holders:
        year = date_released.split("-")[0] if date_released else ""
        preferred_citation = {
            "type": "dataset",
            "title": title,
            "authors": authors,
            "version": version,
            "date_released": date_released,
            "publisher": publisher,
            "copyright": f"© {year} {', '.join(copyright_holders)}" if copyright_holders else None,
        }
    text = render_text_template(
        template_file,
        cff_version="1.2.0",
        title=title,
        message=message,
        citation_type="dataset",
        authors=authors,
        contact=contact,
        preferred_citation=preferred_citation,
        version=version,
        date_released=date_released,
        license_id=license_id,
        repository_code=repository_code,
        url=url,
        doi=doi,
        identifiers=identifiers,
        notes=notes,
    )
    path.write_text(text, encoding="utf-8")
    return path


def patch_citation_with_identifier(
    citation_path: Path, *, value: str, kind: str, url: Optional[str], description: str,
    allow_as_primary: bool = True,
) -> bool:
    """Escribe un DOI/PID en un CITATION.cff ya renderizado — patrón
    genérico compartido por zenodo.py's _patch_citation_with_doi/b2share.py's
    _patch_citation_with_pid (ambos ahora envoltorios finos sobre esta
    función, cada uno con su propia política: Zenodo nunca usa
    `allow_as_primary=True` en sandbox, y añade además su propio campo
    "notes"; B2SHARE distingue "doi" de "epic") y por
    services.doi_populate (que cruza el DOI de un repo en el CITATION.cff
    de otro, con su propio `description` identificando de qué repo viene).

    Si `kind` es "doi", `allow_as_primary` es True, y el CITATION.cff
    todavía no tiene un "doi" de nivel superior, se escribe ahí (+ "url").
    En cualquier otro caso se añade (o reemplaza, casando por
    `description`) una entrada en la lista "identifiers", sin tocar el
    campo principal — así conviven varios DOI/PID de distintos orígenes sin
    pisarse.

    Si el CITATION.cff ya tiene EXACTAMENTE este valor como "doi" de nivel
    superior, se trata también como el caso "primario" (re-confirma/
    actualiza su "url" si ha cambiado, p.ej. de la URL del draft a la del
    record ya publicado) en vez de cavar hacia identifiers — evita que una
    llamada posterior con el mismo DOI (reservado pronto y confirmado otra
    vez al publicar) lo duplique también ahí.

    Returns:
        True si el fichero cambió de verdad (el caller debe entonces
        regenerar checksums, y volver a subirlo si ya estaba subido).
    """
    if not citation_path.is_file():
        return False
    original_text = citation_path.read_text(encoding="utf-8")
    citation = yaml.safe_load(original_text) or {}

    already_primary = kind == "doi" and citation.get("doi") == value
    if kind == "doi" and allow_as_primary and (already_primary or not citation.get("doi")):
        citation["doi"] = value
        citation["url"] = url or citation.get("url")
    else:
        identifiers = [
            item for item in (citation.get("identifiers") or [])
            if not (isinstance(item, dict) and item.get("description") == description)
        ]
        identifiers.append({"type": "doi" if kind == "doi" else "other", "value": url or value, "description": description})
        citation["identifiers"] = identifiers

    new_text = yaml.safe_dump(citation, sort_keys=False, allow_unicode=True)
    if new_text == original_text:
        return False
    citation_path.write_text(new_text, encoding="utf-8")
    return True


def patch_readme_citation_url(readme_path: Path, url: str) -> bool:
    """Replaces the URL in the rendered README's '## Citation' blockquote
    (the APA citation line — see format_apa_citation) with `url`, whatever
    was already there — the dataset's own repo URL (the default every
    write_readme renders), an already cross-referenced DOI from an earlier
    call, or nothing meaningful yet.

    Matches on the http(s):// pattern itself, not on "last token on the
    line" — format_apa_citation may append a "© <year> <holder(s)>" notice
    AFTER the URL (see its own copyright_holders param), so the URL is no
    longer necessarily the line's last word.

    Unlike a one-shot placeholder swap (e.g. zenodo.py's own
    PLACEHOLDER_CITATION_URL, resolved exactly once, always early — Zenodo/
    B2SHARE reserve their own DOI right at upload time), a repo that never
    provides its own DOI (HFH — see PROVIDES_DOI) may or may not ever get
    one cross-referenced from another repo, and that can happen well after
    its own README already shows its default (own-repo) citation URL — from
    the SAME publish run's doi_populate.populate(), or a separate, later
    'zenodo sync-doi'/'b2share sync-pid'/'gbif sync-doi' run entirely. This
    finds and replaces whatever's currently there instead, so it works
    correctly no matter when it's called — including more than once, if a
    later run cross-references a different DOI still.

    Returns:
        True if the README was actually changed.
    """
    if not readme_path.is_file():
        return False
    text = readme_path.read_text(encoding="utf-8")
    heading_idx = text.find("## Citation")
    if heading_idx == -1:
        return False
    match = re.search(r"^> (?:.*\S)?$", text[heading_idx:], flags=re.MULTILINE)
    if not match:
        return False
    line = match.group(0)
    new_line = re.sub(r"https?://\S+", url, line)
    if new_line == line:
        return False
    start = heading_idx + match.start()
    end = heading_idx + match.end()
    new_text = text[:start] + new_line + text[end:]
    readme_path.write_text(new_text, encoding="utf-8")
    return True


def rewrite_media_filepaths_to_hfh(output_dir: Path, repo_id: str, *, images_dirname: str = IMAGES_DIRNAME) -> int:
    """Rewrites filePath in media.csv to the predictable HuggingFace Hub URL
    for each file (https://huggingface.co/datasets/{repo_id}/resolve/main/
    {images_dirname}/{bucket}/{fileName}, bucket = _image_bucket(fileName))
    — the same predictable, sharded pattern used by 'hfh upload'. If
    `output_dir`/<images_dirname>/ exists locally (images were downloaded
    here), only rows whose file is actually present there are rewritten
    (the rest keep their original filePath, with a warning); if it doesn't
    exist (e.g. 'zenodo prepare --hfh-repo-id' without downloading anything
    locally), every row is rewritten unconditionally, trusting that the
    file already lives on HuggingFace Hub.

    Returns:
        Number of rewritten rows.
    """
    media_csv = output_dir / MEDIA_CSV_FILENAME
    fieldnames, rows = read_csv(media_csv)
    if FILE_PATH_COLUMN not in fieldnames or FILE_NAME_COLUMN not in fieldnames:
        return 0

    images_dir = output_dir / images_dirname
    check_local = images_dir.is_dir()
    rewritten = 0
    missing = []
    for row in rows:
        file_name = row.get(FILE_NAME_COLUMN)
        if not file_name:
            continue
        bucket = _image_bucket(file_name)
        if check_local and not (images_dir / bucket / file_name).is_file():
            missing.append(file_name)
            continue
        row[FILE_PATH_COLUMN] = (
            f"https://huggingface.co/datasets/{repo_id}/resolve/main/{images_dirname}/{bucket}/{file_name}"
        )
        rewritten += 1

    write_csv(media_csv, fieldnames, rows)

    if missing:
        console.print(
            f"  [yellow]{len(missing)} row(s) of media.csv keep their original filePath "
            f"(the file was not downloaded to {images_dirname}/): {', '.join(missing[:5])}"
            + (", ..." if len(missing) > 5 else "") + "[/yellow]"
        )

    return rewritten


def _link_or_copy(source: Path, destination: Path) -> None:
    """Hard links `destination` to `source` when possible — same directory
    entry count as a real copy would give in disk usage terms (near-zero:
    just another name for the same inode), but instant, and always safe
    against later mutation: the only code that ever rewrites a mirrored
    image's own bytes (fit_images_to_size) writes to a temp file and swaps
    it in via Path.replace, which dereferences the old inode rather than
    overwriting its shared content. Falls back to a real copy if hardlinking
    isn't possible (e.g. source/destination on different filesystems —
    never the case for download_public_images's own cache_dir, always under
    the same session_dir, but cheap to guard against regardless)."""
    try:
        destination.hardlink_to(source)
    except OSError:
        shutil.copy2(source, destination)


def download_public_images(
    output_dir: Path, *, input_dir: Path, images_dirname: str = IMAGES_DIRNAME, timeout: int = DEFAULT_IMAGE_TIMEOUT,
    cache_dir: Path | None = None,
) -> None:
    """Trae a `output_dir`/<images_dirname>/ cada fichero referenciado en
    media.csv (ya filtrado a solo público) — su columna filePath admite las
    dos formas que reconoce el propio estándar Camtrap DP: una URL absoluta
    (como la entrega Trapper, con token de un solo uso, o un Camtrap DP ya
    publicado obtenido vía Public URL) se descarga por red sin autenticación
    adicional; cualquier otra cosa se trata como una ruta relativa a
    `input_dir` — el paquete ya trae sus propias imágenes localmente (p.ej.
    un directorio local ya autocontenido, con el mismo convenio que genera
    write_local_zip) — y simplemente se copia de ahí. Ya presentes en
    destino (mismo nombre) se saltan; los fallos de un fichero concreto no
    abortan el resto.

    Cada fichero se guarda bajo un subdirectorio de 2 caracteres hex
    (`_image_bucket(fileName)`), no suelto en la raíz de <images_dirname>/
    — HuggingFace Hub rechaza el push si algún directorio del repo supera
    los 10 000 ficheros, y un dataset grande de cámaras trampa lo supera
    con facilidad.

    cache_dir, si se da, se consulta/rellena ANTES que la descarga/copia
    real — cada fichero se materializa ahí una vez y de ahí a `destination`
    va como HARDLINK (ver _link_or_copy), no una copia real: sin coste de
    espacio ni de tiempo extra por cada repo que lo reutiliza. Seguro pese a
    que cada repo redimensiona después sus propias imágenes in-place a su
    propio min_image_edge/tamaño objetivo (ver fit_images_to_size), porque
    esa función nunca reescribe el contenido de un inode compartido: escribe
    a un fichero temporal y lo intercambia con Path.replace, que solo
    desreferencia el inode antiguo. Pensado para publish_orchestrator: una
    única caché por sesión compartida entre todos los repos de una
    publicación multi-repo, para que cada mediaID solo se descargue/copie de
    su origen real UNA vez por sesión, sin importar a cuántos repos se
    publique — y sin duplicar el espacio en disco entre `cache_dir` y el
    images/ propio de cada repo."""
    media_csv = output_dir / MEDIA_CSV_FILENAME
    fieldnames, rows = read_csv(media_csv)
    if FILE_PATH_COLUMN not in fieldnames:
        console.print(f"  [yellow]{media_csv} does not have the '{FILE_PATH_COLUMN}' column — no image will be downloaded.[/yellow]")
        return

    images_dir = output_dir / images_dirname
    images_dir.mkdir(parents=True, exist_ok=True)

    if not rows:
        console.print("  No public images to download.")
        return

    console.print(f"Fetching {len(rows)} public image(s) into {images_dir} ...")
    downloaded = copied = cached = skipped = failed = 0
    with httpx.Client(timeout=timeout) as client:
        for row in track(rows, description="Fetching images"):
            file_path = row.get(FILE_PATH_COLUMN)
            file_name = row.get(FILE_NAME_COLUMN) or row.get(MEDIA_ID_COLUMN)
            if not file_path or not file_name:
                failed += 1
                continue

            bucket = _image_bucket(file_name)
            bucket_dir = images_dir / bucket
            bucket_dir.mkdir(exist_ok=True)
            destination = bucket_dir / file_name
            if destination.exists():
                skipped += 1
                continue

            cache_destination = None
            if cache_dir is not None:
                cache_bucket_dir = cache_dir / bucket
                cache_bucket_dir.mkdir(parents=True, exist_ok=True)
                cache_destination = cache_bucket_dir / file_name
                if cache_destination.is_file():
                    _link_or_copy(cache_destination, destination)
                    cached += 1
                    continue

            # Absent a cache, fetched straight into `destination`; with one,
            # fetched into the cache first so it's there for the next repo
            # too, then hardlinked (see _link_or_copy) into `destination`
            # just like a cache hit above would have.
            fetch_destination = cache_destination or destination

            if file_path.startswith("http://") or file_path.startswith("https://"):
                try:
                    response = client.get(file_path)
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    console.print(f"  [red]✘  Could not download {file_name}: {exc}[/red]")
                    failed += 1
                    continue
                fetch_destination.write_bytes(response.content)
                downloaded += 1
            else:
                source = input_dir / file_path
                if not source.is_file():
                    console.print(f"  [red]✘  {file_name}: local file not found at {source}[/red]")
                    failed += 1
                    continue
                shutil.copy2(source, fetch_destination)
                copied += 1

            if cache_destination is not None:
                _link_or_copy(fetch_destination, destination)

    cache_note = f"{cached} reused from cache, " if cache_dir is not None else ""
    console.print(
        f"[green]✔  Images: {downloaded} downloaded, {copied} copied locally, {cache_note}"
        f"{skipped} already existed, {failed} failed.[/green]"
    )


_FIT_SIZE_NOOP_THRESHOLD = 0.9   # skip resizing entirely if already under this fraction of target_bytes
_FIT_SIZE_TARGET_MARGIN = 0.85   # scale for this fraction of target_bytes, not 100% (zip/tables overhead, rounding)


def fit_images_to_size(images_dir: Path, *, target_bytes: int, min_edge: int = 640, quality: int = 85) -> None:
    """Downscales every image under `images_dir` in place, uniformly, so
    their combined size fits within `target_bytes` — meant to run right
    after download_public_images (mirror mode) and before write_local_zip
    bundles them into --self-contained's own zip, so Zenodo's/B2SHARE's own
    per-file upload cap doesn't get hit with no way to recover other than
    dropping media entirely (see each module's own DEFAULT_MAX_ZIP_BYTES).

    A no-op whenever what's already on disk fits under
    `target_bytes * _FIT_SIZE_NOOP_THRESHOLD` — no resizing, no re-encoding,
    images untouched. Otherwise computes a single scale factor up front —
    `sqrt(target_bytes * _FIT_SIZE_TARGET_MARGIN / current_size)`, since a
    JPEG's size roughly scales with its pixel count, which scales with
    scale² — and applies it to every image the same way, so the whole
    dataset ends up at one consistent resolution rather than some images
    sharper than others depending on download order. This is a single pass:
    no build-the-zip-then-measure-then-redo loop, since the images are
    already local at this point and their combined size is measured
    directly, not estimated.

    Never shrinks an image's longest edge below `min_edge` pixels, and never
    upscales one already smaller than that — past that floor, shrinking
    further trades away more identifiability (species, individual markings)
    than it saves in bytes, so a still-oversized result is left for the
    caller's own final size check to catch and report, rather than silently
    degraded further here.

    Only files Pillow can open as images are touched, each re-saved in its
    own original format (JPEG stays JPEG at `quality`, PNG stays PNG, ...) —
    video files (if any) are left exactly as they were, and still count
    fully toward whatever the final zip ends up weighing.
    """
    image_paths = [p for p in images_dir.rglob("*") if p.is_file()] if images_dir.is_dir() else []
    if not image_paths:
        return

    current_size = sum(p.stat().st_size for p in image_paths)
    if current_size <= target_bytes * _FIT_SIZE_NOOP_THRESHOLD:
        return

    scale = min(1.0, (target_bytes * _FIT_SIZE_TARGET_MARGIN / current_size) ** 0.5)
    console.print(
        f"  Images: {current_size / 1024**3:.2f} GiB would exceed the archive's "
        f"{target_bytes / 1024**3:.2f} GiB budget — resizing to ~{scale:.0%} of original "
        f"dimensions (never below {min_edge}px on the longest edge)..."
    )

    resized = skipped = failed = 0
    for image_path in track(image_paths, description="Resizing images"):
        try:
            with Image.open(image_path) as img:
                width, height = img.size
                longest_edge = max(width, height)
                target_longest_edge = min(longest_edge, max(min_edge, round(longest_edge * scale)))
                if target_longest_edge == longest_edge:
                    skipped += 1
                    continue
                image_scale = target_longest_edge / longest_edge
                new_size = (max(1, round(width * image_scale)), max(1, round(height * image_scale)))
                save_format = img.format or "JPEG"
                resized_img = img.resize(new_size, Image.LANCZOS)
            # img (and its file handle) is closed before writing anything —
            # saved to a fresh temp file, then swapped onto image_path via
            # Path.replace, rather than reopened/overwritten in place: a
            # file that reached here as a hardlink (see
            # download_public_images's own cache_dir, shared across every
            # repo of one session) has its shared inode simply dereferenced
            # by the swap, never mutated — the cache's own copy (and any
            # OTHER repo's still-hardlinked one) stays exactly as it was.
            save_kwargs: dict[str, Any] = {"optimize": True}
            if save_format == "JPEG":
                if resized_img.mode not in ("RGB", "L"):
                    resized_img = resized_img.convert("RGB")
                save_kwargs["quality"] = quality
            tmp_path = image_path.with_name(f"{image_path.name}.tmp")
            resized_img.save(tmp_path, format=save_format, **save_kwargs)
            tmp_path.replace(image_path)
            resized += 1
        except Exception as exc:
            console.print(f"  [red]✘  Could not resize {image_path.name}: {exc}[/red]")
            failed += 1

    new_size_bytes = sum(p.stat().st_size for p in images_dir.rglob("*") if p.is_file())
    console.print(
        f"[green]✔  Images: {resized} resized, {skipped} already small enough, {failed} failed "
        f"— now {new_size_bytes / 1024**3:.2f} GiB.[/green]"
    )


def write_local_zip(
    output_dir: Path, *, images_dirname: str = IMAGES_DIRNAME, zip_filename: str = LOCAL_ZIP_FILENAME,
    embed_images: bool = False,
) -> Path:
    """Crea <zip_filename>: datapackage.json, deployments.csv, media.csv y
    observations.csv ya presentes en `output_dir` (solo media pública), pero
    con filePath de media.csv reescrito a una ruta relativa
    (<images_dirname>/<bucket>/<fichero>, bucket = _image_bucket(fichero),
    mismo esquema de sharding que download_public_images) en vez de la URL
    remota.

    Si `embed_images` es False (por defecto, uso de hfh), el zip asume que
    `output_dir`/<images_dirname>/ ya vive físicamente al lado del zip — para
    usar el paquete en local junto a esa carpeta ya descargada, sin depender
    de red. Los ficheros van sueltos en la raíz del zip.

    Si `embed_images` es True (uso de zenodo/b2share --self-contained), la
    carpeta de imágenes se empaqueta DENTRO del propio zip, de forma que un
    único fichero (el zip) contenga todo lo necesario — imprescindible en
    Zenodo (que no aloja estructuras de carpetas, solo ficheros sueltos) y,
    desde la migración de B2SHARE a InvenioRDM, también en B2SHARE (que limita
    cada record a 100 ficheros — un fichero por imagen suelta lo agotaría en
    cualquier dataset mediano). Al ser ya autocontenido, en este caso el zip
    queda además listo para usarse como GBIF's --archive-url (ver
    services.gbif/write_remote_zip, cuyas mismas dos correcciones se aplican
    aquí):
      - Los cuatro ficheros y la carpeta de imágenes se anidan dentro de una
        única carpeta raíz (el propio nombre del zip) — GBIF exige
        exactamente un directorio raíz al descomprimir, o trata el dataset
        entero como vacío sin ningún error visible.
      - El datapackage.json empaquetado recibe el campo
        `gbifIngestion.observationLevel` (detectado en observations.csv),
        sin el cual GBIF filtraría silenciosamente todas las observaciones."""
    fieldnames, rows = read_csv(output_dir / MEDIA_CSV_FILENAME)
    images_dir = output_dir / images_dirname
    if FILE_PATH_COLUMN in fieldnames and FILE_NAME_COLUMN in fieldnames:
        for row in rows:
            file_name = row.get(FILE_NAME_COLUMN)
            if file_name and (images_dir / _image_bucket(file_name) / file_name).is_file():
                row[FILE_PATH_COLUMN] = f"{images_dirname}/{_image_bucket(file_name)}/{file_name}"

    media_csv_buffer = io.StringIO()
    writer = csv.DictWriter(media_csv_buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

    zip_path = output_dir / zip_filename
    root_dirname = zip_path.stem if embed_images else None
    observation_level = _detect_observation_level(output_dir) if embed_images else None

    def arcname(name: str) -> str:
        return f"{root_dirname}/{name}" if root_dirname else name

    with ZipFile(zip_path, "w") as zf:
        datapackage_path = output_dir / DATAPACKAGE_FILENAME
        if observation_level:
            datapackage = json.loads(datapackage_path.read_text(encoding="utf-8"))
            datapackage.setdefault("gbifIngestion", {})["observationLevel"] = observation_level
            zf.writestr(arcname(DATAPACKAGE_FILENAME), json.dumps(datapackage, indent=2))
        else:
            zf.write(datapackage_path, arcname(DATAPACKAGE_FILENAME))
        deployments_path = output_dir / DEPLOYMENTS_CSV_FILENAME
        if deployments_path.is_file():
            zf.write(deployments_path, arcname(DEPLOYMENTS_CSV_FILENAME))
        zf.writestr(arcname(MEDIA_CSV_FILENAME), media_csv_buffer.getvalue())
        observations_path = output_dir / OBSERVATIONS_CSV_FILENAME
        if observations_path.is_file():
            zf.write(observations_path, arcname(OBSERVATIONS_CSV_FILENAME))
        if embed_images and images_dir.is_dir():
            for image_path in sorted(images_dir.rglob("*")):
                if image_path.is_file():
                    relative = image_path.relative_to(images_dir).as_posix()
                    zf.write(image_path, arcname(f"{images_dirname}/{relative}"))

    note = " (images embedded, GBIF-ready)" if embed_images else ""
    console.print(f"  {zip_filename}: created with filePath relative to {images_dirname}/{note}.")
    return zip_path


def _detect_observation_level(output_dir: Path) -> Optional[str]:
    """Reads observations.csv's own observationLevel column — "event" (one
    row per detection event/sequence) or "media" (one row per individual
    image/video, no event-level grouping) are the two values the Camtrap DP
    standard itself defines. Returns None if the column is missing, empty,
    or (unexpectedly) mixes both values within the same package — in any of
    those cases, write_remote_zip leaves gbifIngestion unset rather than
    guess wrong."""
    fieldnames, rows = read_csv(output_dir / OBSERVATIONS_CSV_FILENAME)
    if "observationLevel" not in fieldnames:
        return None
    levels = {row.get("observationLevel") for row in rows if row.get("observationLevel")}
    return levels.pop() if len(levels) == 1 else None


def write_remote_zip(output_dir: Path, *, zip_filename: str = REMOTE_ZIP_FILENAME) -> Path:
    """Packs the four core Camtrap DP files (datapackage.json/deployments.csv/
    media.csv/observations.csv), AS-IS, into a zip — meant to be registered
    as GBIF's --archive-url (see services.gbif). GBIF's CAMTRAP_DP crawler
    downloads that URL and decompresses it, so it must be a real zip archive
    — unlike write_local_zip's own zip, whose media.csv is deliberately
    rewritten to local-relative images/ paths (meaningful only alongside a
    sibling images/ folder downloaded/uploaded together, not once extracted
    in isolation by an external crawler). "Remote" as opposed to "local":
    media.csv here keeps whatever REMOTE URLs it already had, unmodified.

    Called by hfh.upload_to_huggingface for every Camtrap DP publish,
    mirror or link mode alike. In mirror mode it runs AFTER media.csv's own
    filePath has already been rewritten to real, permanent Hugging Face Hub
    URLs (see product.ProductAdapter.link_media_to_hfh) — those URLs travel
    with the package completely unmodified, so GBIF can resolve every image
    directly without needing them embedded in the zip too. In link mode,
    filePath is left exactly as prepare_hfh_export produced it (whatever the
    original source gave it), since no rewrite ever happens there — the zip
    itself (the file GBIF's --archive-url points at) is equally permanent
    either way, once uploaded to Hugging Face Hub; only whether each
    individual filePath entry stays resolvable afterwards depends on mode/
    source, a separate, lesser concern from the archive itself existing.

    The four files are nested inside a single top-level folder (named after
    the zip itself) rather than sitting at the zip's own root — GBIF's own
    CAMTRAP_DP crawler unpacks the archive and requires exactly one root
    directory in the result (org.gbif.utils.file.CompressionUtil errors with
    "More than one root directory" otherwise, treating the whole dataset as
    empty — no records, no error visible anywhere in this project — since
    four loose files at the zip's root unpack into four separate "roots").

    The zipped copy of datapackage.json also gets a `gbifIngestion.
    observationLevel` field injected — GBIF's own Camtrap DP -> Darwin Core
    conversion (the "camtrapdp"/"camtraptor" R packages) only keeps
    observations whose own observationLevel matches this value, DEFAULTING TO
    "event" when it's absent (see inbo/camtrapdp's write_dwc.R) — silently
    producing zero occurrences for a package like Trapper's own, which is
    always media-level, with no error visible anywhere either. This field is
    a GBIF-specific vendor extension (not part of the Camtrap DP standard
    itself), so it's only added to THIS zip, not to the on-disk
    datapackage.json every other repo also copies as-is."""
    zip_path = output_dir / zip_filename
    root_dirname = zip_path.stem
    observation_level = _detect_observation_level(output_dir)
    with ZipFile(zip_path, "w") as zf:
        for filename in CORE_CAMTRAPDP_FILES:
            source = output_dir / filename
            if not source.is_file():
                continue
            if filename == DATAPACKAGE_FILENAME and observation_level:
                datapackage = json.loads(source.read_text(encoding="utf-8"))
                datapackage.setdefault("gbifIngestion", {})["observationLevel"] = observation_level
                zf.writestr(f"{root_dirname}/{filename}", json.dumps(datapackage, indent=2))
            else:
                zf.write(source, f"{root_dirname}/{filename}")
    console.print(f"  {zip_filename}: created for GBIF registration (media.csv already points to Hugging Face Hub).")
    return zip_path


def find_camtrap_dp_root(extract_dir: Path) -> Path:
    """Locates the directory that actually holds datapackage.json right
    after extracting a Camtrap DP zip archive — it may sit directly at
    `extract_dir`'s own root, or nested one level inside a single top-level
    folder (see write_remote_zip — recent archives are always built this
    way, since GBIF's own CAMTRAP_DP crawler requires exactly one root
    directory when it unpacks one). Used by gbif.validate_camtrap_dp_archive/
    camtrapdp_source.fetch_camtrap_dp_archive right after zf.extractall().

    Raises:
        RuntimeError: if datapackage.json isn't at either of those two
        places.
    """
    if (extract_dir / DATAPACKAGE_FILENAME).is_file():
        return extract_dir
    subdirs = [p for p in extract_dir.iterdir() if p.is_dir()]
    if len(subdirs) == 1 and (subdirs[0] / DATAPACKAGE_FILENAME).is_file():
        return subdirs[0]
    raise RuntimeError(
        f"Could not find {DATAPACKAGE_FILENAME} directly in the archive, nor inside a single "
        "top-level folder within it."
    )


def cleanup_self_contained_sources(
    output_dir: Path, adapter: product.ProductAdapter, product_meta: dict, zip_filename: str,
) -> None:
    """Once `zip_filename` bundles the whole product (its own files plus the
    images/ folder — see write_local_zip's embed_images=True), the loose
    copies serve no purpose in --self-contained mode — worse, they may still
    carry stale one-time-use token URLs. Removes everything except the
    well-known generated wrapper files (product.GENERATED_FILENAMES) and the
    zip itself, so `output_dir` ends up with only what's meant to be
    uploaded (used by both zenodo.py and b2share.py's own --self-contained
    mode)."""
    for entry in output_dir.iterdir():
        if entry.name in product.GENERATED_FILENAMES or entry.name == zip_filename:
            continue
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()

    console.print(f"  Removed the loose {product_meta['product_type']} files (already bundled inside {zip_filename}).")
