"""
AcuCalyx Ultrasound: Transducer Profiles & Acoustic Probe Geometry
Governed by Milestone M14B of ACU-M14-EXEC-PLAN-2026-V2.

Provides:
1. Standard configurable clinical transducer profiles (Curvilinear C5-2, Linear L12-4).
2. Transducer geometry and SE(3) coordinate transformation representation.
3. Acoustic scanline ray sampling across transducer sector and linear arrays.
"""

from dataclasses import dataclass, field
import enum
import math
from typing import List, Optional, Tuple
import numpy as np


class TransducerType(str, enum.Enum):
    CURVILINEAR = "CURVILINEAR"
    LINEAR = "LINEAR"
    PHASED_ARRAY = "PHASED_ARRAY"


@dataclass(frozen=True)
class TransducerProfile:
    """
    Physical and acoustic operating specifications for an ultrasound transducer probe.
    Parameters align with typical commercial PCNL interventional ultrasound probes.
    """
    probe_id: str
    name: str
    transducer_type: TransducerType
    center_frequency_mhz: float
    frequency_range_mhz: Tuple[float, float]
    radius_of_curvature_mm: float  # Curvature radius Rc (0 for linear)
    sector_angle_deg: float  # Total sector sweep angle (0 for linear)
    footprint_width_mm: float  # Transducer physical aperture width
    elevation_slice_thickness_mm: float  # Elevational beam FWHM at focus
    default_focal_depth_mm: float
    max_imaging_depth_mm: float
    num_scanlines: int = 128
    num_depth_samples: int = 256

    @property
    def sector_angle_rad(self) -> float:
        return math.radians(self.sector_angle_deg)


# Standard Clinical Transducers
CURVILINEAR_C5_2 = TransducerProfile(
    probe_id="CURV_C5_2",
    name="Curvilinear C5-2 (Abdominal/Renal Standard)",
    transducer_type=TransducerType.CURVILINEAR,
    center_frequency_mhz=3.5,
    frequency_range_mhz=(2.0, 5.0),
    radius_of_curvature_mm=40.0,
    sector_angle_deg=60.0,
    footprint_width_mm=60.0,
    elevation_slice_thickness_mm=3.5,
    default_focal_depth_mm=80.0,
    max_imaging_depth_mm=180.0,
    num_scanlines=128,
    num_depth_samples=256,
)

LINEAR_L12_4 = TransducerProfile(
    probe_id="LIN_L12_4",
    name="Linear L12-4 (High-Frequency Superficial/Needle)",
    transducer_type=TransducerType.LINEAR,
    center_frequency_mhz=7.5,
    frequency_range_mhz=(4.0, 12.0),
    radius_of_curvature_mm=0.0,
    sector_angle_deg=0.0,
    footprint_width_mm=40.0,
    elevation_slice_thickness_mm=2.0,
    default_focal_depth_mm=35.0,
    max_imaging_depth_mm=80.0,
    num_scanlines=128,
    num_depth_samples=256,
)

STANDARD_PROBES = {
    CURVILINEAR_C5_2.probe_id: CURVILINEAR_C5_2,
    LINEAR_L12_4.probe_id: LINEAR_L12_4,
}


def get_ultrasound_probe(probe_id: str) -> TransducerProfile:
    """Retrieves probe profile by probe_id, defaulting to CURVILINEAR_C5_2."""
    return STANDARD_PROBES.get(probe_id, CURVILINEAR_C5_2)


# Backwards compatibility alias
UltrasoundProbeProfile = TransducerProfile


@dataclass
class UltrasoundProbePose:
    """
    SE(3) Pose representing transducer orientation in patient coordinate space (DICOM LPS).
    - origin: center of transducer footprint on skin (x, y, z) in mm.
    - axial_direction: unit vector pointing into tissue along central acoustic axis.
    - lateral_direction: unit vector pointing along probe width (scan plane lateral axis).
    - elevational_direction: unit vector perpendicular to scan plane (axial x lateral).
    """
    origin: np.ndarray
    axial_direction: np.ndarray
    lateral_direction: np.ndarray
    elevational_direction: np.ndarray

    @classmethod
    def create_aligned_with_trajectory(
        cls,
        entry_point: np.ndarray,
        target_point: np.ndarray,
        lateral_hint: Optional[np.ndarray] = None,
    ) -> "UltrasoundProbePose":
        """
        Creates a probe pose positioned at the entry point on patient skin,
        with axial axis pointing towards target point (needle corridor view).
        """
        entry = np.asarray(entry_point, dtype=float)
        target = np.asarray(target_point, dtype=float)
        diff = target - entry
        dist = np.linalg.norm(diff)
        if dist < 1e-6:
            axial = np.array([0.0, 0.0, 1.0])
        else:
            axial = diff / dist

        if lateral_hint is not None:
            lat = np.asarray(lateral_hint, dtype=float)
            # Orthogonalize against axial
            lat = lat - np.dot(lat, axial) * axial
            if np.linalg.norm(lat) > 1e-4:
                lat = lat / np.linalg.norm(lat)
            else:
                lat = None

        if lateral_hint is None or lat is None:
            # Pick arbitrary perpendicular vector
            if abs(axial[0]) < 0.9 and abs(axial[1]) < 0.9:
                cand = np.array([0.0, 1.0, 0.0])
            else:
                cand = np.array([0.0, 0.0, 1.0])
            lat = cand - np.dot(cand, axial) * axial
            lat = lat / np.linalg.norm(lat)

        elev = np.cross(axial, lat)
        elev = elev / np.linalg.norm(elev)

        return cls(
            origin=entry,
            axial_direction=axial,
            lateral_direction=lat,
            elevational_direction=elev,
        )

    def sample_scanline_rays(
        self,
        probe: TransducerProfile,
    ) -> List[Tuple[np.ndarray, np.ndarray]]:
        """
        Samples (ray_origin, ray_direction) pairs for each scanline in probe profile.
        Ray origin is on the probe surface in 3D patient coordinates,
        ray direction is unit vector pointing into patient space.
        """
        rays = []
        n_lines = probe.num_scanlines

        if probe.transducer_type == TransducerType.CURVILINEAR:
            half_angle = probe.sector_angle_rad / 2.0
            r_c = probe.radius_of_curvature_mm

            # Virtual center of curvature is behind probe surface: origin - r_c * axial
            virtual_center = self.origin - r_c * self.axial_direction

            for i in range(n_lines):
                # Theta sweeps from -half_angle to +half_angle
                if n_lines > 1:
                    theta = -half_angle + (2.0 * half_angle * i) / (n_lines - 1)
                else:
                    theta = 0.0

                # Direction in probe local coordinates
                # cos(theta) along axial, sin(theta) along lateral
                ray_dir = (
                    math.cos(theta) * self.axial_direction +
                    math.sin(theta) * self.lateral_direction
                )
                ray_dir = ray_dir / np.linalg.norm(ray_dir)

                # Ray origin on the curved probe face
                ray_orig = virtual_center + r_c * ray_dir
                rays.append((ray_orig, ray_dir))

        elif probe.transducer_type == TransducerType.LINEAR:
            half_w = probe.footprint_width_mm / 2.0
            ray_dir = self.axial_direction

            for i in range(n_lines):
                if n_lines > 1:
                    offset = -half_w + (2.0 * half_w * i) / (n_lines - 1)
                else:
                    offset = 0.0
                ray_orig = self.origin + offset * self.lateral_direction
                rays.append((ray_orig, ray_dir))

        else:
            # Default fallback
            for i in range(n_lines):
                rays.append((self.origin, self.axial_direction))

        return rays
