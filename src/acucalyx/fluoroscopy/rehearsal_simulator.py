"""
AcuCalyx Fluoroscopy: Surgical Puncture Rehearsal Simulator & State Engine (Phase 5 / M3)

Governing Requirement: Frozen Plan v5.1 (Section 8.2 & Section 8.3)
Implements:
1. 4-View Synchronized Rehearsal State across the anatomical progression sequence:
   Skin Entry -> Parenchymal Tunnel -> Papillary Target Zone -> Collecting Lumen -> Calculus
2. Continuous needle advancement slider (0.0 to 1.0) with real-time SE(3) projected overlays:
   - 3D physical position
   - 2D MPR slice coordinate tracking
   - Bull's-Eye View en-face projection
   - Depth-Verification View lateral shaft projection
3. C-Arm Technician Transfer Card (ALARA presets, primary/secondary gantry angles, pulse rate).
"""

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from acucalyx.fluoroscopy.carm_profile import CArmProfile, PHILIPS_ZENITION_70
from acucalyx.fluoroscopy.needle_renderer import (
    NeedleProfile,
    ProjectedNeedleOverlay,
    STANDARD_CHIBA_18G,
    project_needle_onto_drr,
)
from acucalyx.fluoroscopy.surgical_pose import (
    CArmPoseGeometry,
    construct_bullseye_carm_pose,
    construct_depth_verification_carm_pose,
)
from acucalyx.geometry.coordinates import SpatialOrientation
from acucalyx.geometry.transforms import LineSegment3D
from acucalyx.validation.procedural_evaluator import TargetFornicealZone


class AnatomicalProgressionPhase(str, Enum):
    """Clinical anatomical milestone during needle advancement."""
    SKIN_ENTRY = "SKIN_ENTRY"
    PARENCHYMAL_TUNNEL = "PARENCHYMAL_TUNNEL"
    PAPILLARY_TARGET_ZONE = "PAPILLARY_TARGET_ZONE"
    COLLECTING_SYSTEM_LUMEN = "COLLECTING_SYSTEM_LUMEN"
    CALCULUS_CONTACT = "CALCULUS_CONTACT"


@dataclass(frozen=True)
class CarmTechnicianTransferCard:
    """Standardized C-arm positioning instruction card for the radiologic technician."""
    case_id: str
    target_calyx: str
    bullseye_view_label: str
    bullseye_primary_angle_deg: float      # LAO (+) / RAO (-)
    bullseye_secondary_angle_deg: float    # CRAN (+) / CAUD (-)
    depth_view_label: str
    depth_primary_angle_deg: float
    depth_secondary_angle_deg: float
    recommended_pulse_rate_pps: int = 8
    alara_collimation_hint: str = "Tight collimation centered on target renal calyx extent"
    procedural_checklist: List[str] = field(default_factory=list)
    laterality: str = "LEFT"
    carm_model: str = "Philips Zenition 70"
    calibration_revision: str = "CAL-REV-2026A"
    projection_confidence: str = "DEVICE_PROFILE_CALIBRATED"
    mandatory_assumption_block: str = (
        "VIRTUAL PREOPERATIVE PLAN ASSUMPTION BLOCK: Starting projection poses are calculated from "
        "preoperative CT DICOM coordinates, assumed operative positioning, and calibrated C-arm kinematics. "
        "Actual intraoperative gantry position must be independently verified by the surgical team under live imaging."
    )


@dataclass
class RehearsalState:
    """Synchronized multi-view state at a given needle advancement percentage."""
    advancement_fraction: float            # 0.0 (skin entry) to 1.0 (calyx target)
    current_tip_lps: np.ndarray            # [x, y, z] in mm
    active_progression_phase: AnatomicalProgressionPhase
    penetration_depth_mm: float
    total_planned_depth_mm: float
    projected_bullseye: ProjectedNeedleOverlay
    projected_depth_view: ProjectedNeedleOverlay
    mpr_slice_voxel_indices: Tuple[int, int, int] # [i, j, k] for axial, coronal, sagittal slices


