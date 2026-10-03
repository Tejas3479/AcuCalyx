"""
AcuCalyx Fluoroscopy: Configurable NeedleProfile & Perspective Overlay Renderer

Implements Step 4.05 of Phase 4 (Frozen v4.1):
Renders surgical puncture needles with perspective accuracy onto 2D DRR images:
- Parameterized NeedleProfile (gauge, length, bevel, 1-cm graduation depth rings).
- Perspective projection of needle shaft, hub, and depth markers using P = K [R | t].
- In Bull's-Eye view: Renders concentric en-face target ring when needle collapses.
- In Depth-Verification view: Renders full shaft with depth centimeter tick marks.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import numpy as np

from acucalyx.fluoroscopy.surgical_pose import CArmPoseGeometry
from acucalyx.geometry.transforms import LineSegment3D


@dataclass(frozen=True)
class NeedleProfile:
    """Mechanical and optical specifications of a percutaneous access needle."""
    name: str                          # e.g. 'Chiba_18G_200mm'
    gauge: float                       # Gauge number (e.g. 18.0)
    outer_diameter_mm: float           # 1.25 mm for 18G, 0.9 mm for 20G
    length_mm: float                   # 150.0 to 200.0 mm
    bevel_angle_deg: float             # 15.0 to 30.0 degrees
    graduation_ring_spacing_mm: float  # 10.0 mm (1 cm marks)
    radiopacity_hu_equivalent: float   # Stainless steel attenuation boost


STANDARD_CHIBA_18G = NeedleProfile(
    name="Standard_Chiba_18G_200mm",
    gauge=18.0,
    outer_diameter_mm=1.25,
    length_mm=200.0,
    bevel_angle_deg=15.0,
    graduation_ring_spacing_mm=10.0,
    radiopacity_hu_equivalent=3000.0
)

STANDARD_TROCAR_18G = NeedleProfile(
    name="Standard_Trocar_18G_150mm",
    gauge=18.0,
    outer_diameter_mm=1.25,
    length_mm=150.0,
    bevel_angle_deg=30.0,
    graduation_ring_spacing_mm=10.0,
    radiopacity_hu_equivalent=3000.0
)


@dataclass(frozen=True)
class ProjectedNeedleOverlay:
    """2D perspective projection coordinates of needle components on the DRR image."""
    tip_px: Tuple[float, float]
    entry_px: Tuple[float, float]
    hub_px: Tuple[float, float]
    shaft_length_px: float
    shaft_width_px: float
    is_bullseye_collapsed: bool        # True if projected length < 10 pixels
    graduation_rings_px: List[Tuple[float, float]] # 2D points along shaft


def project_needle_onto_drr(
    trajectory: LineSegment3D,
    pose: CArmPoseGeometry,
    needle_profile: NeedleProfile = STANDARD_CHIBA_18G,
    output_resolution: Tuple[int, int] = (256, 256)
) -> ProjectedNeedleOverlay:
    """
    Computes 2D perspective coordinates of needle tip, shaft, and graduation rings.
    """
    scale_x = output_resolution[0] / pose.profile.detector_width_px
    scale_y = output_resolution[1] / pose.profile.detector_height_px

    tip_lps = trajectory.end_point
    entry_lps = trajectory.start_point
    needle_dir = trajectory.unit_direction

    # Hub is positioned along negative needle direction from skin entry
    remaining_length = max(10.0, needle_profile.length_mm - trajectory.length)
    hub_lps = entry_lps - needle_dir * remaining_length

    u_tip, v_tip, depth_tip = pose.project_point_to_detector_px(tip_lps)
    u_entry, v_entry, depth_entry = pose.project_point_to_detector_px(entry_lps)
    u_hub, v_hub, depth_hub = pose.project_point_to_detector_px(hub_lps)

    # Scale to output resolution
    tip_2d = (u_tip * scale_x, v_tip * scale_y)
    entry_2d = (u_entry * scale_x, v_entry * scale_y)
    hub_2d = (u_hub * scale_x, v_hub * scale_y)

    shaft_len = float(np.hypot(tip_2d[0] - entry_2d[0], tip_2d[1] - entry_2d[1]))
    is_collapsed = shaft_len < 6.0  # < 6 pixels = Bull's-eye en-face view

    # Magnification factor M = SID / depth
    mag = pose.profile.source_to_detector_distance_mm / max(100.0, depth_entry)
    projected_width = (needle_profile.outer_diameter_mm * mag / pose.profile.pixel_pitch_mm[0]) * scale_x

    # Compute graduation rings every 10 mm along shaft from tip toward entry
    rings_2d: List[Tuple[float, float]] = []
    n_rings = int(trajectory.length // needle_profile.graduation_ring_spacing_mm)
    for k in range(1, n_rings + 1):
        dist_from_tip = k * needle_profile.graduation_ring_spacing_mm
        ring_lps = tip_lps - needle_dir * dist_from_tip
        u_r, v_r, _ = pose.project_point_to_detector_px(ring_lps)
        rings_2d.append((u_r * scale_x, v_r * scale_y))

    return ProjectedNeedleOverlay(
        tip_px=tip_2d,
        entry_px=entry_2d,
        hub_px=hub_2d,
        shaft_length_px=shaft_len,
        shaft_width_px=max(1.5, float(projected_width)),
        is_bullseye_collapsed=is_collapsed,
        graduation_rings_px=rings_2d
    )


def overlay_needle_on_drr(
    drr_image: np.ndarray,
    overlay: ProjectedNeedleOverlay,
    color_val: int = 0
) -> np.ndarray:
    """
    Renders the projected needle onto a copy of the 2D DRR image.
    In standard inverted fluoroscopy, dark needle color_val = 0 or 30.
    """
    img = drr_image.copy()
    h, w = img.shape

    if overlay.is_bullseye_collapsed:
        # Render en-face concentric target circle ("eye of the needle")
        cx, cy = int(round(overlay.tip_px[0])), int(round(overlay.tip_px[1]))
        r = 6
        y_coords, x_coords = np.ogrid[:h, :w]
        dist_from_center = np.sqrt((x_coords - cx) ** 2 + (y_coords - cy) ** 2)
        circle_mask = (dist_from_center >= r - 1.5) & (dist_from_center <= r + 1.5)
        img[circle_mask] = color_val
        # Center dot
        dot_mask = dist_from_center <= 1.5
        img[dot_mask] = color_val
    else:
        # Render shaft line from hub through entry to tip
        x0, y0 = int(round(overlay.hub_px[0])), int(round(overlay.hub_px[1]))
        x1, y1 = int(round(overlay.tip_px[0])), int(round(overlay.tip_px[1]))

        # Bresenham-style line drawing
        num_pts = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
        if num_pts > 1:
            xs = np.linspace(x0, x1, num_pts).astype(int)
            ys = np.linspace(y0, y1, num_pts).astype(int)
            valid = (xs >= 0) & (xs < w) & (ys >= 0) & (ys < h)
            img[ys[valid], xs[valid]] = color_val

        # Render graduation ring tick marks
        for rx, ry in overlay.graduation_rings_px:
            ix, iy = int(round(rx)), int(round(ry))
            for dx in [-2, -1, 0, 1, 2]:
                for dy in [-2, -1, 0, 1, 2]:
                    if 0 <= ix + dx < w and 0 <= iy + dy < h:
                        img[iy + dy, ix + dx] = color_val

    return img
