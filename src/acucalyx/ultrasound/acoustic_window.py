"""
AcuCalyx Ultrasound: Multi-Factor Flank Acoustic Window Planner
Governed by Milestone M14B of ACU-M14-EXEC-PLAN-2026-V2.

Provides:
1. Multi-factor flank acoustic window planning (rib shadow corridor intersection, pleural clearance, skin contact).
2. Categorical classification: GOOD / CONDITIONAL / POOR / UNAVAILABLE.
3. Clinical recommendations and interventional advisories.
"""

from dataclasses import dataclass, field
import enum
import math
from typing import List, Optional, Tuple
import numpy as np

from acucalyx.ultrasound.probe_profile import TransducerProfile, UltrasoundProbePose, CURVILINEAR_C5_2
from acucalyx.ultrasound.needle_ultrasound import calculate_needle_acoustic_visibility, NAVIResult


class AcousticWindowCategory(str, enum.Enum):
    GOOD = "GOOD"
    CONDITIONAL = "CONDITIONAL"
    POOR = "POOR"
    UNAVAILABLE = "UNAVAILABLE"


# Aliases
AcousticWindowStatus = AcousticWindowCategory


@dataclass(frozen=True)
class FlankAcousticWindowReport:
    """Quantitative and categorical assessment of flank acoustic access window."""
    window_category: AcousticWindowCategory
    corridor_rib_occlusion_pct: float  # Percentage of trajectory corridor shadowed by ribs (0 - 100)
    pleural_clearance_mm: float  # Distance from probe/corridor to lowest pleural reflection margin
    skin_contact_conformance_pct: float  # Footprint acoustic coupling contact percentage (0 - 100)
    navi_score: float  # Needle Acoustic Visibility Index (0 - 1.0)
    probe_id: str
    target_calyx_visible: bool
    requires_end_expiratory_apnea: bool
    recommended_probe_tilt_deg: float
    recommendations: List[str]


AcousticWindowEvaluationResult = FlankAcousticWindowReport


