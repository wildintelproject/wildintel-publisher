"""FastAPI router — the app's own settings.toml (see
wildintel_publisher.config), edited on the settings page. A secret field
(json_schema_extra={"secret": True} in config.py) never goes back to the
frontend as a value: the response replaces it with a has_<field> boolean,
and saving one left blank keeps what's already saved."""
from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter

from wildintel_publisher.config import (
    B2ShareSettings, GBIFSettings, HFHSettings, ProductSettings, Settings, TrapperSettings, ZenodoSettings,
    load_settings, save_settings,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])

_SECTION_MODELS: dict[str, type[BaseModel]] = {
    "TRAPPER": TrapperSettings,
    "HFH": HFHSettings,
    "ZENODO": ZenodoSettings,
    "B2SHARE": B2ShareSettings,
    "GBIF": GBIFSettings,
    "PRODUCT": ProductSettings,
}


def _secret_fields(model: type[BaseModel]) -> list[str]:
    return [name for name, info in model.model_fields.items() if (info.json_schema_extra or {}).get("secret")]


def _public(settings: Settings) -> dict:
    data = settings.model_dump(mode="json")
    for section, model in _SECTION_MODELS.items():
        for field in _secret_fields(model):
            data[section][f"has_{field}"] = bool(data[section].pop(field))
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
    return _public(new)
