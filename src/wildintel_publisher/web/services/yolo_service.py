"""YOLO (AI Dataset) sources for the web backend — thin wrapper around
wildintel_publisher.core.services.yolo_adapter's working-copy and metadata-editor
helpers. Same flow the wizard already follows for a local Camtrap DP source
(see camtrapdp_source_service.resolve_local_source): the user's own
directory is never modified — only a session-owned working copy of its
data.yaml is, while images/ and labels/ keep being read from the original."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from wildintel_publisher.core.services import product
from wildintel_publisher.core.services import yolo_adapter

from wildintel_publisher.web.services import session_store


def resolve_local_source(path: str, *, task_id: str | None = None) -> dict[str, Any]:
    """Creates (or, for the same task_id, refreshes) the session's working
    copy of `path` and validates it. Returns the same
    {status, workingDir, sourceDir, taskId, error} shape as
    camtrapdp_source_service.resolve_local_source — "taskId" always set, so
    a failed attempt can be retried against the same session."""
    task_id = task_id or session_store.new_task_id()
    output_dir = session_store.session_dir(task_id) / "source"
    fetch = {"source_type": "local", "params": {"path": path}, "output_dir": str(output_dir), "input_dir": None}
    try:
        working_dir = yolo_adapter.create_working_copy(Path(path), output_dir)
        yolo_adapter.check_dataset(working_dir)
        fetch["input_dir"] = str(working_dir)
        session_store.write_fetch_phase(
            task_id, product_type=product.YOLO, source_type="local", fetch=fetch, status="done", error=None,
        )
        return {"status": "valid", "workingDir": str(working_dir), "sourceDir": path, "taskId": task_id, "error": None}
    except RuntimeError as exc:
        session_store.write_fetch_phase(
            task_id, product_type=product.YOLO, source_type="local", fetch=fetch, status="error", error=str(exc),
        )
        return {"status": "invalid", "workingDir": None, "sourceDir": path, "taskId": task_id, "error": str(exc)}


def read_data_yaml_fields(input_dir: Path) -> dict[str, Any]:
    """The editable metadata keys (see yolo_adapter.YoloEditableMetadata),
    plus read-only facts about the dataset itself (classes, images per
    split) and its validation warnings, for the wizard's metadata step.

    Raises:
        RuntimeError: if the dataset doesn't validate.
    """
    warnings = yolo_adapter.check_dataset(input_dir)
    config = yolo_adapter.parse_data_yaml(input_dir)
    return {
        **yolo_adapter.read_editable_fields(input_dir),
        "class_names": config.names,
        "split_image_counts": yolo_adapter.split_image_counts(input_dir),
        "warnings": warnings,
    }


def update_data_yaml(input_dir: Path, fields: yolo_adapter.YoloEditableMetadata) -> None:
    """Writes the edited metadata keys into input_dir's data.yaml — meant
    for the working copy only (see resolve_local_source), and BEFORE
    generate-metadata, which re-reads them from there."""
    yolo_adapter.update_editable_fields(input_dir, fields)
