"""
AcuCalyx Federated Learning & Differential Privacy API Routes
Exposes privacy-preserving model training endpoints to attending urologists.
Guarantees patient data privacy isolation and zero transmission of raw PHI.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.auth import Doctor, get_current_doctor
from app.api.case_store import CaseStore
from src.acucalyx.ai.federated_learning import federated_coordinator, FEATURE_NAMES

logger = logging.getLogger("acucalyx.api.learning")
router = APIRouter(prefix="/api/learning", tags=["Privacy-Preserving Federated Learning"])


class LocalTrainingRequest(BaseModel):
    case_ids: Optional[List[str]] = Field(
        default=None,
        description="Optional list of specific patient case IDs to train on. If empty, uses all doctor's approved cases."
    )
    epochs: int = Field(default=1, ge=1, le=10)
    learning_rate: float = Field(default=0.05, ge=0.001, le=0.5)


@router.get("/overview")
def get_federated_learning_overview(
    current_doctor: Doctor = Depends(get_current_doctor)
) -> Dict[str, Any]:
    """
    Returns current federated learning status, differential privacy budget consumption,
    consensus model parameters, and recent privacy audit trail.
    """
    overview = federated_coordinator.get_overview()
    overview["current_doctor"] = {
        "doctor_id": current_doctor.doctor_id,
        "full_name": current_doctor.full_name,
        "role": current_doctor.role
    }
    return overview


@router.post("/train-local")
def train_local_privacy_model(
    req: LocalTrainingRequest,
    current_doctor: Doctor = Depends(get_current_doctor)
) -> Dict[str, Any]:
    """
    Initiates a local, patient-isolated training epoch on the current doctor's approved cases.
    Computes local loss and gradients, clips L2 norm (C=1.0), adds calibrated Gaussian noise,
    and submits only the differentially private gradient delta to the consensus model.
    No patient names, MRNs, CT images, or organ coordinates ever leave this machine.
    """
    case_store = CaseStore()
    doctor_cases = case_store.list_cases_for_doctor(current_doctor.doctor_id)
    
    # Extract feature representations from doctor's cases if available
    features_list: List[List[float]] = []
    labels_list: List[float] = []

    for c in doctor_cases:
        cid = c.get("case_id")
        if req.case_ids and cid not in req.case_ids:
            continue
        # Extract normalized planning parameters if available
        meta = c.get("meta", {})
        plan = meta.get("plan", {})
        candidates = plan.get("candidates", [])

        # If candidates not in case_meta.json, check artifacts/candidates.json
        if not candidates and cid:
            try:
                from app.api.case_store import get_case_dir
                cand_file = get_case_dir(cid) / "artifacts" / "candidates.json"
                if cand_file.is_file():
                    with open(cand_file, "r", encoding="utf-8") as f:
                        loaded_cands = json.load(f)
                        if isinstance(loaded_cands, list):
                            candidates = loaded_cands
            except Exception:
                pass
        
        if candidates and isinstance(candidates, list) and len(candidates) > 0:
            top_cand = candidates[0]
            # Normalize tract length (standard 50mm - 150mm)
            tl = float(top_cand.get("tract_length_mm", 95.0))
            tl_norm = min(1.0, max(0.0, (tl - 50.0) / 100.0))
            
            # Clearance margin (0 - 20mm)
            clr = float(top_cand.get("min_effective_clearance_mm", 8.0))
            clr_norm = min(1.0, max(0.0, clr / 20.0))
            
            # Stone coverage
            sc = float(top_cand.get("reachable_stone_fraction", 0.9))
            
            # Scope deflection (0 - 90 deg)
            defl = float(top_cand.get("required_scope_deflection_deg", 18.0))
            defl_norm = min(1.0, max(0.0, defl / 90.0))
            
            # Parenchyma depth (standard ~20mm)
            parench = float(top_cand.get("parenchyma_depth_mm", 18.0))
            parench_norm = min(1.0, max(0.0, parench / 40.0))
            
            # Rib safety
            rib = top_cand.get("access_rib_classification", "SUBCOSTAL")
            rib_score = 1.0 if rib == "SUBCOSTAL" else (0.7 if "11_12" in rib else 0.3)
            
            # Infundibular angle
            angle = float(top_cand.get("infundibular_pelvic_angle_deg", 75.0))
            angle_norm = min(1.0, max(0.0, angle / 120.0))
            
            features_list.append([
                tl_norm, clr_norm, sc, defl_norm, parench_norm, rib_score, angle_norm
            ])
            labels_list.append(1.0 if top_cand.get("is_pareto_optimal", True) else 0.5)

    result = federated_coordinator.train_local_model_step(
        doctor_id=current_doctor.doctor_id,
        doctor_name=current_doctor.full_name,
        case_features=features_list,
        case_labels=labels_list
    )
    return result


@router.get("/audit")
def get_privacy_audit_log(
    limit: int = Query(default=50, ge=1, le=200),
    current_doctor: Doctor = Depends(get_current_doctor)
) -> Dict[str, Any]:
    """
    Returns the complete cryptographic privacy audit log proving Differential Privacy compliance,
    gradient clipping thresholds, and zero-PHI transmission verifications.
    """
    audit_entries = federated_coordinator.audit_log[-limit:]
    return {
        "status": "success",
        "total_records": len(federated_coordinator.audit_log),
        "audit_trail": [a.model_dump() for a in reversed(audit_entries)]
    }
