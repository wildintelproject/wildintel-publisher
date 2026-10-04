"""FastAPI router — settings shared by every product type (Camtrap DP,
YOLO...), independent of how the product was obtained."""
from __future__ import annotations

from fastapi import APIRouter

from wildintel_publisher.core.config import load_settings

router = APIRouter(prefix="/api/product", tags=["product"])


@router.get("/organizations")
def organizations() -> list[dict]:
    """wildintel_publisher.web.settings.toml's own PRODUCT.organizations, offered as the options for
    BOTH the product's publisher and its rights holder in the wizard's
    metadata-editing step (Camtrap DP and YOLO alike), and as GBIF's
    "Publishing organization UUID" quick-fill — hand-edit settings.toml's
    own [[PRODUCT.organizations]] to add/remove one."""
    return [org.model_dump() for org in load_settings().PRODUCT.organizations]


@router.get("/authors")
def authors() -> list[dict]:
    """settings.toml's own PRODUCT.authors, offered in the wizard's
    metadata-editing step as quick-add options for a product's authors —
    hand-edit settings.toml's own [[PRODUCT.authors]] (or the settings
    page's Authors section) to add/remove one."""
    return [author.model_dump() for author in load_settings().PRODUCT.authors]
