"""Preparación y publicación en B2SHARE (EUDAT) del mismo Camtrap DP que
'hfh prepare'/'zenodo prepare' — con los mismos tres modos que 'zenodo
prepare' para el filePath de media.csv (ver prepare_b2share_export):
ninguno de los dos flags (tal cual), --hfh-repo-id (enlazado a HuggingFace
Hub, sin descargar nada), o --self-contained.

--self-contained se comporta EXACTAMENTE igual que el de Zenodo (ya no como
el de 'hfh prepare'): descarga las imágenes públicas y las empaqueta DENTRO
de un único zip autocontenido (camtrapdp.zip — datapackage.json + CSVs +
images/, con el filePath de media.csv relativo a images/), borrando después
los ficheros sueltos — 'b2share upload' solo sube ese zip (más
README/LICENSE/CITATION.cff/checksums), nunca las imágenes sueltas una por
una. Esto no es una preferencia de diseño: la API de B2SHARE limita cada
record a 100 ficheros (RDM_RECORDS_MAX_FILES_COUNT, por defecto en
InvenioRDM) — cualquier dataset de cámaras-trampa con más de un puñado de
imágenes agotaría ese límite al segundo si se subiera fichero a fichero, tal
como ocurría con el diseño anterior (ver el historial de este módulo).

API de B2SHARE: token por cabecera 'Authorization: Bearer'. sandbox =
trng-b2share.eudat.eu (pruebas), production = b2share.eudat.eu (PID/DOI
real).

IMPORTANTE: B2SHARE migró de su antigua API "clásica" (buckets de ficheros,
PATCH a publication_state) a InvenioRDM (la misma base que el Zenodo
moderno) — a diferencia de Zenodo, no mantiene ninguna capa de
compatibilidad con la API vieja. Todo lo de aquí abajo está escrito contra
la API nueva, verificada consultando directamente /api/communities,
/api/records, /api/vocabularies/* y el JSON schema publicado
(record-v10.0.0.json) en b2share.eudat.eu.

Flujo (InvenioRDM estándar):
  1. POST /api/records — crea el draft (metadata únicamente).
  2. PUT /api/records/{id}/draft/review — fija a qué comunidad se solicita
     unirse (community-submission) — B2SHARE exige comunidad siempre.
  3. POST /api/records/{id}/draft/pids/doi — reserva el DOI (best-effort,
     ver reserve_doi/upload_to_b2share) ANTES de subir ningún fichero, para
     poder escribir el DOI real en CITATION.cff/README.md desde el
     principio en vez de solo tras publicar. El DOI reservado no
     resuelve/no es citable hasta que el record se publique de verdad, pero
     el identificador en sí ya es el definitivo.
  4. Por fichero: POST .../draft/files (inicializa) -> PUT
     .../draft/files/{key}/content (sube los bytes) -> POST
     .../draft/files/{key}/commit (confirma).
  5. POST /api/records/{id}/draft/actions/submit-review — envía el draft a
     revisión de un moderador de la comunidad (nunca hay publish directo:
     B2SHARE exige comunidad, y esa comunidad revisa todo lo que llega —
     ver record_submission_policy/review_policy en /api/communities).
"""
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import httpx
import yaml
from rich.console import Console

from wildintel_publisher.config import B2ShareSettings, REPO_ROOT
from wildintel_publisher.services import common, product

console = Console()

DEFAULT_VERSION = "1.0"
DEFAULT_IMAGE_TIMEOUT = common.DEFAULT_IMAGE_TIMEOUT

# Used by the generic services.doi_populate to know which repos are
# candidate DOI *sources* — see hfh.py's own PROVIDES_DOI (always False).
PROVIDES_DOI = True

COMMON_TEMPLATES_DIR = REPO_ROOT / "templates" / "common"
LICENSE_TEMPLATE_FILE = COMMON_TEMPLATES_DIR / "LICENSE.j2"
CITATION_TEMPLATE_FILE = COMMON_TEMPLATES_DIR / "CITATION.cff.j2"

README_FILENAME = "README.md"
CITATION_FILENAME = "CITATION.cff"
RECORD_FILENAME = "b2share_record.json"

B2SHARE_PID_DESCRIPTION = "B2SHARE (EUDAT) dataset record PID/DOI"

