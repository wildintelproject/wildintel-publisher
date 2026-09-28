"""Configuración de la aplicación — cargada con Dynaconf y validada con Pydantic.

El fichero de configuración vive en el directorio de app del usuario (no en
el repo), porque las credenciales de Trapper son específicas de cada
máquina/usuario:
  - Linux:   ~/.config/wildintel-publisher/settings.toml
  - macOS:   ~/Library/Application Support/wildintel-publisher/settings.toml
  - Windows: %APPDATA%\\wildintel-publisher\\settings.toml
Se genera automáticamente con los valores por defecto la primera vez que se usa.
"""
import sys
from pathlib import Path
from typing import Any, Literal, Optional

import platformdirs
import typer
from dynaconf import Dynaconf, loaders
from pydantic import BaseModel, Field, model_validator

APP_NAME = "wildintel-publisher"

# Cuando se ejecuta como un ejecutable PyInstaller (--onefile), __file__ vive
# dentro del directorio temporal de extracción, no junto a templates/ como en
# checkout normal — sys._MEIPASS es la raíz de ese bundle (ver
# --add-data "templates:templates" en el workflow de release).
if getattr(sys, "frozen", False):
    REPO_ROOT = Path(sys._MEIPASS)  # type: ignore[attr-defined]
else:
    REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SETTINGS_DIR = Path(typer.get_app_dir(APP_NAME))
DEFAULT_CONFIG_FILE  = DEFAULT_SETTINGS_DIR / "settings.toml"


def get_app_documents_dir() -> Path:
    """<Documents>/wildintel-publisher — raíz de los paquetes Camtrap DP descargados."""
    return Path(platformdirs.user_documents_dir()) / APP_NAME


def get_trapper_output_dir() -> Path:
    """Directorio por defecto donde 'trapper download' descarga y extrae el paquete Camtrap DP."""
    return get_app_documents_dir() / "trapper"


def get_hfh_output_dir() -> Path:
    """Directorio por defecto donde 'hfh prepare' prepara el export para HuggingFace Hub."""
    return get_app_documents_dir() / "hfh"


def get_zenodo_output_dir() -> Path:
    """Directorio por defecto donde 'zenodo prepare' prepara el registro para Zenodo."""
    return get_app_documents_dir() / "zenodo"


def get_b2share_output_dir() -> Path:
    """Directorio por defecto donde 'b2share prepare' prepara el registro para B2SHARE."""
    return get_app_documents_dir() / "b2share"


def get_gbif_output_dir() -> Path:
    """Directorio por defecto donde 'gbif register' lee/escribe gbif_linked_dataset_record.json."""
    return get_app_documents_dir() / "gbif"


def get_software_output_dir() -> Path:
    """Directorio por defecto donde se clonan los repositorios git de productos software."""
    return get_app_documents_dir() / "software"


def get_camtrapdp_archive_output_dir() -> Path:
    """Directorio por defecto donde se descargan/extraen los Camtrap DP obtenidos por URL pública."""
    return get_app_documents_dir() / "camtrapdp-archive"


def get_sessions_dir() -> Path:
    """Directorio donde persisten las sesiones de publicación en curso o
    interrumpidas — ver services.publish_orchestrator (web app)."""
    return get_app_documents_dir() / "sessions"


def _slug_to_dataset_name(slug: str) -> str:
    """Deriva un nombre legible ('wildintel-camtrapdp' -> 'Wildintel Camtrapdp')
    a partir de un slug, igual que donadataset.config._slug_to_dataset_name."""
    return slug.replace("-", " ").replace("_", " ").title()


