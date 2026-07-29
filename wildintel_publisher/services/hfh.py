"""Preparación del export de HuggingFace Hub a partir de cualquier producto
soportado (Camtrap DP, YOLO...) — ver services.product.ProductAdapter.

'hfh prepare' no obtiene el producto directamente — parte de lo que ya se
obtuvo (Trapper download, un directorio local...) y de su metadata.json (ver
services.product.generate_metadata_json), delegando en el ProductAdapter del
tipo de producto correspondiente todo lo específico de su formato (qué
ficheros copiar, cómo filtrar/mirror sus imágenes).
"""
from datetime import datetime
from pathlib import Path

import httpx
import yaml
from huggingface_hub import HfApi, create_repo, upload_folder, whoami
from huggingface_hub.utils import HfHubHTTPError, RepositoryNotFoundError
from rich.console import Console

from wildintel_publisher.config import REPO_ROOT, HFHSettings
from wildintel_publisher.services import common, product

console = Console()

IMAGES_DIRNAME = common.IMAGES_DIRNAME

DEFAULT_IMAGE_TIMEOUT = common.DEFAULT_IMAGE_TIMEOUT
DEFAULT_VERSION = "1.0"

# HFH never produces its own DOI/PID (unlike Zenodo/B2SHARE) — used by the
# generic services.doi_populate to know which repos are candidate DOI
# *sources* (only PROVIDES_DOI=True ones) versus which can only ever be a
# DOI *destination* (HFH: gets someone else's DOI cross-referenced into its
# own CITATION.cff, with the user picking which one is primary if more than
# one is available).
PROVIDES_DOI = False

COMMON_TEMPLATES_DIR = REPO_ROOT / "templates" / "common"
LICENSE_TEMPLATE_FILE = COMMON_TEMPLATES_DIR / "LICENSE.j2"
CITATION_TEMPLATE_FILE = COMMON_TEMPLATES_DIR / "CITATION.cff.j2"

README_FILENAME = "README.md"
CITATION_FILENAME = "CITATION.cff"

# Written into README.md's/CITATION.cff's repo_id/url at prepare time — the
# real destination repo_id isn't known yet ('hfh prepare' has no --repo-id
# of its own, same as 'zenodo prepare'/'b2share prepare' not knowing their
# eventual DOI/PID). Replaced with the real thing once upload_to_huggingface
# actually knows it — see _patch_readme_with_repo_id/_patch_citation_with_repo_id.
PLACEHOLDER_REPO_ID = "REPLACE_WITH_HF_USER/dataset"