class PunctureRehearsalSimulator:
    """
    Simulates continuous virtual needle insertion for preoperative rehearsal,
    coordinating 3D geometry, 2D MPR tracking, and dual-monitor C-arm fluoroscopy.
    """

    def __init__(
        self,
        carm_profile: CArmProfile = PHILIPS_ZENITION_70,
        needle_profile: NeedleProfile = STANDARD_CHIBA_18G
    ):
        self.carm_profile = carm_profile
        self.needle_profile = needle_profile

    def generate_transfer_card(
        self,
        case_id: str,
        target_calyx_name: str,
        planned_trajectory: LineSegment3D,
        laterality: str = "LEFT",
        oblique_angle_deg: float = 30.0
    ) -> CarmTechnicianTransferCard:
        """Generates ALARA-compliant gantry angle presets for the operative team."""
        be_pose = construct_bullseye_carm_pose(planned_trajectory, profile=self.carm_profile)
        dv_pose = construct_depth_verification_carm_pose(
            planned_trajectory,
            oblique_angle_offset_deg=oblique_angle_deg,
            profile=self.carm_profile
        )

        checklist = [
            f"1. Position C-arm for Bull's-Eye View: Primary {be_pose.gantry_primary_angle_deg:.1f}°, Secondary {be_pose.gantry_secondary_angle_deg:.1f}°.",
            "2. Align skin needle hub and tip en-face over target calyx fornix.",
            f"3. Switch to Depth View ({oblique_angle_deg:.0f}° oblique): Primary {dv_pose.gantry_primary_angle_deg:.1f}°, Secondary {dv_pose.gantry_secondary_angle_deg:.1f}°.",
            "4. Monitor needle depth markings to confirm papillary entry and avoid counter-puncture.",
            "5. Note: All starting poses are virtual planning estimates and must be independently verified under live low-dose imaging."
        ]

        return CarmTechnicianTransferCard(
            case_id=case_id,
            target_calyx=target_calyx_name,
            bullseye_view_label="Bull's-Eye (En-Face Infundibular Alignment)",
            bullseye_primary_angle_deg=round(be_pose.gantry_primary_angle_deg, 1),
            bullseye_secondary_angle_deg=round(be_pose.gantry_secondary_angle_deg, 1),
            depth_view_label=f"Depth-Verification ({oblique_angle_deg:.0f}° Oblique Profile)",
            depth_primary_angle_deg=round(dv_pose.gantry_primary_angle_deg, 1),
            depth_secondary_angle_deg=round(dv_pose.gantry_secondary_angle_deg, 1),
            recommended_pulse_rate_pps=8,
            alara_collimation_hint=f"Tight collimation bounded by {laterality.upper()} target calyx and access corridor anatomy",
            procedural_checklist=checklist,
            laterality=laterality.upper(),
            carm_model=self.carm_profile.model_name,
            calibration_revision=self.carm_profile.calibration_revision_id,
            projection_confidence=self.carm_profile.projection_confidence.value
        )

    def compute_advancement_state(
        self,
        planned_trajectory: LineSegment3D,
        target_zone: TargetFornicealZone,
        advancement_fraction: float,
        spatial: SpatialOrientation,
        output_resolution: Tuple[int, int] = (512, 512)
    ) -> RehearsalState:
        """
        Computes 4-view synchronized surgical state at a specific advancement step.
        """
        frac = float(np.clip(advancement_fraction, 0.0, 1.0))
        total_depth = planned_trajectory.length

        start_pt = planned_trajectory.start_point
        end_pt = planned_trajectory.end_point
        current_tip = start_pt + frac * (end_pt - start_pt)
        penetration_depth = frac * total_depth

        # Partial needle line segment representing inserted needle length
        # (with small epsilon at fraction 0.0 to maintain well-defined direction)
        eff_frac = max(frac, 1e-4)
        effective_tip = start_pt + eff_frac * (end_pt - start_pt)
        active_segment = LineSegment3D(start_point=start_pt, end_point=effective_tip)

        # Determine anatomical progression milestone
        if frac <= 0.05:
            phase = AnatomicalProgressionPhase.SKIN_ENTRY
        elif frac < 0.85:
            phase = AnatomicalProgressionPhase.PARENCHYMAL_TUNNEL
        elif target_zone.contains_point(current_tip):
            phase = AnatomicalProgressionPhase.PAPILLARY_TARGET_ZONE
        elif frac >= 0.98:
            phase = AnatomicalProgressionPhase.CALCULUS_CONTACT
        else:
            phase = AnatomicalProgressionPhase.COLLECTING_SYSTEM_LUMEN

        # Poses for Bull's-Eye and Depth views
        be_pose = construct_bullseye_carm_pose(planned_trajectory, profile=self.carm_profile)
        dv_pose = construct_depth_verification_carm_pose(planned_trajectory, profile=self.carm_profile)

        proj_be = project_needle_onto_drr(
            active_segment, be_pose, self.needle_profile, output_resolution
        )
        proj_dv = project_needle_onto_drr(
            active_segment, dv_pose, self.needle_profile, output_resolution
        )

        # 2D MPR Voxel coordinate tracking
        vox_coords = spatial.physical_to_voxel(current_tip)
        mpr_indices = (int(round(vox_coords[0])), int(round(vox_coords[1])), int(round(vox_coords[2])))

        return RehearsalState(
            advancement_fraction=round(frac, 3),
            current_tip_lps=current_tip,
            active_progression_phase=phase,
            penetration_depth_mm=round(penetration_depth, 2),
            total_planned_depth_mm=round(total_depth, 2),
            projected_bullseye=proj_be,
            projected_depth_view=proj_dv,
            mpr_slice_voxel_indices=mpr_indices
        )
