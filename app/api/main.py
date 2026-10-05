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
from pathlib import Path
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
from acucalyx.pipeline import run_planning_pipeline, PlanningPipelineResult
from acucalyx.geometry.transforms import LineSegment3D
from tests.phantom.phantom_generator import generate_synthetic_pcnl_phantom, save_phantom_to_nifti
from app.api.schemas import (
    CaseState, CaseSummaryResponse, CaseUploadResponse,
    PlanGenerationRequest, TrajectorySelectionRequest, ManualOverrideRequest,
    QualityGateSummary, StoneMetricItem, CandidateTrajectoryItem,
    HazardClearanceItem, MonteCarloItem, FluoroscopyViewData
)

logger = logging.getLogger("acucalyx.api")
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(name)s: %(message)s")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CASES_DIR = BASE_DIR / "data" / "cases"
FRONTEND_DIR = BASE_DIR / "app" / "frontend"
CASES_DIR.mkdir(parents=True, exist_ok=True)
FRONTEND_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="AcuCalyx™ Clinical Decision Support API",
    version="2.1.0",
    description="Computational Planning and Virtual Fluoroscopy Simulator for Percutaneous Nephrolithotomy (PCNL)"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


# In-memory bounded LRU cache for active volumes (max 3 cases to prevent OOM)
MAX_CACHED_VOLUMES = 3
_ACTIVE_VOLUMES: OrderedDict[str, Dict[str, Any]] = OrderedDict()


