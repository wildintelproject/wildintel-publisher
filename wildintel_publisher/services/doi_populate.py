"""Genérico: tras subir (upload) el producto a todos los repos
seleccionados pero ANTES de bloquear ninguno (Zenodo: release/publish;
B2SHARE: release/submit-review; HFH: crear el tag — ver
hfh.py's tag_release_on_huggingface), cruza los DOI ya obtenidos entre
ellos, escribiendo cada uno como "alternate identifier" en el CITATION.cff
de los demás.

Se apoya en el mecanismo que ya existe en cada repo desde antes de este
módulo (reservar el DOI antes de subir — ver zenodo.py's
build_zenodo_metadata/prereserve_doi y b2share.py's reserve_doi): en el
momento en que se llama a populate(), cualquier repo con PROVIDES_DOI=True
que haya conseguido reservar el suyo ya lo tiene escrito en su propio
CITATION.cff (campo top-level doi/url) — esta función solo necesita leerlo
de su propio fichero de registro local (RECORD_FILENAME de cada repo) y
cruzarlo con los demás.

HFH nunca provee su propio DOI (PROVIDES_DOI=False — ver hfh.py) — si
populate() recibe más de un DOI candidato y no se indica
`primary_doi_source`, ninguno se marca como principal en su CITATION.cff
(todos van a identifiers); con un único candidato disponible, ese se usa
como principal automáticamente. El README.md de un repo que SÍ se marca
como principal (solo posible para uno con PROVIDES_DOI=False, hoy solo
HFH) también se actualiza — ver common.patch_readme_citation_url, que
sustituye lo que sea que haya ahora mismo en su sección "## Citation" (su
propia URL por defecto, la de una llamada anterior...) por la del DOI
cruzado, sin depender de un marcador de una sola vez como el
PLACEHOLDER_CITATION_URL de Zenodo/B2SHARE (que sí resuelven su propio DOI
siempre pronto, al subir).

`outputs`' propios directorios NO necesitan ser el build_dir completo de
cada repo — deliberadamente: para cuando populate() corre, el build_dir ya
podría no existir (ver services.publish_orchestrator's propio docstring).
Esta función solo necesita, por cada repo, tres ficheros pequeños
(CITATION.cff, README.md, checksums-sha256.txt) y su propio RECORD_FILENAME
si provee DOI — de ahí que el checksum se actualice con
common.update_checksums_entries (que solo re-hashea los 1-2 ficheros que
de verdad cambiaron aquí) en vez de con common.write_checksums (que
necesitaría re-hashear TODOS los ficheros del export, físicamente
presentes en ese mismo directorio, para no dejar el checksums incompleto).
"""
import json
from pathlib import Path
from typing import NamedTuple, Optional

from wildintel_publisher.services import b2share, common, hfh, zenodo

REPO_MODULES = {"hfh": hfh, "zenodo": zenodo, "b2share": b2share}

REPO_LABELS = {"hfh": "Hugging Face Hub", "zenodo": "Zenodo", "b2share": "B2SHARE (EUDAT)"}


class RepoIdentifier(NamedTuple):
    repo: str
    value: str
    url: str


def _read_identifier(repo: str, output_dir: Path) -> Optional[RepoIdentifier]:
    """El DOI que `repo` ya tiene reservado/obtenido en su propio
    output_dir, o None si ese repo no provee DOI (ver PROVIDES_DOI) o
    todavía no lo ha conseguido."""
    module = REPO_MODULES[repo]
    if not getattr(module, "PROVIDES_DOI", False):
        return None
    record_path = output_dir / module.RECORD_FILENAME
    if not record_path.is_file():
        return None
    record = json.loads(record_path.read_text(encoding="utf-8"))

    if repo == "zenodo":
        doi = record.get("doi")
        if not doi:
            return None
        return RepoIdentifier(repo=repo, value=doi, url=f"https://doi.org/{doi}")

    if repo == "b2share":
        pid = record.get("pid")
        pid_kind = record.get("pid_kind")
        # Only real DOIs are cross-referenced here — B2SHARE's ePIC PID
        # (pid_kind == "epic") is never assigned until the record actually
        # publishes, which happens AFTER populate() runs, so it can't show
        # up yet at this point in the flow.
        if not pid or pid_kind != "doi":
            return None
        return RepoIdentifier(repo=repo, value=pid, url=f"https://doi.org/{pid}")

    return None


