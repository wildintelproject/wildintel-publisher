"""FastAPI router — the reports of validations and publications (see core.services.report_service)."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Response

from wildintel_publisher.core.services import report_service

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _read(report_id: str) -> dict:
    try:
        return report_service.read(report_id)
    except report_service.ReportError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("")
def list_reports() -> list[dict]:
    """What each report says of itself, newest first."""
    return report_service.list_reports()


@router.get("/{report_id}")
def get_report(report_id: str) -> dict:
    return _read(report_id)


@router.get("/{report_id}/download")
def download_report(report_id: str, format: str = "json") -> Response:
    """The report as a file: its own JSON, or a CSV with a row per entry."""
    report = _read(report_id)
    if format == "csv":
        body, media_type = report_service.to_csv(report), "text/csv; charset=utf-8"
    elif format == "json":
        body, media_type = json.dumps(report, indent=2, ensure_ascii=False), "application/json"
    else:
        raise HTTPException(400, "The format is json or csv.")
    return Response(body, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{report_id}.{format}"'})


@router.delete("/{report_id}")
def delete_report(report_id: str) -> dict:
    try:
        report_service.delete(report_id)
    except report_service.ReportError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"status": "ok"}
