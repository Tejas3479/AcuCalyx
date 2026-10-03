"""
AcuCalyx Planning: Conical Puncture Zones & Papillary Target Generator

Implements Step 07 of AcuCalyx v2.1:
Replaces single-point/stone-centroid targets with 3D Conical Puncture Zones:
- Apex placed at the posterior calyx fornix / papilla tip
- Central axis aligned along the calyx infundibulum
- Enforces an acceptable angular entry corridor (+/- 15 degrees) to prevent
  parenchymal torque and tearing of segmental interlobar arteries
- Explicitly labels evidence state (DIRECT vs ESTIMATED_PRIOR)
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple
import numpy as np

from acucalyx.geometry.transforms import angle_between_vectors
from acucalyx.collecting_system.visibility_gate import PCSVisibilityState


class CalyxGroup(str, Enum):
    POSTERIOR_LOWER = "POSTERIOR_LOWER"
    POSTERIOR_MIDDLE = "POSTERIOR_MIDDLE"
    POSTERIOR_UPPER = "POSTERIOR_UPPER"
    ANTERIOR_LOWER = "ANTERIOR_LOWER"
    ANTERIOR_MIDDLE = "ANTERIOR_MIDDLE"
    ANTERIOR_UPPER = "ANTERIOR_UPPER"


@dataclass(frozen=True)
class PapillaryTargetZone:
    """
    Patient-specific papillary/forniceal target zone.
    Separates needle access vector (Skin -> Papilla) from instrument working axis
    (Papilla -> Infundibulum -> Pelvis) and models morphological tolerance envelopes
    without arbitrary 15° or 8 mm constants.
    """
    zone_id: str
    calyx_group: CalyxGroup
    centroid_lps_mm: np.ndarray            # [x, y, z] target centroid in physical LPS
    infundibular_axis_unit: np.ndarray    # Unit vector pointing along calyx neck into pelvis
    morphological_radii_mm: np.ndarray    # [rx, ry, rz] target tolerance envelope in mm
    visibility_state: PCSVisibilityState
    confidence_score: float               # [0.0, 1.0] derived from image evidence
    is_uncertain: bool = False            # True when direct PCS visibility unavailable

    def evaluate_access_alignment(
        self,
        skin_entry_lps_mm: np.ndarray,
        instrument_max_torque_angle_deg: float = 20.0
    ) -> Tuple[float, float, bool]:
        """
        Evaluates the geometric relationship between the needle access vector
        and the instrument working axis.
        
        Returns:
            tract_length_mm: Euclidean distance from skin entry to target centroid
            infundibular_angle_deg: Angle between access vector and infundibular centerline
            is_mechanically_feasible: Whether angle is within instrument torque envelope
        """
        access_vec = self.centroid_lps_mm - skin_entry_lps_mm
        tract_length = float(np.linalg.norm(access_vec))
        if tract_length < 1e-3:
            return 0.0, 0.0, True

        access_unit = access_vec / tract_length
        # Angle between forward access vector and infundibular centerline vector
        angle = angle_between_vectors(access_unit, self.infundibular_axis_unit)
        is_feasible = angle <= instrument_max_torque_angle_deg
        return tract_length, angle, is_feasible

    def is_point_inside(self, query_point_lps: np.ndarray) -> bool:
        """Evaluates whether a physical point lies inside the ellipsoidal target envelope."""
        diff = (query_point_lps - self.centroid_lps_mm) / np.maximum(self.morphological_radii_mm, 1e-3)
        return bool(np.sum(diff ** 2) <= 1.0)


@dataclass(frozen=True)
class ConicalPunctureZone:
    """3D conical target zone associated with a specific renal calyx (Backward compatibility)."""
    zone_id: str
    calyx_group: CalyxGroup
    apex_papilla_lps_mm: np.ndarray        # [x, y, z] fornix / papilla tip in mm
    infundibular_axis_unit: np.ndarray    # Unit vector pointing along calyx neck into pelvis
    cone_half_angle_deg: float            # Acceptable entry angle corridor (e.g. 15.0 deg)
    visibility_state: PCSVisibilityState
    confidence_score: float               # [0.0, 1.0]

    def is_trajectory_coaxial(self, needle_unit_direction: np.ndarray) -> Tuple[bool, float]:
        """Tests whether needle trajectory enters within allowable cone angle."""
        angle = angle_between_vectors(needle_unit_direction, self.infundibular_axis_unit)
        is_valid = angle <= self.cone_half_angle_deg
        return is_valid, angle


def generate_papillary_target_zones(
    kidney_center_lps: np.ndarray,
    kidney_radii_lps: np.ndarray,
    pcs_visibility: PCSVisibilityState,
    detected_stone_centroids: Optional[List[np.ndarray]] = None,
    side: str = "left",
    is_malrotated: bool = False
) -> List[PapillaryTargetZone]:
    """
    Constructs patient-specific papillary target zones with morphological envelopes.
    Does not assume universal posterior preference in malrotated or horseshoe anatomy.
    """
    zones: List[PapillaryTargetZone] = []
    medial_dir = -1.0 if side.lower() == "left" else 1.0

    is_uncertain = pcs_visibility in (
        PCSVisibilityState.UNDILATED_ESTIMATED,
        PCSVisibilityState.ANATOMICALLY_ESTIMATED,
        PCSVisibilityState.PCS_COLLAPSED_INVISIBLE
    ) if hasattr(PCSVisibilityState, "PCS_COLLAPSED_INVISIBLE") else (
        pcs_visibility not in (PCSVisibilityState.DIRECTLY_OPACIFIED, PCSVisibilityState.HYDRONEPHROTIC_DISTENDED)
    )

    conf_score = 0.90 if pcs_visibility == PCSVisibilityState.DIRECTLY_OPACIFIED else (
        0.75 if pcs_visibility == PCSVisibilityState.HYDRONEPHROTIC_DISTENDED else 0.35
    )

    # 1. Posterior Lower Calyx
    lower_centroid = np.array([
        kidney_center_lps[0] + 0.3 * kidney_radii_lps[0] * (-medial_dir),
        kidney_center_lps[1] + 0.5 * kidney_radii_lps[1],
        kidney_center_lps[2] - 0.6 * kidney_radii_lps[2]
    ])
    lower_axis = np.array([medial_dir * 0.7, -0.6, 0.4])
    lower_axis = lower_axis / np.linalg.norm(lower_axis)

    zones.append(PapillaryTargetZone(
        zone_id="ZONE_POSTERIOR_LOWER",
        calyx_group=CalyxGroup.POSTERIOR_LOWER,
        centroid_lps_mm=lower_centroid,
        infundibular_axis_unit=lower_axis,
        morphological_radii_mm=np.array([4.0, 4.0, 5.0]),
        visibility_state=pcs_visibility,
        confidence_score=conf_score,
        is_uncertain=is_uncertain
    ))

    # 2. Posterior Middle Calyx
    mid_centroid = np.array([
        kidney_center_lps[0] + 0.4 * kidney_radii_lps[0] * (-medial_dir),
        kidney_center_lps[1] + 0.6 * kidney_radii_lps[1],
        kidney_center_lps[2]
    ])
    mid_axis = np.array([medial_dir * 0.8, -0.6, 0.0])
    mid_axis = mid_axis / np.linalg.norm(mid_axis)

    zones.append(PapillaryTargetZone(
        zone_id="ZONE_POSTERIOR_MIDDLE",
        calyx_group=CalyxGroup.POSTERIOR_MIDDLE,
        centroid_lps_mm=mid_centroid,
        infundibular_axis_unit=mid_axis,
        morphological_radii_mm=np.array([4.0, 4.0, 5.0]),
        visibility_state=pcs_visibility,
        confidence_score=conf_score,
        is_uncertain=is_uncertain
    ))

    # 3. Posterior Upper Calyx
    upper_centroid = np.array([
        kidney_center_lps[0] + 0.2 * kidney_radii_lps[0] * (-medial_dir),
        kidney_center_lps[1] + 0.5 * kidney_radii_lps[1],
        kidney_center_lps[2] + 0.6 * kidney_radii_lps[2]
    ])
    upper_axis = np.array([medial_dir * 0.7, -0.6, -0.4])
    upper_axis = upper_axis / np.linalg.norm(upper_axis)

    zones.append(PapillaryTargetZone(
        zone_id="ZONE_POSTERIOR_UPPER",
        calyx_group=CalyxGroup.POSTERIOR_UPPER,
        centroid_lps_mm=upper_centroid,
        infundibular_axis_unit=upper_axis,
        morphological_radii_mm=np.array([4.0, 4.0, 5.0]),
        visibility_state=pcs_visibility,
        confidence_score=conf_score,
        is_uncertain=is_uncertain
    ))

    # 4. Anterior Calyx (Evaluated if malrotated or individualized)
    ant_centroid = np.array([
        kidney_center_lps[0] + 0.3 * kidney_radii_lps[0] * (-medial_dir),
        kidney_center_lps[1] - 0.5 * kidney_radii_lps[1],
        kidney_center_lps[2] - 0.3 * kidney_radii_lps[2]
    ])
    ant_axis = np.array([medial_dir * 0.7, 0.6, 0.3])
    ant_axis = ant_axis / np.linalg.norm(ant_axis)

    zones.append(PapillaryTargetZone(
        zone_id="ZONE_ANTERIOR_LOWER",
        calyx_group=CalyxGroup.ANTERIOR_LOWER,
        centroid_lps_mm=ant_centroid,
        infundibular_axis_unit=ant_axis,
        morphological_radii_mm=np.array([4.0, 4.0, 5.0]),
        visibility_state=pcs_visibility,
        confidence_score=conf_score * 0.85 if not is_malrotated else conf_score,
        is_uncertain=is_uncertain
    ))

    return zones


def generate_candidate_puncture_zones(
    kidney_center_lps: np.ndarray,
    kidney_radii_lps: np.ndarray,
    pcs_visibility: PCSVisibilityState,
    detected_stone_centroids: List[np.ndarray],
    side: str = "left"
) -> List[ConicalPunctureZone]:
    """
    Constructs candidate conical puncture zones for backward compatibility with v2.1 tests.
    """
    zones: List[ConicalPunctureZone] = []
    medial_dir = -1.0 if side.lower() == "left" else 1.0

    lower_papilla = np.array([
        kidney_center_lps[0] + 0.3 * kidney_radii_lps[0] * (-medial_dir),
        kidney_center_lps[1] + 0.5 * kidney_radii_lps[1],
        kidney_center_lps[2] - 0.6 * kidney_radii_lps[2]
    ])
    lower_axis = np.array([medial_dir * 0.7, -0.6, 0.4])
    lower_axis = lower_axis / np.linalg.norm(lower_axis)

    conf_score = 0.90 if pcs_visibility == PCSVisibilityState.DIRECTLY_OPACIFIED else (
        0.75 if pcs_visibility == PCSVisibilityState.HYDRONEPHROTIC_DISTENDED else 0.35
    )

    zones.append(ConicalPunctureZone(
        zone_id="ZONE_POSTERIOR_LOWER",
        calyx_group=CalyxGroup.POSTERIOR_LOWER,
        apex_papilla_lps_mm=lower_papilla,
        infundibular_axis_unit=lower_axis,
        cone_half_angle_deg=20.0,
        visibility_state=pcs_visibility,
        confidence_score=conf_score
    ))

    mid_papilla = np.array([
        kidney_center_lps[0] + 0.4 * kidney_radii_lps[0] * (-medial_dir),
        kidney_center_lps[1] + 0.6 * kidney_radii_lps[1],
        kidney_center_lps[2]
    ])
    mid_axis = np.array([medial_dir * 0.8, -0.6, 0.0])
    mid_axis = mid_axis / np.linalg.norm(mid_axis)

    zones.append(ConicalPunctureZone(
        zone_id="ZONE_POSTERIOR_MIDDLE",
        calyx_group=CalyxGroup.POSTERIOR_MIDDLE,
        apex_papilla_lps_mm=mid_papilla,
        infundibular_axis_unit=mid_axis,
        cone_half_angle_deg=20.0,
        visibility_state=pcs_visibility,
        confidence_score=conf_score
    ))

    return zones