class TrapperSettings(BaseModel):
    """Valores por defecto reutilizados entre ejecuciones de 'prepare'.

    Igual que GBIFSettings en donadataset (Basic Auth con user_name/user_password):
    las variables de entorno WILDINTEL_BASE_URL/WILDINTEL_USER_NAME/
    WILDINTEL_USER_PASSWORD, si están definidas, tienen prioridad sobre estos
    valores — ver commands/camtrapdp.py, donde son el envvar= de cada flag.

    dataset_slug/dataset_name/description viven aquí (no en HFH) porque son
    la "semilla" que 'trapper download' pasa a Trapper (--title/--description)
    para que datapackage.json nazca ya con esos valores — 'hfh prepare' los
    lee de datapackage.json y NO tiene su propio fallback: si el camtrapdp no
    los trae, falla en vez de sustituirlos en silencio (ver services/hfh.py)."""
    base_url: Optional[str] = Field(
        default=None,
        description=(
            "Base URL of the Trapper instance, e.g. https://trapper.miteco.es. The "
            "WILDINTEL_BASE_URL environment variable, if set, takes priority over this "
            "value. (TRAPPER.base_url)"
        ),
    )
    user_name: Optional[str] = Field(
        default=None,
        description=(
            "Trapper user with access to the classification project. The "
            "WILDINTEL_USER_NAME environment variable, if set, takes priority over this "
            "value. (TRAPPER.user_name)"
        ),
        json_schema_extra={"secret": True},
    )
    user_password: Optional[str] = Field(
        default=None,
        description=(
            "Password of the Trapper user. The WILDINTEL_USER_PASSWORD environment "
            "variable, if set, takes priority over this value. (TRAPPER.user_password)"
        ),
        json_schema_extra={"secret": True},
    )
    project_id: Optional[int] = Field(
        default=None,
        description=(
            "Default id of the Trapper classification project to fetch the Camtrap DP "
            "from — can be overridden with --project-id. (TRAPPER.project_id)"
        ),
    )
    # WildINTEL project policy: every dataset is published under CC-BY-NC-4.0
    # (Attribution-NonCommercial), never plain CC-BY — deliberately fixed,
    # not something to vary per project/dataset. Used to patch any scope
    # (data/media) Trapper has left as "private" in datapackage.json (known
    # bug in Trapper's web license selector) — see
    # camtrapdp_source._fix_license_from_trapper_settings/
    # trapper.fetch_camtrapdp_package, applied regardless of which of the
    # three Camtrap DP sources (Trapper, Local Directory, Public URL) the
    # package came in through.
    license_id: Optional[str] = Field(
        default="CC-BY-NC-4.0",
        description=(
            "License identifier, e.g. CC-BY-NC-4.0 — used by 'trapper download' to patch "
            "any scope (data/media) that Trapper has left as \"private\" in "
            "datapackage.json (known bug in Trapper's web license selector). "
            "(TRAPPER.license_id)"
        ),
    )
    license_name: Optional[str] = Field(
        default="Creative Commons Attribution-NonCommercial 4.0 International",
        description="Full license name, for the same patch. (TRAPPER.license_name)",
    )
    license_url: Optional[str] = Field(
        default="https://creativecommons.org/licenses/by-nc/4.0/",
        description="License URL, for the same patch. (TRAPPER.license_url)",
    )
    dataset_slug: Optional[str] = Field(
        default="wildintel-camtrapdp",
        description=(
            "Short internal identifier (lowercase, no spaces) used to derive dataset_name "
            "if not set by hand — unrelated to the HuggingFace Hub repo, that's "
            "HFH.repo_id. (TRAPPER.dataset_slug)"
        ),
    )
    dataset_name: Optional[str] = Field(
        default=None,
        description=(
            "Default value of --title in 'trapper download' (title written into "
            "datapackage.json). If not set, it's derived automatically from dataset_slug. "
            "(TRAPPER.dataset_name)"
        ),
    )
    description: Optional[str] = Field(
        default=None,
        description=(
            "Default value of --description in 'trapper download'. Left unset by default — "
            "CamtrapDPAdapter.extract_metadata always appends its own WildINTEL attribution "
            "paragraph to whatever description ends up in datapackage.json, regardless of this "
            "setting. (TRAPPER.description)"
        ),
    )

    @model_validator(mode="after")
    def _derive_dataset_name(self) -> "TrapperSettings":
        if not self.dataset_name and self.dataset_slug:
            self.dataset_name = _slug_to_dataset_name(self.dataset_slug)
        return self


class HFHSettings(BaseModel):
    """Valores por defecto reutilizados entre ejecuciones de 'hfh upload'/'hfh
    release' — solo lo que de verdad no puede salir del propio camtrapdp
    (message/repository_code no existen en el estándar Camtrap DP; repo_id/
    token son específicos de HuggingFace Hub). El resto (título, descripción,
    licencia, autores) se lee siempre de datapackage.json — si no está,
    'hfh prepare' falla en vez de sustituirlo por un valor de configuración."""
    message: Optional[str] = Field(
        default="If you use this dataset, please cite it as below.",
        description="Citation message in CITATION.cff. (HFH.message)",
    )
    repository_code: Optional[str] = Field(
        default="https://github.com/wildintelproject/wildintel-publisher",
        description="Source code repository URL. (HFH.repository_code)",
    )
    repo_id: Optional[str] = Field(
        default=None,
        description="HuggingFace Hub repository, format user_or_org/dataset. (HFH.repo_id)",
    )
    username: Optional[str] = Field(
        default=None,
        description=(
            "HuggingFace Hub username or organization name (just the part before '/' in "
            "repo_id) — unlike repo_id, this is worth remembering across different products, "
            "since the dataset name itself changes per product. (HFH.username)"
        ),
    )
    token: Optional[str] = Field(
        default=None,
        description=(
            "HuggingFace Hub access token (write permission) — "
            "https://huggingface.co/settings/tokens. The HF_TOKEN environment variable, "
            "if set, takes priority over this value. (HFH.token)"
        ),
        json_schema_extra={"secret": True},
    )


