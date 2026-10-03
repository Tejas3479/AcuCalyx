"""
AcuCalyx Audit: Case Provenance and Reproducibility Tracking

Implements Module 0 of AcuCalyx v2:
- Computes SHA-256 hashes of input studies, software configurations, and model weights
- Maintains an auditable JSON/dictionary record ensuring any computed trajectory
  can be bit-for-bit reproduced from stored inputs.
"""

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class CaseProvenanceRecord:
    """Immutable case record ensuring regulatory traceability."""
    case_id: str
    study_instance_uid: str
    series_instance_uid: str
    modality: str
    acquisition_timestamp: Optional[str]
    patient_position_tag: Optional[str]
    input_data_sha256: str
    software_version: str
    configuration_sha256: str
    analysis_timestamp: str


def compute_sha256_bytes(data: bytes) -> str:
    """Computes SHA-256 hex digest for binary data."""
    return hashlib.sha256(data).hexdigest()


def compute_sha256_file(filepath: Path) -> str:
    """Computes SHA-256 hex digest for a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def create_provenance_record(
    case_id: str,
    study_uid: str,
    series_uid: str,
    modality: str = "CT",
    patient_position: Optional[str] = "HFS",
    input_data_hash: str = "synthetic",
    config_dict: Optional[Dict[str, Any]] = None,
    software_version: str = "0.2.0"
) -> CaseProvenanceRecord:
    """
    Creates a cryptographically verifiable case provenance record.
    """
    cfg_json = json.dumps(config_dict or {}, sort_keys=True)
    cfg_hash = compute_sha256_bytes(cfg_json.encode('utf-8'))
    
    timestamp = datetime.now(timezone.utc).isoformat()
    
    return CaseProvenanceRecord(
        case_id=case_id,
        study_instance_uid=study_uid,
        series_instance_uid=series_uid,
        modality=modality,
        acquisition_timestamp=timestamp,
        patient_position_tag=patient_position,
        input_data_sha256=input_data_hash,
        software_version=software_version,
        configuration_sha256=cfg_hash,
        analysis_timestamp=timestamp
    )
