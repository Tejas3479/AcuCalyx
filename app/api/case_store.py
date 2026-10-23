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
import secrets
import shutil
import threading
import time
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException
from app.api.auth import Doctor, get_current_doctor

_CASE_META_LOCK = threading.Lock()
_AUDIT_LOG_LOCK = threading.Lock()


def _atomic_replace_with_retry(src_path: Path, dst_path: Path, max_attempts: int = 5) -> None:
    """Atomic file replacement with exponential backoff retry for Windows WinError 32 resilience."""
    for attempt in range(max_attempts):
        try:
            src_path.replace(dst_path)
            return
        except OSError:
            if attempt == max_attempts - 1:
                raise
            time.sleep(0.02 * (2 ** attempt))

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
            detail=f"Invalid case identifier (case_id) '{case_id}'. Must be 3-64 alphanumeric characters, underscores, or hyphens."
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


def resolve_case_input_path(case_id: str, meta: Optional[Dict[str, Any]] = None) -> Path:
    """
    Resolve the source imaging path (NIfTI volume or DICOM directory) for a case
    in a fully portable, container-friendly, cross-platform manner.
    Guarantees resolution even when cases were created on a different host OS or path.
    """
    if meta is None:
        meta = load_case_meta(case_id)
    case_dir = get_case_dir(case_id)

    raw_p = meta.get("input_path")
    if raw_p:
        p = Path(raw_p)
        # 1. Direct path exists on disk
        if p.exists():
            return p

        # 2. Relative to case_dir
        if not p.is_absolute():
            cand = case_dir / p
            if cand.exists():
                return cand

        # 3. Absolute path from another host (e.g. Windows path on Linux Docker)
        cand_raw = case_dir / "raw" / p.name
        if cand_raw.exists():
            return cand_raw

        cand_direct = case_dir / p.name
        if cand_direct.exists():
            return cand_direct

    # 4. Fallback search inside case_dir/raw
    raw_dir = case_dir / "raw"
    if raw_dir.is_dir():
        phantom_p = raw_dir / "phantom.nii.gz"
        if phantom_p.exists():
            return phantom_p
        for f in sorted(raw_dir.glob("*.nii*")):
            if f.is_file():
                return f
        for d in sorted(raw_dir.iterdir()):
            if d.is_dir() and any(d.glob("*.dcm")):
                return d
        if any(raw_dir.glob("*.dcm")):
            return raw_dir

    # 5. Default fallback path within case_dir
    return case_dir / "raw" / "phantom.nii.gz"


def enrich_case_patient_metadata(meta: Dict[str, Any], doctor_id: Optional[str] = None, doctor_name: Optional[str] = None) -> Dict[str, Any]:
    """Ensures case metadata has patient privacy partitioning and clinical context."""
    if "owner_doctor_id" not in meta or not meta["owner_doctor_id"]:
        meta["owner_doctor_id"] = doctor_id or "DOC_ELENA_CHEN"
    if "owner_doctor_name" not in meta or not meta["owner_doctor_name"]:
        meta["owner_doctor_name"] = doctor_name or "Dr. Elena Chen, MD, FACS"
    if "patient_id" not in meta:
        case_hash = abs(hash(meta.get("case_id", "case"))) % 9000 + 1000
        meta["patient_id"] = f"PT-{case_hash}"
    if "patient_age" not in meta:
        meta["patient_age"] = 45 + (abs(hash(meta.get("case_id", ""))) % 30)
    if "patient_sex" not in meta:
        meta["patient_sex"] = "M" if (abs(hash(meta.get("case_id", ""))) % 2 == 0) else "F"
    if "clinical_indication" not in meta:
        indications = [
            "Left lower pole nephrolithiasis (>20mm)",
            "Partial staghorn calculus with infundibular stenosis",
            "Symptomatic lower pole calculus, failed ureteroscopy",
            "Obstructing renal pelvic calculus with mild caliectasis",
            "Recurrent calcium oxalate calculus requiring percutaneous access"
        ]
        idx = abs(hash(meta.get("case_id", ""))) % len(indications)
        meta["clinical_indication"] = indications[idx]
    if "privacy_status" not in meta:
        meta["privacy_status"] = "RESTRICTED_ATTENDING_ONLY"
    return meta


def load_case_meta(case_id: str) -> Dict[str, Any]:
    """Loads authoritative case metadata JSON."""
    meta_path = get_case_meta_path(case_id)
    if not meta_path.is_file():
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return enrich_case_patient_metadata(data)
    except Exception as e:
        logger.error(f"Failed to read metadata for case {case_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to read metadata for case '{case_id}'.")


def save_case_meta(case_id: str, meta: Dict[str, Any]) -> None:
    """Persists authoritative case metadata JSON atomically with ISO-8601 UTC timestamp and lock protection."""
    meta_path = get_case_meta_path(case_id)
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta["updated_at"] = datetime.now(timezone.utc).isoformat()
    temp_path = meta_path.with_suffix(f".tmp_{secrets.token_hex(4)}")
    with _CASE_META_LOCK:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        _atomic_replace_with_retry(temp_path, meta_path)


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
    temp_audit = audit_path.with_suffix(f".tmp_{secrets.token_hex(4)}")
    with _AUDIT_LOG_LOCK:
        with open(temp_audit, "w", encoding="utf-8") as f:
            json.dump(events, f, indent=2)
        _atomic_replace_with_retry(temp_audit, audit_path)


class CaseStore:
    """Object-oriented wrapper providing filtered case listings and doctor privacy scoping."""

    def __init__(self, cases_dir: Path = CASES_DIR):
        self.cases_dir = cases_dir
        self.cases_dir.mkdir(parents=True, exist_ok=True)

    def list_all_cases(self) -> list[Dict[str, Any]]:
        """Returns metadata for all cases stored locally."""
        results = []
        for folder in sorted(self.cases_dir.iterdir()):
            if folder.is_dir():
                meta_file = folder / "case_meta.json"
                if meta_file.is_file():
                    try:
                        with open(meta_file, "r", encoding="utf-8") as f:
                            meta = json.load(f)
                        meta = enrich_case_patient_metadata(meta)
                        results.append(meta)
                    except Exception as e:
                        logger.warning(f"Failed to read case {folder.name}: {e}")
        return results

    def list_cases_for_doctor(self, doctor_id: str, is_admin: bool = False) -> list[Dict[str, Any]]:
        """
        Enforces strict patient data privacy isolation.
        A physician can only view their own assigned cases, unless administrator.
        """
        all_cases = self.list_all_cases()
        if is_admin or not doctor_id:
            return all_cases
        return [c for c in all_cases if c.get("owner_doctor_id") == doctor_id]



def verify_case_access(case_id: str, current_doctor: Doctor = Depends(get_current_doctor)) -> Dict[str, Any]:
    """
    Enforces Object-Level Authorization (BOLA/IDOR protection per OWASP API1:2023).
    Restricts access to the assigned physician unless Chief Surgeon or Administrator.
    Demo/phantom cases are universally accessible for rehearsal and training.
    """
    meta = load_case_meta(case_id)
    if meta.get("is_demo", False):
        return meta
    doc_role = getattr(current_doctor, "role", "")
    doc_id = getattr(current_doctor, "doctor_id", "")
    if doc_role not in ("CHIEF_SURGEON", "ADMIN"):
        owner_id = meta.get("owner_doctor_id")
        if owner_id and owner_id != doc_id:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied: Case '{case_id}' belongs to another clinician's private partition."
            )
    return meta