def evaluate_flank_acoustic_window(
    entry_point: np.ndarray,
    target_point: np.ndarray,
    rib_surface_points: Optional[np.ndarray] = None,
    pleural_reflection_z_mm: Optional[float] = None,
    probe: Optional[TransducerProfile] = None,
    skin_normal: Optional[np.ndarray] = None,
) -> FlankAcousticWindowReport:
    """
    Evaluates multi-factor acoustic window for percutaneous puncture trajectory.
    
    Parameters:
    - entry_point: 3D point on skin surface (x, y, z in mm)
    - target_point: 3D point at target calyx / stone (x, y, z in mm)
    - rib_surface_points: Optional Nx3 array of bony rib surface coordinates
    - pleural_reflection_z_mm: Optional Z-coordinate of lowest posterior pleural line
    - probe: Configurable TransducerProfile (defaults to Curvilinear C5-2)
    - skin_normal: Inward-facing skin surface normal vector
    """
    if probe is None:
        probe = CURVILINEAR_C5_2

    entry = np.asarray(entry_point, dtype=float)
    target = np.asarray(target_point, dtype=float)
    traj_vec = target - entry
    traj_len = np.linalg.norm(traj_vec)

    if traj_len < 1e-4:
        traj_dir = np.array([0.0, 0.0, 1.0])
    else:
        traj_dir = traj_vec / traj_len

    # Establish probe pose aligned with access corridor
    probe_pose = UltrasoundProbePose.create_aligned_with_trajectory(
        entry_point=entry,
        target_point=target,
    )

    # 1. Rib shadow occlusion evaluation
    rib_occlusion_pct = 0.0
    if rib_surface_points is not None and len(rib_surface_points) > 0:
        pts = np.asarray(rib_surface_points, dtype=float)
        # Sample points along the trajectory corridor (cylinder radius r = 8 mm)
        corridor_radius_mm = 8.0
        n_samples = 30
        t_vals = np.linspace(0.1, 0.9, n_samples)
        occluded_samples = 0

        for t in t_vals:
            corridor_pt = entry + t * traj_vec
            # Distance from rib points to corridor point
            dists = np.linalg.norm(pts - corridor_pt, axis=1)
            min_dist = float(np.min(dists)) if len(dists) > 0 else 999.0
            if min_dist < corridor_radius_mm:
                occluded_samples += 1

        rib_occlusion_pct = (occluded_samples / n_samples) * 100.0

    # 2. Pleural clearance calculation
    pleural_clearance = 45.0  # Safe default if not specified
    if pleural_reflection_z_mm is not None:
        # Distance along cranio-caudal axis (Z in DICOM LPS)
        # In LPS, more superior is higher Z. Puncture should be caudal (lower Z) to pleural reflection.
        z_entry = float(entry[2])
        z_target = float(target[2])
        highest_z = max(z_entry, z_target)
        pleural_clearance = pleural_reflection_z_mm - highest_z

    # 3. Skin contact conformance
    contact_pct = 95.0
    recommended_tilt = 0.0
    if skin_normal is not None:
        sn = np.asarray(skin_normal, dtype=float)
        sn = sn / np.linalg.norm(sn)
        cos_align = float(np.dot(probe_pose.axial_direction, sn))
        # Angular misalignment
        misalign_rad = math.acos(min(1.0, max(-1.0, abs(cos_align))))
        misalign_deg = math.degrees(misalign_rad)
        recommended_tilt = misalign_deg
        # Higher tilt reduces acoustic coupling contact
        contact_pct = max(40.0, 100.0 - (misalign_deg * 1.2))

    # 4. Needle Acoustic Visibility Index (NAVI)
    # Needle tangent along trajectory, beam along probe axial
    navi_eval = calculate_needle_acoustic_visibility(
        needle_tangent=traj_dir,
        beam_propagation_direction=probe_pose.axial_direction,
        elevational_offset_mm=0.0,  # In-plane alignment
        elevational_slice_fwhm_mm=probe.elevation_slice_thickness_mm,
    )

    # 5. Multi-factor Categorization
    recs = []
    target_visible = True
    req_apnea = False

    if rib_occlusion_pct > 40.0 or pleural_clearance < 0.0 or contact_pct < 50.0:
        if pleural_clearance < 0.0:
            category = AcousticWindowCategory.UNAVAILABLE
            recs.append("Trajectory breaches pleural line. High pneumothorax/hemothorax risk. Reposition below 12th rib.")
            target_visible = False
        else:
            category = AcousticWindowCategory.POOR
            recs.append("Extensive rib acoustic shadowing obscures >40% of puncture corridor.")
            recs.append("Consider alternative intercostal window, subcostal lower-pole calyx, or combined fluoroscopy.")
            target_visible = False
    elif rib_occlusion_pct > 10.0 or (0.0 <= pleural_clearance < 15.0) or contact_pct < 80.0:
        category = AcousticWindowCategory.CONDITIONAL
        if rib_occlusion_pct > 10.0:
            recs.append(f"Moderate rib acoustic shadowing ({rib_occlusion_pct:.1f}%). Adjust probe tilt by {recommended_tilt:.1f}°.")
        if pleural_clearance < 15.0:
            recs.append(f"Marginal pleural clearance ({pleural_clearance:.1f} mm). Protocol requires end-expiratory apnea.")
            req_apnea = True
        if contact_pct < 80.0:
            recs.append("Suboptimal transducer flank coupling; use generous acoustic gel or adjust entry position.")
    else:
        category = AcousticWindowCategory.GOOD
        recs.append("Clear acoustic intercostal/subcostal window to target calyx with minimal rib obstruction.")
        recs.append("Excellent candidate for ultrasound-guided puncture.")

    return FlankAcousticWindowReport(
        window_category=category,
        corridor_rib_occlusion_pct=rib_occlusion_pct,
        pleural_clearance_mm=pleural_clearance,
        skin_contact_conformance_pct=contact_pct,
        navi_score=navi_eval.navi_score,
        probe_id=probe.probe_id,
        target_calyx_visible=target_visible,
        requires_end_expiratory_apnea=req_apnea,
        recommended_probe_tilt_deg=recommended_tilt,
        recommendations=recs,
    )