def prepare_hfh_export(
    *,
    input_dir: Path,
    output_dir: Path,
    metadata: HFHSettings,
    version: str = DEFAULT_VERSION,
    image_timeout: int = DEFAULT_IMAGE_TIMEOUT,
    overwrite: bool = False,
    mirror_images: bool = True,
) -> Path:
    """Copia el producto de `input_dir` a `output_dir` (vía el ProductAdapter
    de su tipo, leído de `input_dir`/metadata.json) y escribe README.md,
    CITATION.cff, LICENSE y checksums-sha256.txt.

    Si `mirror_images` es True (por defecto, modo "mirror"), además hace que
    el adapter descargue/copie las imágenes a `output_dir`/images/ y genera
    camtrapdp-local.zip (con rutas relativas a images/, para uso sin red).
    Si es False (modo "link"), el adapter deja la referencia a la media tal
    cual venía en `input_dir` (para Camtrap DP: apuntando a Trapper) y no se
    genera ese zip.

    title/description/version/licencia/autores/homepage salen siempre de
    metadata.json (ya extraídos una vez por generate_metadata_json — sin
    fallback aquí). message/repository_code (que no existen en ningún
    estándar de producto) siguen viniendo de HFHSettings.

    Returns:
        `output_dir`, listo para subir a HuggingFace Hub.

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

    common.ensure_output_dir(output_dir, overwrite=overwrite)

    product_meta = product.read_metadata_json(input_dir)
    adapter = product.get_adapter(product_meta["product_type"])

    console.print(f"Copying the product from {input_dir} to {output_dir} ...")
    adapter.prepare(input_dir, output_dir, mirror=mirror_images, image_timeout=image_timeout)
    product.copy_metadata_json(input_dir, output_dir)

    title = product_meta["title"]
    description = product_meta["description"]
    resolved_version = product_meta.get("version") or version
    license = product_meta["license"]
    authors = product_meta["authors"]
    date_released = datetime.now().date().isoformat()

    write_readme(
        output_dir, metadata, resolved_version, adapter,
        title=title, description=description, license_id=license["id"],
        authors=authors, date_released=date_released, mirror_images=mirror_images,
    )
    common.write_license(
        LICENSE_TEMPLATE_FILE, output_dir,
        license_id=license["id"], license_name=license["name"], license_url=license["url"],
    )
    common.write_citation(
        CITATION_TEMPLATE_FILE, output_dir,
        title=title, message=metadata.message, authors=authors, version=resolved_version,
        date_released=date_released, license_id=license["id"], repository_code=metadata.repository_code,
    )
    if mirror_images:
        # Named per product type — the Camtrap DP adapter's own default
        # (common.LOCAL_ZIP_FILENAME) is "camtrapdp-local.zip"; other
        # product types (e.g. yolo) get their own type-named zip instead of
        # a filename that only makes sense for Camtrap DP.
        local_zip_filename = (
            common.LOCAL_ZIP_FILENAME if adapter.product_type == product.CAMTRAPDP
            else f"{adapter.product_type}-local.zip"
        )
        adapter.bundle_local_zip(input_dir, output_dir, output_dir / local_zip_filename, embed_images=False)
    common.write_checksums(output_dir)

    console.print(f"[green]✔  HuggingFace Hub export prepared in {output_dir}[/green]")
    return output_dir


def write_readme(
    output_dir: Path, metadata: HFHSettings, version: str, adapter: product.ProductAdapter, *,
    title: str, description: str, license_id: str, authors: list, date_released: str,
    mirror_images: bool = True,
) -> Path:
    """Renders templates/common/README-{product_type}-body.md.j2 (shared by
    hfh/zenodo/b2share for the same product_type — see that file's own
    comment) with HFH's own format/location fragments slotted in (see
    templates/hfh/_readme-format-{product_type}.md.j2/_readme-location.md.j2)."""
    path = output_dir / README_FILENAME
    # The real destination repo_id isn't known at prepare time (see
    # PLACEHOLDER_REPO_ID) — upload_to_huggingface patches it in once it is.
    repo_url = f"https://huggingface.co/datasets/{PLACEHOLDER_REPO_ID}"
    body_template = COMMON_TEMPLATES_DIR / f"README-{adapter.product_type}-body.md.j2"
    text = common.render_text_template(
        body_template,
        dataset_name=title,
        version=version,
        description=description,
        repo_id=PLACEHOLDER_REPO_ID,
        license_id=license_id,
        repository_code=metadata.repository_code,
        mirror_images=mirror_images,
        record_noun="export",
        format_template=f"hfh/_readme-format-{adapter.product_type}.md.j2",
        location_template="hfh/_readme-location.md.j2",
        apa_citation=common.format_apa_citation(
            authors=authors, title=title, version=version, date_released=date_released,
            publisher="Hugging Face", url=repo_url,
        ),
        **adapter.readme_context(output_dir),
    )
    path.write_text(text, encoding="utf-8")
    return path


def _repo_exists(api: HfApi, repo_id: str, token: str) -> bool:
    try:
        api.repo_info(repo_id=repo_id, repo_type="dataset", token=token)
        return True
    except (RepositoryNotFoundError, HfHubHTTPError):
        return False


def _patch_readme_with_repo_id(readme_path: Path, repo_id: str) -> None:
    """Replaces PLACEHOLDER_REPO_ID (written at prepare time — see
    write_readme) with the real repo_id, now that upload_to_huggingface
    actually knows it. Plain text replacement: the placeholder appears
    verbatim both in the "Hugging Face repository" section and inside the
    APA citation sentence, and is distinctive enough not to collide with
    anything else in the file."""
    if not readme_path.is_file():
        return
    text = readme_path.read_text(encoding="utf-8")
    readme_path.write_text(text.replace(PLACEHOLDER_REPO_ID, repo_id), encoding="utf-8")


def _patch_citation_with_repo_id(citation_path: Path, repo_id: str) -> None:
    """Writes the dataset's real HuggingFace Hub url into an already-written
    CITATION.cff, now that upload_to_huggingface actually knows repo_id —
    same pattern as zenodo.py's _patch_citation_with_doi/b2share.py's
    _patch_citation_with_pid (never a "repository-artifact" field, just
    "url"). Unlike Zenodo/B2SHARE's DOI/PID (only assigned once actually
    published), HFH's repo_id is a user choice known as soon as upload
    starts — no need to wait for a separate 'release' step."""
    if not citation_path.is_file():
        return
    citation = yaml.safe_load(citation_path.read_text(encoding="utf-8")) or {}
    citation["url"] = f"https://huggingface.co/datasets/{repo_id}"
    citation_path.write_text(yaml.safe_dump(citation, sort_keys=False, allow_unicode=True), encoding="utf-8")



def tag_exists(repo_id: str, tag: str, token: str) -> bool:
    """Whether `tag` already exists as a git tag on the HFH dataset repo
    `repo_id` — used both to fail fast in upload_to_huggingface (before
    spending time/bandwidth uploading) and to warn upfront when the web
    wizard's "Test token" is clicked (see the web backend's
    hfh_service.test_token), before the user even starts publishing.
    Returns False (rather than raising) if the repo doesn't exist yet —
    a repo that doesn't exist can't have any tags either."""
    api = HfApi(token=token)
    try:
        refs = api.list_repo_refs(repo_id=repo_id, repo_type="dataset", token=token)
    except (RepositoryNotFoundError, HfHubHTTPError):
        return False
    return any(ref.name == tag for ref in refs.tags)


def upload_to_huggingface(
    output_dir: Path, *, repo_id: str, token: str, private: bool = True, mirror_images: bool = True,
) -> str:
    """Sube todo `output_dir` (README.md, CITATION.cff, LICENSE, datapackage.json,
    deployments.csv, media.csv, observations.csv, y en modo mirror también
    images/ y camtrapdp-local.zip, checksums-sha256.txt) a un repositorio
    dataset de HuggingFace Hub — menos metadata.json, bookkeeping interno
    del pipeline (product_type, publish_history...) que se queda en
    output_dir para el propio encadenado entre repos, pero nunca se publica.
    NO etiqueta el commit todavía (ver
    tag_release_on_huggingface) — así se puede, entre medias, hacer un
    "populate" de DOI cruzados con otros repos (ver services.doi_populate)
    antes de bloquear la versión con su tag; llamar a esta función una
    segunda vez (p.ej. tras ese populate, para volver a subir un
    CITATION.cff/README.md ya parcheados) es seguro: reutiliza el mismo
    repositorio y simplemente sube un nuevo commit.

    Antes de subir, siempre parchea README.md/CITATION.cff con el repo_id
    real (prepare_hfh_export solo pudo escribir un placeholder, ya que en
    ese momento el destino aún no se conoce — ver PLACEHOLDER_REPO_ID) y
    regenera checksums-sha256.txt.

    Si `mirror_images` es True (modo "mirror", por defecto), además hace que
    el adapter del producto reescriba sus referencias de media para que
    apunten a la URL de HuggingFace Hub de cada fichero (en vez de a su
    origen), y fija metadata.json's "homepage" a la URL del repo (ya que el
    propio HFH pasa a ser el hogar real de la media — ver
    product.write_homepage). Si es False (modo "link"), no se toca ni la
    media ni homepage — la referencia se deja tal cual traía
    `prepare_hfh_export`, porque la media no vive realmente en este repo de
    HFH.

    Para Camtrap DP, `camtrapdp-remote.zip` (ver common.write_remote_zip) se
    genera y sube siempre, en ambos modos — media.csv dentro del zip lleva
    lo que ya tuviera filePath en ese momento (URLs reales de HFH en modo
    mirror, o la referencia original — el token de un solo uso de Trapper, o
    lo que sea — en modo link). El zip en sí (el fichero que GBIF descarga)
    queda alojado de forma permanente en este repo de HFH en cualquiera de
    los dos modos; que sus entradas de filePath internas sigan siendo
    resolubles más adelante depende únicamente del modo/origen, no de si el
    zip mismo existe.

    Returns:
        La URL del repositorio en HuggingFace Hub.

    Raises:
        RuntimeError: si el token no es válido, si la versión ya se había
        publicado antes (ya existe como tag), o si falla la creación del
        repositorio o la subida.
    """
    if "/" not in repo_id:
        raise RuntimeError(f"Invalid repo_id: '{repo_id}' — must have the format user_or_organization/dataset.")

    try:
        whoami(token=token)
    except Exception as exc:
        raise RuntimeError(f"Invalid or unauthorized HuggingFace Hub token: {exc}") from exc

    product_meta = product.read_metadata_json(output_dir)
    adapter = product.get_adapter(product_meta["product_type"])
    version = product_meta.get("version") or DEFAULT_VERSION

    api = HfApi(token=token)
    if not _repo_exists(api, repo_id, token):
        console.print(f"Repository {repo_id} does not exist — creating it ({'private' if private else 'public'})...")
        try:
            create_repo(repo_id=repo_id, repo_type="dataset", private=private, token=token, exist_ok=True)
        except Exception as exc:
            raise RuntimeError(f"Could not create repository {repo_id}: {exc}") from exc
    elif tag_exists(repo_id, version, token):
        # Fails fast, before spending time/bandwidth uploading — the real,
        # can't-be-raced check is tag_release_on_huggingface's own, at
        # actual tag-creation time.
        raise RuntimeError(
            f"Version '{version}' has already been published to {repo_id} (a tag with that name "
            "already exists) — bump metadata.json's version before publishing again."
        )

    _patch_readme_with_repo_id(output_dir / README_FILENAME, repo_id)
    _patch_citation_with_repo_id(output_dir / CITATION_FILENAME, repo_id)

    if mirror_images:
        rewritten = adapter.link_media_to_hfh(output_dir, repo_id)
        console.print(f"  {rewritten} media reference(s) now pointing to HuggingFace Hub.")
        product.write_homepage(output_dir, f"https://huggingface.co/datasets/{repo_id}")

    if adapter.product_type == product.CAMTRAPDP:
        # Generated in both modes — write_remote_zip packs media.csv AS-IS
        # (see its own docstring), so in mirror mode this is built AFTER
        # link_media_to_hfh has already rewritten filePath to real HFH URLs
        # above; in link mode, filePath is left exactly as prepare_hfh_export
        # produced it (whatever the original source gave it — a Trapper
        # one-shot token URL, a local path, or an already-public URL, if the
        # source itself was a Public URL). Either way, the zip's own HFH URL
        # (where GBIF's --archive-url points) is permanent regardless of
        # mode — only its INTERNAL filePath entries' resolvability depends on
        # mirror/source, a separate, lesser concern than the archive itself
        # existing and being fetchable/decompressible.
        common.write_remote_zip(output_dir)

    common.write_checksums(output_dir)

    console.print(f"Uploading {output_dir} to {repo_id} ...")
    try:
        upload_folder(
            folder_path=str(output_dir),
            repo_id=repo_id,
            repo_type="dataset",
            token=token,
            commit_message="Publish Camtrap DP dataset via wildintel-publisher",
            # metadata.json is internal pipeline bookkeeping (product_type,
            # publish_history...), kept locally for chaining/re-reading —
            # never meant to be part of the published dataset itself.
            ignore_patterns=[product.METADATA_FILENAME],
        )
    except Exception as exc:
        raise RuntimeError(f"Could not upload the export to {repo_id}: {exc}") from exc

    repo_url = f"https://huggingface.co/datasets/{repo_id}"
    console.print(f"[green]✔  Uploaded to {repo_url} (not tagged yet — see 'hfh release').[/green]")
    return repo_url


def tag_release_on_huggingface(*, repo_id: str, token: str, version: str) -> None:
    """Etiqueta el commit ya subido con `version` — el momento en que esa
    versión queda bloqueada: una vez etiquetada, no se puede volver a
    publicar la misma versión (ver tag_exists). Se llama por separado de
    upload_to_huggingface precisamente para poder, entre medias, hacer un
    "populate" de DOI cruzados con otros repos (ver services.doi_populate)
    y volver a subir los ficheros ya parcheados antes de bloquear nada.

    Raises:
        RuntimeError: si la versión ya se había publicado antes (ya existe
        como tag), o si falla el etiquetado.
    """
    api = HfApi(token=token)
    try:
        api.create_tag(repo_id=repo_id, tag=version, repo_type="dataset", token=token)
        console.print(f"  Tagged {repo_id} as '{version}'.")
    except HfHubHTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        if status_code == 409:
            raise RuntimeError(
                f"Version '{version}' was already published to {repo_id} (a tag with that name "
                "already exists) — bump metadata.json's version before publishing again."
            ) from exc
        raise RuntimeError(f"Could not tag {repo_id} with version '{version}': {exc}") from exc

    repo_url = f"https://huggingface.co/datasets/{repo_id}"
    console.print(f"[green]✔  Published at {repo_url}[/green]")
    return repo_url


def _check_public_url(url: str) -> bool:
    """Comprueba, sin token (petición anónima), que `url` responde con éxito."""
    try:
        response = httpx.head(url, follow_redirects=True, timeout=15)
        if response.status_code in (403, 405):
            response = httpx.get(url, follow_redirects=True, timeout=15)
        return 200 <= response.status_code < 400
    except httpx.HTTPError:
        return False


def _set_repo_public(api: HfApi, repo_id: str, token: str) -> None:
    """Cambia la visibilidad del repo a público. huggingface_hub ha renombrado
    este método entre versiones (update_repo_visibility -> update_repo_settings),
    así que se prueban ambos."""
    try:
        api.update_repo_settings(repo_id=repo_id, repo_type="dataset", private=False, token=token)
    except (TypeError, AttributeError):
        api.update_repo_visibility(repo_id=repo_id, repo_type="dataset", private=False, token=token)


def release_on_huggingface(*, repo_id: str, token: str, dry_run: bool = False, verify_only: bool = False) -> bool:
    """Hace público el repositorio dataset `repo_id` de HuggingFace Hub (si
    todavía es privado) y verifica, con peticiones sin token, que es
    accesible públicamente de verdad.

    Args:
        dry_run: No cambia nada — solo informa de si ya es público/accesible.
        verify_only: No cambia nada — pero, a diferencia de dry_run, lanza
            RuntimeError si no es accesible públicamente.

    Returns:
        True si el repositorio es (ya, o tras esta llamada) público y accesible sin token.

    Raises:
        RuntimeError: si `verify_only=True` y el repo no es accesible públicamente.
    """
    api = HfApi(token=token)
    info = api.dataset_info(repo_id=repo_id, token=token)
    already_public = not info.private

    if already_public:
        console.print(f"Repository {repo_id} is already public.")
    elif dry_run or verify_only:
        console.print(f"[yellow]Repository {repo_id} is still private.[/yellow]")
    else:
        console.print(f"Making repository {repo_id} public ...")
        _set_repo_public(api, repo_id, token)
        already_public = True

    dataset_url = f"https://huggingface.co/datasets/{repo_id}"
    accessible = _check_public_url(dataset_url) and _check_public_url(f"{dataset_url}/tree/main")

    if verify_only and not accessible:
        raise RuntimeError(f"{repo_id} is not publicly accessible yet ({dataset_url}).")

    if accessible:
        console.print(f"[green]✔  {repo_id} is publicly accessible without a token: {dataset_url}[/green]")
    else:
        console.print(f"[red]✘  {repo_id} is not publicly accessible yet.[/red]")

    return accessible