class ZenodoSettings(BaseModel):
    """Valores por defecto reutilizados entre ejecuciones de 'zenodo upload'/
    'zenodo release'/'zenodo sync-doi'. Igual que HFHSettings: título,
    descripción, licencia y autores salen siempre de datapackage.json — solo
    lo que Zenodo necesita y no existe en el estándar Camtrap DP vive aquí."""
    environment: Optional[Literal["sandbox", "production"]] = Field(
        default="sandbox",
        description=(
            "Zenodo environment: 'sandbox' (sandbox.zenodo.org, testing, no real DOI) or "
            "'production' (zenodo.org, real DOI). (ZENODO.environment)"
        ),
    )
    communities: Optional[str] = Field(
        default=None,
        description=(
            "Zenodo communities to submit the deposition to when creating it, comma-"
            "separated (e.g. wildintelproject). (ZENODO.communities)"
        ),
    )
    token: Optional[str] = Field(
        default=None,
        description=(
            "Zenodo access token (or Zenodo Sandbox's if environment=sandbox) — "
            "https://zenodo.org/account/settings/applications/tokens/new/ (or the "
            "equivalent on sandbox.zenodo.org). The ZENODO_TOKEN environment variable, if "
            "set, takes priority over this value. (ZENODO.token)"
        ),
        json_schema_extra={"secret": True},
    )


class B2ShareSettings(BaseModel):
    """Valores por defecto reutilizados entre ejecuciones de 'b2share upload'/
    'b2share release'/'b2share sync-pid'. Igual que ZenodoSettings: título,
    descripción, licencia y autores salen siempre de datapackage.json — solo
    lo que B2SHARE necesita y no existe en el estándar Camtrap DP vive aquí.
    A diferencia de Zenodo/HFH, B2SHARE no da PID/DOI hasta que un moderador
    de la comunidad EUDAT aprueba el registro — puede quedar pendiente tras
    'b2share release'."""
    environment: Optional[Literal["sandbox", "production"]] = Field(
        default="sandbox",
        description=(
            "B2SHARE environment: 'sandbox' (trng-b2share.eudat.eu, testing) or "
            "'production' (b2share.eudat.eu, real PID/DOI). (B2SHARE.environment)"
        ),
    )
    community_id: Optional[str] = Field(
        default=None,
        description=(
            "UUID of the EUDAT B2SHARE community this record belongs to. Request it from "
            "EUDAT (it cannot be guessed). (B2SHARE.community_id)"
        ),
    )
    token: Optional[str] = Field(
        default=None,
        description=(
            "B2SHARE access token (or its sandbox's if environment=sandbox) — generated "
            "from your profile at b2share.eudat.eu. The B2SHARE_TOKEN environment "
            "variable, if set, takes priority over this value. (B2SHARE.token)"
        ),
        json_schema_extra={"secret": True},
    )


class GBIFInstallation(BaseModel):
    """Una instalación GBIF ya registrada y seleccionable — a diferencia de
    PRODUCT.organizations (una organización real-world, compartida con el
    editor de publisher/rightsHolder del wizard), una instalación es un
    concepto exclusivo de GBIF (el sistema/software que sirve los datos —
    en este caso, esta misma app actuando de fuente) sin ningún equivalente
    en los productos, así que vive aquí, no ahí. sandbox/production son
    Registries independientes con su propio UUID cada uno para la MISMA
    instalación real — nunca se derivan el uno del otro."""
    title: str = Field(description="Nombre legible de la instalación, solo para el desplegable del wizard.")
    sandbox_installation_key: Optional[str] = Field(
        default=None, description="UUID de esta instalación en el Registry sandbox de GBIF (gbif-test.org).",
    )
    production_installation_key: Optional[str] = Field(
        default=None, description="UUID de esta instalación en el Registry de producción de GBIF (gbif.org).",
    )


