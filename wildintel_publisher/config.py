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
from typing import Literal, Optional

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
    license_id: Optional[str] = Field(
        default="CC-BY-4.0",
        description=(
            "License identifier, e.g. CC-BY-4.0 — used by 'trapper download' to patch "
            "any scope (data/media) that Trapper has left as \"private\" in "
            "datapackage.json (known bug in Trapper's web license selector). "
            "(TRAPPER.license_id)"
        ),
    )
    license_name: Optional[str] = Field(
        default="Creative Commons Attribution 4.0 International",
        description="Full license name, for the same patch. (TRAPPER.license_name)",
    )
    license_url: Optional[str] = Field(
        default="https://creativecommons.org/licenses/by/4.0/",
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
        default="Camtrap DP camera-trap dataset, published via the WildINTEL project.",
        description="Default value of --description in 'trapper download'. (TRAPPER.description)",
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


class Settings(BaseModel):
    TRAPPER: TrapperSettings = Field(default_factory=TrapperSettings)
    HFH: HFHSettings = Field(default_factory=HFHSettings)
    ZENODO: ZenodoSettings = Field(default_factory=ZenodoSettings)
    B2SHARE: B2ShareSettings = Field(default_factory=B2ShareSettings)
    GBIF: GBIFSettings = Field(default_factory=GBIFSettings)


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


settings = load_settings()
