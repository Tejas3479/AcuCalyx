"""
AcuCalyx API: Surgical Rehearsal Simulator & Phantom Metrology Routes (Phase 5 / M3)

Provides REST endpoints for:
- Anthropomorphic phantom specifications and CT radiodensity validation
- Automated negative mold CAD package generation
- C-arm technician transfer card with ALARA presets
- Real-time 4-view synchronized puncture rehearsal state updates
- ASTM F2554 procedural accuracy cohort evaluation & Clopper-Pearson risk bounds
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
import numpy as np

from acucalyx.fluoroscopy.carm_profile import PHILIPS_ZENITION_70, get_carm_profile
from acucalyx.fluoroscopy.rehearsal_simulator import (
    PunctureRehearsalSimulator,
    CarmTechnicianTransferCard,
    RehearsalState,
)
from acucalyx.geometry.coordinates import SpatialOrientation
from acucalyx.geometry.transforms import LineSegment3D
from acucalyx.phantom.mold_generator import PhantomMoldCADGenerator
from acucalyx.phantom.phantom_spec import (
    MetrologyUncertaintyBudget,
    STANDARD_ANTHROPOMORPHIC_SPEC,
)
from acucalyx.validation.procedural_evaluator import (
    ProceduralAccuracyEvaluator,
    PunctureExecutionTrial,
    TargetFornicealZone,
    compute_exact_clopper_pearson_upper_bound,
)

router = APIRouter(prefix="/api", tags=["rehearsal_and_phantom"])

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CASES_DIR = BASE_DIR / "data" / "cases"


class CTScanValidationRequest(BaseModel):
    layer_measurements_hu: Dict[str, float]


class ProceduralTrialRequest(BaseModel):
    trial_id: str
    operator_id: str
    planned_entry_lps: List[float] = Field(..., min_length=3, max_length=3)
    planned_target_lps: List[float] = Field(..., min_length=3, max_length=3)
    physical_entry_lps: List[float] = Field(..., min_length=3, max_length=3)
    physical_tip_lps: List[float] = Field(..., min_length=3, max_length=3)
    target_calyx_name: str = "lower_pole_posterior"
    infundibular_axis_unit: List[float] = Field(default=[0.0, 1.0, 0.0], min_length=3, max_length=3)
    papilla_radius_mm: float = 3.0
    is_counter_puncture_observed: bool = False
    is_first_pass: bool = True
    fluoroscopy_time_seconds: float = 0.0
    dose_area_product_gy_cm2: float = 0.0
    repositioning_attempts: int = 0


class CohortEvaluationRequest(BaseModel):
    trials: List[ProceduralTrialRequest]


@router.get("/phantom/spec")
def get_phantom_specification():
    """Returns the multi-material anthropomorphic torso phantom specification and metrology budget."""
    spec = STANDARD_ANTHROPOMORPHIC_SPEC
    layers_dict = {}
    for name, layer in spec.layers.items():
        layers_dict[name] = {
            "material": layer.material_description,
            "target_hu": layer.target_hu,
            "acceptable_hu_range": list(layer.acceptable_hu_range),
            "shore_hardness": layer.shore_hardness,
            "fabrication_method": layer.fabrication_method,
            "functional_purpose": layer.functional_purpose
        }
    return {
        "phantom_name": spec.name,
        "fiducial_count": spec.fiducial_count,
        "fiducial_material": spec.fiducial_material,
        "uncertainty_budget": spec.uncertainty_budget.generate_uncertainty_report(),
        "layers": layers_dict
    }


@router.post("/phantom/validate-scan")
def validate_phantom_ct_scan(request: CTScanValidationRequest):
    """Validates measured CT attenuation (HU) across all phantom tissue layers."""
    report = STANDARD_ANTHROPOMORPHIC_SPEC.validate_phantom_scan(request.layer_measurements_hu)
    return report


def _load_case_trajectory_or_nominal(case_id: str, candidate_id: Optional[str] = None):
    case_dir = CASES_DIR / case_id
    meta_path = case_dir / "case_meta.json"
    cand_path = case_dir / "artifacts" / "candidates.json"

    laterality = "LEFT"
    spatial = SpatialOrientation.from_dicom_parameters(
        image_orientation_patient=[1.0, 0.0, 0.0, 0.0, 1.0, 0.0],
        image_position_patient=[-64.0, -64.0, 0.0],
        pixel_spacing=[1.0, 1.0],
        slice_spacing=1.0
    )
    planned_traj = LineSegment3D(
        start_point=np.array([25.0, -80.0, 35.0]),
        end_point=np.array([22.0, 15.0, 40.0])
    )
    target_name = "lower_pole_posterior"

    if meta_path.is_file():
        try:
            with open(meta_path, "r") as f:
                meta = json.load(f)
                laterality = meta.get("target_kidney_side", "left").upper()
                if "input_path" in meta:
                    inp = Path(meta["input_path"])
                    if inp.is_file() and (inp.name.endswith(".nii.gz") or inp.name.endswith(".nii")):
                        from acucalyx.ingestion.nifti import load_research_nifti
                        res = load_research_nifti(inp)
                        spatial = res.spatial_orientation
        except Exception:
            pass

    if cand_path.is_file():
        try:
            with open(cand_path, "r") as f:
                cands = json.load(f)
                if cands:
                    target_cand = None
                    if candidate_id:
                        target_cand = next((c for c in cands if c.get("candidate_id") == candidate_id), None)
                    if not target_cand:
                        target_cand = cands[0]
                    entry = np.array(target_cand["entry_point_lps"], dtype=np.float64)
                    target = np.array(target_cand["target_point_lps"], dtype=np.float64)
                    planned_traj = LineSegment3D(entry, target)
                    target_name = target_cand.get("target_calyx", target_name)
        except Exception:
            pass

    diff = planned_traj.end_point - planned_traj.start_point
    axis = diff / (np.linalg.norm(diff) + 1e-6)
    zone = TargetFornicealZone(
        calyx_name=target_name,
        forniceal_apex_lps=planned_traj.end_point,
        infundibular_axis_unit=axis
    )

    return planned_traj, zone, target_name, laterality, spatial


@router.get("/cases/{case_id}/rehearsal/transfer-card")
def get_carm_transfer_card(
    case_id: str,
    candidate_id: Optional[str] = Query(None, description="Specific candidate ID"),
    carm_model: str = Query("philips_zenition_70", description="C-arm hardware profile key"),
    oblique_angle_deg: float = Query(30.0, description="Depth-verification oblique angle")
):
    """Generates standardized C-arm gantry angle presets and ALARA instructions for the technician."""
    profile = get_carm_profile(carm_model)
    sim = PunctureRehearsalSimulator(carm_profile=profile)
    planned_traj, zone, target_name, laterality, spatial = _load_case_trajectory_or_nominal(case_id, candidate_id)

    card = sim.generate_transfer_card(
        case_id=case_id,
        target_calyx_name=target_name,
        planned_trajectory=planned_traj,
        laterality=laterality,
        oblique_angle_deg=oblique_angle_deg
    )
    return card


@router.get("/cases/{case_id}/rehearsal/state")
def get_rehearsal_state(
    case_id: str,
    candidate_id: Optional[str] = Query(None, description="Specific candidate ID"),
    advancement: float = Query(0.0, ge=0.0, le=1.0, description="Needle advancement fraction 0.0 to 1.0"),
    carm_model: str = Query("philips_zenition_70", description="C-arm hardware profile key")
):
    """Computes synchronized 4-view rehearsal state at given needle advancement fraction."""
    profile = get_carm_profile(carm_model)
    sim = PunctureRehearsalSimulator(carm_profile=profile)
    planned_traj, zone, target_name, laterality, spatial = _load_case_trajectory_or_nominal(case_id, candidate_id)

    state = sim.compute_advancement_state(planned_traj, zone, advancement, spatial)

    return {
        "case_id": case_id,
        "candidate_id": candidate_id or "default",
        "advancement_fraction": state.advancement_fraction,
        "penetration_depth_mm": state.penetration_depth_mm,
        "total_planned_depth_mm": state.total_planned_depth_mm,
        "active_progression_phase": state.active_progression_phase.value,
        "current_tip_lps": [round(float(x), 2) for x in state.current_tip_lps],
        "mpr_slice_voxel_indices": list(state.mpr_slice_voxel_indices),
        "bullseye_projection": {
            "tip_px": [round(float(x), 1) for x in state.projected_bullseye.tip_px],
            "hub_px": [round(float(x), 1) for x in state.projected_bullseye.hub_px],
            "shaft_length_px": round(state.projected_bullseye.shaft_length_px, 1),
            "is_collapsed": state.projected_bullseye.is_bullseye_collapsed
        },
        "depth_projection": {
            "tip_px": [round(float(x), 1) for x in state.projected_depth_view.tip_px],
            "hub_px": [round(float(x), 1) for x in state.projected_depth_view.hub_px],
            "shaft_length_px": round(state.projected_depth_view.shaft_length_px, 1),
            "graduation_markers_count": len(state.projected_depth_view.graduation_rings_px)
        }
    }


@router.post("/validation/procedural/evaluate")
def evaluate_procedural_cohort(request: CohortEvaluationRequest):
    """
    Evaluates a cohort of experimental needle punctures against ASTM F2554,
    reporting zone-based TLE, classifications, and exact Clopper-Pearson safety bounds.
    """
    if not request.trials:
        raise HTTPException(status_code=400, detail="Cohort must contain at least one trial")

    evaluator = ProceduralAccuracyEvaluator()
    trials_obj = []

    for t in request.trials:
        traj = LineSegment3D(
            start_point=np.array(t.planned_entry_lps),
            end_point=np.array(t.planned_target_lps)
        )
        zone = TargetFornicealZone(
            calyx_name=t.target_calyx_name,
            forniceal_apex_lps=np.array(t.planned_target_lps),
            infundibular_axis_unit=np.array(t.infundibular_axis_unit),
            papilla_radius_mm=t.papilla_radius_mm
        )
        trial = PunctureExecutionTrial(
            trial_id=t.trial_id,
            operator_id=t.operator_id,
            planned_trajectory=traj,
            physical_needle_entry_lps=np.array(t.physical_entry_lps),
            physical_needle_tip_lps=np.array(t.physical_tip_lps),
            target_zone=zone,
            is_counter_puncture_observed=t.is_counter_puncture_observed,
            is_first_pass=t.is_first_pass,
            fluoroscopy_time_seconds=t.fluoroscopy_time_seconds,
            dose_area_product_gy_cm2=t.dose_area_product_gy_cm2,
            repositioning_attempts=t.repositioning_attempts
        )
        trials_obj.append(trial)

    summary = evaluator.evaluate_cohort(
        trials=trials_obj,
        metrology_budget=STANDARD_ANTHROPOMORPHIC_SPEC.uncertainty_budget
    )
    return summary