class GBIFSettings(BaseModel):
    """Valores por defecto reutilizados entre ejecuciones de 'gbif register'.
    A diferencia de HFH/Zenodo/B2SHARE, GBIF no aloja ningún fichero: solo
    registra en su Registry un dataset que apunta a una URL donde el
    camtrapdp YA está publicado (HuggingFace Hub, Zenodo, B2SHARE, o
    cualquier otro sitio público) — por eso no hay aquí ni token de subida
    ni modo self-contained/hfh-repo-id. Título/descripción/licencia salen,
    igual que en los demás, de metadata.json (ver services.product) — solo
    lo que la Registry API de GBIF exige y no existe en el estándar Camtrap
    DP vive aquí. publishing_organization_key/installation_key no se pueden
    adivinar: hacen falta una organización e instalación ya registradas y
    endosadas a mano en gbif.org (o su sandbox, gbif-test.org) — ver el
    mensaje que imprime 'gbif register' si faltan. La Registry API usa
    Basic Auth (username/password de tu cuenta gbif.org), no un token único
    como Zenodo/B2SHARE."""
    environment: Optional[Literal["sandbox", "production"]] = Field(
        default="sandbox",
        description=(
            "GBIF Registry API environment: 'sandbox' (gbif-test.org, testing, requires "
            "its own separate account/organization) or 'production' (gbif.org, real "
            "public dataset). (GBIF.environment)"
        ),
    )
    publishing_organization_key: Optional[str] = Field(
        default=None,
        description=(
            "UUID of your organization already registered and endorsed on gbif.org (or "
            "gbif-test.org for sandbox). Cannot be guessed. (GBIF.publishing_organization_key)"
        ),
    )
    installation_key: Optional[str] = Field(
        default=None,
        description=(
            "UUID of your installation already registered under that organization on "
            "gbif.org (or gbif-test.org). Cannot be guessed. (GBIF.installation_key)"
        ),
    )
    registry_language: Optional[str] = Field(
        default="eng",
        description=(
            "Language code (ISO 639-2/T, e.g. eng/spa) required by the Registry API's "
            "'language' field when registering the dataset. (GBIF.registry_language)"
        ),
    )
    username: Optional[str] = Field(
        default=None,
        description=(
            "Username of your gbif.org account (or gbif-test.org's, if environment="
            "sandbox) — the Registry API uses Basic Auth. The GBIF_USERNAME environment "
            "variable, if set, takes priority over this value. (GBIF.username)"
        ),
        json_schema_extra={"secret": True},
    )
    password: Optional[str] = Field(
        default=None,
        description=(
            "Password of that same account. The GBIF_PASSWORD environment variable, if "
            "set, takes priority over this value. (GBIF.password)"
        ),
        json_schema_extra={"secret": True},
    )
    installations: list[GBIFInstallation] = Field(
        default_factory=lambda: [
            GBIFInstallation(title="WildINTEL", sandbox_installation_key="9970e64a-f762-11e1-a439-00145eb45e9a"),
        ],
        description=(
            "Selectable installations for the web wizard's own \"Installation UUID\" "
            "dropdown (see GBIFPublishForm.tsx). (GBIF.installations)"
        ),
    )


class Organization(BaseModel):
    """One selectable entry of PRODUCT.organizations below — the web
    wizard's metadata-editing step (WizardPage.tsx) offers these as the
    options for BOTH the product's "publisher" and its rights holder
    (Camtrap DP: datapackage.json's "publisher"/"rightsHolder" contributor
    roles; YOLO: data.yaml's "publisher"/"copyright_holders"), so one shared
    list covers both instead of two. Also offered, separately, as the
    "Publishing organization UUID" dropdown in GBIFPublishForm.tsx — see
    gbif_sandbox_organization_key/gbif_production_organization_key below."""
    title: str = Field(description="Organization name, written as-is as the publisher/rights holder's own name.")
    path: Optional[str] = Field(default=None, description="Organization website, written as the publisher's own website.")
    email: Optional[str] = Field(
        default=None,
        description=(
            "Contact email, written into the contributor's own \"email\" — only meaningful "
            "for the publisher role (see services.common.resolve_publisher); rightsHolder "
            "ignores it."
        ),
    )
    gbif_sandbox_organization_key: Optional[str] = Field(
        default=None,
        description=(
            "This organization's own UUID on GBIF's sandbox Registry (gbif-test.org) — a "
            "SEPARATE registration from production's own, with its own UUID (GBIF's sandbox "
            "and production are independent systems). Left unset (the default) if this "
            "organization has no sandbox registration to offer as a quick-fill option."
        ),
    )
    gbif_production_organization_key: Optional[str] = Field(
        default=None,
        description=(
            "This organization's own UUID on GBIF's production Registry (gbif.org) — see "
            "gbif_sandbox_organization_key above for why it's a distinct value, never derived "
            "from it."
        ),
    )