# Zip autocontenido de --self-contained: igual que el de Zenodo (mismo
# nombre — ambos son ficheros generados en output_dir's independientes,
# nunca coinciden en disco), empaqueta también las imágenes DENTRO del
# propio zip — B2SHARE no puede alojar cientos/miles de ficheros sueltos por
# record (límite de 100 ficheros por record, ver el docstring del módulo),
# así que subir un único zip es la única opción viable para datasets de
# cámaras-trampa de tamaño real.
SELF_CONTAINED_ZIP_FILENAME = "camtrapdp.zip"


def _self_contained_zip_filename(product_type: str) -> str:
    """Named per product type — SELF_CONTAINED_ZIP_FILENAME is only the
    Camtrap DP name; other product types (e.g. yolo) get their own
    type-named zip instead of a filename that only makes sense for
    Camtrap DP."""
    return SELF_CONTAINED_ZIP_FILENAME if product_type == product.CAMTRAPDP else f"{product_type}.zip"

# Marcador del CITATION.cff/README.md de --self-contained (link mode ya
# apunta a una URL real, la de HuggingFace Hub, así que no necesita
# marcador) — sustituido por la URL del resolver del DOI en cuanto
# upload_to_b2share consigue reservarlo (ver reserve_doi/_patch_readme_with_doi),
# o si no, al publicar (ver release_on_b2share).
PLACEHOLDER_CITATION_URL = "(DOI assigned by B2SHARE upon publication)"


