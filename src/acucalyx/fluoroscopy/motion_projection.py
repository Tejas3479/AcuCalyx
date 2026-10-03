"""
AcuCalyx Fluoroscopy: Respiratory Motion Projection & Uncertainty Envelope

Implements Step 4.07 of Phase 4 (Frozen v4.1):
Projects 3D respiratory and positional renal motion uncertainty onto the 2D detector plane.
Demonstrates to the surgeon how much the target calyx papilla moves under free-breathing
relative to the static puncture line on Bull's-Eye fluoroscopy.

Literature-Derived Kinematic Prior:
Craniocaudal excursion mean ~9.5 mm, AP excursion ~3.0 mm, ML excursion ~2.0 mm
(4DCT radiotherapy cohorts; e.g. Balter et al., Langen et al.).
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import numpy as np

from acucalyx.fluoroscopy.surgical_pose import CArmPoseGeometry


@dataclass(frozen=True)
class ProjectedUncertaintyEnvelope2D:
    """2D ellipse parameters of target motion uncertainty projected onto the DRR detector."""
    center_px: Tuple[float, float]
    semi_major_axis_px: float
    semi_minor_axis_px: float
    rotation_deg: float
    confidence_level: float             # e.g. 0.95
    excursion_range_mm: Tuple[float, float, float] # [ML, AP, CC]
    clinical_advisory: str


def compute_projected_motion_envelope(
    target_lps_mm: np.ndarray,
    pose: CArmPoseGeometry,
    output_resolution: Tuple[int, int] = (256, 256),
    craniocaudal_sigma_mm: float = 4.5, # 2*sigma ≈ 9.0 mm CC excursion
    anteroposterior_sigma_mm: float = 1.5,
    mediolateral_sigma_mm: float = 1.0,
    confidence_factor: float = 2.0      # 2-sigma ≈ 95% confidence interval
) -> ProjectedUncertaintyEnvelope2D:
    """
    Projects 3D motion covariance ellipsoid onto the 2D detector plane.
    """
    scale_x = output_resolution[0] / pose.profile.detector_width_px
    scale_y = output_resolution[1] / pose.profile.detector_height_px

    # Project nominal target center
    u_c, v_c, depth = pose.project_point_to_detector_px(target_lps_mm)
    center_2d = (u_c * scale_x, v_c * scale_y)

    # 3D covariance matrix in LPS (diag: [ML, AP, CC])
    # LPS: X=ML, Y=AP, Z=CC
    cov_3d = np.diag([
        (mediolateral_sigma_mm * confidence_factor) ** 2,
        (anteroposterior_sigma_mm * confidence_factor) ** 2,
        (craniocaudal_sigma_mm * confidence_factor) ** 2
    ])

    # Sample extreme excursion points along principal axes
    dx = np.array([mediolateral_sigma_mm * confidence_factor, 0.0, 0.0])
    dy = np.array([0.0, anteroposterior_sigma_mm * confidence_factor, 0.0])
    dz = np.array([0.0, 0.0, craniocaudal_sigma_mm * confidence_factor])

    pts_3d = [
        target_lps_mm + dx, target_lps_mm - dx,
        target_lps_mm + dy, target_lps_mm - dy,
        target_lps_mm + dz, target_lps_mm - dz
    ]

    pts_2d = []
    for pt in pts_3d:
        u_p, v_p, _ = pose.project_point_to_detector_px(pt)
        pts_2d.append([u_p * scale_x, v_p * scale_y])

    pts_2d_arr = np.array(pts_2d) - np.array(center_2d)

    # 2D covariance from projected excursion points
    cov_2d = np.cov(pts_2d_arr.T)
    eigenvals, eigenvecs = np.linalg.eigh(cov_2d)

    semi_major = float(np.sqrt(max(1.0, eigenvals[1]))) * 2.0
    semi_minor = float(np.sqrt(max(1.0, eigenvals[0]))) * 2.0
    angle_deg = float(np.degrees(np.arctan2(eigenvecs[1, 1], eigenvecs[0, 1])))

    advisory = (
        f"Projected target respiratory excursion envelope ({semi_major:.1f} x {semi_minor:.1f} px). "
        "Intraoperative puncture must be timed to end-expiration breath-hold."
    )

    return ProjectedUncertaintyEnvelope2D(
        center_px=center_2d,
        semi_major_axis_px=semi_major,
        semi_minor_axis_px=semi_minor,
        rotation_deg=angle_deg,
        confidence_level=0.95,
        excursion_range_mm=(
            mediolateral_sigma_mm * confidence_factor * 2.0,
            anteroposterior_sigma_mm * confidence_factor * 2.0,
            craniocaudal_sigma_mm * confidence_factor * 2.0
        ),
        clinical_advisory=advisory
    )


def overlay_motion_envelope_on_drr(
    drr_image: np.ndarray,
    envelope: ProjectedUncertaintyEnvelope2D,
    color_val: int = 180
) -> np.ndarray:
    """
    Renders the projected uncertainty ellipse onto the DRR image.
    """
    img = drr_image.copy()
    h, w = img.shape
    cx, cy = envelope.center_px
    a = envelope.semi_major_axis_px
    b = envelope.semi_minor_axis_px
    rad = np.radians(envelope.rotation_deg)
    cos_a = np.cos(rad)
    sin_a = np.sin(rad)

    # Parametric ellipse points
    theta = np.linspace(0, 2 * np.pi, 100)
    x_local = a * np.cos(theta)
    y_local = b * np.sin(theta)

    x_rot = cos_a * x_local - sin_a * y_local + cx
    y_rot = sin_a * x_local + cos_a * y_local + cy

    xs = np.round(x_rot).astype(int)
    ys = np.round(y_rot).astype(int)

    valid = (xs >= 0) & (xs < w) & (ys >= 0) & (ys < h)
    img[ys[valid], xs[valid]] = color_val

    return img
