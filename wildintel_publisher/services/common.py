"""Utilidades compartidas por los distintos servicios de publicación
(wildintel_publisher.services.hfh, .zenodo y .b2share) — hashing,
renderizado de plantillas, y todo lo relacionado con leer/validar/filtrar el
propio camtrapdp (datapackage.json + CSVs) o descargar sus imágenes, que no
depende de a qué repositorio se vaya a publicar después.
"""
import csv
import hashlib
import io
import json
import re
import shutil
from pathlib import Path
from typing import Any, Optional
from zipfile import ZipFile

import httpx
import yaml
from frictionless import validate as frictionless_validate
from jinja2 import Environment, FileSystemLoader
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

# ~1.1 km at the equator — coarse enough to obscure the exact deployment
# point, still regionally useful. See anonymize_deployment_coordinates.
DEFAULT_COORDINATE_DECIMALS = 2

IMAGES_DIRNAME = "images"
LOCAL_ZIP_FILENAME = "camtrapdp-local.zip"
REMOTE_ZIP_FILENAME = "camtrapdp-remote.zip"
DEFAULT_IMAGE_TIMEOUT = 60

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


def validate_camtrap_dp(output_dir: Path) -> None:
    """Valida datapackage.json (y los CSV que referencia) contra el esquema
    oficial de Camtrap DP con frictionless — no solo la estructura genérica
    de Data Package, sino los requisitos propios del estándar (campos
    obligatorios, columnas de cada tabla, número de licencias, claves entre
    tablas...).

    Si datapackage.json no declara "profile" (necesario para que frictionless
    sepa que debe aplicar el esquema de Camtrap DP, no solo el genérico de
    Data Package), se le añade aquí mismo — queda así permanentemente en el
    fichero, que es lo que el propio estándar recomienda para que cualquier
    herramienta lo autodetecte.

    Raises:
        RuntimeError: si datapackage.json no es JSON válido, o si la
        validación de Camtrap DP falla (con el detalle de cada error).
    """
    datapackage_path = output_dir / DATAPACKAGE_FILENAME
    if not datapackage_path.is_file():
        raise RuntimeError(f"{datapackage_path} not found — cannot validate the camtrapdp.")

    try:
        data = json.loads(datapackage_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(f"{datapackage_path} is not valid JSON: {exc}") from exc

    if not data.get("profile"):
        data["profile"] = CAMTRAP_DP_PROFILE_URL
        datapackage_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        console.print(f"  datapackage.json: added \"profile\": \"{CAMTRAP_DP_PROFILE_URL}\" (it didn't have one).")

    console.print("Validating the camtrapdp against the Camtrap DP schema (frictionless)...")
    report = frictionless_validate(str(datapackage_path))

    if report.valid:
        console.print("[green]✔  The camtrapdp is valid according to the Camtrap DP schema.[/green]")
        return

    console.print("[red]✘  The camtrapdp is not valid according to the Camtrap DP schema:[/red]")
    for _type, title, message in report.flatten(["type", "title", "message"]):
        console.print(f"  [red]•[/red] {title}: {message}")

    raise RuntimeError(
        f"The camtrapdp in {output_dir} does not pass Camtrap DP validation (frictionless) — "
        "review the errors above."
    )


def read_datapackage_metadata(output_dir: Path) -> dict:
    """Lee title/description/version/licenses/contributors/homepage de
    datapackage.json, si existe y es válido."""
    datapackage_path = output_dir / DATAPACKAGE_FILENAME
    if not datapackage_path.is_file():
        return {}
    try:
        data = json.loads(datapackage_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    result = {key: data[key] for key in ("title", "description", "version") if data.get(key)}
    result["licenses"] = data.get("licenses") or []
    result["contributors"] = data.get("contributors") or []
    result["homepage"] = data.get("homepage")
    return result


def write_homepage(output_dir: Path, url: str) -> None:
    """Sets/overwrites the top-level "homepage" property (standard Data
    Package/Camtrap DP field for "a URL for the home on the web that is
    related to this data package") in datapackage.json — used by
    'hfh upload' in mirror mode to record the HuggingFace Hub dataset the
    images actually got uploaded to, so a later publish step (Zenodo,
    B2SHARE) can detect it instead of asking the user to retype it. Not
    called in link mode: media stays wherever it already was (e.g. Trapper),
    so this HFH repo isn't really the media's home."""
    datapackage_path = output_dir / DATAPACKAGE_FILENAME
    data = json.loads(datapackage_path.read_text(encoding="utf-8"))
    data["homepage"] = url
    datapackage_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def resolve_license(licenses: list) -> dict:
    """Busca la primera licencia real en datapackage.json (ignorando los
    placeholders "private" que Trapper añade cuando no hay una real para ese
    scope — ver get_package_metadata() en el servidor). Sin fallback: si no
    hay ninguna, es que 'trapper download' no llegó a parchearla (o el
    camtrapdp viene de otra vía) — hay que arreglar el camtrapdp, no
    sustituirla aquí.

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
        if name and name != "private":
            return {"id": name, "name": licence.get("title") or name, "url": licence.get("path") or ""}

    raise RuntimeError(
        "datapackage.json has no real license (everything is \"private\" placeholders, "
        "or the list is empty). Regenerate the package with 'trapper download' (it patches "
        "the license automatically)."
    )


def resolve_authors(contributors: list) -> list:
    """Convierte los contributors de datapackage.json (title/organization,
    nombre completo sin separar en nombre/apellidos — ver get_contributors()
    en el servidor) en autores "entity" de CITATION.cff. Sin fallback: si no
    hay contributors, es que el proyecto de clasificación en Trapper no
    tiene administradores configurados — hay que arreglarlo ahí, no
    sustituirlo aquí por un autor genérico.

    Raises:
        RuntimeError: si no hay ningún contributor con nombre.
    """
    authors = []
    for contributor in contributors:
        if not isinstance(contributor, dict):
            continue
        name = contributor.get("title")
        if not name:
            continue
        authors.append({"name": name, "affiliation": contributor.get("organization") or ""})

    if authors:
        return authors

    raise RuntimeError(
        "datapackage.json has no 'contributor' with a name — configure the administrators "
        "of the classification project in Trapper (get_contributors() derives them from there)."
    )


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


def format_apa_citation(*, authors: list, title: str, version: str, date_released: str, publisher: str, url: str) -> str:
    """Cita en formato APA (7ª ed.) para un dataset, generada a partir de los
    mismos datos que CITATION.cff — mismo criterio que la tarjeta "Cite this
    repository" de GitHub."""
    author_strs = [format_apa_author(a) for a in authors]
    if len(author_strs) == 1:
        authors_part = author_strs[0]
    elif len(author_strs) == 2:
        authors_part = f"{author_strs[0]} & {author_strs[1]}"
    else:
        authors_part = ", ".join(author_strs[:-1]) + f", & {author_strs[-1]}"

    year = date_released.split("-")[0] if date_released else "n.d."

    return f"{authors_part} ({year}). *{title}* (Version {version}) [Data set]. {publisher}. {url}"


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
    never through a second call to this function."""
    path = output_dir / "CITATION.cff"
    text = render_text_template(
        template_file,
        cff_version="1.2.0",
        title=title,
        message=message,
        citation_type="dataset",
        authors=authors,
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
    """Replaces the URL at the end of the rendered README's '## Citation'
    blockquote (the APA citation line — see format_apa_citation, which
    always ends the line with '<publisher>. <url>', nothing after it) with
    `url`, whatever was already there — the dataset's own repo URL (the
    default every write_readme renders), an already cross-referenced DOI
    from an earlier call, or nothing meaningful yet.

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
    new_line = re.sub(r"\S+$", url, line)
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
    {images_dirname}/{fileName}) — the same predictable pattern used by
    'hfh upload'. If `output_dir`/<images_dirname>/ exists locally (images
    were downloaded here), only rows whose file is actually present there
    are rewritten (the rest keep their original filePath, with a warning);
    if it doesn't exist (e.g. 'zenodo prepare --hfh-repo-id' without
    downloading anything locally), every row is rewritten unconditionally,
    trusting that the file already lives on HuggingFace Hub.

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
        if check_local and not (images_dir / file_name).is_file():
            missing.append(file_name)
            continue
        row[FILE_PATH_COLUMN] = f"https://huggingface.co/datasets/{repo_id}/resolve/main/{images_dirname}/{file_name}"
        rewritten += 1

    write_csv(media_csv, fieldnames, rows)

    if missing:
        console.print(
            f"  [yellow]{len(missing)} row(s) of media.csv keep their original filePath "
            f"(the file was not downloaded to {images_dirname}/): {', '.join(missing[:5])}"
            + (", ..." if len(missing) > 5 else "") + "[/yellow]"
        )

    return rewritten


