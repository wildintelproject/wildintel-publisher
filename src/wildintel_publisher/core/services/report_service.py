"""The reports: a record of what a validation or a publication found and did — what the screen
shows of it and what can be downloaded to look at it in detail afterwards.

A report is a JSON file in config.reports_dir():

    {"id", "kind": "validation" | "publication", "title", "created_at", "source_dir", "product_type",
     "parameters", "checked",
     "checks": {check: {"label", "ok", "failed", "warnings"}},
     "totals": {"entries", "ok", "failed", "warnings"},
     "entries": [{"identifier", "check", "status": "ok" | "failed" | "warning", "message"}]}

An entry is one check of one thing: the dataset itself (validation) or one repository (publication).
A "warning" is a non-blocking problem worth knowing about. The same file gives the CSV."""
from __future__ import annotations

import csv
import io
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from wildintel_publisher.core import config

logger = logging.getLogger(__name__)

KINDS = ("validation", "publication")
DATASET = "(dataset)"
CSV_COLUMNS = ("identifier", "check", "status", "message")

_ID = re.compile(r"^\d{8}-\d{6}_(validation|publication)_[0-9A-Za-z_.-]*$")

LABELS = {
    "validation": "Dataset validation", "warnings": "Warnings",
    "publication": "Publication", "doi": "DOI",
}


class ReportError(ValueError):
    """A report that isn't there, or isn't a report's id — reported to the user."""


# ── building ─────────────────────────────────────────────────────────────────

def _build(kind: str, title: str, entries: list[dict], *, source_dir: str | None, product_type: str | None, parameters: dict) -> dict:
    checks: dict[str, dict] = {}
    for entry in entries:
        info = checks.setdefault(entry["check"], {"label": LABELS.get(entry["check"], entry["check"]), "ok": 0, "failed": 0, "warnings": 0})
        info[{"ok": "ok", "failed": "failed", "warning": "warnings"}[entry["status"]]] += 1
    count = lambda status: sum(1 for e in entries if e["status"] == status)
    return {
        "kind": kind, "title": title, "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_dir": source_dir, "product_type": product_type, "parameters": parameters, "checked": len({e["identifier"] for e in entries}),
        "checks": checks, "totals": {"entries": len(entries), "ok": count("ok"), "failed": count("failed"), "warnings": count("warning")},
        "entries": entries,
    }


def checks_report(source: Path, product_type: str, structure: list[dict], deep: list[dict]) -> dict:
    """The report of a YOLO dataset's checks: one entry per structural requirement, then — for each deeper check —
    one entry per image that failed it, or a single one saying it passed."""
    entries = [
        {"identifier": DATASET, "check": c["check"], "status": "ok" if c["ok"] else "failed", "message": c["message"]}
        for c in structure
    ]
    labels = {c["check"]: c["label"] for c in structure}
    for result in deep:
        labels[result["check"]] = result["label"]
        if result["ok"]:
            entries.append({"identifier": DATASET, "check": result["check"], "status": "ok", "message": result["message"]})
            continue
        entries += [
            {"identifier": item, "check": result["check"], "status": "failed", "message": result["failure_message"]}
            for item in result["failures"]
        ]
        if result["truncated"]:
            entries.append({
                "identifier": DATASET, "check": result["check"], "status": "failed",
                "message": f"{result['total']:,} failed in all; only the first {len(result['failures']):,} are listed.",
            })
    report = _build(
        "validation", f"Validation of {source.name}", entries, source_dir=str(source), product_type=product_type,
        parameters={"checks": [*labels]},
    )
    for check, info in report["checks"].items():
        info["label"] = labels.get(check, info["label"])
    return report


def validation_report(source: Path, product_type: str, *, error: str | None, warnings: Iterable[str] = ()) -> dict:
    """The report of validating the product at `source`: whether it passed (or why not), and its warnings."""
    entries = [{
        "identifier": DATASET, "check": "validation", "status": "failed" if error else "ok",
        "message": error or "The dataset is valid.",
    }]
    entries += [{"identifier": DATASET, "check": "warnings", "status": "warning", "message": w} for w in warnings]
    return _build("validation", f"Validation of {source.name}", entries, source_dir=str(source), product_type=product_type, parameters={})