def get_cached_volume(case_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves volume from cache and updates LRU recency position."""
    if case_id in _ACTIVE_VOLUMES:
        _ACTIVE_VOLUMES.move_to_end(case_id)
        return _ACTIVE_VOLUMES[case_id]
    return None


def set_cached_volume(case_id: str, vol: np.ndarray, spatial: Any) -> None:
    """Stores volume in LRU cache, evicting the least recently accessed case if limit exceeded."""
    if case_id in _ACTIVE_VOLUMES:
        _ACTIVE_VOLUMES.move_to_end(case_id)
    else:
        if len(_ACTIVE_VOLUMES) >= MAX_CACHED_VOLUMES:
            evicted_id, _ = _ACTIVE_VOLUMES.popitem(last=False)
            logger.info(f"LRU Cache Eviction: Cleared volume memory for case {evicted_id}")
    _ACTIVE_VOLUMES[case_id] = {"volume": vol, "spatial": spatial}


def get_case_meta_path(case_id: str) -> Path:
    return CASES_DIR / case_id / "case_meta.json"


def load_case_meta(case_id: str) -> Dict[str, Any]:
    meta_path = get_case_meta_path(case_id)
    if not meta_path.is_file():
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    with open(meta_path, "r") as f:
        return json.load(f)


def save_case_meta(case_id: str, meta: Dict[str, Any]) -> None:
    meta_path = get_case_meta_path(case_id)
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta["updated_at"] = datetime.now(timezone.utc).isoformat()
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)


def log_case_audit_event(case_id: str, action: str, details: Dict[str, Any], user: str = "System") -> None:
    audit_path = CASES_DIR / case_id / "audit_trail.json"
    events = []
    if audit_path.is_file():
        try:
            with open(audit_path, "r") as f:
                events = json.load(f)
        except Exception:
            events = []
    events.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user": user,
        "action": action,
        "details": details
    })
    with open(audit_path, "w") as f:
        json.dump(events, f, indent=2)


@app.get("/api/health")
def health_check():
    return {"status": "ok", "system": "AcuCalyx", "version": "2.1.0"}


@app.get("/api/cases", response_model=List[CaseSummaryResponse])
def list_cases():
    """Lists all registered cases and their workflow state."""
    results = []
    for case_folder in sorted(CASES_DIR.iterdir()):
        if case_folder.is_dir():
            meta_path = case_folder / "case_meta.json"
            if meta_path.is_file():
                try:
                    with open(meta_path, "r") as f:
                        meta = json.load(f)
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
                        clinical_notice=meta.get("clinical_notice", "")
                    ))
                except Exception as e:
                    logger.warning(f"Error reading case meta in {case_folder}: {e}")
    return results


@app.post("/api/cases/demo", response_model=CaseSummaryResponse)
def create_demo_case():
    """
    Creates an instant synthetic phantom case with analytical ground truth.
    Provides immediate testing without requiring external DICOM uploads.
    """
    case_id = f"DEMO_PHANTOM_{datetime.now().strftime('%H%M%S')}"
    case_dir = CASES_DIR / case_id
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

    # Initial metadata
    now_iso = datetime.now(timezone.utc).isoformat()
    meta = {
        "case_id": case_id,
        "state": CaseState.READY.value,
        "created_at": now_iso,
        "updated_at": now_iso,
        "input_path": str(nii_path),
        "target_side": "left",
        "is_stale": False,
        "active_candidate_id": None,
        "stone_count": 1,
        "candidate_count": 0,
        "clinical_notice": "Synthetic analytical CT calibration phantom."
    }
    save_case_meta(case_id, meta)
    log_case_audit_event(case_id, "DEMO_CASE_CREATED", {"source": "Synthetic Phantom Generator"})

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
        clinical_notice="Synthetic analytical CT calibration phantom ready for planning."
    )


@app.post("/api/cases/upload", response_model=CaseUploadResponse)
async def upload_case(file: UploadFile = File(...), target_side: str = Query(default="left")):
    """Uploads a CT series (either a .zip containing DICOM slices or a .nii/.nii.gz file)."""
    filename = file.filename or "uploaded_ct"
    stem = Path(filename).stem.replace(".nii", "").replace(" ", "_")
    case_id = f"CASE_{stem}_{datetime.now().strftime('%H%M%S')}"

    case_dir = CASES_DIR / case_id
    raw_dir = case_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    dest_path = raw_dir / filename

    content = await file.read()
    with open(dest_path, "wb") as f:
        f.write(content)

    input_file_count = 1
    input_path = dest_path

    # If zip, extract slices
    if filename.lower().endswith(".zip"):
        extract_dir = raw_dir / "dicom_series"
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(dest_path, "r") as z:
            z.extractall(extract_dir)
        dcm_files = [p for p in extract_dir.rglob("*") if p.is_file() and not p.name.startswith(".")]
        input_file_count = len(dcm_files)
        input_path = extract_dir

        # HIPAA / PS 3.15 Basic Application Level Confidentiality Profile Guard
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
                logger.debug(f"Skip during de-identification of {dcm_file}: {e}")
        if scrubbed_count > 0:
            logger.info(f"PHIGuard: Successfully scrubbed direct PHI from {scrubbed_count} slices for case {case_id}")
            log_case_audit_event(case_id, "PHI_SCRUBBED_INGESTION", {"scrubbed_slices": scrubbed_count})
    elif filename.lower().endswith(".dcm"):
        try:
            import pydicom
            phi_guard = PHIGuard()
            ds = pydicom.dcmread(str(dest_path), force=True)
            scrubbed = phi_guard.deidentify(ds)
            scrubbed.save_as(str(dest_path))
            log_case_audit_event(case_id, "PHI_SCRUBBED_INGESTION", {"scrubbed_slices": 1})
        except Exception as e:
            logger.debug(f"Single DICOM de-identification skipped: {e}")

    now_iso = datetime.now(timezone.utc).isoformat()
    meta = {
        "case_id": case_id,
        "state": CaseState.READY.value,
        "created_at": now_iso,
        "updated_at": now_iso,
        "input_path": str(input_path),
        "target_side": target_side.lower(),
        "is_stale": False,
        "active_candidate_id": None,
        "stone_count": 0,
        "candidate_count": 0,
        "clinical_notice": f"Uploaded {input_file_count} file(s). Ready for planning."
    }
    save_case_meta(case_id, meta)
    log_case_audit_event(case_id, "CASE_UPLOADED", {"filename": filename, "file_count": input_file_count})

    return CaseUploadResponse(
        case_id=case_id,
        state=CaseState.READY,
        message=f"Successfully ingested {input_file_count} file(s). Case {case_id} is READY.",
        input_file_count=input_file_count
    )


@app.get("/api/cases/{case_id}/status", response_model=CaseSummaryResponse)
def get_case_status(case_id: str):
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
def run_case_planning(case_id: str, req: PlanGenerationRequest):
    """Executes the full planning pipeline, generating Pareto candidates, 3D meshes, and report."""
    meta = load_case_meta(case_id)
    case_dir = CASES_DIR / case_id
    artifacts_dir = case_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    input_path = Path(meta["input_path"])
    if not input_path.exists():
        raise HTTPException(status_code=400, detail=f"Source imaging path not found: {input_path}")

    # Transition state to VALIDATING
    meta["state"] = CaseState.VALIDATING.value
    save_case_meta(case_id, meta)
    log_case_audit_event(case_id, "PLANNING_STARTED", {"target_side": req.target_side})

    try:
        pipeline_cfg = {
            "coarse_step_mm": req.coarse_step_mm,
            "monte_carlo_samples": req.monte_carlo_samples,
            "allow_marginal": req.allow_marginal
        }
        res: PlanningPipelineResult = run_planning_pipeline(
            input_path=input_path,
            output_dir=artifacts_dir,
            side=req.target_side,
            case_id=case_id,
            config=pipeline_cfg
        )
    except Exception as e:
        logger.exception("Pipeline execution failed")
        meta["state"] = CaseState.REJECTED.value
        meta["clinical_notice"] = f"Pipeline execution error: {str(e)}"
        save_case_meta(case_id, meta)
        raise HTTPException(status_code=500, detail=f"Planning pipeline failed: {str(e)}")

    if res.status == "GATE_REJECTED":
        meta["state"] = CaseState.REJECTED.value
        meta["clinical_notice"] = "DICOM Quality Gate rejected series due to non-standard or missing geometry."
    else:
        meta["state"] = CaseState.PLAN_GENERATED.value
        meta["target_side"] = req.target_side
        meta["stone_count"] = len(res.stones)
        meta["candidate_count"] = len(res.candidates)
        meta["is_stale"] = False
        meta["active_candidate_id"] = res.candidates[0].candidate_id if res.candidates else None
        meta["clinical_notice"] = f"Generated {len(res.candidates)} Pareto candidate trajectories."

    save_case_meta(case_id, meta)
    log_case_audit_event(case_id, "PLANNING_COMPLETED", {
        "status": res.status,
        "candidates": len(res.candidates),
        "stones": len(res.stones)
    })

    return get_case_status(case_id)


@app.get("/api/cases/{case_id}/quality")
def get_quality_metrics(case_id: str):
    """Returns the fail-closed DICOM quality gate results."""
    case_dir = CASES_DIR / case_id
    q_file = case_dir / "artifacts" / "quality.json"
    if not q_file.is_file():
        raise HTTPException(status_code=404, detail="Quality report not found. Has planning been run?")
    with open(q_file, "r") as f:
        return json.load(f)


@app.get("/api/cases/{case_id}/stones", response_model=List[StoneMetricItem])
def get_stone_metrics(case_id: str):
    """Returns detected kidney stones with true 3D volumetry and attenuation statistics."""
    case_dir = CASES_DIR / case_id
    s_file = case_dir / "artifacts" / "stones.json"
    if not s_file.is_file():
        raise HTTPException(status_code=404, detail="Stone metrics not found. Has planning been run?")
    with open(s_file, "r") as f:
        data = json.load(f)
    return data


@app.get("/api/cases/{case_id}/candidates", response_model=List[CandidateTrajectoryItem])
def get_candidate_trajectories(case_id: str):
    """Returns all computed Pareto access trajectories with clinical trade-offs and safety badges."""
    case_dir = CASES_DIR / case_id
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
def select_candidate_trajectory(case_id: str, req: TrajectorySelectionRequest):
    """
    Clinician approves a candidate trajectory.
    Logs auditable event and transitions case state to CLINICIAN_REVIEW.
    """
    meta = load_case_meta(case_id)
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
def clinician_override(case_id: str, req: ManualOverrideRequest):
    """
    Clinician overrides an anatomical contour or target coordinate.
    Adheres strictly to AcuCalyx v2.1 governance: marks downstream plan as STALE.
    """
    meta = load_case_meta(case_id)
    meta["is_stale"] = True
    meta["clinical_notice"] = f"STALE PLAN: Manual override applied ({req.override_type}). Re-planning recommended."
    save_case_meta(case_id, meta)

    log_case_audit_event(
        case_id,
        "MANUAL_OVERRIDE_APPLIED",
        {
            "override_type": req.override_type,
            "target_calyx_id": req.target_calyx_id,
            "coordinates": req.modified_coordinates_lps,
            "reason": req.reason
        },
        user=req.clinician_id
    )
    return {"status": "success", "is_stale": True, "notice": meta["clinical_notice"]}


@app.get("/api/cases/{case_id}/meshes/{mesh_name}")
def get_case_mesh(case_id: str, mesh_name: str):
    """Streams binary GLB 3D surface meshes for Three.js WebGL visualization."""
    case_dir = CASES_DIR / case_id
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
    input_path = Path(meta["input_path"])

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
        slice_data = vol[idx, :, :]
    elif orient_upper == "SAGITTAL":
        idx = max(0, min(slice_index, cols - 1))
        slice_data = vol[:, idx, :]
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
    c_file = CASES_DIR / case_id / "artifacts" / "candidates.json"
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
                    px, py = int(p_interp[1]), int(p_interp[2])
                else:
                    px, py = int(p_interp[0]), int(p_interp[2])

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
    input_path = Path(meta["input_path"])

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
def get_case_nephrolithometry(case_id: str):
    """
    Milestone M11: Descriptive Clinical Nephrolithometry Assessment.
    Computes Guy's Stone Score (I-IV) and S.T.O.N.E. score (5-13) strictly as
    descriptive morphometric summaries under FDA CDS guidance (no predictive claims).
    """
    from acucalyx.stones.scoring import compute_guys_stone_score, compute_stone_nephrolithometry

    case_dir = CASES_DIR / case_id
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
    case_dir = CASES_DIR / case_id
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


@app.get("/api/cases/{case_id}/report")
def download_planning_report(case_id: str):
    """Downloads the auditable 2-page Preoperative Planning PDF Report."""
    case_dir = CASES_DIR / case_id
    pdf_path = case_dir / "artifacts" / "report.pdf"
    if not pdf_path.is_file():
        raise HTTPException(status_code=404, detail="Planning report PDF not found. Run planning first.")
    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=f"AcuCalyx_{case_id}_Preoperative_Report.pdf"
    )


@app.get("/api/cases/{case_id}/provenance")
def get_case_provenance(case_id: str):
    """Downloads the cryptographic SHA-256 case provenance manifest."""
    case_dir = CASES_DIR / case_id
    prov_path = case_dir / "artifacts" / "provenance.json"
    if not prov_path.is_file():
        raise HTTPException(status_code=404, detail="Provenance record not found.")
    with open(prov_path, "r") as f:
        return json.load(f)


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

# Mount Frontend UI Static Files
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
