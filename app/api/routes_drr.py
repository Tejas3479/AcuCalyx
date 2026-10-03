"""
AcuCalyx API: DRR Fluoroscopy Streaming & Radiation Planning Routes

Implements Step 4.09 of Phase 4 (Frozen v4.1):
- /api/cases/{case_id}/drr/{candidate_id}/bullseye: Renders Bull's-Eye en-face DRR with needle and motion envelope
- /api/cases/{case_id}/drr/{candidate_id}/depth_verification: Renders Depth-Verification DRR with 1-cm depth tick marks
- /api/cases/{case_id}/drr/{candidate_id}/alara: Returns ALARA radiation safety planning metrics
"""

import io
import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Response
import numpy as np
from PIL import Image

from acucalyx.fluoroscopy.alara_metrics import generate_alara_planning_report
from acucalyx.fluoroscopy.carm_profile import get_carm_profile
from acucalyx.fluoroscopy.cpu_reference_drr import generate_cpu_reference_drr
from acucalyx.fluoroscopy.motion_projection import (
    compute_projected_motion_envelope,
    overlay_motion_envelope_on_drr,
)
from acucalyx.fluoroscopy.needle_renderer import (
    STANDARD_CHIBA_18G,
    overlay_needle_on_drr,
    project_needle_onto_drr,
)
from acucalyx.fluoroscopy.surgical_pose import (
    construct_bullseye_carm_pose,
    construct_depth_verification_carm_pose,
)
from acucalyx.fluoroscopy.virtual_contrast import (
    VirtualContrastMode,
    apply_virtual_contrast_to_volume,
)
from acucalyx.geometry.transforms import LineSegment3D
from acucalyx.ingestion.dicom import load_dicom_series
from acucalyx.ingestion.nifti import load_research_nifti

router = APIRouter(prefix="/api/cases/{case_id}/drr", tags=["Fluoroscopy DRR"])

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CASES_DIR = BASE_DIR / "data" / "cases"


def _load_case_data_and_candidate(case_id: str, candidate_id: str):
    case_dir = CASES_DIR / case_id
    meta_path = case_dir / "case_meta.json"
    cand_path = case_dir / "artifacts" / "candidates.json"

    if not meta_path.is_file() or not cand_path.is_file():
        raise HTTPException(status_code=404, detail="Case data or artifacts not found.")

    with open(meta_path, "r") as f:
        meta = json.load(f)

    with open(cand_path, "r") as f:
        candidates = json.load(f)

    cand = next((c for c in candidates if c["candidate_id"] == candidate_id), None)
    if not cand:
        raise HTTPException(status_code=404, detail=f"Candidate {candidate_id} not found.")

    input_path = Path(meta["input_path"])
    
    # Check if active volume cache from main module has this case
    try:
        from app.api.main import get_cached_volume, set_cached_volume
        cached = get_cached_volume(case_id)
    except Exception:
        cached = None

    if cached is not None:
        volume = cached["volume"]
        spatial = cached["spatial"]
    else:
        if input_path.is_dir():
            dcm_res = load_dicom_series(input_path)
            volume = dcm_res.volume_hu
            spatial = dcm_res.spatial_orientation
        else:
            nii_res = load_research_nifti(input_path)
            volume = nii_res.volume_hu
            spatial = nii_res.spatial_orientation
        try:
            from app.api.main import set_cached_volume
            set_cached_volume(case_id, volume, spatial)
        except Exception:
            pass

    entry = np.array(cand["entry_point_lps"], dtype=np.float64)
    target = np.array(cand["target_point_lps"], dtype=np.float64)
    traj = LineSegment3D(entry, target)

    return volume, spatial, traj, cand