def collect_identifiers(outputs: dict[str, Path]) -> list[RepoIdentifier]:
    """Los DOI ya disponibles ahora mismo entre los repos de `outputs`
    ({repo_name: output_dir}) — solo los que de verdad proveen DOI y ya lo
    tienen (ver _read_identifier)."""
    identifiers = []
    for repo, output_dir in outputs.items():
        ident = _read_identifier(repo, output_dir)
        if ident:
            identifiers.append(ident)
    return identifiers


def populate(
    outputs: dict[str, Path], *, primary_doi_source: Optional[str] = None,
    checksums_paths: Optional[dict[str, Path]] = None,
) -> dict[str, bool]:
    """Para cada repo en `outputs`, cruza en su propio CITATION.cff (y
    README.md, si el módulo tiene su propio marcador — ver el docstring del
    módulo) los DOI ya obtenidos por LOS DEMÁS repos.

    - Si el repo ya provee su propio DOI (Zenodo/B2SHARE — ya lo tienen
      como principal desde antes de subir), los de los demás se añaden
      siempre como alternate identifiers.
    - Si no provee DOI propio (HFH), `primary_doi_source` indica qué repo
      debe ir como principal (campo doi/url) — el resto, como alternate
      identifiers. Sin indicarlo: si solo hay un candidato, se usa ese
      automáticamente; con más de uno, ninguno se marca como principal.

    `checksums_paths` — opcional, {repo: ruta a SU checksums-sha256.txt} —
    solo hace falta cuando ese fichero no vive junto al CITATION.cff/
    README.md de `outputs` (p.ej. una caché aparte — ver
    publish_orchestrator's own docstring sobre por qué build_dir podría no
    seguir existiendo). Un repo ausente de este dict usa el valor por
    defecto de siempre: `outputs[repo] / checksums-sha256.txt`.

    Returns:
        {repo: True/False} — si el CITATION.cff (y checksums-sha256.txt)
        de ese repo cambiaron de verdad. El caller debe entonces volver a
        subir ese repo's CITATION.cff/README.md/checksums-sha256.txt antes
        de bloquearlo (Zenodo/B2SHARE: llamar de nuevo a su propio
        upload_to_X, que reutiliza el draft/deposition existente; HFH:
        upload_to_huggingface de nuevo, que reutiliza el mismo repositorio).
    """
    identifiers = collect_identifiers(outputs)
    changed: dict[str, bool] = {repo: False for repo in outputs}
    checksums_paths = checksums_paths or {}

    for repo, output_dir in outputs.items():
        others = [i for i in identifiers if i.repo != repo]
        if not others:
            continue

        module = REPO_MODULES[repo]
        own_provides_doi = getattr(module, "PROVIDES_DOI", False)
        effective_primary = primary_doi_source
        if not own_provides_doi and effective_primary is None and len(others) == 1:
            effective_primary = others[0].repo

        citation_path = output_dir / "CITATION.cff"
        readme_path = output_dir / "README.md"
        repo_changed = False
        # Only the (up to 2) files that actually changed get re-hashed —
        # see update_checksums_entries below, and the module's own
        # docstring on why the rest of the export's files are never
        # touched (or even present) here.
        changed_files: dict[str, Path] = {}

        for ident in others:
            allow_as_primary = (not own_provides_doi) and ident.repo == effective_primary
            file_changed = common.patch_citation_with_identifier(
                citation_path, value=ident.value, kind="doi", url=ident.url,
                description=f"{REPO_LABELS.get(ident.repo, ident.repo)} DOI", allow_as_primary=allow_as_primary,
            )
            if file_changed:
                changed_files["CITATION.cff"] = citation_path
            repo_changed = repo_changed or file_changed
            if allow_as_primary:
                # Only a repo that never provides its own DOI (HFH — see
                # PROVIDES_DOI) ever reaches here: its README's own Citation
                # section still shows its default (own-repo) URL, since
                # nothing set it otherwise at prepare/upload time — replace
                # it with the cross-referenced DOI's own resolver URL (see
                # common.patch_readme_citation_url — value-aware, so this
                # works regardless of what's currently there).
                readme_changed = common.patch_readme_citation_url(readme_path, ident.url)
                if readme_changed:
                    changed_files["README.md"] = readme_path
                repo_changed = repo_changed or readme_changed

        if repo_changed:
            checksums_path = checksums_paths.get(repo) or (output_dir / common.CHECKSUM_FILENAME)
            common.update_checksums_entries(checksums_path, changed_files)
        changed[repo] = repo_changed

    return changed
