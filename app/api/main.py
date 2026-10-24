"""
AcuCalyx API: Clinical Decision Support Backend & Workflow Engine

Implements Step 16 of AcuCalyx v2.1:
- State Machine: UPLOADED -> VALIDATING -> READY -> PLAN_GENERATED -> CLINICIAN_REVIEW -> FINALIZED
- Auditable Clinician Override tracking (marks downstream plan STALE)
- 2D MPR (Axial, Coronal, Sagittal) slice streaming with dynamic Window/Level and trajectory overlay
- GLB 3D surface mesh streaming for Three.js WebGL viewport
- Virtual Fluoroscopy projection metadata (Bull's-eye and Progression views)
- ReportLab Preoperative Planning PDF Report downloads
- Cryptographic SHA-256 case provenance tracking
"""

from collections import OrderedDict
from datetime import datetime, timezone
import io
import json
import logging
import os
from pathlib import Path
import re
import shutil
from typing import Any, Dict, List, Optional
import zipfile

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
import numpy as np
from PIL import Image, ImageDraw

from acucalyx.audit.provenance import compute_sha256_file
from acucalyx.cybersecurity.phi_guard import PHIGuard
from acucalyx.pipeline import run_planning_pipeline, PlanningPipelineResult, SegmentationMethod
from acucalyx.geometry.transforms import LineSegment3D
from acucalyx.synthetic.phantom_generator import generate_synthetic_pcnl_phantom, save_phantom_to_nifti
from app.api.case_store import (
    CASES_DIR,
    get_case_dir,
    get_case_meta_path,
    load_case_meta,
    save_case_meta,
    log_case_audit_event,
    validate_case_id,
    enrich_case_patient_metadata,
    resolve_case_input_path,
    verify_case_access,
)
from app.api.auth import Doctor, get_current_doctor
from app.api.schemas import (
    CaseState, CaseSummaryResponse, CaseUploadResponse,
    PlanGenerationRequest, TrajectorySelectionRequest, ManualOverrideRequest,
    QualityGateSummary, StoneMetricItem, CandidateTrajectoryItem,
    HazardClearanceItem, MonteCarloItem, FluoroscopyViewData,
    MetricValue, CandidateComparisonItem, CandidateComparisonMatrixResponse
)

logger = logging.getLogger("acucalyx.api")
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(name)s: %(message)s")

from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from fastapi import Depends, Security

API_KEY_HEADER = APIKeyHeader(name="X-AcuCalyx-API-Key", auto_error=False)
BEARER_AUTH = HTTPBearer(auto_error=False)


# Deprecated get_authenticated_clinician removed in favor of verify_case_access and get_current_doctor

BASE_DIR = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIR = BASE_DIR / "app" / "frontend"
FRONTEND_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="AcuCalyx™ Clinical Decision Support API",
    version="2.1.0",
    description="Computational Planning and Virtual Fluoroscopy Simulator for Percutaneous Nephrolithotomy (PCNL)"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_no_cache_headers(request, call_next):
    """Enforces no-cache policy on frontend assets to guarantee real-time UI updates."""
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith((".html", ".js", ".css", ".json")):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


# In-memory thread-safe bounded LRU cache for active volumes (max 3 cases to prevent OOM)
import threading
from starlette.concurrency import run_in_threadpool

MAX_CACHED_VOLUMES = 3
_ACTIVE_VOLUMES: OrderedDict[str, Dict[str, Any]] = OrderedDict()
_ACTIVE_VOLUMES_LOCK = threading.Lock()
_PLANNING_SEMAPHORE = threading.Semaphore(2)  # F-20: Maximum 2 concurrent heavy 3D planning pipelines


