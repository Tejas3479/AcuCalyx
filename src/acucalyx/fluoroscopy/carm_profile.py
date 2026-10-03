"""
AcuCalyx Fluoroscopy: C-Arm Device Profile Abstraction (Frozen v4.1)

Implements Step 4.00 of Phase 4:
Replaces hardcoded geometric constants with device-specific profiles covering:
- Manufacturer and model specifications (Philips, Siemens, GE)
- Source-to-Detector (SID) and Source-to-Isocenter (SOD) distances
- Flat-panel detector resolution, pixel pitch, and field-of-view
- Gantry rotational axes and mechanical reachability envelopes
- Default fluoroscopy polarity and magnification modes
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class ProjectionConfidence(str, Enum):
    """Clinical confidence grade of the C-arm projection geometry."""
    CALIBRATED_PHANTOM = "CALIBRATED_PHANTOM"
    DEVICE_PROFILE_CALIBRATED = "DEVICE_PROFILE_CALIBRATED"
    GENERIC_PROFILE = "GENERIC_PROFILE"
    ASSUMED_UNVERIFIED = "ASSUMED_UNVERIFIED"


@dataclass(frozen=True)
class CArmProfile:
    """Hardware specifications and kinematic envelopes of a mobile C-arm."""
    manufacturer: str              # 'Siemens', 'Philips', 'GE'
    model_name: str                # 'Cios_Alpha', 'Zenition_70', 'OEC_Elite'
    source_to_detector_distance_mm: float # e.g. 993.0 to 1000.0 mm
    source_to_isocenter_distance_mm: float # e.g. 600.0 to 750.0 mm
    detector_width_px: int         # e.g. 512, 1024
    detector_height_px: int        # e.g. 512, 1024
    pixel_pitch_mm: Tuple[float, float] # e.g. (0.28, 0.28) mm
    primary_axis_name: str         # 'ORBITAL' or 'LAO_RAO'
    secondary_axis_name: str       # 'ANGULATION' or 'CRAN_CAUD'
    primary_min_max_deg: Tuple[float, float]   # e.g. (-50.0, 90.0)
    secondary_min_max_deg: Tuple[float, float] # e.g. (-45.0, 45.0)
    default_polarity: str = "INVERTED_FLUOROSCOPY"  # Configurable display preference
    magnification_modes: Dict[str, float] = field(default_factory=lambda: {'NORM': 1.0, 'MAG1': 1.25, 'MAG2': 1.5})
    firmware_version: str = "v1.0"
    calibration_revision_id: str = "CAL-REV-2026A"
    principal_point_px: Tuple[float, float] = (512.0, 512.0)
    projection_confidence: ProjectionConfidence = ProjectionConfidence.DEVICE_PROFILE_CALIBRATED
    distortion_coefficients: Optional[List[float]] = None

    @property
    def detector_physical_width_mm(self) -> float:
        return self.detector_width_px * self.pixel_pitch_mm[0]

    @property
    def detector_physical_height_mm(self) -> float:
        return self.detector_height_px * self.pixel_pitch_mm[1]

    def validate_gantry_angles(
        self,
        primary_angle_deg: float,
        secondary_angle_deg: float
    ) -> Tuple[bool, Optional[str]]:
        """Verifies if the requested angles fall within this machine's physical reach."""
        p_min, p_max = self.primary_min_max_deg
        s_min, s_max = self.secondary_min_max_deg

        if not (p_min <= primary_angle_deg <= p_max):
            return False, (
                f"Primary {self.primary_axis_name} angle ({primary_angle_deg:.1f}°) exceeds "
                f"{self.model_name} mechanical limits [{p_min:.1f}°, {p_max:.1f}°]."
            )

        if not (s_min <= secondary_angle_deg <= s_max):
            return False, (
                f"Secondary {self.secondary_axis_name} angle ({secondary_angle_deg:.1f}°) exceeds "
                f"{self.model_name} mechanical limits [{s_min:.1f}°, {s_max:.1f}°]."
            )

        return True, None


# Pre-configured clinical C-arm hardware profiles
PHILIPS_ZENITION_70 = CArmProfile(
    manufacturer="Philips",
    model_name="Zenition_70_Flat_Detector",
    source_to_detector_distance_mm=993.0,
    source_to_isocenter_distance_mm=750.0,
    detector_width_px=1024,
    detector_height_px=1024,
    pixel_pitch_mm=(0.28, 0.28),
    primary_axis_name="ORBITAL_LAO_RAO",
    secondary_axis_name="ANGULATION_CRAN_CAUD",
    primary_min_max_deg=(-50.0, 90.0),
    secondary_min_max_deg=(-45.0, 45.0),
    default_polarity="INVERTED_FLUOROSCOPY",
    magnification_modes={"NORM": 1.0, "MAG1": 1.25, "MAG2": 1.50}
)

SIEMENS_CIOS_ALPHA = CArmProfile(
    manufacturer="Siemens_Healthineers",
    model_name="Cios_Alpha_FD",
    source_to_detector_distance_mm=1000.0,
    source_to_isocenter_distance_mm=750.0,
    detector_width_px=1024,
    detector_height_px=1024,
    pixel_pitch_mm=(0.29, 0.29),
    primary_axis_name="ORBITAL_LAO_RAO",
    secondary_axis_name="ANGULATION_CRAN_CAUD",
    primary_min_max_deg=(-40.0, 90.0),
    secondary_min_max_deg=(-45.0, 45.0),
    default_polarity="INVERTED_FLUOROSCOPY",
    magnification_modes={"NORM": 1.0, "MAG1": 1.30, "MAG2": 1.60}
)

GE_OEC_ELITE = CArmProfile(
    manufacturer="GE_Healthcare",
    model_name="OEC_Elite_CFD",
    source_to_detector_distance_mm=1000.0,
    source_to_isocenter_distance_mm=750.0,
    detector_width_px=1024,
    detector_height_px=1024,
    pixel_pitch_mm=(0.30, 0.30),
    primary_axis_name="ORBITAL_LAO_RAO",
    secondary_axis_name="ANGULATION_CRAN_CAUD",
    primary_min_max_deg=(-45.0, 90.0),
    secondary_min_max_deg=(-30.0, 30.0),
    default_polarity="INVERTED_FLUOROSCOPY",
    magnification_modes={"NORM": 1.0, "MAG1": 1.25, "MAG2": 1.50}
)

CARM_PROFILE_REGISTRY: Dict[str, CArmProfile] = {
    "philips_zenition_70": PHILIPS_ZENITION_70,
    "siemens_cios_alpha": SIEMENS_CIOS_ALPHA,
    "ge_oec_elite": GE_OEC_ELITE,
}


def get_carm_profile(identifier: str = "philips_zenition_70") -> CArmProfile:
    """Retrieves standard C-arm device profile or raises informative error."""
    key = identifier.lower().replace("-", "_").replace(" ", "_")
    if key in CARM_PROFILE_REGISTRY:
        return CARM_PROFILE_REGISTRY[key]
    raise ValueError(
        f"Unknown C-arm profile '{identifier}'. "
        f"Available profiles: {list(CARM_PROFILE_REGISTRY.keys())}"
    )