class ProductSettings(BaseModel):
    """Settings shared by every product type. organizations: selectable as
    a product's own publisher/rights holder in the web wizard's
    metadata-editing step — hand-edit settings.toml's own
    [[PRODUCT.organizations]] array-of-tables to add/remove one, no
    frontend change needed. The same list also backs GBIFPublishForm's own
    "Publishing organization UUID" quick-fill dropdown (see each entry's
    own gbif_sandbox_organization_key/gbif_production_organization_key).
    The CLI's own 'trapper download'/'gbif register' never read this —
    neither has an equivalent organization-picking step of its own.

    Formerly CAMTRAPDP.organizations — see Settings's own migration."""
    organizations: list[Organization] = Field(
        default_factory=lambda: [
            Organization(
                title="Institute of Nature Conservation PAS", path="https://www.iop.krakow.pl/",
                gbif_sandbox_organization_key="f121e450-78ba-11d8-a19c-b8a03c50a862",
                gbif_production_organization_key="f121e450-78ba-11d8-a19c-b8a03c50a862",
            ),
            Organization(
                title="University of Huelva", path="https://www.uhu.es/",
                gbif_production_organization_key="37ec4ca1-fb42-4e11-939e-dafa4aa78e9e",
            ),
            Organization(
                title="University of South-Eastern Norway", path="https://www.usn.no/",
                gbif_production_organization_key="7f3b33d6-3864-4fd7-b6be-e4cbeba014b1",
            ),
            Organization(
                title="German Centre for Integrative Biodiversity Research", path="https://www.idiv.de/",
                gbif_sandbox_organization_key="b48dbd22-0452-4c31-a6b5-28f04e99d8cf",
                gbif_production_organization_key="b48dbd22-0452-4c31-a6b5-28f04e99d8cf",
            ),
            Organization(title="Spanish National Research Council", path="https://www.csic.es/"),
            Organization(title="Massachusetts Institute of Technology", path="https://www.mit.edu/"),
            Organization(title="Spanish Node of the Global Biodiversity Information Facility", path="https://www.gbif.es/"),
        ],
        description="Selectable publisher/rights holder organizations for the web wizard's metadata-editing step. (PRODUCT.organizations)",
    )


class Settings(BaseModel):
    TRAPPER: TrapperSettings = Field(default_factory=TrapperSettings)
    HFH: HFHSettings = Field(default_factory=HFHSettings)
    ZENODO: ZenodoSettings = Field(default_factory=ZenodoSettings)
    B2SHARE: B2ShareSettings = Field(default_factory=B2ShareSettings)
    GBIF: GBIFSettings = Field(default_factory=GBIFSettings)
    PRODUCT: ProductSettings = Field(default_factory=ProductSettings)

    @model_validator(mode="before")
    @classmethod
    def _migrate_camtrapdp_organizations(cls, data: Any) -> Any:
        """A settings.toml written before organizations became shared by
        every product type still has them under [[CAMTRAPDP.organizations]]
        — read from there (keeping any hand-edits) unless PRODUCT already
        has its own."""
        if not isinstance(data, dict) or "CAMTRAPDP" not in data:
            return data
        data = dict(data)
        legacy = data.pop("CAMTRAPDP") or {}
        if "PRODUCT" not in data and isinstance(legacy, dict) and "organizations" in legacy:
            data["PRODUCT"] = {"organizations": legacy["organizations"]}
        return data


def _ensure_config_file(config_file: Path) -> None:
    """Crea config_file con los valores por defecto si todavía no existe."""
    if config_file.exists():
        return
    config_file.parent.mkdir(parents=True, exist_ok=True)
    defaults = Settings().model_dump(mode="json")
    loaders.toml_loader.write(str(config_file), defaults, merge=False)


def load_settings(config_file: Path = DEFAULT_CONFIG_FILE) -> Settings:
    _ensure_config_file(config_file)
    dynaconf_settings = Dynaconf(settings_files=[str(config_file)], envvar_prefix="WILDINTEL_PUBLISHER")
    return Settings.model_validate(dynaconf_settings.to_dict())


def save_settings(new: Settings, config_file: Path = DEFAULT_CONFIG_FILE) -> None:
    """Sobrescribe config_file entero con new — ver el router de
    settings.toml (web app), que preserva los secretos que llegan en blanco
    antes de llamar a esto."""
    config_file.parent.mkdir(parents=True, exist_ok=True)
    loaders.toml_loader.write(str(config_file), new.model_dump(mode="json"), merge=False)


settings = load_settings()