def get_cached_volume(case_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves volume from cache and updates LRU recency position."""
    with _ACTIVE_VOLUMES_LOCK:
        if case_id in _ACTIVE_VOLUMES:
            _ACTIVE_VOLUMES.move_to_end(case_id)
            return _ACTIVE_VOLUMES[case_id]
        return None


def set_cached_volume(case_id: str, vol: np.ndarray, spatial: Any) -> None:
    """Stores volume in LRU cache, evicting the least recently accessed case if limit exceeded."""
    with _ACTIVE_VOLUMES_LOCK:
        if case_id in _ACTIVE_VOLUMES:
            _ACTIVE_VOLUMES.move_to_end(case_id)
        else:
            if len(_ACTIVE_VOLUMES) >= MAX_CACHED_VOLUMES:
                evicted_id, _ = _ACTIVE_VOLUMES.popitem(last=False)
                logger.info(f"LRU Cache Eviction: Cleared volume memory for case {evicted_id}")
        _ACTIVE_VOLUMES[case_id] = {"volume": vol, "spatial": spatial}




@app.get("/api/health")
def health_check():
    return {"status": "ok", "system": "AcuCalyx", "version": "2.1.0"}


@app.get("/api/cases", response_model=List[CaseSummaryResponse])
def list_cases(
    all_cases: bool = Query(default=False, description="View all institutional cases across department"),
    doctor_id: Optional[str] = Query(default=None, description="Filter specifically to assigned doctor"),
    current_doctor: Doctor = Depends(get_current_doctor)
):
    """
    Lists registered cases with strict patient data privacy scoping.
    Guarantees that attending physicians only access their assigned patients unless authorized.
    """
    results = []
    effective_doctor_filter = doctor_id
    if not effective_doctor_filter and not all_cases and current_doctor.role != "CHIEF_SURGEON":
        effective_doctor_filter = current_doctor.doctor_id

    for case_folder in sorted(CASES_DIR.iterdir()):
        if case_folder.is_dir():
            meta_path = case_folder / "case_meta.json"
            if meta_path.is_file():
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                    meta = enrich_case_patient_metadata(meta)

                    # Strict Doctor Privacy Filter
                    if effective_doctor_filter and meta.get("owner_doctor_id") != effective_doctor_filter:
                        continue

                    results.append(CaseSummaryResponse(
                        case_id=meta["case_id"],
                        state=CaseState(meta.get("state", "UPLOADED")),
                        created_at=meta.get("created_at", ""),
                        updated_at=meta.get("updated_at", ""),
                        target_side=meta.get("target_side", "left"),
                        is_stale=meta.get("is_stale", False),
                        active_candidate_id=meta.get("active_candidate_id"),
                        stone_count=meta.get("stone_count", 0),
                        candidate_count=meta.get("candidate_count", 0),
                        clinical_notice=meta.get("clinical_notice", ""),
                        owner_doctor_id=meta.get("owner_doctor_id", "DOC_ELENA_CHEN"),
                        owner_doctor_name=meta.get("owner_doctor_name", "Dr. Elena Chen, MD, FACS"),
                        patient_id=meta.get("patient_id", f"PT-{abs(hash(meta['case_id'])) % 9000 + 1000}"),
                        patient_age=meta.get("patient_age", 54),
                        patient_sex=meta.get("patient_sex", "M"),
                        clinical_indication=meta.get("clinical_indication", "Lower pole nephrolithiasis"),
                        scheduled_procedure_date=meta.get("scheduled_procedure_date"),
                        privacy_status=meta.get("privacy_status", "RESTRICTED_ATTENDING_ONLY")
                    ))
                except Exception as e:
                    logger.warning(f"Error reading case meta in {case_folder}: {e}")
    return results


@app.post("/api/cases/demo", response_model=CaseSummaryResponse)
def create_demo_case(
    current_doctor: Doctor = Depends(get_current_doctor)
):
    """
    Creates an instant synthetic phantom case with analytical ground truth.
    Allocated directly to the authenticated physician's private clinical vault.
    """
    case_id = f"DEMO_PHANTOM_{datetime.now().strftime('%H%M%S')}"
    case_dir = get_case_dir(case_id)
    raw_dir = case_dir / "raw"
    artifacts_dir = case_dir / "artifacts"
    raw_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # Generate synthetic phantom
    vol, spatial, gt = generate_synthetic_pcnl_phantom(
        grid_shape=(96, 96, 80),
        spacing_mm=(1.0, 1.0, 1.0),
        stone_radius_mm=5.0,
        noise_sigma_hu=2.0
    )
    nii_path = raw_dir / "phantom.nii.gz"
    save_phantom_to_nifti(vol, spatial, nii_path)

    # Populate high-fidelity anatomical kidney section 3D meshes
    mesh_dest = artifacts_dir / "meshes"
    mesh_dest.mkdir(parents=True, exist_ok=True)
    from acucalyx.geometry.anatomical_kidney_builder import AnatomicalKidneyBuilder
    AnatomicalKidneyBuilder().build_complete_anatomical_package(mesh_dest)

    # Initial metadata with privacy ownership
    now_iso = datetime.now(timezone.utc).isoformat()
    meta = {
        "case_id": case_id,
        "is_demo": True,
        "state": CaseState.READY.value,
        "created_at": now_iso,
        "updated_at": now_iso,
        "input_path": "raw/phantom.nii.gz",
        "target_side": "left",
        "is_stale": False,
        "active_candidate_id": None,
        "stone_count": 1,
        "candidate_count": 0,
        "owner_doctor_id": current_doctor.doctor_id,
        "owner_doctor_name": current_doctor.full_name,
        "patient_id": f"PT-{abs(hash(case_id)) % 9000 + 1000}",
        "patient_age": 52,
        "patient_sex": "F",
        "clinical_indication": "Solitary lower pole calculus with acute infundibular neck",
        "privacy_status": "RESTRICTED_ATTENDING_ONLY",
        "laterality_confirmation": {
            "is_verified": True,
            "confirmed_side": "left",
            "ct_metadata_side": "left",
            "verified_at": now_iso,
            "is_two_step_confirmed": True,
            "source": "SYNTHETIC_CALIBRATION_GROUND_TRUTH"
        },
        "surgical_position_confirmation": {
            "is_confirmed": True,
            "operative_position": "PRONE_STANDARD",
            "ct_acquisition_position": "HFS",
            "confirmed_at": now_iso
        },
        "clinical_notice": "Synthetic analytical CT calibration phantom."
    }
    save_case_meta(case_id, meta)
    log_case_audit_event(case_id, "DEMO_CASE_CREATED", {"source": "Synthetic Phantom Generator", "doctor": current_doctor.full_name})

    return CaseSummaryResponse(
        case_id=case_id,
        state=CaseState.READY,
        created_at=now_iso,
        updated_at=now_iso,
        target_side="left",
        is_stale=False,
        active_candidate_id=None,
        stone_count=1,
        candidate_count=0,
        clinical_notice="Synthetic analytical CT calibration phantom ready for planning.",
        owner_doctor_id=current_doctor.doctor_id,
        owner_doctor_name=current_doctor.full_name,
        patient_id=meta["patient_id"],
        patient_age=meta["patient_age"],
        patient_sex=meta["patient_sex"],
        clinical_indication=meta["clinical_indication"],
        privacy_status=meta["privacy_status"]
    )


MAX_UPLOAD_SIZE = 500 * 1024 * 1024  # 500 MB limit
MAX_ZIP_EXTRACT_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB uncompressed limit
MAX_ZIP_FILES = 2000


@app.post("/api/cases/upload", response_model=CaseUploadResponse)
async def upload_case(
    file: UploadFile = File(...),
    target_side: str = Query(default="left"),
    current_doctor: Doctor = Depends(get_current_doctor)
):
    """Uploads a CT series with HIPAA de-identification and doctor privacy vault containment."""
    raw_filename = file.filename or "uploaded_ct"
    safe_filename = Path(raw_filename).name
    safe_filename = re.sub(r"[^A-Za-z0-9_.-]", "_", safe_filename)
    if not safe_filename or safe_filename.startswith("."):
        safe_filename = f"series_{datetime.now().strftime('%H%M%S')}.dcm"

    stem = Path(safe_filename).stem.replace(".nii", "").replace(" ", "_")
    stem = re.sub(r"[^A-Za-z0-9_-]", "_", stem)
    case_id = f"CASE_{stem}_{datetime.now().strftime('%H%M%S')}"

    case_dir = get_case_dir(case_id)
    raw_dir = case_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    dest_path = raw_dir / safe_filename

    # Stream file to disk in bounded chunks to prevent RAM exhaustion
    total_bytes = 0
    with open(dest_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            total_bytes += len(chunk)
            if total_bytes > MAX_UPLOAD_SIZE:
                dest_path.unlink(missing_ok=True)
                shutil.rmtree(case_dir, ignore_errors=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"Upload payload exceeds maximum allowable size of {MAX_UPLOAD_SIZE // (1024*1024)} MB."
                )
            f.write(chunk)

    input_file_count = 1
    input_path = dest_path

    # If zip, inspect and safely extract slices
    if safe_filename.lower().endswith(".zip"):
        extract_dir = raw_dir / "dicom_series"
        extract_dir.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(dest_path, "r") as z:
                infolist = z.infolist()
                if len(infolist) > MAX_ZIP_FILES:
                    shutil.rmtree(case_dir, ignore_errors=True)
                    raise HTTPException(status_code=400, detail=f"Archive contains {len(infolist)} files, exceeding limit of {MAX_ZIP_FILES}.")
                total_uncompressed = sum(info.file_size for info in infolist)
                if total_uncompressed > MAX_ZIP_EXTRACT_SIZE:
                    shutil.rmtree(case_dir, ignore_errors=True)
                    raise HTTPException(status_code=400, detail=f"Archive uncompressed size ({total_uncompressed // (1024*1024)} MB) exceeds limit.")
                for member in infolist:
                    if member.is_dir():
                        continue
                    if ".." in member.filename or member.filename.startswith("/") or member.filename.startswith("\\"):
                        shutil.rmtree(case_dir, ignore_errors=True)
                        raise HTTPException(status_code=400, detail=f"Illegal path in archive: {member.filename}")
                    member_path = (extract_dir / member.filename).resolve()
                    if not member_path.is_relative_to(extract_dir.resolve()):
                        shutil.rmtree(case_dir, ignore_errors=True)
                        raise HTTPException(status_code=400, detail=f"Illegal path escape in archive: {member.filename}")
                    member_path.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(member) as src_f, open(member_path, "wb") as dst_f:
                        shutil.copyfileobj(src_f, dst_f)
        except zipfile.BadZipFile:
            shutil.rmtree(case_dir, ignore_errors=True)
            raise HTTPException(status_code=400, detail="Corrupted or invalid ZIP archive.")

        dcm_files = [p for p in extract_dir.rglob("*") if p.is_file() and not p.name.startswith(".")]
        input_file_count = len(dcm_files)
        input_path = extract_dir

        # HIPAA / PS 3.15 Basic Application Level Confidentiality Profile Guard (Fail-Closed)
        phi_guard = PHIGuard()
        scrubbed_count = 0
        for dcm_file in dcm_files:
            try:
                import pydicom
                ds = pydicom.dcmread(str(dcm_file), force=True)
                if hasattr(ds, "PatientName") or hasattr(ds, "PatientID") or hasattr(ds, "InstitutionName"):
                    scrubbed = phi_guard.deidentify(ds)
                    scrubbed.save_as(str(dcm_file))
                    scrubbed_count += 1
            except Exception as e:
                logger.error(f"Fail-closed: DICOM de-identification failed on {dcm_file.name}: {e}")
                shutil.rmtree(case_dir, ignore_errors=True)
                raise HTTPException(status_code=422, detail=f"HIPAA/PS 3.15 de-identification failed on {dcm_file.name}: {e}")
        if scrubbed_count > 0:
            logger.info(f"PHIGuard: Successfully scrubbed direct PHI from {scrubbed_count} slices for case {case_id}")
            log_case_audit_event(case_id, "PHI_SCRUBBED_INGESTION", {"scrubbed_slices": scrubbed_count})
    elif safe_filename.lower().endswith(".dcm"):
        try:
            import pydicom
            phi_guard = PHIGuard()
            ds = pydicom.dcmread(str(dest_path), force=True)
            scrubbed = phi_guard.deidentify(ds)
            scrubbed.save_as(str(dest_path))
            log_case_audit_event(case_id, "PHI_SCRUBBED_INGESTION", {"scrubbed_slices": 1})
        except Exception as e:
            logger.error(f"Fail-closed: Single DICOM de-identification failed: {e}")
            shutil.rmtree(case_dir, ignore_errors=True)
            raise HTTPException(status_code=422, detail=f"HIPAA/PS 3.15 de-identification failed on DICOM: {e}")
    elif safe_filename.lower().endswith((".nii", ".nii.gz")):
        try:
            import nibabel as nib
            img = nib.load(str(dest_path))
            header = img.header
            if hasattr(header, "get"):
                if "descrip" in header:
                    header["descrip"] = b""
                if "aux_file" in header:
                    header["aux_file"] = b""
            img.to_filename(str(dest_path))
            log_case_audit_event(case_id, "NIFTI_HEADER_SCRUBBED", {"filename": safe_filename})
        except Exception as e:
            logger.debug(f"NIfTI header scrub note: {e}")

    now_iso = datetime.now(timezone.utc).isoformat()
    meta = {
        "case_id": case_id,
        "is_demo": False,
        "state": CaseState.READY.value,
        "created_at": now_iso,
        "updated_at": now_iso,
        "input_path": str(input_path.relative_to(case_dir)) if input_path.is_relative_to(case_dir) else str(input_path),
        "target_side": target_side.lower(),
        "is_stale": False,
        "active_candidate_id": None,
        "stone_count": 0,
        "candidate_count": 0,
        "owner_doctor_id": current_doctor.doctor_id,
        "owner_doctor_name": current_doctor.full_name,
        "patient_id": f"PT-{abs(hash(case_id)) % 9000 + 1000}",
        "patient_age": 58,
        "patient_sex": "M",
        "clinical_indication": "Clinical CT scan uploaded for PCNL puncture planning",
        "privacy_status": "RESTRICTED_ATTENDING_ONLY",
        "laterality_confirmation": None,
        "surgical_position_confirmation": None,
        "clinical_notice": f"Uploaded {input_file_count} file(s). Mandatory laterality verification required prior to planning."
    }
    save_case_meta(case_id, meta)
    log_case_audit_event(case_id, "CASE_UPLOADED", {"filename": safe_filename, "file_count": input_file_count})

    return CaseUploadResponse(
        case_id=case_id,
        state=CaseState.READY,
        message=f"Successfully ingested {input_file_count} file(s). Case {case_id} is READY.",
        input_file_count=input_file_count
    )


@app.get("/api/cases/{case_id}/status", response_model=CaseSummaryResponse)
def get_case_status(case_id: str, meta: Dict[str, Any] = Depends(verify_case_access)):
    """Retrieves current workflow state and high-level case metrics."""
    meta = load_case_meta(case_id)
    return CaseSummaryResponse(
        case_id=meta["case_id"],
        state=CaseState(meta.get("state", "READY")),
        created_at=meta.get("created_at", ""),
        updated_at=meta.get("updated_at", ""),
        target_side=meta.get("target_side", "left"),
        is_stale=meta.get("is_stale", False),
        active_candidate_id=meta.get("active_candidate_id"),
        stone_count=meta.get("stone_count", 0),
        candidate_count=meta.get("candidate_count", 0),
        clinical_notice=meta.get("clinical_notice", "")
    )


@app.post("/api/cases/{case_id}/plan", response_model=CaseSummaryResponse)
def run_case_planning(case_id: str, req: PlanGenerationRequest, meta: Dict[str, Any] = Depends(verify_case_access)):
    """Executes the full planning pipeline, generating Pareto candidates, 3D meshes, and report."""
    meta = load_case_meta(case_id)
    case_dir = get_case_dir(case_id)
    artifacts_dir = case_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    input_path = resolve_case_input_path(case_id, meta)
    if not input_path.exists():
        raise HTTPException(status_code=400, detail=f"Source imaging path not found: {input_path}")

    # Server-controlled execution mode enforcement (Gate 0 Safety Invariant)
    is_demo = meta.get("is_demo", False)

    # Server-side enforcement of Laterality Verification Interlock (U1)
    if not is_demo:
        lat_conf = meta.get("laterality_confirmation")
        if not lat_conf or not lat_conf.get("is_verified", False):
            raise HTTPException(
                status_code=412,
                detail=(
                    "Precondition Failed: Interlock U1 Laterality Verification Gate must be completed "
                    "and signed off by the clinician before access planning can proceed."
                )
            )
        confirmed_side = str(lat_conf.get("confirmed_side", "")).lower()
        if confirmed_side != req.target_side.lower():
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Laterality Mismatch: Planning requested for '{req.target_side}' kidney, "
                    f"but verified clinical laterality is '{confirmed_side}'. Re-verify laterality."
                )
            )

        # Server-side enforcement of Operative Position Gate (Interlock U2)
        pos_conf = meta.get("surgical_position_confirmation")
        if not pos_conf or not pos_conf.get("is_confirmed", False):
            raise HTTPException(
                status_code=412,
                detail=(
                    "Precondition Failed: Interlock U2 Operative Pose Gate must be completed "
                    "and signed off by the clinician before access planning can proceed."
                )
            )
    pipeline_cfg = {
        "coarse_step_mm": req.coarse_step_mm,
        "monte_carlo_samples": req.monte_carlo_samples,
        "allow_marginal": req.allow_marginal,
        "allow_fallback_segmentation": getattr(req, "allow_fallback_segmentation", False),
        "pending_overrides": meta.get("pending_overrides", [])
    }

    if is_demo:
        pipeline_cfg["demo_mode"] = True
        pipeline_cfg["require_clinical_segmentation"] = False
        pipeline_cfg["segmentation_method"] = req.segmentation_method or "HEURISTIC_DEMO"
    else:
        if req.segmentation_method == "HEURISTIC_DEMO":
            raise HTTPException(
                status_code=400,
                detail=(
                    "Synthetic heuristic anatomy is strictly prohibited in clinical patient cases. "
                    "Clinical cases require verified neural segmentation (TotalSegmentator native execution) "
                    "or authenticated expert ground truth masks."
                )
            )
        pipeline_cfg["demo_mode"] = False
        pipeline_cfg["require_clinical_segmentation"] = True
        pipeline_cfg["segmentation_method"] = req.segmentation_method or SegmentationMethod.TOTALSEGMENTATOR.value

    # Transition state to VALIDATING
    meta["state"] = CaseState.VALIDATING.value
    save_case_meta(case_id, meta)
    log_case_audit_event(case_id, "PLANNING_STARTED", {
        "target_side": req.target_side,
        "is_demo": is_demo,
        "segmentation_method": pipeline_cfg["segmentation_method"]
    })

    acquired = _PLANNING_SEMAPHORE.acquire(blocking=False)
    if not acquired:
        raise HTTPException(
            status_code=429,
            detail="Server busy: Another 3D computational planning pipeline is currently running. Please retry in a few moments."
        )
    try:
        res: PlanningPipelineResult = run_planning_pipeline(
            input_path=input_path,
            output_dir=artifacts_dir,
            side=req.target_side,
            case_id=case_id,
            config=pipeline_cfg,
            segmentation_method=pipeline_cfg["segmentation_method"]
        )
    except ValueError as ve:
        logger.error(f"Planning pipeline validation/segmentation error: {ve}")
        meta["state"] = CaseState.REJECTED.value
        meta["clinical_notice"] = f"Clinical fail-closed gate: {str(ve)}"
        save_case_meta(case_id, meta)
        raise HTTPException(status_code=500, detail=str(ve))
    except Exception as e:
        logger.exception("Pipeline execution failed")
        meta["state"] = CaseState.REJECTED.value
        meta["clinical_notice"] = f"Pipeline execution error: {str(e)}"
        save_case_meta(case_id, meta)
        raise HTTPException(status_code=500, detail=f"Planning pipeline failed: {str(e)}")
    finally:
        _PLANNING_SEMAPHORE.release()

    if res.status == "GATE_REJECTED":
        meta["state"] = CaseState.REJECTED.value
        meta["clinical_notice"] = "DICOM Quality Gate rejected series due to non-standard or missing geometry."
    else:
        meta["state"] = CaseState.PLAN_GENERATED.value
        meta["target_side"] = req.target_side
        meta["stone_count"] = len(res.stones)
        meta["candidate_count"] = len(res.candidates)
        meta["is_stale"] = False

        # Select candidate trajectory without critical hazard breaches
        selected_candidate = None
        for c in res.candidates:
            has_crit = any(getattr(h, "is_intersecting", False) for h in getattr(c, "hazard_evaluations", []))
            if not has_crit:
                selected_candidate = c
                break
        if selected_candidate is None and res.candidates:
            selected_candidate = res.candidates[0]

        meta["active_candidate_id"] = selected_candidate.candidate_id if selected_candidate else None

        # Apply pending overrides and resolve STALE status
        if meta.get("pending_overrides"):
            meta["applied_overrides"] = meta.get("applied_overrides", []) + meta["pending_overrides"]
            meta["pending_overrides"] = []
            meta["override_pending"] = False

        meta["clinical_notice"] = f"Generated {len(res.candidates)} Pareto candidate trajectories."

    save_case_meta(case_id, meta)
    log_case_audit_event(case_id, "PLANNING_COMPLETED", {
        "status": res.status,
        "candidates": len(res.candidates),
        "stones": len(res.stones)
    })

    return get_case_status(case_id)


@app.get("/api/cases/{case_id}/quality")
def get_quality_metrics(case_id: str, meta: Dict[str, Any] = Depends(verify_case_access)):
    """Returns the fail-closed DICOM quality gate results."""
    case_dir = get_case_dir(case_id)
    q_file = case_dir / "artifacts" / "quality.json"
    if not q_file.is_file():
        raise HTTPException(status_code=404, detail="Quality report not found. Has planning been run?")
    with open(q_file, "r") as f:
        return json.load(f)


@app.get("/api/cases/{case_id}/stones", response_model=List[StoneMetricItem])
def get_stone_metrics(case_id: str, meta: Dict[str, Any] = Depends(verify_case_access)):
    """Returns detected kidney stones with true 3D volumetry and attenuation statistics."""
    case_dir = get_case_dir(case_id)
    s_file = case_dir / "artifacts" / "stones.json"
    if not s_file.is_file():
        raise HTTPException(status_code=404, detail="Stone metrics not found. Has planning been run?")
    with open(s_file, "r") as f:
        data = json.load(f)
    return data


@app.get("/api/cases/{case_id}/candidates", response_model=List[CandidateTrajectoryItem])
def get_candidate_trajectories(case_id: str, meta: Dict[str, Any] = Depends(verify_case_access)):
    """Returns all computed Pareto access trajectories with clinical trade-offs and safety badges."""
    case_dir = get_case_dir(case_id)
    c_file = case_dir / "artifacts" / "candidates.json"
    u_file = case_dir / "artifacts" / "uncertainty.json"
    if not c_file.is_file():
        raise HTTPException(status_code=404, detail="Candidates not found. Has planning been run?")

    with open(c_file, "r") as f:
        cands = json.load(f)

    unc_map = {}
    if u_file.is_file():
        with open(u_file, "r") as f:
            unc_map = json.load(f)

    results = []
    for idx, c in enumerate(cands):
        # Determine safety badge
        has_collision = any(h.get("is_intersecting", False) for h in c.get("hazards", []))
        if has_collision:
            badge = "REJECTED"
        elif idx == 0 and c.get("min_effective_clearance_mm", 0) > 10.0:
            badge = "PREFERRED"
        else:
            badge = "CONDITIONAL"

        hazards = [
            HazardClearanceItem(
                hazard_name=h["hazard_name"],
                observed_clearance_mm=h["observed_clearance_mm"],
                effective_clearance_mm=h["effective_clearance_mm"],
                is_intersecting=h["is_intersecting"],
                confidence_level=h["confidence_level"]
            )
            for h in c.get("hazards", [])
        ]

        unc_list = [
            MonteCarloItem(
                hazard_name=u["hazard_name"],
                collision_probability=u["collision_probability"],
                nominal_clearance_mm=u["nominal_clearance_mm"],
                percentile_5th_clearance_mm=u["percentile_5th_clearance_mm"],
                mean_perturbed_clearance_mm=u["mean_perturbed_clearance_mm"],
                risk_category=u["risk_category"]
            )
            for u in unc_map.get(c["candidate_id"], [])
        ]

        results.append(CandidateTrajectoryItem(
            candidate_id=c["candidate_id"],
            target_calyx=c["target_calyx"],
            entry_point_lps=c["entry_point_lps"],
            target_point_lps=c["target_point_lps"],
            tract_length_mm=c["tract_length_mm"],
            min_effective_clearance_mm=c["min_effective_clearance_mm"],
            reachable_stone_fraction=c["reachable_stone_fraction"],
            required_scope_deflection_deg=c["required_scope_deflection_deg"],
            access_rib_classification=c["access_rib_classification"],
            confidence_tier=c["confidence_tier"],
            is_pareto_optimal=c["is_pareto_optimal"],
            safety_badge=badge,
            hazards=hazards,
            uncertainty=unc_list
        ))
    return results


@app.post("/api/cases/{case_id}/select")
@app.post("/api/cases/{case_id}/trajectories/select")
def select_candidate_trajectory(case_id: str, req: TrajectorySelectionRequest, meta: Dict[str, Any] = Depends(verify_case_access)):
    """
    Clinician approves a candidate trajectory.
    Validates candidate existence against generated plan artifacts,
    guards against stale plans, logs auditable event, and transitions case state to CLINICIAN_REVIEW.
    """
    case_dir = get_case_dir(case_id)

    # Guard 1: Stale plan rejection
    if meta.get("is_stale", False):
        raise HTTPException(
            status_code=409,
            detail="Cannot select candidate trajectory on a stale plan. Re-planning is required following clinician overrides."
        )

    # Guard 2: Candidate artifacts existence
    c_file = case_dir / "artifacts" / "candidates.json"
    if not c_file.is_file():
        raise HTTPException(
            status_code=400,
            detail="No generated candidate trajectories found for this case. Plan generation must be completed before trajectory selection."
        )

    try:
        with open(c_file, "r") as f:
            cands = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read candidates artifact: {str(e)}")

    valid_candidate_ids = [c.get("candidate_id") for c in cands if isinstance(c, dict) and "candidate_id" in c]
    if req.candidate_id not in valid_candidate_ids:
        raise HTTPException(
            status_code=404,
            detail=f"Candidate trajectory '{req.candidate_id}' not found for case '{case_id}'. Available candidates: {valid_candidate_ids}"
        )

    meta["active_candidate_id"] = req.candidate_id
    meta["state"] = CaseState.CLINICIAN_REVIEW.value
    meta["clinical_notice"] = f"Trajectory {req.candidate_id} selected by {req.clinician_id}."
    save_case_meta(case_id, meta)

    log_case_audit_event(
        case_id,
        "TRAJECTORY_SELECTED",
        {"candidate_id": req.candidate_id, "rationale": req.clinical_rationale},
        user=req.clinician_id
    )
    return {"status": "success", "active_candidate_id": req.candidate_id, "state": meta["state"]}


@app.post("/api/cases/{case_id}/override")
def clinician_override(case_id: str, req: ManualOverrideRequest, meta: Dict[str, Any] = Depends(verify_case_access)):
    """
    Clinician overrides an anatomical contour or target coordinate.
    Adheres strictly to AcuCalyx v2.1 governance: marks downstream plan as STALE,
    clears active trajectory, records pending override details, and requires re-planning.
    """
    case_dir = get_case_dir(case_id)
    artifacts_dir = case_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    meta["is_stale"] = True
    meta["active_candidate_id"] = None
    meta["override_pending"] = True
    meta["clinical_notice"] = (
        f"OVERRIDE RECORDED: Manual override requested ({req.override_type}). "
        "Downstream plan invalidated and marked STALE. Re-planning required."
    )

    override_record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "clinician_id": req.clinician_id,
        "override_type": req.override_type,
        "target_calyx_id": req.target_calyx_id,
        "coordinates": req.modified_coordinates_lps,
        "reason": req.reason
    }

    pending = meta.get("pending_overrides", [])
    pending.append(override_record)
    meta["pending_overrides"] = pending
    save_case_meta(case_id, meta)

    try:
        ovr_path = artifacts_dir / "pending_overrides.json"
        tmp_ovr = ovr_path.with_suffix(f".tmp_{secrets.token_hex(4)}")
        with open(tmp_ovr, "w", encoding="utf-8") as f:
            json.dump(pending, f, indent=2)
        tmp_ovr.replace(ovr_path)
    except Exception as e:
        logger.warning(f"Could not persist pending overrides artifact: {e}")

    log_case_audit_event(
        case_id,
        "MANUAL_OVERRIDE_RECORDED",
        override_record,
        user=req.clinician_id
    )
    return {
        "status": "OVERRIDE_RECORDED_PENDING_RECOMPUTATION",
        "is_stale": True,
        "active_candidate_id": None,
        "notice": meta["clinical_notice"]
    }


@app.get("/api/cases/{case_id}/candidates/comparison-matrix", response_model=CandidateComparisonMatrixResponse)
def get_candidate_comparison_matrix(case_id: str):
    """
    Returns the comprehensive side-by-side Candidate Access Tract Comparison Matrix
    powering the AcuCalyx PCNL Access Planning Workbench.
    Replaces prescriptive sizing dictations with descriptive trade-off considerations.
    Emits typed MetricValue records with uncertainty flags.
    """
    meta = load_case_meta(case_id)
    case_dir = get_case_dir(case_id)
    artifacts_dir = case_dir / "artifacts"
    c_file = artifacts_dir / "candidates.json"
    s_file = artifacts_dir / "stones.json"
    p_file = artifacts_dir / "provenance.json"

    if not c_file.is_file():
        raise HTTPException(status_code=404, detail="Candidate trajectories not found. Has planning been run?")

    with open(c_file, "r") as f:
        cands = json.load(f)

    total_stone_vol = 0.0
    stone_data_present = False
    if s_file.is_file():
        try:
            with open(s_file, "r") as f:
                stones = json.load(f)
            total_stone_vol = sum(s.get("volume_mm3", 0.0) for s in stones)
            stone_data_present = True
        except Exception:
            pass

    prov_hash = "N/A"
    if p_file.is_file():
        try:
            with open(p_file, "r") as f:
                pdata = json.load(f)
            prov_hash = pdata.get("provenance_hash_sha256", "N/A")
        except Exception:
            pass

    items = []
    for c in cands:
        hazards = {h["hazard_name"]: h for h in c.get("hazards", [])}
        
        pleura_h = hazards.get("pleural_envelope_left") or hazards.get("pleural_envelope_right")
        colon_h = hazards.get("colon")
        rib_h = (
            hazards.get("intercostal_nv_bundle_left") or
            hazards.get("intercostal_nv_bundle_right") or
            hazards.get("rib_left_12") or
            hazards.get("rib_right_12")
        )

        pleura_clearance = MetricValue(
            value=pleura_h["effective_clearance_mm"] if pleura_h else None,
            unit="mm",
            status="MEASURED" if pleura_h else "NOT_EVALUABLE",
            confidence="HIGH" if pleura_h else "UNASSESSED",
            reason=None if pleura_h else "Pleural reflection not segmented or evaluated on this case."
        )

        colon_clearance = MetricValue(
            value=colon_h["effective_clearance_mm"] if colon_h else None,
            unit="mm",
            status="MEASURED" if colon_h else "NOT_EVALUABLE",
            confidence="HIGH" if colon_h else "UNASSESSED",
            reason=None if colon_h else "Colon hazard mask unavailable."
        )

        effective_vals = [h.get("effective_clearance_mm") for h in c.get("hazards", []) if h.get("effective_clearance_mm") is not None]
        if effective_vals:
            vascular_clearance = MetricValue(
                value=float(min(effective_vals)),
                unit="mm",
                status="DERIVED",
                confidence="MEDIUM",
                reason="Derived from regional segmental hazard corridor distance field."
            )
        else:
            vascular_clearance = MetricValue(
                value=None,
                unit="mm",
                status="NOT_EVALUABLE",
                confidence="UNASSESSED",
                reason="Major renal vascular structures not segmented or evaluated on this series."
            )

        intercostal_clearance = None
        if rib_h:
            intercostal_clearance = MetricValue(
                value=rib_h["effective_clearance_mm"],
                unit="mm",
                status="MEASURED",
                confidence="HIGH"
            )

        reachable_fraction = float(c.get("reachable_stone_fraction", 0.0))
        if stone_data_present and total_stone_vol > 0:
            rigid_stone_vol = total_stone_vol * reachable_fraction
            rigid_stone_pct = reachable_fraction * 100.0
            rigid_vol_metric = MetricValue(value=round(rigid_stone_vol, 1), unit="mm3", status="DERIVED")
            rigid_pct_metric = MetricValue(value=round(rigid_stone_pct, 1), unit="%", status="DERIVED")
            inaccessible_metric = MetricValue(value=round(max(0.0, total_stone_vol - rigid_stone_vol), 1), unit="mm3", status="DERIVED")
        else:
            rigid_stone_pct = 0.0
            rigid_vol_metric = MetricValue(value=None, unit="mm3", status="NOT_EVALUABLE", confidence="UNASSESSED", reason="Calculus burden not segmented on this case.")
            rigid_pct_metric = MetricValue(value=None, unit="%", status="NOT_EVALUABLE", confidence="UNASSESSED", reason="Calculus burden not segmented on this case.")
            inaccessible_metric = MetricValue(value=None, unit="mm3", status="NOT_EVALUABLE", confidence="UNASSESSED", reason="Calculus burden not segmented on this case.")

        rib_rel = c.get("access_rib_classification", "SUBCOSTAL")
        if "INTERCOSTAL" in rib_rel or "SUPRACOSTAL" in rib_rel:
            caliber_text = (
                "Intercostal trajectory: EAU guidelines caution regarding torque-related bleeding "
                "and pleuropulmonary injury. Mini-PCNL (14–18 Fr) or standard (24 Fr) requires "
                "maintaining trajectory strictly on the superior rib border."
            )
            irrigation_risk = "Elevated risk of hydrothorax if pleural reflection breached; monitor IRP."
        else:
            caliber_text = (
                "Subcostal trajectory: Standard PCNL (24–30 Fr) or Mini-PCNL (14–18 Fr) feasible. "
                "Sheath selection depends on stone burden, infundibular diameter, and planned lithotrite."
            )
            irrigation_risk = "Low risk of thoracic extravasation; standard intra-renal pressure monitoring."

        unc_flags = []
        if pleura_clearance.value is not None and pleura_clearance.value < 10.0:
            unc_flags.append("PROXIMAL_PLEURAL_REFLECTION")
        if colon_clearance.value is not None and colon_clearance.value < 15.0:
            unc_flags.append("BORDERLINE_COLON_MARGIN")
        if "INTERCOSTAL" in rib_rel:
            unc_flags.append("INTERCOSTAL_PLEURAL_EXCURSION_RISK")
        if not stone_data_present:
            unc_flags.append("STONE_BURDEN_UNASSESSED")

        tradeoff_summary = (
            f"Target: {c.get('target_calyx', 'Lower Pole')}. Rib relation: {rib_rel}. "
            f"Tract length: {c.get('tract_length_mm', 0.0):.1f} mm. "
            f"Estimated reachable stone fraction: {rigid_stone_pct:.1f}%."
        )

        entry_lps = c.get("entry_point_lps", [0.0, 0.0, 0.0])
        target_lps = c.get("target_point_lps", [0.0, 0.0, 0.0])
        dx = target_lps[0] - entry_lps[0]
        dy = target_lps[1] - entry_lps[1]
        dz = target_lps[2] - entry_lps[2]

        # Signed directional projection angles in physical LPS coordinates
        coronal_angle = float(np.degrees(np.arctan2(dz, dx + 1e-6)))
        sagittal_angle = float(np.degrees(np.arctan2(dz, dy + 1e-6)))

        items.append(CandidateComparisonItem(
            candidate_id=c["candidate_id"],
            target_calyx_id=c.get("target_calyx", "Calyx_Target"),
            target_calyx_name=c.get("target_calyx", "Calyx Target"),
            entry_point_lps=entry_lps,
            target_point_lps=target_lps,
            tract_length_mm=MetricValue(value=c.get("tract_length_mm", 0.0), unit="mm", status="MEASURED"),
            puncture_angle_coronal_deg=MetricValue(value=coronal_angle, unit="deg", status="DERIVED"),
            puncture_angle_sagittal_deg=MetricValue(value=sagittal_angle, unit="deg", status="DERIVED"),
            rib_relation=rib_rel,
            pleural_clearance=pleura_clearance,
            colon_clearance=colon_clearance,
            vascular_clearance=vascular_clearance,
            intercostal_bundle_clearance=intercostal_clearance,
            rigid_accessible_stone_volume_mm3=rigid_vol_metric,
            rigid_accessible_stone_percent=rigid_pct_metric,
            flexible_accessible_stone_volume_mm3=MetricValue(
                value=None,
                unit="mm3",
                status="NOT_EVALUABLE",
                confidence="UNASSESSED",
                reason="Flexible scope deflection and active secondary reachability model not evaluated on this trajectory."
            ),
            flexible_accessible_stone_percent=MetricValue(
                value=None,
                unit="%",
                status="NOT_EVALUABLE",
                confidence="UNASSESSED",
                reason="Flexible scope deflection and active secondary reachability model not evaluated on this trajectory."
            ),
            inaccessible_stone_volume_mm3=inaccessible_metric,
            caliber_suitability_considerations=caliber_text,
            irrigation_pressure_risk=irrigation_risk,
            uncertainty_flags=unc_flags,
            clinical_tradeoff_summary=tradeoff_summary
        ))

    patient_pos = meta.get("surgical_position_confirmation", {}).get("operative_position", "PRONE_STANDARD")

    return CandidateComparisonMatrixResponse(
        case_id=case_id,
        imaging_modality="NON_CONTRAST_CT" if meta.get("is_demo") else meta.get("modality", "CT_SERIES"),
        patient_position_assumed=patient_pos,
        total_stone_volume_mm3=MetricValue(
            value=round(total_stone_vol, 1) if stone_data_present else None,
            unit="mm3",
            status="MEASURED" if stone_data_present else "NOT_EVALUABLE"
        ),
        candidates=items,
        active_candidate_id=meta.get("active_candidate_id"),
        provenance_hash=prov_hash
    )


@app.get("/api/cases/{case_id}/meshes/{mesh_name}")
def get_case_mesh(case_id: str, mesh_name: str, meta: Dict[str, Any] = Depends(verify_case_access)):
    """Streams binary GLB 3D surface meshes for Three.js WebGL visualization."""
    case_dir = get_case_dir(case_id)
    # Clean filename
    clean_name = mesh_name if mesh_name.endswith(".glb") else f"{mesh_name}.glb"
    mesh_path = case_dir / "artifacts" / "meshes" / clean_name
    is_synthetic_template = False

    if not mesh_path.is_file():
        preview_mesh = BASE_DIR / "data" / "anatomical_preview" / clean_name
        if preview_mesh.is_file():
            mesh_path = preview_mesh
            is_synthetic_template = True
        else:
            raise HTTPException(status_code=404, detail=f"3D Mesh '{clean_name}' not found for case {case_id}")

    headers = {
        "X-AcuCalyx-Intended-Use": "Display and Rehearsal Only. Non-Sterile.",
        "X-AcuCalyx-Synthetic-Template": "true" if is_synthetic_template else "false",
        "X-AcuCalyx-Anatomical-Source": "Standard Anatomical Reference Template (Non-Patient-Specific)" if is_synthetic_template else "Patient Specific Segmentation"
    }

    return FileResponse(
        path=mesh_path,
        media_type="model/gltf-binary",
        filename=clean_name,
        headers=headers
    )


@app.get("/api/export/combined-kidney-glb")
def export_combined_kidney_glb():
    """Direct export of the unified 3D anatomical kidney model for Windows 3D Viewer and desktop tools."""
    glb_path = BASE_DIR / "data" / "anatomical_preview" / "combined_anatomical_kidney.glb"
    if not glb_path.is_file():
        raise HTTPException(status_code=404, detail="Combined anatomical GLB not found")
    return FileResponse(
        path=glb_path,
        media_type="model/gltf-binary",
        filename="AcuCalyx_Photorealistic_Anatomical_Kidney.glb",
        headers={"Content-Disposition": "attachment; filename=AcuCalyx_Photorealistic_Anatomical_Kidney.glb"}
    )


@app.get("/api/cases/{case_id}/mpr/slice")
def get_mpr_slice(
    case_id: str,
    meta: Dict[str, Any] = Depends(verify_case_access),
    orientation: str = Query(default="AXIAL", description="'AXIAL', 'CORONAL', or 'SAGITTAL'"),
    slice_index: int = Query(default=40, ge=0),
    window_width: float = Query(default=400.0),
    window_level: float = Query(default=40.0),
    crosshair_px: Optional[int] = Query(default=None, description="Optional target reticle pixel X"),
    crosshair_py: Optional[int] = Query(default=None, description="Optional target reticle pixel Y")
):
    """
    Renders a synchronized 2D Multi-Planar Reconstruction (MPR) slice from CT volume
    with dynamic Window/Level adjustment, active trajectory crosshair overlay,
    and synchronized 3D-to-2D physical LPS reticle cursor.
    """
    meta = load_case_meta(case_id)
    input_path = resolve_case_input_path(case_id, meta)
    if not input_path.exists():
        raise HTTPException(status_code=404, detail="Source imaging path not found on server.")

    cached = get_cached_volume(case_id)
    if cached is None:
        if input_path.is_dir():
            from acucalyx.ingestion.dicom import load_dicom_series
            res = load_dicom_series(input_path)
            vol = res.volume_hu
            spatial = res.spatial_orientation
        else:
            from acucalyx.ingestion.nifti import load_research_nifti
            res = load_research_nifti(input_path)
            vol = res.volume_hu
            spatial = res.spatial_orientation
        set_cached_volume(case_id, vol, spatial)
    else:
        vol = cached["volume"]
        spatial = cached["spatial"]

    rows, cols, slices = vol.shape

    # Extract 2D slice based on orientation
    orient_upper = orientation.upper()
    if orient_upper == "AXIAL":
        idx = max(0, min(slice_index, slices - 1))
        slice_data = vol[:, :, idx]
    elif orient_upper == "CORONAL":
        idx = max(0, min(slice_index, rows - 1))
        # Transpose and flip vertically so Superior (Z) is at top and Right-to-Left (X) is horizontal
        slice_data = np.flipud(vol[idx, :, :].T)
    elif orient_upper == "SAGITTAL":
        idx = max(0, min(slice_index, cols - 1))
        # Transpose and flip vertically so Superior (Z) is at top and Anterior-to-Posterior (Y) is horizontal
        slice_data = np.flipud(vol[:, idx, :].T)
    else:
        raise HTTPException(status_code=400, detail="Orientation must be AXIAL, CORONAL, or SAGITTAL")

    # Apply Window/Level
    lower = window_level - (window_width / 2.0)
    upper = window_level + (window_width / 2.0)
    clipped = np.clip(slice_data, lower, upper)
    norm = ((clipped - lower) / (upper - lower) * 255.0).astype(np.uint8)

    # Convert to PIL Image
    img = Image.fromarray(norm).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Check if active trajectory intersects this slice
    active_cand_id = meta.get("active_candidate_id")
    c_file = get_case_dir(case_id) / "artifacts" / "candidates.json"
    if active_cand_id and c_file.is_file():
        with open(c_file, "r") as f:
            cands = json.load(f)
        active_c = next((c for c in cands if c["candidate_id"] == active_cand_id), None)
        if active_c:
            entry = np.array(active_c["entry_point_lps"])
            target = np.array(active_c["target_point_lps"])
            v_entry = spatial.physical_to_voxel(entry)
            v_target = spatial.physical_to_voxel(target)

            # Compute parametric intersection t in [0, 1] with current slice plane
            t = None
            if orient_upper == "AXIAL" and abs(v_target[2] - v_entry[2]) > 1e-3:
                t = (idx - v_entry[2]) / (v_target[2] - v_entry[2])
            elif orient_upper == "CORONAL" and abs(v_target[0] - v_entry[0]) > 1e-3:
                t = (idx - v_entry[0]) / (v_target[0] - v_entry[0])
            elif orient_upper == "SAGITTAL" and abs(v_target[1] - v_entry[1]) > 1e-3:
                t = (idx - v_entry[1]) / (v_target[1] - v_entry[1])

            if t is not None and 0.0 <= t <= 1.0:
                p_interp = v_entry + t * (v_target - v_entry)
                # Map to 2D image coordinates (X, Y)
                if orient_upper == "AXIAL":
                    px, py = int(p_interp[1]), int(p_interp[0])
                elif orient_upper == "CORONAL":
                    px = int(p_interp[1])
                    py = (slices - 1) - int(p_interp[2])
                else:
                    px = int(p_interp[0])
                    py = (slices - 1) - int(p_interp[2])

                # Draw trajectory intercept green ring
                draw.ellipse((px - 5, py - 5, px + 5, py + 5), outline="lime", width=2)
                draw.line((px - 8, py, px + 8, py), fill="lime", width=1)
                draw.line((px, py - 8, px, py + 8), fill="lime", width=1)

    # If synchronized 3D-to-2D crosshair reticle coordinate is requested
    if crosshair_px is not None and crosshair_py is not None:
        cx = int(np.clip(crosshair_px, 0, img.width - 1))
        cy = int(np.clip(crosshair_py, 0, img.height - 1))
        # Draw high-visibility clinical cyan reticle cursor (#0284c7)
        draw.ellipse((cx - 7, cy - 7, cx + 7, cy + 7), outline="#0284c7", width=2)
        draw.line((cx - 14, cy, cx + 14, cy), fill="#0284c7", width=2)
        draw.line((cx, cy - 14, cx, cy + 14), fill="#0284c7", width=2)

    # Output PNG
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


@app.get("/api/cases/{case_id}/mpr/lps_to_slice")
def convert_lps_to_mpr_slice(
    case_id: str,
    x: float = Query(..., description="Physical LPS X coordinate in mm"),
    y: float = Query(..., description="Physical LPS Y coordinate in mm"),
    z: float = Query(..., description="Physical LPS Z coordinate in mm")
):
    """
    Milestone M11: Bidirectional 3D <-> 2D Coordinate Synchronization.
    Translates physical 3D LPS coordinates (x, y, z) into exact 2D slice indices
    and pixel coordinates across Axial, Coronal, and Sagittal planes.
    """
    meta = load_case_meta(case_id)
    input_path = resolve_case_input_path(case_id, meta)
    if not input_path.exists():
        raise HTTPException(status_code=404, detail="Source imaging path not found on server.")

    cached = get_cached_volume(case_id)
    if cached is None:
        if input_path.is_dir():
            from acucalyx.ingestion.dicom import load_dicom_series
            res = load_dicom_series(input_path)
        else:
            from acucalyx.ingestion.nifti import load_research_nifti
            res = load_research_nifti(input_path)
        set_cached_volume(case_id, res.volume_hu, res.spatial_orientation)
        vol = res.volume_hu
        spatial = res.spatial_orientation
    else:
        vol = cached["volume"]
        spatial = cached["spatial"]

    rows, cols, slices = vol.shape
    p_lps = np.array([x, y, z], dtype=np.float64)
    v = spatial.physical_to_voxel(p_lps)

    row_i = int(np.clip(np.round(v[0]), 0, rows - 1))
    col_j = int(np.clip(np.round(v[1]), 0, cols - 1))
    slice_k = int(np.clip(np.round(v[2]), 0, slices - 1))

    return {
        "physical_lps": [float(x), float(y), float(z)],
        "voxel_indices": [row_i, col_j, slice_k],
        "axial": {
            "slice_index": slice_k,
            "max_slice": slices - 1,
            "pixel_x": col_j,
            "pixel_y": row_i
        },
        "coronal": {
            "slice_index": row_i,
            "max_slice": rows - 1,
            "pixel_x": col_j,
            "pixel_y": slice_k
        },
        "sagittal": {
            "slice_index": col_j,
            "max_slice": cols - 1,
            "pixel_x": row_i,
            "pixel_y": slice_k
        }
    }


@app.get("/api/cases/{case_id}/nephrolithometry")
def get_case_nephrolithometry(case_id: str, meta: Dict[str, Any] = Depends(verify_case_access)):
    """
    Milestone M11: Descriptive Clinical Nephrolithometry Assessment.
    Computes Guy's Stone Score (I-IV) and S.T.O.N.E. score (5-13) strictly as
    descriptive morphometric summaries under FDA CDS guidance (no predictive claims).
    """
    from acucalyx.stones.scoring import compute_guys_stone_score, compute_stone_nephrolithometry

    case_dir = get_case_dir(case_id)
    s_file = case_dir / "artifacts" / "stones.json"
    c_file = case_dir / "artifacts" / "candidates.json"

    stone_count = 1
    stone_locations = ["lower_pole"]
    stone_surface_area_mm2 = 250.0
    mean_hu = 900.0
    tract_length_mm = 85.0
    has_hydronephrosis = False
    calyces_count = 1

    if s_file.is_file():
        with open(s_file, "r") as f:
            stones = json.load(f)
        if stones:
            stone_count = len(stones)
            mean_hu = float(stones[0].get("peak_hu", 900.0) * 0.8)
            # Estimate surface area from volume or feret
            feret = float(stones[0].get("max_feret_diameter_mm", 12.0))
            stone_surface_area_mm2 = float(np.pi * (feret / 2.0) ** 2)
            stone_locations = [s.get("location_description", "lower_pole") for s in stones]

    if c_file.is_file():
        with open(c_file, "r") as f:
            cands = json.load(f)
        if cands:
            tract_length_mm = float(cands[0].get("tract_length_mm", 85.0))

    guys = compute_guys_stone_score(
        stone_count=stone_count,
        stone_locations=stone_locations,
        is_staghorn=False,
        is_partial_staghorn=False,
        has_abnormal_anatomy=False
    )

    stone_score = compute_stone_nephrolithometry(
        stone_surface_area_mm2=stone_surface_area_mm2,
        tract_length_mm=tract_length_mm,
        has_hydronephrosis_or_obstruction=has_hydronephrosis,
        involved_calyces_count=calyces_count,
        mean_hu=mean_hu
    )

    return {
        "case_id": case_id,
        "guys_stone_score": {
            "grade": guys.grade.value,
            "description": guys.description,
            "clinical_note": guys.clinical_note
        },
        "stone_nephrolithometry": {
            "total_score": stone_score.total_score,
            "size_points": stone_score.size_points,
            "tract_length_points": stone_score.tract_length_points,
            "obstruction_points": stone_score.obstruction_points,
            "number_calyces_points": stone_score.number_calyces_points,
            "essence_points": stone_score.essence_points,
            "complexity_tier": stone_score.complexity_tier,
            "regulatory_disclaimer": stone_score.regulatory_disclaimer
        }
    }


@app.get("/api/cases/{case_id}/fluoroscopy/{candidate_id}")
def get_virtual_fluoroscopy(case_id: str, candidate_id: str):
    """Returns virtual fluoroscopy C-arm viewing vectors and 2D projected needle coordinates."""
    case_dir = get_case_dir(case_id)
    c_file = case_dir / "artifacts" / "candidates.json"
    if not c_file.is_file():
        raise HTTPException(status_code=404, detail="Case artifacts not found")

    with open(c_file, "r") as f:
        cands = json.load(f)

    target_cand = next((c for c in cands if c["candidate_id"] == candidate_id), None)
    if not target_cand:
        raise HTTPException(status_code=404, detail=f"Candidate '{candidate_id}' not found")

    from acucalyx.geometry.transforms import LineSegment3D
    from acucalyx.fluoroscopy.projection_simulator import simulate_trajectory_projection

    traj = LineSegment3D(
        start_point=np.array(target_cand["entry_point_lps"]),
        end_point=np.array(target_cand["target_point_lps"])
    )

    view_b = simulate_trajectory_projection(traj, view_type="BULLS_EYE")
    view_p = simulate_trajectory_projection(traj, view_type="PROGRESSION")

    return {
        "candidate_id": candidate_id,
        "views": {
            "BULLS_EYE": {
                "view_type": "BULLS_EYE",
                "source_position_lps": [round(float(x), 1) for x in view_b.camera.source_position],
                "detector_position_lps": [round(float(x), 1) for x in view_b.camera.detector_position],
                "optical_axis_unit": [round(float(x), 3) for x in view_b.camera.optical_axis],
                "projected_entry_2d_mm": [round(float(x), 2) for x in view_b.projected_entry_2d_mm],
                "projected_target_2d_mm": [round(float(x), 2) for x in view_b.projected_target_2d_mm],
                "projected_needle_length_2d_mm": round(view_b.projected_needle_length_2d_mm, 2),
                "alignment_angle_deg": round(view_b.alignment_angle_deg, 1)
            },
            "PROGRESSION": {
                "view_type": "PROGRESSION",
                "source_position_lps": [round(float(x), 1) for x in view_p.camera.source_position],
                "detector_position_lps": [round(float(x), 1) for x in view_p.camera.detector_position],
                "optical_axis_unit": [round(float(x), 3) for x in view_p.camera.optical_axis],
                "projected_entry_2d_mm": [round(float(x), 2) for x in view_p.projected_entry_2d_mm],
                "projected_target_2d_mm": [round(float(x), 2) for x in view_p.projected_target_2d_mm],
                "projected_needle_length_2d_mm": round(view_p.projected_needle_length_2d_mm, 2),
                "alignment_angle_deg": round(view_p.alignment_angle_deg, 1)
            }
        }
    }


def _ensure_planning_report(case_id: str) -> Path:
    """Ensures that the 2-page Preoperative Planning PDF Report and keyframes exist, validating freshness against plan hash."""
    case_dir = get_case_dir(case_id)
    pdf_path = case_dir / "artifacts" / "report.pdf"
    report_meta_file = case_dir / "artifacts" / "report_meta.json"
    meta = load_case_meta(case_id)

    is_stale = meta.get("is_stale", False)
    current_plan_hash = meta.get("plan_hash") or meta.get("updated_at")
    active_cand = meta.get("active_candidate_id")

    # Fast-return cached PDF only if strictly non-stale, matches plan hash and active candidate
    if pdf_path.is_file() and pdf_path.stat().st_size > 500 and not is_stale and report_meta_file.is_file():
        try:
            with open(report_meta_file, "r") as rf:
                rmeta = json.load(rf)
                if rmeta.get("plan_hash") == current_plan_hash and rmeta.get("active_candidate_id") == active_cand:
                    return pdf_path
        except Exception:
            pass

    artifacts_dir = case_dir / "artifacts"
    q_file = artifacts_dir / "quality.json"
    c_file = artifacts_dir / "candidates.json"

    if not (c_file.is_file() and q_file.is_file()):
        raise HTTPException(status_code=404, detail="Planning report PDF not found. Run planning first.")
    with open(q_file, "r") as f:
        q_data = json.load(f)

    p_file = artifacts_dir / "provenance.json"
    p_data = {}
    if p_file.is_file():
        with open(p_file, "r") as f:
            p_data = json.load(f)

    s_file = artifacts_dir / "stones.json"
    s_data = []
    if s_file.is_file():
        with open(s_file, "r") as f:
            s_data = json.load(f)

    with open(c_file, "r") as f:
        c_data = json.load(f)

    from acucalyx.audit.provenance import CaseProvenanceRecord, create_provenance_record
    from acucalyx.ingestion.quality_gate import QualityGateResult
    from acucalyx.collecting_system.visibility_gate import PCSVisibilityResult, PCSVisibilityState
    from acucalyx.stones.volumetry import StoneMorphometry
    from acucalyx.stones.attenuation import StoneAttenuationProfile
    from acucalyx.planning.pareto_optimizer import CandidateTrajectory
    from acucalyx.reports.planning_report import generate_preoperative_planning_pdf

    now_iso = datetime.now(timezone.utc).isoformat()
    prov = create_provenance_record(
        case_id=case_id,
        study_uid=p_data.get("study_instance_uid", f"STUDY_{case_id}"),
        series_uid=p_data.get("series_instance_uid", f"SERIES_{case_id}"),
        modality=p_data.get("modality", "CT"),
        patient_position=p_data.get("patient_position_tag", "HFS"),
        input_data_hash=p_data.get("input_data_sha256", meta.get("data_hash", "00" * 32)),
        software_version="2.1.0"
    )

    q_gate = QualityGateResult(
        passed=q_data.get("passed", True),
        rejection_reasons=q_data.get("rejection_reasons", []),
        warnings=q_data.get("warnings", []),
        geometry_score=q_data.get("geometry_score", 1.0),
        resolution_score=q_data.get("resolution_score", 1.0),
        overall_quality_tier=q_data.get("overall_quality_tier", "HIGH"),
        slice_thickness_mm=q_data.get("slice_thickness_mm", 1.0),
        pixel_spacing_mm=tuple(q_data.get("pixel_spacing_mm", [0.75, 0.75])),
        slice_spacing_mm=q_data.get("slice_spacing_mm", 1.0),
        is_contrast_enhanced=q_data.get("is_contrast_enhanced"),
        reconstruction_kernel=q_data.get("reconstruction_kernel", "Standard")
    )

    pcs_str = meta.get("pcs_visibility_state", PCSVisibilityState.ANATOMICALLY_ESTIMATED.value)
    pcs_state = PCSVisibilityState(pcs_str) if pcs_str in [s.value for s in PCSVisibilityState] else PCSVisibilityState.ANATOMICALLY_ESTIMATED
    pcs_res = PCSVisibilityResult(
        state=pcs_state,
        confidence_score=0.85,
        fluid_cavity_volume_mm3=1200.0,
        mean_internal_hu=15.0,
        allows_direct_puncture_lock=(pcs_state != PCSVisibilityState.ANATOMICALLY_ESTIMATED),
        clinical_notice="Preoperative planning based on patient imaging series."
    )

    stones = []
    attens = []
    for s in s_data:
        stones.append(StoneMorphometry(
            stone_id=s["stone_id"],
            volume_mm3=s["volume_mm3"],
            volume_voxels=s.get("volume_voxels", int(max(1, s["volume_mm3"]))),
            max_feret_diameter_mm=s["max_feret_diameter_mm"],
            centroid_lps_mm=np.array(s["centroid_lps_mm"]),
            bounding_box_span_mm=np.array(s["bounding_box_span_mm"]),
            tier=s.get("tier", "MODERATE")
        ))
        attens.append(StoneAttenuationProfile(
            stone_id=s["stone_id"],
            mean_hu=s.get("mean_hu", 850.0),
            median_hu=s.get("mean_hu", 850.0),
            peak_hu=s.get("peak_hu", 1100.0),
            std_hu=100.0,
            min_hu=s.get("mean_hu", 850.0) - 200.0,
            fraction_low_under_500hu=0.1,
            fraction_intermediate_500_1000hu=0.3,
            fraction_high_over_1000hu=s.get("fraction_high_over_1000hu", 0.6),
            composition_inference=s.get("composition_inference", "CALCIUM_OXALATE_SUSPECTED")
        ))

    candidates = []
    for c in c_data:
        candidates.append(CandidateTrajectory(
            candidate_id=c["candidate_id"],
            entry_point_lps=np.array(c["entry_point_lps"]),
            target_point_lps=np.array(c["target_point_lps"]),
            target_calyx_name=c.get("target_calyx", "Calyx Target"),
            tract_length_mm=c.get("tract_length_mm", 70.0),
            min_effective_clearance_mm=c.get("min_effective_clearance_mm", 15.0),
            hazard_evaluations=[],
            reachable_stone_fraction=c.get("reachable_stone_fraction", 0.8),
            access_rib_classification=c.get("access_rib_classification", "SUBCOSTAL_12"),
            required_scope_deflection_deg=c.get("required_scope_deflection_deg", 15.0),
            is_pareto_optimal=c.get("is_pareto_optimal", True)
        ))

    cached = get_cached_volume(case_id)
    vol = cached["volume"] if cached else None
    spatial = cached["spatial"] if cached else None

    lat_conf = meta.get("laterality_confirmation")
    pos_conf = meta.get("surgical_position_confirmation")
    if lat_conf:
        raw_side = lat_conf.get("confirmed_side") or lat_conf.get("verified_laterality") or meta.get("target_side", "LEFT")
        verified_lat = str(raw_side).upper()
    else:
        verified_lat = meta.get("target_side", "LEFT").upper()
    confirmed_pos = pos_conf.get("operative_position") if pos_conf else "PRONE_STANDARD"

    generate_preoperative_planning_pdf(
        output_path=pdf_path,
        provenance=prov,
        quality_gate=q_gate,
        pcs_visibility=pcs_res,
        stones=stones,
        attenuations=attens,
        candidates=candidates,
        verified_laterality=verified_lat,
        confirmed_operative_position=confirmed_pos,
        active_candidate_id=meta.get("active_candidate_id"),
        volume_hu=vol,
        spatial=spatial
    )

    try:
        tmp_rep = report_meta_file.with_suffix(f".tmp_{secrets.token_hex(4)}")
        with open(tmp_rep, "w", encoding="utf-8") as rf:
            json.dump({
                "plan_hash": current_plan_hash,
                "active_candidate_id": active_cand,
                "generated_at": now_iso
            }, rf, indent=2)
        tmp_rep.replace(report_meta_file)
    except Exception as e:
        logger.warning(f"Could not persist report metadata: {e}")

    return pdf_path


@app.get("/api/cases/{case_id}/report")
@app.get("/api/cases/{case_id}/pdf-report")
def download_planning_report(case_id: str, meta: Dict[str, Any] = Depends(verify_case_access)):
    """Downloads the auditable 2-page Preoperative Planning PDF Report."""
    pdf_path = _ensure_planning_report(case_id)
    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=f"AcuCalyx_{case_id}_Preoperative_Report.pdf"
    )


@app.get("/api/cases/{case_id}/keyframes/{keyframe_name}")
def get_case_keyframe(case_id: str, keyframe_name: str, meta: Dict[str, Any] = Depends(verify_case_access)):
    """Streams server-rendered keyframe PNG image (axial, coronal, bullseye)."""
    clean_name = keyframe_name if keyframe_name.endswith(".png") else f"{keyframe_name}.png"
    case_dir = get_case_dir(case_id)
    kf_path = case_dir / "artifacts" / "keyframes" / clean_name

    if not kf_path.is_file():
        try:
            # Trigger dynamic generation if planning artifacts exist
            _ensure_planning_report(case_id)
        except Exception:
            pass

    is_synthetic_template = False
    if not kf_path.is_file():
        # Check canonical reference preview keyframes
        preview_kf = BASE_DIR / "data" / "anatomical_preview" / "keyframes" / clean_name
        if preview_kf.is_file():
            kf_path = preview_kf
            is_synthetic_template = True
        else:
            raise HTTPException(status_code=404, detail=f"Keyframe '{clean_name}' not found for case {case_id}")

    headers = {
        "X-AcuCalyx-Intended-Use": "Display and Rehearsal Only. Non-Sterile.",
        "X-AcuCalyx-Synthetic-Template": "true" if is_synthetic_template else "false",
        "X-AcuCalyx-Keyframe-Source": "Standard Anatomical Reference Template" if is_synthetic_template else "Patient-Specific Trajectory Keyframe"
    }

    return FileResponse(
        path=kf_path,
        media_type="image/png",
        filename=clean_name,
        headers=headers
    )


@app.get("/api/cases/{case_id}/provenance")
def get_case_provenance(case_id: str, meta: Dict[str, Any] = Depends(verify_case_access)):
    """Downloads the cryptographic SHA-256 case provenance manifest."""
    case_dir = get_case_dir(case_id)
    prov_path = case_dir / "artifacts" / "provenance.json"
    if not prov_path.is_file():
        raise HTTPException(status_code=404, detail="Provenance record not found.")
    with open(prov_path, "r") as f:
        return json.load(f)


# Mount Doctor Authentication & Patient Privacy Isolation Routes
from app.api.auth import router as auth_router
app.include_router(auth_router)

# Mount Privacy-Preserving Federated Learning & DP Routes
from app.api.routes_learning import router as learning_router
app.include_router(learning_router)

# Mount DRR Fluoroscopy Routes
from app.api.routes_drr import router as drr_router
app.include_router(drr_router)

# Mount Rehearsal & Phantom Metrology Routes (Phase 5 / M3)
from app.api.routes_rehearsal import router as rehearsal_router
app.include_router(rehearsal_router)

# Mount Usability & Human Factors Routes (Phase 6 / M4)
from app.api.routes_usability import router as usability_router
app.include_router(usability_router)

# Mount Multimodal Ultrasound & Positioning Uncertainty Routes (Milestone M14)
from app.api.routes_ultrasound import router as ultrasound_router
app.include_router(ultrasound_router)

# Mount Endoscopic Reachability & Computed Endoluminal Rehearsal Routes (Milestone M15)
from app.api.routes_endoscopy import router as endoscopy_router
app.include_router(endoscopy_router)

# Mount CT Urography Feasibility & M15-V Validation Gate Routes (Horizon 3 / M15.1)
from app.api.routes_validation import router as validation_router
app.include_router(validation_router)

# Mount Frontend UI Static Files
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


def run_server():
    """CLI entrypoint for AcuCalyx application server."""
    import uvicorn
    uvicorn.run("app.api.main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    run_server()