def publication_report(
    title: str, repos: dict[str, dict], *, source_dir: str | None, product_type: str | None, dry_run: bool, error: str | None = None,
) -> dict:
    """The report of one publish run: for each repository where it ended up (or why it didn't). `repos` is the run's
    status per repository: {repo: {"status", "error", "repo_url", "doi", "pid"}}."""
    entries: list[dict] = []
    for repo, st in repos.items():
        where = st.get("repo_url") or st.get("pid")
        if st.get("status") == "done":
            entries.append({
                "identifier": repo, "check": "publication", "status": "ok",
                "message": ("Dry run — nothing was uploaded." if dry_run else f"Published{f' at {where}' if where else ''}."),
            })
            if st.get("doi"):
                entries.append({"identifier": repo, "check": "doi", "status": "ok", "message": st["doi"]})
        else:
            entries.append({
                "identifier": repo, "check": "publication", "status": "failed",
                "message": st.get("error") or error or f"Not finished ({st.get('status', 'unknown')}).",
            })
    return _build(
        "publication", title, entries, source_dir=source_dir, product_type=product_type,
        parameters={"dry_run": dry_run, "repositories": list(repos)},
    )


# ── keeping ──────────────────────────────────────────────────────────────────

def _slug(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z_.-]+", "-", text).strip("-")[:60] or "report"


def save(report: dict, root: Path | None = None) -> str:
    """Writes the report to the reports folder and returns its id — also set in the report."""
    root = root or config.reports_dir()
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = _slug(Path(report.get("source_dir") or "").name or report["kind"])
    report_id, n = f"{stamp}_{report['kind']}_{name}", 1
    while (root / f"{report_id}.json").exists():
        n += 1
        report_id = f"{stamp}_{report['kind']}_{name}-{n}"
    report["id"] = report_id
    tmp = root / f"{report_id}.json.tmp"
    tmp.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(root / f"{report_id}.json")
    return report_id


def try_save(report: dict) -> str | None:
    """save(), for a report that is a by-product of something else: failing to keep it (a read-only or missing folder...)
    is logged, never raised — it mustn't break the validation or the publication it comes from."""
    try:
        return save(report)
    except OSError as exc:
        logger.warning("Could not keep the %s report: %s", report.get("kind"), exc)
        return None


def _path(report_id: str, root: Path | None) -> Path:
    if not _ID.match(report_id):
        raise ReportError(f"'{report_id}' isn't a report.")
    path = (root or config.reports_dir()) / f"{report_id}.json"
    if not path.is_file():
        raise ReportError(f"There is no report '{report_id}'.")
    return path


def read(report_id: str, root: Path | None = None) -> dict:
    """Raises:
        ReportError: it isn't a report's id, or there is no such report.
    """
    return json.loads(_path(report_id, root).read_text(encoding="utf-8"))


def list_reports(root: Path | None = None) -> list[dict]:
    """What each report says of itself, newest first — without its entries."""
    root = root or config.reports_dir()
    out = []
    for path in sorted(root.glob("*.json"), reverse=True) if root.is_dir() else []:
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out.append({k: report.get(k) for k in ("id", "kind", "title", "created_at", "source_dir", "product_type", "checked", "totals")})
    return out


def delete(report_id: str, root: Path | None = None) -> None:
    _path(report_id, root).unlink()


def delete_older_than(days: int, root: Path | None = None) -> int:
    """Deletes the reports older than `days` days, and says how many."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    gone = 0
    for item in list_reports(root):
        try:
            if datetime.fromisoformat(item["created_at"]) < cutoff:
                delete(item["id"], root)
                gone += 1
        except (TypeError, ValueError, ReportError):
            continue
    return gone


def to_csv(report: dict) -> str:
    """One row per entry — the dataset or a repository, a check, its status and what it says."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(CSV_COLUMNS)
    for entry in report["entries"]:
        writer.writerow([entry[c] for c in CSV_COLUMNS])
    return out.getvalue()