def prepare_b2share_export(
    *,
    input_dir: Path,
    output_dir: Path,
    metadata: B2ShareSettings,
    hfh_repo_id: Optional[str] = None,
    self_contained: bool = False,
    version: str = DEFAULT_VERSION,
    image_timeout: int = DEFAULT_IMAGE_TIMEOUT,
    overwrite: bool = False,
) -> Path:
    """Copia el producto de `input_dir` a `output_dir` (vía el ProductAdapter
    de su tipo, leído de `input_dir`/metadata.json) — mismos tres modos que
    'zenodo prepare' para la referencia a la media:

    - `self_contained=True`: igual que 'zenodo prepare' --self-contained —
      descarga la media a `output_dir`/images/, la empaqueta DENTRO de
      `camtrapdp.zip` (junto con datapackage.json/CSVs, con el filePath de
      media.csv relativo a images/) y borra los ficheros sueltos después:
      'b2share upload' solo sube el zip, nunca las imágenes una a una (la
      API de B2SHARE limita cada record a 100 ficheros — ver el docstring
      del módulo). Tiene prioridad sobre `hfh_repo_id` si ambos se indican.
    - `hfh_repo_id` (sin `self_contained`): no descarga nada — hace que el
      adapter reescriba la referencia a la URL predecible de HuggingFace
      Hub (asumiendo que ya está, o va a estar, subida allí vía
      'hfh upload').
    - Ninguno de los dos: la referencia se deja tal cual traía `input_dir`,
      sin modificar.

    title/description/version/licencia/autores salen siempre de
    metadata.json — sin fallback aquí, igual que en 'hfh prepare'/'zenodo
    prepare' (ya se validaron una vez al generarlo).

    Returns:
        `output_dir`, listo para subir a B2SHARE.

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
        output_dir, resolved_version, adapter, self_contained=self_contained,
        title=title, description=description, license_id=license["id"],
        authors=authors, date_released=date_released, hfh_repo_id=hfh_repo_id,
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
        adapter.bundle_local_zip(output_dir, output_dir / zip_filename, embed_images=True)
        common.cleanup_self_contained_sources(output_dir, adapter, product_meta, zip_filename)
    common.write_checksums(output_dir)

    mode = "self-contained (with images, exactly like zenodo)" if self_contained else (
        "linked to HuggingFace Hub" if hfh_repo_id else "no image handling"
    )
    console.print(f"[green]✔  B2SHARE record prepared in {output_dir} ({mode}).[/green]")
    return output_dir


def write_readme(
    output_dir: Path, version: str, adapter: product.ProductAdapter, *, self_contained: bool,
    title: str, description: str, license_id: str, authors: list, date_released: str,
    hfh_repo_id: Optional[str],
) -> Path:
    """Renders templates/common/README-{product_type}-body.md.j2 (shared
    with hfh.py/zenodo.py for the same product_type) with B2SHARE's own
    format fragment slotted in (see
    templates/b2share/_readme-format-{product_type}.md.j2 — it folds its
    own "where this lives" bit in directly, so no location_template here,
    unlike HFH)."""
    path = output_dir / README_FILENAME
    hfh_repo_id_display = hfh_repo_id or "REPLACE_WITH_HF_USER/dataset"
    publisher_url = (
        PLACEHOLDER_CITATION_URL if self_contained else f"https://huggingface.co/datasets/{hfh_repo_id_display}"
    )
    body_template = COMMON_TEMPLATES_DIR / f"README-{adapter.product_type}-body.md.j2"
    text = common.render_text_template(
        body_template,
        dataset_name=title,
        version=version,
        description=description,
        hfh_repo_id=hfh_repo_id_display,
        self_contained=self_contained,
        zip_filename=_self_contained_zip_filename(adapter.product_type),
        license_id=license_id,
        repository_code="https://github.com/wildintelproject/wildintel-publisher",
        record_noun="record",
        format_template=f"b2share/_readme-format-{adapter.product_type}.md.j2",
        location_template=None,
        apa_citation=common.format_apa_citation(
            authors=authors, title=title, version=version, date_released=date_released,
            publisher="B2SHARE (EUDAT)", url=publisher_url,
        ),
        **adapter.readme_context(output_dir),
    )
    path.write_text(text, encoding="utf-8")
    return path


# ── API de B2SHARE ───────────────────────────────────────────────────────────

def _base_url(environment: str) -> str:
    return "https://trng-b2share.eudat.eu" if environment == "sandbox" else "https://b2share.eudat.eu"


def _api_base_url(environment: str) -> str:
    return f"{_base_url(environment)}/api"


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _check_response(response: httpx.Response, expected: tuple, context: str) -> None:
    if response.status_code in expected:
        return
    try:
        body = response.json()
    except Exception:
        body = response.text
    raise RuntimeError(f"{context} failed. HTTP status={response.status_code}. Response={body}")


def build_b2share_metadata(
    *, title: str, description: str, authors: list, license_id: str,
    related_identifier_url: Optional[str],
) -> dict:
    """Devuelve el body completo de POST /api/records (InvenioRDM) — no solo
    "metadata": B2SHARE también exige "access"/"files" a nivel superior.
    community_id ya NO va aquí (el esquema del record no tiene un campo de
    comunidad editable) — se fija aparte, vía request_community_review, una
    vez creado el draft.

    person_or_org.type importa de verdad aquí (a diferencia de Zenodo, que
    no distingue): InvenioRDM exige family_name cuando type="personal" —
    validación real de la API, no algo opcional. Los autores de este
    proyecto llegan siempre como "entity" (nombre completo sin separar en
    nombre/apellidos — ver resolve_authors en common.py/_resolve_authors en
    yolo_adapter.py), así que se marcan "organizational" (solo exige name).
    given_names/family_names (type="personal") es el único caso con ambos
    campos ya separados, si alguna vez llega así."""
    creators = []
    for author in authors:
        if author.get("given_names"):
            person: dict = {
                "type": "personal",
                "given_name": author["given_names"],
                "family_name": author.get("family_names", ""),
                "name": f"{author.get('family_names', '')}, {author['given_names']}",
            }
        else:
            person = {"type": "organizational", "name": author.get("name", "")}
        entry: dict = {"person_or_org": person}
        if author.get("affiliation"):
            entry["affiliations"] = [{"name": author["affiliation"]}]
        creators.append(entry)

    metadata = {
        "resource_types": [{"id": "dataset"}],
        "title": title,
        "description": description,
        "creators": creators,
        "rights": [{"id": license_id.lower()}],
        "publisher": "EUDAT B2SHARE",
        "publication_date": datetime.now().date().isoformat(),
    }
    if related_identifier_url:
        metadata["related_identifiers"] = [{
            "identifier": related_identifier_url,
            "scheme": "url",
            "relation_type": {"id": "isidenticalto"},
        }]
    return {
        "access": {"record": "public", "files": "public"},
        "files": {"enabled": True},
        "metadata": metadata,
    }


def create_draft_record(api_base_url: str, token: str, body: dict) -> dict:
    response = httpx.post(f"{api_base_url}/records", headers=_headers(token), json=body, timeout=60)
    _check_response(response, (200, 201), "Create B2SHARE draft")
    return response.json()


def request_community_review(api_base_url: str, token: str, record_id: str, community_id: str) -> dict:
    """Fija a qué comunidad se solicita unirse este draft — un "community
    submission" request (ver PUT .../draft/review). Sin esto,
    submit_for_review no tiene a quién enviar el draft."""
    url = f"{api_base_url}/records/{record_id}/draft/review"
    body = {"receiver": {"community": community_id}, "type": "community-submission"}
    response = httpx.put(url, headers=_headers(token), json=body, timeout=60)
    _check_response(response, (200, 201), "Set B2SHARE community review request")
    return response.json()


def reserve_doi(api_base_url: str, token: str, record_id: str) -> Optional[str]:
    """Reserva un DOI para el draft vía POST .../draft/pids/doi (InvenioRDM
    estándar) — puede llamarse nada más crear el draft, antes de subir
    ningún fichero, para poder escribir el DOI real en CITATION.cff/
    README.md desde el principio en vez de solo tras 'b2share release'. El
    DOI reservado no resuelve/no es citable hasta que el record se publique
    de verdad (moderador de la comunidad aprobando), pero el identificador
    en sí ya es el definitivo.

    NOTA sin verificar con una subida real: no confirmado que B2SHARE
    permita esto con la comunidad ya fijada pero sin ficheros subidos
    todavía — ver upload_to_b2share, que trata cualquier fallo aquí como no
    fatal (se reserva más tarde, al publicar, como antes de esto)."""
    url = f"{api_base_url}/records/{record_id}/draft/pids/doi"
    response = httpx.post(url, headers=_headers(token), timeout=60)
    _check_response(response, (200, 201), "Reserve a DOI for the B2SHARE draft")
    pids = response.json().get("pids", {})
    doi = pids.get("doi", {}).get("identifier") if isinstance(pids.get("doi"), dict) else None
    return str(doi) if doi else None


def get_record(api_base_url: str, token: str, record_id: str, draft: bool = False) -> dict:
    suffix = "/draft" if draft else ""
    url = f"{api_base_url}/records/{record_id}{suffix}"
    response = httpx.get(url, headers=_headers(token), timeout=60)
    _check_response(response, (200,), "Fetch B2SHARE record")
    return response.json()


def upload_file(api_base_url: str, token: str, record_id: str, file_path: Path, remote_filename: str) -> dict:
    """Sube un fichero al draft en los tres pasos que exige InvenioRDM:
    inicializar la clave, subir el contenido, y confirmarlo (commit) — la
    antigua API de B2SHARE lo hacía en un único PUT a un bucket, que ya no
    existe. Usada tanto para los pocos ficheros de metadatos como para el
    propio zip de --self-contained (nunca para imágenes sueltas — ver el
    docstring del módulo sobre el límite de 100 ficheros por record)."""
    key = quote(remote_filename)
    init_url = f"{api_base_url}/records/{record_id}/draft/files"
    init_response = httpx.post(init_url, headers=_headers(token), json=[{"key": remote_filename}], timeout=60)
    _check_response(init_response, (200, 201), f"Initialize B2SHARE file upload: {remote_filename}")

    content_url = f"{api_base_url}/records/{record_id}/draft/files/{key}/content"
    content_response = httpx.put(
        content_url, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/octet-stream"},
        content=file_path.read_bytes(), timeout=300,
    )
    _check_response(content_response, (200, 201), f"Upload file content to B2SHARE: {remote_filename}")

    commit_url = f"{api_base_url}/records/{record_id}/draft/files/{key}/commit"
    commit_response = httpx.post(commit_url, headers=_headers(token), timeout=60)
    _check_response(commit_response, (200, 201), f"Commit B2SHARE file: {remote_filename}")
    return commit_response.json()


def submit_for_review(api_base_url: str, token: str, record_id: str) -> dict:
    """Envía el draft a revisión de la comunidad ya fijada por
    request_community_review — B2SHARE no tiene un "publish" directo propio
    del depositante: siempre pasa por la comunidad, que lo aprueba o lo
    rechaza."""
    url = f"{api_base_url}/records/{record_id}/draft/actions/submit-review"
    response = httpx.post(url, headers=_headers(token), json={}, timeout=60)
    _check_response(response, (200, 201, 202), "Submit B2SHARE record for community review")
    return response.json()


def extract_pid(record: dict) -> tuple:
    """Devuelve (pid, kind) — kind es "doi" o "epic", para poder construir el
    resolver correcto (build_pid_url). InvenioRDM expone ambos bajo
    record["pids"] ({"doi": {"identifier": ...}, "epic": {"identifier": ...}}),
    a diferencia de la API antigua (metadata.DOI/metadata.ePIC_PID) — el
    identifier de "epic" ya viene como URL completa (http://hdl.handle.net/...),
    build_pid_url ya contempla ese caso."""
    pids = record.get("pids") or {}
    doi = pids.get("doi", {}).get("identifier") if isinstance(pids.get("doi"), dict) else None
    if doi:
        return str(doi), "doi"
    epic = pids.get("epic", {}).get("identifier") if isinstance(pids.get("epic"), dict) else None
    if epic:
        return str(epic), "epic"
    return None, None


def build_pid_url(pid: Optional[str], kind: Optional[str]) -> Optional[str]:
    if not pid:
        return None
    if pid.startswith("http"):
        return pid
    return f"http://hdl.handle.net/{pid}" if kind == "epic" else f"https://doi.org/{pid}"


def build_record_url(base_url: str, record: dict) -> Optional[str]:
    links = record.get("links", {})
    if isinstance(links, dict) and links.get("self_html"):
        return str(links["self_html"])
    record_id = record.get("id")
    return f"{base_url}/records/{record_id}" if record_id else None


def _read_record(output_dir: Path) -> dict:
    record_path = output_dir / RECORD_FILENAME
    if not record_path.is_file():
        raise RuntimeError(
            f"{record_path} not found — run 'b2share upload' before 'b2share release'/'b2share sync-pid'."
        )
    return json.loads(record_path.read_text(encoding="utf-8"))


def _write_record(output_dir: Path, record: dict) -> None:
    (output_dir / RECORD_FILENAME).write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")


def upload_to_b2share(
    output_dir: Path, *, token: str, environment: str, community_id: str,
    hfh_repo_id: Optional[str],
) -> dict:
    """Crea (o reutiliza, si ya existe b2share_record.json) un draft en
    B2SHARE, intenta reservar su DOI (ver reserve_doi) ANTES de subir nada
    —para poder escribir el DOI real en CITATION.cff/README.md desde el
    principio—, y sube todos los ficheros de `output_dir` (README,
    CITATION.cff, LICENSE, checksums-sha256.txt, datapackage.json/CSVs — o,
    en modo --self-contained, el único camtrapdp.zip en su lugar: ver
    prepare_b2share_export). Nunca sube imágenes sueltas una a una (la API
    de B2SHARE limita cada record a 100 ficheros — ver el docstring del
    módulo), a diferencia del diseño anterior a la migración a InvenioRDM.

    Si reservar el DOI falla (no verificado end-to-end contra B2SHARE — ver
    reserve_doi), no aborta la subida: sigue igual que antes, dejando que
    'b2share release' lo asigne y lo refleje él solo más tarde.

    Returns:
        El registro local {"record_id", "environment", "pid", ...} — ya
        guardado en `output_dir`/b2share_record.json.

    Raises:
        RuntimeError: si falla cualquier llamada a la API de B2SHARE (salvo
        la reserva del DOI, que es best-effort).
    """
    api_base_url = _api_base_url(environment)
    record_path = output_dir / RECORD_FILENAME

    product_meta = product.read_metadata_json(output_dir)
    license = product_meta["license"]
    authors = product_meta["authors"]
    related_identifier_url = f"https://huggingface.co/datasets/{hfh_repo_id}" if hfh_repo_id else None

    b2share_metadata = build_b2share_metadata(
        title=product_meta["title"],
        description=product_meta["description"],
        authors=authors,
        license_id=license["id"],
        related_identifier_url=related_identifier_url,
    )

    if record_path.is_file():
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record_id = record["record_id"]
        console.print(f"Reusing the existing B2SHARE draft: {record_id}")
        b2share_record = get_record(api_base_url, token, record_id, draft=True)
        if record.get("published"):
            raise RuntimeError(
                f"Record {record_id} is already published — it cannot be modified. "
                "For a new version, delete b2share_record.json and run 'b2share upload' again "
                "(this will create a new draft, unrelated to the already-published one)."
            )
    else:
        console.print("Creating a new draft on B2SHARE...")
        b2share_record = create_draft_record(api_base_url, token, b2share_metadata)
        record_id = b2share_record["id"]
        console.print(f"Requesting inclusion in community {community_id} ...")
        request_community_review(api_base_url, token, record_id, community_id)

    pid, pid_kind = extract_pid(b2share_record)
    if not pid:
        try:
            reserved_doi = reserve_doi(api_base_url, token, record_id)
        except RuntimeError as exc:
            reserved_doi = None
            console.print(
                f"[yellow]⚠ Could not reserve a DOI ahead of upload — it'll only be known after "
                f"'b2share release' instead. ({exc})[/yellow]"
            )
        if reserved_doi:
            pid, pid_kind = reserved_doi, "doi"

    if pid_kind == "doi" and pid:
        doi_url = build_pid_url(pid, "doi")
        _patch_citation_with_pid(output_dir / CITATION_FILENAME, pid=pid, pid_kind="doi", record_url=doi_url)
        _patch_readme_with_doi(output_dir / README_FILENAME, doi_url)
        common.write_checksums(output_dir)
        console.print(f"[green]✔  DOI reserved ahead of upload: {pid}[/green]")

    files = sorted(p for p in output_dir.iterdir() if p.is_file() and p.name != RECORD_FILENAME)
    console.print(f"Uploading {len(files)} metadata file(s) to draft {record_id} ...")
    for file_path in files:
        upload_file(api_base_url, token, record_id, file_path, file_path.name)
        console.print(f"  [green]✓[/green] {file_path.name}")

    record = {
        "record_id": record_id,
        "environment": environment,
        "pid": pid,
        "pid_kind": pid_kind,
        "record_url": build_record_url(_base_url(environment), b2share_record),
        "published": False,
    }
    _write_record(output_dir, record)

    if pid:
        console.print(f"[green]✔  Draft {record_id} prepared, with DOI {pid} already reserved ahead of publication.[/green]")
    else:
        console.print(
            f"[green]✔  Draft {record_id} prepared (DOI not reserved yet — 'b2share release' will assign "
            "one, possibly pending approval by a moderator of the EUDAT community).[/green]"
        )
    return record


def release_on_b2share(output_dir: Path, *, token: str) -> dict:
    """Publica (envía a publicación) el draft de B2SHARE referenciado en
    `output_dir`/b2share_record.json, y — si ya hay PID/DOI disponible —
    lo refleja en el propio CITATION.cff/checksums de `output_dir`.

    A diferencia de Zenodo, publicar no garantiza un PID/DOI inmediato:
    puede quedar pendiente de aprobación por un moderador de la comunidad
    EUDAT — en ese caso, hay que volver a comprobarlo más tarde (ver
    'b2share sync-pid').

    Returns:
        El registro local actualizado (con "pid"/"pid_kind"/"record_url"/"published").

    Raises:
        RuntimeError: si no hay b2share_record.json, o si falla la publicación.
    """
    record = _read_record(output_dir)
    api_base_url = _api_base_url(record["environment"])
    record_id = record["record_id"]

    if record.get("published"):
        console.print(f"Record {record_id} had already been submitted for publication.")
    else:
        console.print(
            f"Submitting B2SHARE record {record_id} for community review (may require approval by a "
            "moderator of the EUDAT community)..."
        )
        submit_for_review(api_base_url, token, record_id)

    # The published view (GET /api/records/{id}, no /draft) 404s until a
    # moderator actually accepts the community-review request — fall back
    # to the draft view in that case (its pids are empty/None either way,
    # same "pending approval" outcome as the published-but-no-PID case).
    try:
        b2share_record = get_record(api_base_url, token, record_id)
    except RuntimeError:
        b2share_record = get_record(api_base_url, token, record_id, draft=True)
    pid, pid_kind = extract_pid(b2share_record)
    record.update({
        "pid": pid,
        "pid_kind": pid_kind,
        "record_url": build_record_url(_base_url(record["environment"]), b2share_record) or record.get("record_url"),
        "published": True,
    })
    _write_record(output_dir, record)

    if pid:
        _patch_citation_with_pid(output_dir / CITATION_FILENAME, pid=pid, pid_kind=pid_kind, record_url=record["record_url"])
        common.write_checksums(output_dir)
        console.print(f"[green]✔  Published — PID/DOI: {pid} ({record['record_url']})[/green]")
    else:
        console.print(
            "[yellow]⚠ Record submitted for publication, but B2SHARE has not returned any "
            f"PID/DOI yet — it may be pending approval by a moderator of the EUDAT community. "
            f"Check {record['record_url']} later and run 'b2share sync-pid'.[/yellow]"
        )
    return record


def _patch_readme_with_doi(readme_path: Path, doi_url: str) -> None:
    """Sustituye PLACEHOLDER_CITATION_URL (solo aparece en modo
    --self-contained — link mode ya cita la URL real de HuggingFace Hub) por
    la URL del resolver del DOI en el README.md ya renderizado — mismo
    patrón de parcheo-de-texto-plano que hfh.py's
    _patch_readme_with_repo_id, en vez de volver a renderizar la plantilla."""
    if not readme_path.is_file():
        return
    text = readme_path.read_text(encoding="utf-8")
    readme_path.write_text(text.replace(PLACEHOLDER_CITATION_URL, doi_url), encoding="utf-8")


def _patch_citation_with_pid(citation_path: Path, *, pid: str, pid_kind: Optional[str], record_url: Optional[str]) -> None:
    """Escribe el PID/DOI de B2SHARE en un CITATION.cff (vía
    common.patch_citation_with_identifier). Si es un DOI real y el
    CITATION.cff todavía no tiene uno (top-level doi/url), se escribe ahí;
    en cualquier otro caso (ya hay un DOI de otra fuente, ej. Zenodo, o es
    un PID Handle en vez de un DOI) se añade a la lista identifiers, sin
    pisar el campo principal."""
    pid_url = build_pid_url(pid, pid_kind) or record_url
    common.patch_citation_with_identifier(
        citation_path, value=pid, kind=pid_kind or "other", url=pid_url, description=B2SHARE_PID_DESCRIPTION,
    )


def sync_pid_to_hfh(*, b2share_output_dir: Path, hfh_output_dir: Path) -> Optional[str]:
    """Lee el PID/DOI ya disponible en `b2share_output_dir`/b2share_record.json,
    y lo refleja en el CITATION.cff de `hfh_output_dir` (el export ya
    preparado para HuggingFace Hub) — regenerando también sus checksums. El
    paso recomendado después es volver a subir con 'hfh upload'.

    Returns:
        El PID/DOI sincronizado, o None si B2SHARE todavía no ha asignado
        ninguno (pendiente de aprobación por un moderador de la comunidad).

    Raises:
        RuntimeError: si no hay b2share_record.json, o si `hfh_output_dir`/CITATION.cff no existe.
    """
    record = _read_record(b2share_output_dir)
    pid = record.get("pid")
    pid_kind = record.get("pid_kind")

    if not pid:
        console.print(
            "[yellow]⚠ There's no PID/DOI in the B2SHARE record yet — it's only assigned upon "
            "publishing (and may be pending approval by a moderator of the EUDAT community). "
            "Run 'b2share release' first, and try again later if it was pending.[/yellow]"
        )
        return None

    hfh_citation_path = hfh_output_dir / CITATION_FILENAME
    if not hfh_citation_path.is_file():
        raise RuntimeError(f"{hfh_citation_path} not found — run 'hfh prepare' first.")

    _patch_citation_with_pid(hfh_citation_path, pid=pid, pid_kind=pid_kind, record_url=record.get("record_url"))
    pid_url = build_pid_url(pid, pid_kind) or record.get("record_url")
    if pid_url:
        common.patch_readme_citation_url(hfh_output_dir / README_FILENAME, pid_url)
    common.write_checksums(hfh_output_dir)

    console.print(f"[green]✔  PID/DOI {pid} reflected in {hfh_citation_path}.[/green]")
    console.print("   Re-upload with [bold]hfh upload[/bold] to publish the change.")
    return pid
