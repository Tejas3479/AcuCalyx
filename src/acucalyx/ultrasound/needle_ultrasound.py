"""
AcuCalyx Ultrasound: Needle Acoustic Visibility Index (NAVI) & Specular Reflection
Governed by Milestone M14B of ACU-M14-EXEC-PLAN-2026-V2.

Provides:
1. Physically derived NAVI specular reflection model based on beam-to-needle incidence angle.
2. Gaussian elevational beam thickness drop-off.
3. Categorical acoustic needle visibility classification.
4. Real-time trajectory rehearsal advisories for urological needle puncture.
"""

from dataclasses import dataclass
import enum
import math
from typing import Optional, Tuple
import numpy as np


class NAVICategory(str, enum.Enum):
    OPTIMAL_ACOUSTIC_ALIGNMENT = "OPTIMAL_ACOUSTIC_ALIGNMENT"
    MODERATE_VISIBILITY = "MODERATE_VISIBILITY"
    SEVERE_SPECULAR_DROPOFF = "SEVERE_SPECULAR_DROPOFF"


@dataclass(frozen=True)
class NAVIResult:
    """Quantitative needle acoustic visibility assessment."""
    navi_score: float  # Value in [0.0, 1.0]
    specular_component: float  # Angle component sin^(2p)(phi) in [0.0, 1.0]
    elevational_component: float  # Gaussian slice thickness component in [0.0, 1.0]
    incidence_angle_deg: float  # Angle phi between beam propagation and needle tangent (deg)
    elevational_offset_mm: float  # Out-of-plane distance Delta z_elev (mm)
    category: NAVICategory
    clinical_guidance: str
    is_in_plane: bool


def calculate_needle_acoustic_visibility(
    needle_tangent: np.ndarray,
    beam_propagation_direction: np.ndarray,
    elevational_offset_mm: float = 0.0,
    elevational_slice_fwhm_mm: float = 3.0,
    specular_exponent_p: float = 2.0,
) -> NAVIResult:
    """
    Calculates physically derived Needle Acoustic Visibility Index (NAVI).

    NAVI(t, b, Delta z) = (1 - |t . b|^2)^p * exp(-(Delta z)^2 / (2 * sigma_elev^2))
                        = sin^(2p)(phi) * exp(-(Delta z)^2 / (2 * sigma_elev^2))

    - t: needle shaft tangent unit vector
    - b: local ultrasound beam propagation unit vector
    - Delta z: distance from center of ultrasound scan plane (elevational offset)
    """
    t = np.asarray(needle_tangent, dtype=float)
    b = np.asarray(beam_propagation_direction, dtype=float)

    norm_t = np.linalg.norm(t)
    norm_b = np.linalg.norm(b)

    if norm_t < 1e-6 or norm_b < 1e-6:
        cos_phi = 0.0
    else:
        t_unit = t / norm_t
        b_unit = b / norm_b
        # Dot product gives cos(theta) where theta is angle between vectors
        cos_phi = min(1.0, max(-1.0, float(np.dot(t_unit, b_unit))))

    abs_cos_phi = abs(cos_phi)
    # sin^2(phi) = 1 - cos^2(phi)
    sin2_phi = max(0.0, 1.0 - abs_cos_phi * abs_cos_phi)
    specular_comp = math.pow(sin2_phi, specular_exponent_p)

    # Incidence angle phi between beam direction and needle shaft in degrees
    # When needle is perpendicular to beam, cos_phi = 0 => phi = 90 deg
    phi_rad = math.acos(min(1.0, max(0.0, abs_cos_phi)))
    phi_deg = math.degrees(phi_rad)

    # Elevational slice Gaussian drop-off
    # FWHM = 2 * sqrt(2 * ln(2)) * sigma => sigma = FWHM / 2.35482
    sigma_elev = max(0.5, elevational_slice_fwhm_mm / (2.0 * math.sqrt(2.0 * math.log(2.0))))
    elev_comp = math.exp(-0.5 * (elevational_offset_mm * elevational_offset_mm) / (sigma_elev * sigma_elev))

    navi = specular_comp * elev_comp
    navi = min(1.0, max(0.0, navi))

    is_in_plane = abs(elevational_offset_mm) <= (elevational_slice_fwhm_mm / 2.0)

    if navi >= 0.70:
        cat = NAVICategory.OPTIMAL_ACOUSTIC_ALIGNMENT
        guidance = "Excellent needle shaft & tip echogenicity. Specular reflection aligned near normal incidence."
    elif navi >= 0.35:
        cat = NAVICategory.MODERATE_VISIBILITY
        guidance = "Moderate needle echogenicity. Consider slight probe tilt toward normal incidence or acoustic needle guide."
    else:
        cat = NAVICategory.SEVERE_SPECULAR_DROPOFF
        if not is_in_plane:
            guidance = "Severe out-of-plane needle drop-off. Elevational offset exceeds beam slice thickness; realign probe scan plane."
        else:
            guidance = "Severe specular reflection drop-off due to steep needle angle relative to beam axis. Needle tip may be invisible."

    return NAVIResult(
        navi_score=navi,
        specular_component=specular_comp,
        elevational_component=elev_comp,
        incidence_angle_deg=phi_deg,
        elevational_offset_mm=abs(elevational_offset_mm),
        category=cat,
        clinical_guidance=guidance,
        is_in_plane=is_in_plane,
    )


# Backwards compatibility aliases
NeedleAcousticVisibilityResult = NAVIResult
compute_needle_acoustic_visibility_index = calculate_needle_acoustic_visibility
