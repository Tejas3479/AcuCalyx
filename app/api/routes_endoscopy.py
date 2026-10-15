"""
AcuCalyx API: Endoscopic Reachability & Computed Endoluminal Rehearsal Routes
Governed by Milestone M15 of ACU-M15-EXEC-PLAN-2026-V2.

Provides:
- GET /api/cases/{case_id}/endoscopy/instruments: Certified commercial endoscopes and tool loading tables
- GET /api/cases/{case_id}/endoscopy/reference-phantoms: Milestone M15.0 certified phantom ground truth
- GET /api/cases/{case_id}/endoscopy/{candidate_id}/reachability: Kinematic workspace & multi-calyx access
- GET /api/cases/{case_id}/endoscopy/{candidate_id}/stone-coverage: Geometric stone-access coverage (f_geom)
- GET /api/cases/{case_id}/endoscopy/{candidate_id}/access-caliber-profiles: Descriptive Mini vs Standard PCNL trade-offs
- GET /api/cases/{case_id}/endoscopy/{candidate_id}/endoluminal-rehearsal: Fly-through camera keyframes & provenance
- GET /api/cases/{case_id}/endoscopy/validation-gate: M15-V agreement & reliability certification report
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
import numpy as np

from acucalyx.endoscopy.instrument_registry import (
    EndoscopeClass,
    WorkingChannelTool,
    ValidatedEndoscopeProfile,
    PhysicalPhantomSpecification,
    get_endoscope_profile,
    list_all_endoscopes,
    STANDARD_ENDOSCOPES,
    M15_REFERENCE_PHANTOMS,
)
from acucalyx.endoscopy.skeletonizer import (
    CollectingSystemGraph,
    build_procedural_collecting_system_graph,
)
from acucalyx.endoscopy.reachability_engine import (
    ReachabilityStatus,
    CalyxReachabilityResult,
    TrajectoryReachabilityReport,
    evaluate_trajectory_reachability,
)
from acucalyx.endoscopy.stone_coverage import (
    StoneBurdenUnit,
    StoneAccessCoverageMap,
    evaluate_geometric_stone_coverage,
)
from acucalyx.endoscopy.tract_sizing import (
    AccessCaliberComparisonReport,
    generate_access_caliber_profiles,
)
from acucalyx.endoscopy.virtual_nephroscopy import (
    ComputedEndoluminalRehearsalTrajectory,
    generate_endoluminal_rehearsal_trajectory,
)
from acucalyx.endoscopy.reachability_validator import (
    M15ValidationGateReport,
    evaluate_m15_validation_gate,
)

import re
import tempfile

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CASES_DIR = BASE_DIR / "data" / "cases"

router = APIRouter(prefix="/api/cases", tags=["Endoscopic Reachability & Virtual Nephroscopy"])


def _validate_case_id(case_id: str) -> str:
    """Validates that case_id is a secure identifier and prevents directory traversal."""
    if not re.match(r"^[A-Za-z0-9_-]+$", case_id):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid case identifier '{case_id}'. Must contain only alphanumeric characters, hyphens, or underscores."
        )
    return case_id


def _get_case_graph(case_id: str, demo_mode: bool = False) -> CollectingSystemGraph:
    """Builds or loads the collecting system graph for a specified case."""
    _validate_case_id(case_id)
    graph_path = CASES_DIR / case_id / "artifacts" / "graph.json"
    if graph_path.is_file():
        try:
            return CollectingSystemGraph.load_from_json(graph_path)
        except Exception as err:
            if not demo_mode:
                raise HTTPException(
                    status_code=422,
                    detail=f"Patient collecting-system graph for case '{case_id}' failed to load: {err}"
                )

    if not demo_mode:
        raise HTTPException(
            status_code=422,
            detail=f"No patient collecting-system graph available for case '{case_id}'. "
                   "Run pelvicalyceal segmentation/skeletonization or pass demo_mode=true for non-clinical simulation."
        )

    # In explicit demo mode, generate procedural benchmark graph
    return build_procedural_collecting_system_graph(case_id=case_id)


def _get_case_trajectory(case_id: str, candidate_id: str, demo_mode: bool = False) -> Dict[str, Any]:
    """Retrieves candidate percutaneous trajectory metadata."""
    cand_path = CASES_DIR / case_id / "artifacts" / "candidates.json"
    candidates = []
    if cand_path.is_file():
        try:
            with open(cand_path, "r") as f:
                candidates = json.load(f)
        except Exception:
            candidates = []

    if not candidates:
        meta_path = CASES_DIR / case_id / "case_meta.json"
        if meta_path.is_file():
            try:
                with open(meta_path, "r") as f:
                    meta = json.load(f)
                candidates = meta.get("plan", {}).get("candidates", [])
            except Exception:
                candidates = []

    if candidates:
        for cand in candidates:
            if cand.get("candidate_id") == candidate_id or cand.get("id") == candidate_id:
                return {
                    "candidate_id": candidate_id,
                    "entry_point": cand.get("entry_point_lps") or cand.get("entry_point"),
                    "target_point": cand.get("target_point_lps") or cand.get("target_point"),
                    "calyx_id": cand.get("target_calyx") or cand.get("calyx_id", "LP"),
                    "calyx_name": cand.get("calyx_name") or cand.get("target_calyx", "Target Calyx"),
                    "length_mm": cand.get("tract_length_mm") or cand.get("length_mm", 150.0),
                }
        # Candidates exist for case, but candidate_id was not in the list
        raise HTTPException(
            status_code=404,
            detail=f"Candidate trajectory '{candidate_id}' not found for case '{case_id}'."
        )

    # No candidates exist on disk for case
    if demo_mode:
        return {
            "candidate_id": candidate_id,
            "entry_point": [115.0, -170.0, -40.0],
            "target_point": [45.0, -10.0, -32.0],
            "calyx_id": "LP",
            "calyx_name": "Lower Posterior Calyx",
            "length_mm": 175.0,
        }

    raise HTTPException(
        status_code=404,
        detail=f"No planned candidate trajectories found for case '{case_id}' (candidate_id='{candidate_id}'). Pass demo_mode=true to evaluate procedural simulation."
    )


def _get_case_stones(case_id: str, demo_mode: bool = False) -> List[StoneBurdenUnit]:
    """Retrieves segmented calculus burden for case, or representative demo stones in demo mode."""
    stones_path = CASES_DIR / case_id / "artifacts" / "stones.json"
    stones_raw = []
    if stones_path.is_file():
        try:
            with open(stones_path, "r") as f:
                stones_raw = json.load(f)
        except Exception:
            stones_raw = []

    if not stones_raw:
        meta_path = CASES_DIR / case_id / "case_meta.json"
        if meta_path.is_file():
            try:
                with open(meta_path, "r") as f:
                    meta = json.load(f)
                stones_raw = meta.get("plan", {}).get("stones", [])
            except Exception:
                stones_raw = []

    if stones_raw:
        units = []
        for idx, s in enumerate(stones_raw):
            sid = str(s.get("stone_id", f"STONE_{idx+1}"))
            cid = s.get("calyx_id", "LP" if idx == 0 else "MP")
            vol = float(s.get("volume_mm3", 0.0))
            caliper = float(s.get("max_caliper_mm") or s.get("max_feret_diameter_mm", 10.0))
            centroid = np.array(s.get("centroid_lps_mm", [45.0, -8.0, -30.0]), dtype=float)
            hu = float(s.get("mean_hu", 1000.0))
            units.append(StoneBurdenUnit(
                stone_id=sid,
                calyx_id=cid,
                volume_mm3=vol,
                max_caliper_mm=caliper,
                centroid_lps_mm=centroid,
                hounsfield_mean=hu,
            ))
        return units

    if demo_mode:
        return [
            StoneBurdenUnit(
                stone_id="STONE_1_LP",
                calyx_id="LP",
                volume_mm3=950.0,
                max_caliper_mm=14.5,
                centroid_lps_mm=np.array([45.0, -10.0, -32.0]),
                hounsfield_mean=1120.0,
            ),
            StoneBurdenUnit(
                stone_id="STONE_2_MP",
                calyx_id="MP",
                volume_mm3=520.0,
                max_caliper_mm=10.2,
                centroid_lps_mm=np.array([52.0, -5.0, 5.0]),
                hounsfield_mean=980.0,
            ),
            StoneBurdenUnit(
                stone_id="STONE_3_MA",
                calyx_id="MA",
                volume_mm3=310.0,
                max_caliper_mm=7.8,
                centroid_lps_mm=np.array([48.0, 35.0, 2.0]),
                hounsfield_mean=860.0,
            ),
        ]

    # In patient mode with no segmented calculi, return empty list (no manufactured calculi)
    return []


# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------

@router.get("/{case_id}/endoscopy/instruments")
def list_endoscopy_instruments(case_id: str) -> Dict[str, Any]:
    """Catalog of certified commercial rigid and flexible urological endoscopes."""
    instruments = []
    for scope in list_all_endoscopes():
        loaded_table = {
            tool.value: {
                "up_deg": up,
                "down_deg": down,
                "max_deg": max(up, down),
            }
            for tool, (up, down) in scope.tool_loaded_deflection_deg.items()
        }
        instruments.append({
            "model_id": scope.model_id,
            "manufacturer": scope.manufacturer,
            "model_name": scope.model_name,
            "catalog_reference": scope.catalog_reference,
            "class": scope.endoscope_class.value,
            "is_flexible": scope.is_flexible,
            "tip_outer_diameter_fr": scope.tip_outer_diameter_fr,
            "tip_outer_diameter_mm": scope.tip_outer_diameter_mm,
            "shaft_outer_diameter_fr": scope.shaft_outer_diameter_fr,
            "shaft_outer_diameter_mm": scope.shaft_outer_diameter_mm,
            "working_length_mm": scope.working_length_mm,
            "working_channel_inner_diameter_fr": scope.working_channel_inner_diameter_fr,
            "field_of_view_deg": scope.field_of_view_deg,
            "direction_of_view_deg": scope.direction_of_view_deg,
            "nominal_deflection_up_deg": scope.nominal_deflection_up_deg,
            "nominal_deflection_down_deg": scope.nominal_deflection_down_deg,
            "min_bend_radius_mm": scope.min_bend_radius_mm,
            "access_sheath_compatibility_fr_min": scope.access_sheath_compatibility_fr_min,
            "tool_loaded_deflection_deg": loaded_table,
            "ifu_reference": scope.ifu_document_reference,
        })

    return {
        "case_id": case_id,
        "instruments": instruments,
        "default_instrument_id": "OLYMPUS_URF_V3",
        "available_tools": [t.value for t in WorkingChannelTool],
    }


@router.get("/{case_id}/endoscopy/reference-phantoms")
def get_endoscopy_reference_phantoms(case_id: str) -> Dict[str, Any]:
    """Milestone M15.0 certified transparent silicone phantom specifications."""
    phantoms = []
    for pid, p in M15_REFERENCE_PHANTOMS.items():
        calyces_summary = {}
        for cid, c in p.calyces.items():
            calyces_summary[cid] = {
                "calyx_group": c.calyx_group,
                "ipa_true_deg": c.ipa_true_deg,
                "iw_min_true_mm": c.iw_min_true_mm,
                "il_true_mm": c.il_true_mm,
                "rigid_accessible": c.is_rigid_accessible_from_lower,
                "flexible_accessible_unloaded": c.is_flexible_accessible_unloaded,
                "flexible_accessible_loaded_200um": c.is_flexible_accessible_loaded_200um,
                "flexible_accessible_loaded_365um": c.is_flexible_accessible_loaded_365um,
            }
        phantoms.append({
            "phantom_id": p.phantom_id,
            "description": p.description,
            "material": p.material,
            "refractive_index": p.refractive_index,
            "fiducials_count": p.fiducials_count,
            "pelvis_volume_mm3": p.pelvis_volume_mm3,
            "calyces": calyces_summary,
        })

    return {
        "case_id": case_id,
        "reference_phantoms": phantoms,
        "standard_protocol": "ISO/IEC Bench Evaluation with Sub-millimeter Optical Tracking",
    }


@router.get("/{case_id}/endoscopy/{candidate_id}/reachability")
def get_trajectory_reachability(
    case_id: str,
    candidate_id: str,
    instrument_model_id: str = Query("OLYMPUS_URF_V3", description="Validated endoscope model ID"),
    tool: str = Query("LASER_FIBER_200UM", description="Working channel tool configuration"),
    demo_mode: bool = Query(False, description="Explicit flag allowing synthetic demo data when true; patient mode (False) fails closed if case artifacts are missing"),
) -> Dict[str, Any]:
    """Evaluates multi-calyceal reachability from candidate trajectory sheath axis."""
    try:
        scope = get_endoscope_profile(instrument_model_id)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        tool_enum = WorkingChannelTool(tool)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid tool '{tool}'. Choose from: {[t.value for t in WorkingChannelTool]}")

    graph = _get_case_graph(case_id, demo_mode=demo_mode)
    cand = _get_case_trajectory(case_id, candidate_id, demo_mode=demo_mode)

    target_pt = np.array(cand.get("target_point", [45.0, -10.0, -32.0]), dtype=float)
    entry_pt = np.array(cand.get("entry_point", [115.0, -170.0, -40.0]), dtype=float)
    tract_vec = target_pt - entry_pt
    tract_unit = tract_vec / (np.linalg.norm(tract_vec) + 1e-6)

    # Sheath tip position is advanced 5 mm beyond papillary puncture into calyx neck
    sheath_tip = target_pt + 5.0 * tract_unit
    entered_calyx_id = cand.get("calyx_id", "LP")

    report = evaluate_trajectory_reachability(
        graph=graph,
        trajectory_id=candidate_id,
        entered_calyx_id=entered_calyx_id,
        sheath_tip_lps=sheath_tip,
        tract_unit_vector=tract_unit,
        instrument_model_id=instrument_model_id,
        tool=tool_enum,
    )

    results_out = {}
    for cid, res in report.calyx_results.items():
        results_out[cid] = {
            "calyx_id": res.calyx_id,
            "calyx_group": res.calyx_group,
            "status": res.status.value,
            "is_reachable": res.is_reachable,
            "is_rigid_reachable": res.is_rigid_reachable,
            "is_flexible_reachable": res.is_flexible_reachable,
            "required_deflection_deg": round(res.required_deflection_deg, 1),
            "active_deflection_limit_deg": round(res.active_deflection_limit_deg, 1),
            "min_lumen_feret_mm": round(res.min_lumen_feret_mm, 2),
            "instrument_outer_diameter_mm": round(res.instrument_outer_diameter_mm, 2),
            "clearance_margin_mm": round(res.clearance_margin_mm, 2),
            "infundibulopelvic_angle_deg": round(res.infundibulopelvic_angle_deg, 1),
            "path_length_from_sheath_mm": round(res.path_length_from_sheath_mm, 1),
            "max_path_curvature": round(res.max_path_curvature, 4),
            "confidence_score": round(res.confidence_score, 2),
            "alternative_strategies": res.alternative_strategies,
            "rationale": res.rationale,
        }

    return {
        "case_id": case_id,
        "candidate_id": candidate_id,
        "provenance_mode": "SYNTHETIC_DEMO_NON_CLINICAL" if demo_mode else "PATIENT_DERIVED_VERIFIED",
        "entered_calyx_id": entered_calyx_id,
        "instrument_model_id": instrument_model_id,
        "instrument_name": scope.model_name,
        "tool_configuration": tool_enum.value,
        "overall_reachability_fraction": round(report.overall_reachability_fraction, 3),
        "reachable_calyces_count": len(report.reachable_calyx_ids),
        "total_calyces_count": len(graph.calyces),
        "reachable_calyx_ids": report.reachable_calyx_ids,
        "unreachable_calyx_ids": report.unreachable_calyx_ids,
        "rigid_accessible_calyx_ids": report.rigid_accessible_calyx_ids,
        "flexible_accessible_calyx_ids": report.flexible_accessible_calyx_ids,
        "sheath_tip_lps_mm": [round(float(v), 2) for v in report.sheath_tip_lps_mm],
        "strategic_advisory": report.strategic_advisory,
        "calyces": results_out,
    }


@router.get("/{case_id}/endoscopy/{candidate_id}/stone-coverage")
def get_stone_access_coverage(
    case_id: str,
    candidate_id: str,
    instrument_model_id: str = Query("OLYMPUS_URF_V3", description="Validated endoscope model ID"),
    tool: str = Query("LASER_FIBER_200UM", description="Working channel tool configuration"),
    demo_mode: bool = Query(False, description="Explicit flag allowing synthetic demo data when true; patient mode (False) fails closed if case artifacts are missing"),
) -> Dict[str, Any]:
    """Computes continuous volumetric stone access coverage estimate f_geom."""
    try:
        scope = get_endoscope_profile(instrument_model_id)
        tool_enum = WorkingChannelTool(tool)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    graph = _get_case_graph(case_id, demo_mode=demo_mode)
    cand = _get_case_trajectory(case_id, candidate_id, demo_mode=demo_mode)
    stones = _get_case_stones(case_id, demo_mode=demo_mode)

    target_pt = np.array(cand.get("target_point", [45.0, -10.0, -32.0]), dtype=float)
    entry_pt = np.array(cand.get("entry_point", [115.0, -170.0, -40.0]), dtype=float)
    tract_vec = target_pt - entry_pt
    tract_unit = tract_vec / (np.linalg.norm(tract_vec) + 1e-6)
    sheath_tip = target_pt + 5.0 * tract_unit
    entered_calyx_id = cand.get("calyx_id", "LP")

    reach_report = evaluate_trajectory_reachability(
        graph=graph,
        trajectory_id=candidate_id,
        entered_calyx_id=entered_calyx_id,
        sheath_tip_lps=sheath_tip,
        tract_unit_vector=tract_unit,
        instrument_model_id=instrument_model_id,
        tool=tool_enum,
    )

    coverage_map = evaluate_geometric_stone_coverage(
        reachability_report=reach_report,
        stones=stones,
        graph=graph,
    )

    stone_items_out = []
    for item in coverage_map.stone_items:
        stone_items_out.append({
            "stone_id": item.stone_id,
            "calyx_id": item.calyx_id,
            "total_volume_mm3": round(item.total_volume_mm3, 1),
            "accessible_volume_mm3": round(item.accessible_volume_mm3, 1),
            "coverage_fraction": round(item.coverage_fraction, 3),
            "access_class": item.access_class.value,
            "access_mode": item.access_mode,
            "rationale": item.rationale,
        })

    return {
        "case_id": case_id,
        "candidate_id": candidate_id,
        "provenance_mode": "SYNTHETIC_DEMO_NON_CLINICAL" if demo_mode else "PATIENT_DERIVED_VERIFIED",
        "instrument_model_id": instrument_model_id,
        "instrument_name": scope.model_name,
        "tool_configuration": tool_enum.value,
        "total_stone_volume_mm3": round(coverage_map.total_stone_volume_mm3, 1),
        "total_accessible_volume_mm3": round(coverage_map.total_accessible_volume_mm3, 1),
        "geometric_coverage_estimate_percent": round(coverage_map.geometric_coverage_estimate_percent, 1),
        "directly_reachable_volume_mm3": round(coverage_map.directly_reachable_volume_mm3, 1),
        "flexibly_accessible_volume_mm3": round(coverage_map.flexibly_accessible_volume_mm3, 1),
        "geometrically_restricted_volume_mm3": round(coverage_map.geometrically_restricted_volume_mm3, 1),
        "angularly_restricted_volume_mm3": round(coverage_map.angularly_restricted_volume_mm3, 1),
        "uncertain_volume_mm3": round(coverage_map.uncertain_volume_mm3, 1),
        "fully_accessible_stone_ids": coverage_map.fully_accessible_stone_ids,
        "partially_accessible_stone_ids": coverage_map.partially_accessible_stone_ids,
        "inaccessible_stone_ids": coverage_map.inaccessible_stone_ids,
        "descriptive_notice": coverage_map.descriptive_notice,
        "alternative_strategy_candidates": coverage_map.alternative_strategy_candidates,
        "stones": stone_items_out,
    }


@router.get("/{case_id}/endoscopy/{candidate_id}/access-caliber-profiles")
def get_access_caliber_profiles(
    case_id: str,
    candidate_id: str,
    demo_mode: bool = Query(False, description="Explicit flag allowing synthetic demo data when true; patient mode (False) fails closed if case artifacts are missing"),
) -> Dict[str, Any]:
    """Generates comparative descriptive access-caliber compatibility profiles."""
    graph = _get_case_graph(case_id, demo_mode=demo_mode)
    cand = _get_case_trajectory(case_id, candidate_id, demo_mode=demo_mode)
    stones = _get_case_stones(case_id, demo_mode=demo_mode)

    total_vol = sum(s.volume_mm3 for s in stones)
    max_caliper = max((s.max_caliper_mm for s in stones), default=10.0)
    target_cid = cand.get("calyx_id", "LP")

    report = generate_access_caliber_profiles(
        case_id=case_id,
        candidate_id=candidate_id,
        target_calyx_id=target_cid,
        graph=graph,
        total_stone_volume_mm3=total_vol,
        max_stone_caliper_mm=max_caliper,
    )

    profiles_out = {}
    for pk, prof in report.profiles.items():
        profiles_out[pk] = {
            "caliber_class": prof.caliber_class.value,
            "sheath_french": prof.sheath_french,
            "sheath_outer_diameter_mm": prof.sheath_outer_diameter_mm,
            "sheath_inner_diameter_mm": prof.sheath_inner_diameter_mm,
            "infundibular_clearance_status": prof.infundibular_clearance_status,
            "minimum_lumen_feret_required_mm": prof.minimum_lumen_feret_required_mm,
            "actual_infundibulum_feret_min_mm": round(prof.actual_infundibulum_feret_min_mm, 2),
            "primary_lithotripsy_modality": prof.primary_lithotripsy_modality,
            "evacuation_mechanism": prof.evacuation_mechanism,
            "relative_operative_tradeoffs": prof.relative_operative_tradeoffs,
            "clinical_governance_notice": prof.clinical_governance_notice,
        }

    return {
        "case_id": case_id,
        "candidate_id": candidate_id,
        "provenance_mode": "SYNTHETIC_DEMO_NON_CLINICAL" if demo_mode else "PATIENT_DERIVED_VERIFIED",
        "target_calyx_id": target_cid,
        "total_stone_volume_mm3": round(total_vol, 1),
        "max_stone_caliper_mm": round(max_caliper, 1),
        "target_calyx_min_feret_mm": round(report.target_calyx_min_feret_mm, 2),
        "profiles": profiles_out,
        "descriptive_summary": report.descriptive_summary,
        "intrarenal_pressure_context": report.intrarenal_pressure_context,
        "guideline_reference": report.governing_guideline_reference,
    }


@router.get("/{case_id}/endoscopy/{candidate_id}/endoluminal-rehearsal")
def get_endoluminal_rehearsal_flythrough(
    case_id: str,
    candidate_id: str,
    target_calyx_id: Optional[str] = Query(None, description="Destination calyx for rehearsal navigation"),
    instrument_model_id: str = Query("OLYMPUS_URF_V3", description="Validated endoscope model ID"),
    tool: str = Query("LASER_FIBER_200UM", description="Working channel tool configuration"),
    demo_mode: bool = Query(False, description="Explicit flag allowing synthetic demo data when true; patient mode (False) fails closed if case artifacts are missing"),
) -> Dict[str, Any]:
    """Generates computed endoluminal rehearsal keyframes with camera poses and HUD telemetry."""
    try:
        scope = get_endoscope_profile(instrument_model_id)
        tool_enum = WorkingChannelTool(tool)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    graph = _get_case_graph(case_id, demo_mode=demo_mode)
    cand = _get_case_trajectory(case_id, candidate_id, demo_mode=demo_mode)
    stones = _get_case_stones(case_id, demo_mode=demo_mode)

    target_pt = np.array(cand.get("target_point", [45.0, -10.0, -32.0]), dtype=float)
    entry_pt = np.array(cand.get("entry_point", [115.0, -170.0, -40.0]), dtype=float)
    tract_vec = target_pt - entry_pt
    tract_unit = tract_vec / (np.linalg.norm(tract_vec) + 1e-6)
    sheath_tip = target_pt + 5.0 * tract_unit
    entered_calyx_id = cand.get("calyx_id", "LP")

    # If target calyx is not specified, default to entered calyx or first secondary calyx
    if not target_calyx_id or target_calyx_id not in graph.calyces:
        target_calyx_id = "MP" if "MP" in graph.calyces else entered_calyx_id

    trajectory = generate_endoluminal_rehearsal_trajectory(
        graph=graph,
        trajectory_id=candidate_id,
        entered_calyx_id=entered_calyx_id,
        target_calyx_id=target_calyx_id,
        sheath_tip_lps=sheath_tip,
        tract_unit_vector=tract_unit,
        instrument_model_id=instrument_model_id,
        tool=tool_enum,
        stones=stones,
    )

    keyframes_out = []
    for kf in trajectory.keyframes:
        keyframes_out.append({
            "frame_index": kf.frame_index,
            "arc_length_s": round(kf.arc_length_s, 2),
            "camera_position_lps": [round(float(v), 2) for v in kf.camera_position_lps_mm],
            "camera_forward_vector": [round(float(v), 4) for v in kf.camera_forward_vector],
            "camera_up_vector": [round(float(v), 4) for v in kf.camera_up_vector],
            "quaternion": [round(float(v), 4) for v in kf.quaternion_orientation],
            "current_calyx_id": kf.current_calyx_id,
            "current_calyx_group": kf.current_calyx_group,
            "anatomy_provenance": kf.anatomy_provenance,
            "active_deflection_deg": round(kf.active_deflection_deg, 1),
            "max_deflection_deg": round(kf.max_deflection_deg, 1),
            "min_feret_diameter_mm": round(kf.min_feret_diameter_mm, 2),
            "visible_stone_ids": kf.visible_stone_ids,
            "synthetic_disclaimer": kf.synthetic_rendering_disclaimer,
        })

    return {
        "case_id": case_id,
        "candidate_id": candidate_id,
        "provenance_mode": "SYNTHETIC_DEMO_NON_CLINICAL" if demo_mode else "PATIENT_DERIVED_VERIFIED",
        "entered_calyx_id": entered_calyx_id,
        "target_calyx_id": target_calyx_id,
        "instrument_model_id": instrument_model_id,
        "instrument_name": scope.model_name,
        "tool_configuration": tool_enum.value,
        "total_path_length_mm": round(trajectory.total_path_length_mm, 1),
        "field_of_view_deg": trajectory.field_of_view_deg,
        "direction_of_view_deg": trajectory.direction_of_view_deg,
        "synthetic_rendering_notice": trajectory.synthetic_rendering_notice,
        "keyframes_count": len(keyframes_out),
        "keyframes": keyframes_out,
    }


@router.get("/{case_id}/endoscopy/validation-gate")
def get_m15_validation_gate_report(
    case_id: str,
    manifest_path: Optional[str] = Query(None, description="Optional path to locked reference manifest JSON")
) -> Dict[str, Any]:
    """Milestone M15-V agreement, calibration, and physical concordance report."""
    _validate_case_id(case_id)
    safe_manifest_path: Optional[Path] = None
    if manifest_path is not None:
        p = Path(manifest_path)
        if ".." in p.parts:
            raise HTTPException(status_code=400, detail="Path traversal sequences ('..') are strictly prohibited in manifest path.")
        
        if not p.is_absolute():
            resolved = (BASE_DIR / p).resolve()
        else:
            resolved = p.resolve()

        # Confine manifest path to project directory or system temp directory
        temp_dir = Path(tempfile.gettempdir()).resolve()
        base_dir_resolved = BASE_DIR.resolve()
        is_in_base = False
        is_in_temp = False
        try:
            resolved.relative_to(base_dir_resolved)
            is_in_base = True
        except ValueError:
            pass
        try:
            resolved.relative_to(temp_dir)
            is_in_temp = True
        except ValueError:
            pass

        if not (is_in_base or is_in_temp):
            raise HTTPException(status_code=403, detail="Manifest path must be confined within the application directory.")

        if resolved.suffix.lower() != ".json":
            raise HTTPException(status_code=400, detail="Manifest file must be a JSON document (.json).")
        safe_manifest_path = resolved

    report = evaluate_m15_validation_gate(manifest_path=safe_manifest_path)
    ipa_dict = None
    if report.ipa_validation:
        ipa_dict = {
            "parameter": report.ipa_validation.parameter_name,
            "sample_size": report.ipa_validation.sample_size,
            "mean_absolute_error_deg": round(report.ipa_validation.mean_absolute_error, 2),
            "root_mean_square_error_deg": round(report.ipa_validation.root_mean_square_error, 2),
            "systematic_bias_deg": round(report.ipa_validation.systematic_bias, 2),
            "bland_altman_95_limits_deg": [
                round(report.ipa_validation.bland_altman_lower_limit_95, 2),
                round(report.ipa_validation.bland_altman_upper_limit_95, 2),
            ],
            "threshold_deg": report.ipa_validation.mae_threshold,
            "passed": report.ipa_validation.passed,
            "details": report.ipa_validation.details,
        }

    iw_dict = None
    if report.iw_validation:
        iw_dict = {
            "parameter": report.iw_validation.parameter_name,
            "sample_size": report.iw_validation.sample_size,
            "mean_absolute_error_mm": round(report.iw_validation.mean_absolute_error, 2),
            "root_mean_square_error_mm": round(report.iw_validation.root_mean_square_error, 2),
            "systematic_bias_mm": round(report.iw_validation.systematic_bias, 2),
            "bland_altman_95_limits_mm": [
                round(report.iw_validation.bland_altman_lower_limit_95, 2),
                round(report.iw_validation.bland_altman_upper_limit_95, 2),
            ],
            "threshold_mm": report.iw_validation.mae_threshold,
            "passed": report.iw_validation.passed,
            "details": report.iw_validation.details,
        }

    class_dict = None
    if report.classification_metrics:
        class_dict = {
            "total_evaluations": report.classification_metrics.total_evaluations,
            "sensitivity": round(report.classification_metrics.sensitivity, 3),
            "specificity": round(report.classification_metrics.specificity, 3),
            "accuracy": round(report.classification_metrics.accuracy, 3),
            "cohens_kappa": round(report.classification_metrics.cohens_kappa, 3),
            "kappa_95_ci": [
                round(report.classification_metrics.kappa_ci_lower_95, 3),
                round(report.classification_metrics.kappa_ci_upper_95, 3),
            ],
            "passed": report.classification_metrics.passed,
        }

    irr_dict = None
    if report.inter_rater_reliability:
        irr_dict = {
            "parameter": report.inter_rater_reliability.parameter_name,
            "num_cases": report.inter_rater_reliability.num_cases,
            "num_raters": report.inter_rater_reliability.num_raters,
            "icc_2_1": round(report.inter_rater_reliability.icc_value, 3) if report.inter_rater_reliability.icc_value is not None else None,
            "interpretation": report.inter_rater_reliability.agreement_interpretation,
            "threshold": report.inter_rater_reliability.icc_threshold,
            "passed": report.inter_rater_reliability.passed,
        }

    phantom_dict = None
    if report.phantom_concordance:
        phantom_dict = {
            "total_calyces": report.phantom_concordance.total_phantom_calyces,
            "concordant_evaluations": report.phantom_concordance.concordant_evaluations,
            "critical_discrepancies": report.phantom_concordance.critical_discrepancies,
            "concordance_rate_percent": round(report.phantom_concordance.concordance_rate_percent, 1),
            "passed": report.phantom_concordance.passed,
        }

    return {
        "case_id": case_id,
        "gate_identifier": report.gate_identifier,
        "status": report.status,
        "overall_gate_passed": report.overall_gate_passed,
        "validation_timestamp": report.validation_timestamp,
        "summary_findings": report.summary_findings,
        "ipa_agreement": ipa_dict,
        "iw_agreement": iw_dict,
        "reachability_classification": class_dict,
        "inter_rater_reliability": irr_dict,
        "physical_phantom_concordance": phantom_dict,
    }
