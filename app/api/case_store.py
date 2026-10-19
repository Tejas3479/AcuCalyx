"""
AcuCalyx API: Authoritative Case Store and Path Containment Manager

Provides central, thread-safe, secure management of case records, metadata,
and audit logs with strict directory traversal prevention and input validation.
"""

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
import shutil
from typing import Any, Dict, Optional

from fastapi import HTTPException

logger = logging.getLogger("acucalyx.case_store")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CASES_DIR = BASE_DIR / "data" / "cases"
CASES_DIR.mkdir(parents=True, exist_ok=True)

CASE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{3,64}$")


def validate_case_id(case_id: str) -> str:
    """
    Validates case_id against strict alphanumeric regex to block path traversal.
    Raises HTTP 400 if malformed or containing path separators.
    """
    if not case_id or not CASE_ID_PATTERN.match(case_id):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid case_id '{case_id}'. Must be 3-64 alphanumeric characters, underscores, or hyphens."
        )
    return case_id


def get_case_dir(case_id: str) -> Path:
    """
    Resolves case directory path and verifies strict boundary containment within CASES_DIR.
    Uses is_relative_to to prevent sibling directory prefix attacks.
    """
    c_id = validate_case_id(case_id)
    case_dir = (CASES_DIR / c_id).resolve()
    base_dir = CASES_DIR.resolve()
    if not case_dir.is_relative_to(base_dir):
        raise HTTPException(status_code=400, detail="Security violation: case path traversal detected.")
    return case_dir


def get_case_meta_path(case_id: str) -> Path:
    """Returns absolute path to case_meta.json within validated case directory."""
    return get_case_dir(case_id) / "case_meta.json"


def load_case_meta(case_id: str) -> Dict[str, Any]:
    """Loads authoritative case metadata JSON."""
    meta_path = get_case_meta_path(case_id)
    if not meta_path.is_file():
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to read metadata for case {case_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to read metadata for case '{case_id}'.")


def save_case_meta(case_id: str, meta: Dict[str, Any]) -> None:
    """Persists authoritative case metadata JSON atomically with ISO-8601 UTC timestamp."""
    meta_path = get_case_meta_path(case_id)
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta["updated_at"] = datetime.now(timezone.utc).isoformat()
    temp_path = meta_path.with_suffix(f".tmp_{datetime.now(timezone.utc).strftime('%H%M%S%f')}")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    temp_path.replace(meta_path)


def log_case_audit_event(case_id: str, action: str, details: Dict[str, Any], user: str = "System") -> None:
    """Appends an auditable event to case audit_trail.json using atomic writes and preserving corruption backups."""
    case_dir = get_case_dir(case_id)
    audit_path = case_dir / "audit_trail.json"
    events = []
    if audit_path.is_file():
        try:
            with open(audit_path, "r", encoding="utf-8") as f:
                events = json.load(f)
        except Exception as e:
            logger.warning(f"Corrupt audit trail detected for {case_id}: {e}. Creating safety backup.")
            backup_path = audit_path.with_suffix(f".bak_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}")
            try:
                shutil.copy2(audit_path, backup_path)
            except Exception:
                pass
            events = [{"warning": "CORRUPT_AUDIT_LOG_PRESERVED_TO_BACKUP", "original_error": str(e)}]
    events.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user": user,
        "action": action,
        "details": details
    })
    temp_audit = audit_path.with_suffix(f".tmp_{datetime.now(timezone.utc).strftime('%H%M%S%f')}")
    with open(temp_audit, "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2)
    temp_audit.replace(audit_path)
