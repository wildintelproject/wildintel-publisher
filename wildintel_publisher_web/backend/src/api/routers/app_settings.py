"""FastAPI router — the app's own settings.toml (see
wildintel_publisher.config), edited on the settings page. A secret field
(json_schema_extra={"secret": True} in config.py) never goes back to the
frontend as a value: the response replaces it with a has_<field> boolean,
and saving one left blank keeps what's already saved."""
from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from wildintel_publisher import logging_setup
from wildintel_publisher.config import (
    B2ShareSettings, CamtrapDPSettings, GBIFSettings, HFHSettings, ProductSettings, S3Settings, Settings, TrapperSettings,
    ZenodoSettings, load_settings, save_settings,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])

_SECTION_MODELS: dict[str, type[BaseModel]] = {
    "TRAPPER": TrapperSettings,
    "CAMTRAPDP": CamtrapDPSettings,
    "HFH": HFHSettings,
    "ZENODO": ZenodoSettings,
    "B2SHARE": B2ShareSettings,
    "GBIF": GBIFSettings,
    "S3": S3Settings,
    "PRODUCT": ProductSettings,
}


def _secret_fields(model: type[BaseModel]) -> list[str]:
    return [name for name, info in model.model_fields.items() if (info.json_schema_extra or {}).get("secret")]


def _public(settings: Settings) -> dict:
    data = settings.model_dump(mode="json")
    for section, model in _SECTION_MODELS.items():
        for field in _secret_fields(model):
            data[section][f"has_{field}"] = bool(data[section].pop(field))
    # Read-only: where the log goes, and whether the environment overrides
    # the level set here.
    data["GENERAL"]["log_file"] = str(logging_setup.log_file())
    data["GENERAL"]["log_level_override"] = logging_setup.env_override()
    return data


@router.get("")
def get_settings() -> dict:
    return _public(load_settings())


@router.put("")
def update_settings(new: Settings) -> dict:
    """Replaces every setting — except a secret field left blank, which
    keeps the saved one."""
    current = load_settings()
    for section, model in _SECTION_MODELS.items():
        new_section, current_section = getattr(new, section), getattr(current, section)
        for field in _secret_fields(model):
            if not getattr(new_section, field):
                setattr(new_section, field, getattr(current_section, field))
    save_settings(new)
    logging_setup.apply_level(logging_setup.effective_level())
    return _public(new)


@router.get("/log")
def download_log() -> FileResponse:
    """The current log file — to attach to a bug report."""
    path = logging_setup.log_file()
    if not path.is_file():
        raise HTTPException(404, "There's no log file yet.")
    return FileResponse(path, media_type="text/plain", filename=path.name)


@router.delete("/log")
def delete_log() -> dict:
    """Deletes the log file and its rotated copies — logging goes on, into a
    new one."""
    return {"deleted": logging_setup.clear_log()}