@router.get("/{candidate_id}/bullseye")
def get_bullseye_drr_image(
    case_id: str,
    candidate_id: str,
    carm_model: str = Query(default="philips_zenition_70"),
    enable_contrast: bool = Query(default=True),
    resolution: int = Query(default=256, ge=128, le=512)
):
    """Generates and streams the Bull's-Eye (en-face) DRR with needle and respiratory uncertainty."""
    volume, spatial, traj, cand = _load_case_data_and_candidate(case_id, candidate_id)
    profile = get_carm_profile(carm_model)

    pose = construct_bullseye_carm_pose(traj, profile)

    # Optional virtual contrast
    if enable_contrast:
        # Load collecting system mask if available
        pcs_file = CASES_DIR / case_id / "artifacts" / "collecting_system.npy"
        pcs_mask = np.load(pcs_file) if pcs_file.is_file() else None
        vol_drr = apply_virtual_contrast_to_volume(volume, pcs_mask, VirtualContrastMode.MODE_B_ATTENUATION_BOOST)
    else:
        vol_drr = volume

    drr = generate_cpu_reference_drr(
        ct_volume_hu=vol_drr,
        spatial=spatial,
        pose=pose,
        output_resolution=(resolution, resolution),
        step_size_mm=2.5,
        polarity=profile.default_polarity
    )

    # Needle overlay (en-face concentric circle)
    overlay = project_needle_onto_drr(traj, pose, STANDARD_CHIBA_18G, (resolution, resolution))
    drr = overlay_needle_on_drr(drr, overlay, color_val=0)

    # Projected respiratory uncertainty ellipse
    motion_env = compute_projected_motion_envelope(traj.end_point, pose, (resolution, resolution))
    drr = overlay_motion_envelope_on_drr(drr, motion_env, color_val=120)

    buf = io.BytesIO()
    Image.fromarray(drr).save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


@router.get("/{candidate_id}/depth_verification")
def get_depth_verification_drr_image(
    case_id: str,
    candidate_id: str,
    carm_model: str = Query(default="philips_zenition_70"),
    oblique_angle_deg: float = Query(default=30.0),
    enable_contrast: bool = Query(default=True),
    resolution: int = Query(default=256, ge=128, le=512)
):
    """Generates and streams the Depth-Verification (Progression) DRR with 1-cm needle graduations."""
    volume, spatial, traj, cand = _load_case_data_and_candidate(case_id, candidate_id)
    profile = get_carm_profile(carm_model)

    pose = construct_depth_verification_carm_pose(traj, oblique_angle_offset_deg=oblique_angle_deg, profile=profile)

    if enable_contrast:
        pcs_file = CASES_DIR / case_id / "artifacts" / "collecting_system.npy"
        pcs_mask = np.load(pcs_file) if pcs_file.is_file() else None
        vol_drr = apply_virtual_contrast_to_volume(volume, pcs_mask, VirtualContrastMode.MODE_B_ATTENUATION_BOOST)
    else:
        vol_drr = volume

    drr = generate_cpu_reference_drr(
        ct_volume_hu=vol_drr,
        spatial=spatial,
        pose=pose,
        output_resolution=(resolution, resolution),
        step_size_mm=2.5,
        polarity=profile.default_polarity
    )

    overlay = project_needle_onto_drr(traj, pose, STANDARD_CHIBA_18G, (resolution, resolution))
    drr = overlay_needle_on_drr(drr, overlay, color_val=0)

    buf = io.BytesIO()
    Image.fromarray(drr).save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


@router.get("/{candidate_id}/alara")
def get_alara_report(
    case_id: str,
    candidate_id: str,
    carm_model: str = Query(default="philips_zenition_70")
):
    """Returns preoperative ALARA radiation planning metrics."""
    volume, spatial, traj, cand = _load_case_data_and_candidate(case_id, candidate_id)
    profile = get_carm_profile(carm_model)

    pose_bull = construct_bullseye_carm_pose(traj, profile)
    pose_depth = construct_depth_verification_carm_pose(traj, oblique_angle_offset_deg=30.0, profile=profile)

    report = generate_alara_planning_report(
        bullseye_angles=(pose_bull.gantry_primary_angle_deg, pose_bull.gantry_secondary_angle_deg),
        depth_angles=(pose_depth.gantry_primary_angle_deg, pose_depth.gantry_secondary_angle_deg),
        profile=profile,
        target_kidney_side="left"
    )

    return {
        "case_id": case_id,
        "candidate_id": candidate_id,
        "carm_model": profile.model_name,
        "planned_views": report.planned_view_count,
        "bullseye_gantry_angles": {
            "primary_angle_deg": report.bullseye_primary_angle_deg,
            "secondary_angle_deg": report.bullseye_secondary_angle_deg
        },
        "depth_gantry_angles": {
            "primary_angle_deg": report.depth_primary_angle_deg,
            "secondary_angle_deg": report.depth_secondary_angle_deg
        },
        "estimated_hunting_exposures_saved": report.estimated_hunting_exposures_saved,
        "recommended_pulse_rate_pps": report.recommended_pulse_rate_pps,
        "pulse_rate_protocol_hint": report.pulse_rate_protocol_hint,
        "collimation_advisory": report.collimation_advisory,
        "alara_checklist": report.alara_clinical_checklist,
        "governing_standards": report.governing_standards,
        "dose_telemetry_disclaimer": report.dose_telemetry_disclaimer
    }