def download_public_images(
    output_dir: Path, *, input_dir: Path, images_dirname: str = IMAGES_DIRNAME, timeout: int = DEFAULT_IMAGE_TIMEOUT,
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
    abortan el resto."""
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
    downloaded = copied = skipped = failed = 0
    with httpx.Client(timeout=timeout) as client:
        for row in track(rows, description="Fetching images"):
            file_path = row.get(FILE_PATH_COLUMN)
            file_name = row.get(FILE_NAME_COLUMN) or row.get(MEDIA_ID_COLUMN)
            if not file_path or not file_name:
                failed += 1
                continue

            destination = images_dir / file_name
            if destination.exists():
                skipped += 1
                continue

            if file_path.startswith("http://") or file_path.startswith("https://"):
                try:
                    response = client.get(file_path)
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    console.print(f"  [red]✘  Could not download {file_name}: {exc}[/red]")
                    failed += 1
                    continue
                destination.write_bytes(response.content)
                downloaded += 1
            else:
                source = input_dir / file_path
                if not source.is_file():
                    console.print(f"  [red]✘  {file_name}: local file not found at {source}[/red]")
                    failed += 1
                    continue
                shutil.copy2(source, destination)
                copied += 1

    console.print(
        f"[green]✔  Images: {downloaded} downloaded, {copied} copied locally, "
        f"{skipped} already existed, {failed} failed.[/green]"
    )


def write_local_zip(
    output_dir: Path, *, images_dirname: str = IMAGES_DIRNAME, zip_filename: str = LOCAL_ZIP_FILENAME,
    embed_images: bool = False,
) -> Path:
    """Crea <zip_filename>: datapackage.json, deployments.csv, media.csv y
    observations.csv ya presentes en `output_dir` (solo media pública), pero
    con filePath de media.csv reescrito a una ruta relativa
    (<images_dirname>/<fichero>) en vez de la URL remota.

    Si `embed_images` es False (por defecto, uso de hfh), el zip asume que
    `output_dir`/<images_dirname>/ ya vive físicamente al lado del zip — para
    usar el paquete en local junto a esa carpeta ya descargada, sin depender
    de red. Si `embed_images` es True (uso de zenodo/b2share --self-contained),
    la carpeta de imágenes se empaqueta DENTRO del propio zip, de forma que un
    único fichero (el zip) contenga todo lo necesario — imprescindible en
    Zenodo (que no aloja estructuras de carpetas, solo ficheros sueltos) y,
    desde la migración de B2SHARE a InvenioRDM, también en B2SHARE (que limita
    cada record a 100 ficheros — un fichero por imagen suelta lo agotaría en
    cualquier dataset mediano)."""
    fieldnames, rows = read_csv(output_dir / MEDIA_CSV_FILENAME)
    images_dir = output_dir / images_dirname
    if FILE_PATH_COLUMN in fieldnames and FILE_NAME_COLUMN in fieldnames:
        for row in rows:
            file_name = row.get(FILE_NAME_COLUMN)
            if file_name and (images_dir / file_name).is_file():
                row[FILE_PATH_COLUMN] = f"{images_dirname}/{file_name}"

    media_csv_buffer = io.StringIO()
    writer = csv.DictWriter(media_csv_buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

    zip_path = output_dir / zip_filename
    with ZipFile(zip_path, "w") as zf:
        zf.write(output_dir / DATAPACKAGE_FILENAME, DATAPACKAGE_FILENAME)
        deployments_path = output_dir / DEPLOYMENTS_CSV_FILENAME
        if deployments_path.is_file():
            zf.write(deployments_path, DEPLOYMENTS_CSV_FILENAME)
        zf.writestr(MEDIA_CSV_FILENAME, media_csv_buffer.getvalue())
        observations_path = output_dir / OBSERVATIONS_CSV_FILENAME
        if observations_path.is_file():
            zf.write(observations_path, OBSERVATIONS_CSV_FILENAME)
        if embed_images and images_dir.is_dir():
            for image_path in sorted(images_dir.iterdir()):
                if image_path.is_file():
                    zf.write(image_path, f"{images_dirname}/{image_path.name}")

    note = " (images embedded)" if embed_images else ""
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

    Must be called AFTER a mirror-mode upload_to_huggingface has already
    rewritten media.csv's filePath to real, permanent Hugging Face Hub URLs
    for each image (see product.ProductAdapter.link_media_to_hfh) — those
    URLs travel with the package completely unmodified, so GBIF can resolve
    every image directly without needing them embedded in the zip too.

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
