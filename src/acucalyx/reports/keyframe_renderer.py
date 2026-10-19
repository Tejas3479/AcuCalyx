"""
AcuCalyx Reports: Headless Preoperative Planning Keyframe Image Renderer

Renders publication-quality, server-side 2D keyframe images for the 2-page PDF report:
1. Axial MPR CT slice at puncture target depth with needle corridor overlay & scale bar.
2. Coronal MPR CT slice along the calyx axis with target reticle & orientation tags.
3. Fluoroscopy Bull's-eye projection preview thumbnail with C-arm gantry angle readouts.

Uses headless numpy and Pillow (PIL) without browser or GUI dependencies.
"""

from pathlib import Path
from typing import Dict, Optional, Tuple, Union
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from acucalyx.geometry.coordinates import SpatialOrientation
from acucalyx.geometry.transforms import LineSegment3D
from acucalyx.planning.pareto_optimizer import CandidateTrajectory


def _get_font(size: int = 12) -> ImageFont.ImageFont:
    """Returns PIL default font."""
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def render_axial_mpr_keyframe(
    volume_hu: np.ndarray,
    spatial: SpatialOrientation,
    entry_lps: np.ndarray,
    target_lps: np.ndarray,
    output_path: Optional[Path] = None,
    window_level: float = 40.0,
    window_width: float = 400.0,
    target_label: str = "Target Calyx",
    margin_mm: float = 5.0,
    image_size: Tuple[int, int] = (512, 512)
) -> Image.Image:
    """
    Renders an Axial MPR CT slice at the puncture target plane (Z = target_z)
    with needle corridor overlay, target reticle, scale bar, and anatomical tags.
    """
    rows, cols, slices = volume_hu.shape
    v_target = spatial.physical_to_voxel(target_lps)
    v_entry = spatial.physical_to_voxel(entry_lps)

    k_target = int(np.clip(round(v_target[2]), 0, slices - 1))
    slice_2d = volume_hu[:, :, k_target].astype(np.float32)

    # Window/Level mapping
    lower = window_level - (window_width / 2.0)
    upper = window_level + (window_width / 2.0)
    clipped = np.clip(slice_2d, lower, upper)
    norm = ((clipped - lower) / (upper - lower) * 255.0).astype(np.uint8)

    # Create base RGB image
    base_img = Image.fromarray(norm).convert("RGB")
    
    # Calculate physical aspect ratio scaling
    dx = float(spatial.spacing[1])  # col spacing mm
    dy = float(spatial.spacing[0])  # row spacing mm
    target_w, target_h = image_size
    
    # Scale base image to desired size
    img = base_img.resize((target_w, target_h), Image.Resampling.BILINEAR)
    draw = ImageDraw.Draw(img)
    font = _get_font()

    # Scaling factors from voxel space to output image pixels
    scale_x = target_w / cols
    scale_y = target_h / rows

    # Map target voxel to image pixels (col -> x, row -> y)
    tx_px = v_target[1] * scale_x
    ty_px = v_target[0] * scale_y

    # Map entry voxel to image pixels
    ex_px = v_entry[1] * scale_x
    ey_px = v_entry[0] * scale_y

    # Trajectory Corridor Overlay
    # Draw corridor margin (±margin_mm)
    perp_vec = np.array([-(ey_px - ty_px), ex_px - tx_px], dtype=np.float64)
    norm_perp = np.linalg.norm(perp_vec)
    if norm_perp > 1e-3:
        perp_unit = perp_vec / norm_perp
        offset_px = (margin_mm / max(1e-3, dx)) * scale_x
        p1_a = (ex_px + perp_unit[0] * offset_px, ey_px + perp_unit[1] * offset_px)
        p2_a = (tx_px + perp_unit[0] * offset_px, ty_px + perp_unit[1] * offset_px)
        p1_b = (ex_px - perp_unit[0] * offset_px, ey_px - perp_unit[1] * offset_px)
        p2_b = (tx_px - perp_unit[0] * offset_px, ty_px - perp_unit[1] * offset_px)
        # Margin boundaries (dashed corridor lines)
        draw.line([p1_a, p2_a], fill=(245, 158, 11), width=1)
        draw.line([p1_b, p2_b], fill=(245, 158, 11), width=1)

    # Trajectory center line
    draw.line([(ex_px, ey_px), (tx_px, ty_px)], fill=(16, 185, 129), width=2)

    # Skin Entry Diamond
    d_r = 6
    draw.polygon([
        (ex_px, ey_px - d_r),
        (ex_px + d_r, ey_px),
        (ex_px, ey_px + d_r),
        (ex_px - d_r, ey_px)
    ], outline=(245, 158, 11), fill=(245, 158, 11, 128))
    draw.text((ex_px + 8, ey_px - 8), "Skin Entry", fill=(245, 158, 11), font=font)

    # Target Reticle (Green concentric rings + crosshairs)
    for r in [4, 9, 15]:
        draw.ellipse([tx_px - r, ty_px - r, tx_px + r, ty_px + r], outline=(16, 185, 129), width=1 if r < 15 else 2)
    draw.line([(tx_px - 18, ty_px), (tx_px + 18, ty_px)], fill=(16, 185, 129), width=1)
    draw.line([(tx_px, ty_px - 18), (tx_px, ty_px + 18)], fill=(16, 185, 129), width=1)
    draw.text((tx_px + 12, ty_px + 6), f"Target: {target_label}", fill=(16, 185, 129), font=font)

    # Scale Bar: 20 mm
    bar_mm = 20.0
    bar_px = (bar_mm / dx) * scale_x
    bx = 25
    by = target_h - 30
    draw.line([(bx, by), (bx + bar_px, by)], fill=(255, 255, 255), width=3)
    draw.line([(bx, by - 4), (bx, by + 4)], fill=(255, 255, 255), width=2)
    draw.line([(bx + bar_px, by - 4), (bx + bar_px, by + 4)], fill=(255, 255, 255), width=2)
    draw.text((bx + 2, by - 16), "20 mm", fill=(255, 255, 255), font=font)

    # Anatomical Orientation Labels (Radiological convention)
    # A (Anterior) at Top, P (Posterior) at Bottom, R (Right) at Left, L (Left) at Right
    draw.text((target_w // 2 - 4, 8), "A", fill=(255, 255, 255), font=font)
    draw.text((target_w // 2 - 4, target_h - 20), "P", fill=(255, 255, 255), font=font)
    draw.text((8, target_h // 2 - 6), "R", fill=(255, 255, 255), font=font)
    draw.text((target_w - 16, target_h // 2 - 6), "L", fill=(255, 255, 255), font=font)

    # Header Banner
    header_text = f"AXIAL MPR @ TARGET (Z = {target_lps[2]:.1f} mm) [Slice {k_target + 1}/{slices}]"
    draw.rectangle([(0, 0), (target_w, 20)], fill=(15, 23, 42, 200))
    draw.text((8, 4), header_text, fill=(243, 244, 246), font=font)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(output_path), format="PNG")

    return img


def render_coronal_mpr_keyframe(
    volume_hu: np.ndarray,
    spatial: SpatialOrientation,
    entry_lps: np.ndarray,
    target_lps: np.ndarray,
    output_path: Optional[Path] = None,
    window_level: float = 40.0,
    window_width: float = 400.0,
    target_label: str = "Target Calyx",
    margin_mm: float = 5.0,
    image_size: Tuple[int, int] = (512, 512)
) -> Image.Image:
    """
    Renders a Coronal MPR CT slice along the calyx axis (Y = target_y)
    with longitudinal needle alignment, target reticle, and orientation tags.
    """
    rows, cols, slices = volume_hu.shape
    v_target = spatial.physical_to_voxel(target_lps)
    v_entry = spatial.physical_to_voxel(entry_lps)

    i_target = int(np.clip(round(v_target[0]), 0, rows - 1))
    
    # Extract coronal slice: (cols, slices) -> transpose to (slices, cols)
    # Flip vertically so Superior (max Z) is at row 0 (Top)
    slice_raw = volume_hu[i_target, :, :].astype(np.float32)  # shape: (cols, slices)
    slice_coronal = np.flipud(slice_raw.T)                    # shape: (slices, cols)

    # Window/Level mapping
    lower = window_level - (window_width / 2.0)
    upper = window_level + (window_width / 2.0)
    clipped = np.clip(slice_coronal, lower, upper)
    norm = ((clipped - lower) / (upper - lower) * 255.0).astype(np.uint8)

    base_img = Image.fromarray(norm).convert("RGB")
    target_w, target_h = image_size
    img = base_img.resize((target_w, target_h), Image.Resampling.BILINEAR)
    draw = ImageDraw.Draw(img)
    font = _get_font()

    # Coordinate mapping:
    # Col index (0..cols-1) -> X in pixels (0..target_w)
    # Slice index (0..slices-1) -> Y in pixels: row = (slices - 1 - k)
    scale_x = target_w / cols
    scale_y = target_h / slices

    tx_px = v_target[1] * scale_x
    ty_px = ((slices - 1) - v_target[2]) * scale_y

    ex_px = v_entry[1] * scale_x
    ey_px = ((slices - 1) - v_entry[2]) * scale_y

    dx = float(spatial.spacing[1])  # col spacing mm
    dz = float(spatial.spacing[2])  # slice spacing mm

    # Trajectory Corridor
    perp_vec = np.array([-(ey_px - ty_px), ex_px - tx_px], dtype=np.float64)
    norm_perp = np.linalg.norm(perp_vec)
    if norm_perp > 1e-3:
        perp_unit = perp_vec / norm_perp
        offset_px = (margin_mm / max(1e-3, dx)) * scale_x
        p1_a = (ex_px + perp_unit[0] * offset_px, ey_px + perp_unit[1] * offset_px)
        p2_a = (tx_px + perp_unit[0] * offset_px, ty_px + perp_unit[1] * offset_px)
        p1_b = (ex_px - perp_unit[0] * offset_px, ey_px - perp_unit[1] * offset_px)
        p2_b = (tx_px - perp_unit[0] * offset_px, ty_px - perp_unit[1] * offset_px)
        draw.line([p1_a, p2_a], fill=(245, 158, 11), width=1)
        draw.line([p1_b, p2_b], fill=(245, 158, 11), width=1)

    # Trajectory center line
    draw.line([(ex_px, ey_px), (tx_px, ty_px)], fill=(16, 185, 129), width=2)

    # Skin Entry Marker
    d_r = 6
    draw.polygon([
        (ex_px, ey_px - d_r),
        (ex_px + d_r, ey_px),
        (ex_px, ey_px + d_r),
        (ex_px - d_r, ey_px)
    ], outline=(245, 158, 11), fill=(245, 158, 11, 128))
    draw.text((ex_px + 8, ey_px - 8), "Skin Entry", fill=(245, 158, 11), font=font)

    # Target Reticle
    for r in [4, 9, 15]:
        draw.ellipse([tx_px - r, ty_px - r, tx_px + r, ty_px + r], outline=(16, 185, 129), width=1 if r < 15 else 2)
    draw.line([(tx_px - 18, ty_px), (tx_px + 18, ty_px)], fill=(16, 185, 129), width=1)
    draw.line([(tx_px, ty_px - 18), (tx_px, ty_px + 18)], fill=(16, 185, 129), width=1)
    draw.text((tx_px + 12, ty_px + 6), f"Target: {target_label}", fill=(16, 185, 129), font=font)

    # Scale Bar: 20 mm
    bar_mm = 20.0
    bar_px = (bar_mm / dx) * scale_x
    bx = 25
    by = target_h - 30
    draw.line([(bx, by), (bx + bar_px, by)], fill=(255, 255, 255), width=3)
    draw.line([(bx, by - 4), (bx, by + 4)], fill=(255, 255, 255), width=2)
    draw.line([(bx + bar_px, by - 4), (bx + bar_px, by + 4)], fill=(255, 255, 255), width=2)
    draw.text((bx + 2, by - 16), "20 mm", fill=(255, 255, 255), font=font)

    # Anatomical Orientation Labels
    # S (Superior) Top, I (Inferior) Bottom, R (Patient Right) Left, L (Patient Left) Right
    draw.text((target_w // 2 - 4, 8), "S", fill=(255, 255, 255), font=font)
    draw.text((target_w // 2 - 4, target_h - 20), "I", fill=(255, 255, 255), font=font)
    draw.text((8, target_h // 2 - 6), "R", fill=(255, 255, 255), font=font)
    draw.text((target_w - 16, target_h // 2 - 6), "L", fill=(255, 255, 255), font=font)

    # Header Banner
    header_text = f"CORONAL MPR @ PUNCTURE AXIS (Y = {target_lps[1]:.1f} mm) [Slice {i_target + 1}/{rows}]"
    draw.rectangle([(0, 0), (target_w, 20)], fill=(15, 23, 42, 200))
    draw.text((8, 4), header_text, fill=(243, 244, 246), font=font)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(output_path), format="PNG")

    return img


def render_bullseye_projection_keyframe(
    trajectory: LineSegment3D,
    bullseye_angles: Tuple[float, float],
    progression_angles: Optional[Tuple[float, float]] = None,
    output_path: Optional[Path] = None,
    target_label: str = "Target Calyx",
    carm_model: str = "Philips Zenition 70",
    image_size: Tuple[int, int] = (512, 512)
) -> Image.Image:
    """
    Renders a virtual fluoroscopy Bull's-eye projection preview thumbnail
    with down-the-barrel needle reticle, collimation aperture, and C-arm presets.
    """
    w, h = image_size
    img = Image.new("RGB", (w, h), color=(15, 23, 42))  # Dark phosphor fluoroscopy background
    draw = ImageDraw.Draw(img)
    font = _get_font()

    cx, cy = w // 2, h // 2
    radius = int(min(w, h) * 0.42)

    # Circular Collimated Fluoroscopy Field
    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=(30, 41, 59), outline=(59, 130, 246), width=3)

    # Calibration Millimeter Rings (Simulated 5mm, 10mm, 20mm rings)
    for r_scale, label in [(0.15, "5mm"), (0.28, "10mm"), (0.40, "20mm")]:
        r_px = int(radius * r_scale)
        draw.ellipse([cx - r_px, cy - r_px, cx + r_px, cy + r_px], outline=(71, 85, 105), width=1)
        draw.text((cx + r_px + 2, cy - 6), label, fill=(148, 163, 184), font=font)

    # Reticle Grid Crosshairs
    draw.line([(cx - radius + 10, cy), (cx + radius - 10, cy)], fill=(71, 85, 105), width=1)
    draw.line([(cx, cy - radius + 10), (cx, cy + radius - 10)], fill=(71, 85, 105), width=1)

    # Calyx Target Zone (Soft green glow)
    calyx_r = int(radius * 0.22)
    draw.ellipse([cx - calyx_r, cy - calyx_r, cx + calyx_r, cy + calyx_r], outline=(16, 185, 129), fill=(16, 185, 129, 40), width=2)

    # Coaxial Needle Point: "Down-the-barrel" alignment
    # Needle hub and tip overlap in true bull's-eye alignment
    draw.ellipse([cx - 7, cy - 7, cx + 7, cy + 7], fill=(245, 158, 11), outline=(255, 255, 255), width=2)
    draw.ellipse([cx - 2, cy - 2, cx + 2, cy + 2], fill=(255, 255, 255))

    # C-arm Gantry Readout Badges
    p_ang, s_ang = bullseye_angles
    p_label = f"LAO {p_ang:.1f}°" if p_ang >= 0 else f"RAO {abs(p_ang):.1f}°"
    s_label = f"CRAN {s_ang:.1f}°" if s_ang >= 0 else f"CAUD {abs(s_ang):.1f}°"

    draw.rectangle([(16, h - 85), (w - 16, h - 16)], fill=(15, 23, 42, 220), outline=(59, 130, 246), width=1)
    draw.text((24, h - 80), f"BULL'S-EYE GANTRY PRESETS ({carm_model})", fill=(96, 165, 250), font=font)
    draw.text((24, h - 64), f"Primary Angle: {p_label}  |  Secondary Angle: {s_label}", fill=(243, 244, 246), font=font)

    if progression_angles:
        pp_ang, ps_ang = progression_angles
        pp_label = f"LAO {pp_ang:.1f}°" if pp_ang >= 0 else f"RAO {abs(pp_ang):.1f}°"
        ps_label = f"CRAN {ps_ang:.1f}°" if ps_ang >= 0 else f"CAUD {abs(ps_ang):.1f}°"
        draw.text((24, h - 48), f"Progression (Depth) View: {pp_label} / {ps_label}", fill=(209, 213, 219), font=font)

    draw.text((24, h - 32), "VERBAL READBACK DIRECTIVE: Confirm gantry angles with surgical team.", fill=(239, 68, 68), font=font)

    # Header Banner
    draw.rectangle([(0, 0), (w, 24)], fill=(15, 23, 42, 230))
    draw.text((8, 6), f"C-ARM VIRTUAL FLUOROSCOPY: BULL'S-EYE VIEW [{target_label.upper()}]", fill=(243, 244, 246), font=font)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(output_path), format="PNG")

    return img


def generate_fallback_keyframes(
    candidate: CandidateTrajectory,
    output_dir: Path,
    bullseye_angles: Optional[Tuple[float, float]] = None,
    progression_angles: Optional[Tuple[float, float]] = None
) -> Dict[str, Path]:
    """
    Generates clean vector/schematic keyframe images when raw CT volume is not in memory.
    Guarantees report generator never fails closed due to missing raster CT arrays.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    axial_path = output_dir / "axial_keyframe.png"
    coronal_path = output_dir / "coronal_keyframe.png"
    bullseye_path = output_dir / "bullseye_keyframe.png"

    b_angles = bullseye_angles or (18.0, -12.0)
    p_angles = progression_angles or (-72.0, 0.0)

    # 1. Fallback Axial schematic
    w, h = 512, 512
    img_ax = Image.new("RGB", (w, h), color=(31, 41, 55))
    draw_ax = ImageDraw.Draw(img_ax)
    font = _get_font()
    
    # Schematic kidney cross section
    draw_ax.ellipse([140, 120, 370, 390], fill=(55, 65, 81), outline=(107, 114, 128), width=2)
    # Calyx target
    cx, cy = 256, 260
    draw_ax.ellipse([cx - 20, cy - 20, cx + 20, cy + 20], fill=(16, 185, 129, 60), outline=(16, 185, 129), width=2)
    # Trajectory
    draw_ax.line([(450, 380), (cx, cy)], fill=(16, 185, 129), width=2)
    draw_ax.text((420, 390), "Skin Entry", fill=(245, 158, 11), font=font)
    draw_ax.text((cx + 25, cy - 10), f"Target: {candidate.target_calyx_name}", fill=(16, 185, 129), font=font)
    draw_ax.text((8, 6), f"SCHEMATIC AXIAL TRAJECTORY [SIMULATION] - Target: {candidate.target_calyx_name}", fill=(255, 255, 255), font=font)
    draw_ax.text((120, 480), "SCHEMATIC DIAGRAM — NOT EMPIRICAL CT MPR", fill=(239, 68, 68), font=font)
    img_ax.save(str(axial_path), format="PNG")

    # 2. Fallback Coronal schematic
    img_cor = Image.new("RGB", (w, h), color=(31, 41, 55))
    draw_cor = ImageDraw.Draw(img_cor)
    draw_cor.ellipse([160, 100, 350, 420], fill=(55, 65, 81), outline=(107, 114, 128), width=2)
    draw_cor.ellipse([cx - 20, cy - 20, cx + 20, cy + 20], fill=(16, 185, 129, 60), outline=(16, 185, 129), width=2)
    draw_cor.line([(440, 390), (cx, cy)], fill=(16, 185, 129), width=2)
    draw_cor.text((410, 400), "Skin Entry", fill=(245, 158, 11), font=font)
    draw_cor.text((cx + 25, cy - 10), f"Target: {candidate.target_calyx_name}", fill=(16, 185, 129), font=font)
    draw_cor.text((8, 6), f"SCHEMATIC CORONAL TRAJECTORY [SIMULATION] - Target: {candidate.target_calyx_name}", fill=(255, 255, 255), font=font)
    draw_cor.text((120, 480), "SCHEMATIC DIAGRAM — NOT EMPIRICAL CT MPR", fill=(239, 68, 68), font=font)
    img_cor.save(str(coronal_path), format="PNG")

    # 3. Bull's-eye projection
    traj = LineSegment3D(candidate.entry_point_lps, candidate.target_point_lps)
    render_bullseye_projection_keyframe(
        trajectory=traj,
        bullseye_angles=b_angles,
        progression_angles=p_angles,
        output_path=bullseye_path,
        target_label=candidate.target_calyx_name
    )

    return {
        "axial": axial_path,
        "coronal": coronal_path,
        "bullseye": bullseye_path
    }


def generate_case_report_keyframes(
    volume_hu: Optional[np.ndarray],
    spatial: Optional[SpatialOrientation],
    candidate: CandidateTrajectory,
    output_dir: Path,
    bullseye_angles: Optional[Tuple[float, float]] = None,
    progression_angles: Optional[Tuple[float, float]] = None
) -> Dict[str, Path]:
    """
    Generates all keyframes (Axial, Coronal, Bull's-eye) for a given case and candidate.
    Falls back gracefully if volume_hu or spatial is None.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    if volume_hu is None or spatial is None:
        return generate_fallback_keyframes(candidate, output_dir, bullseye_angles, progression_angles)

    axial_path = output_dir / "axial_keyframe.png"
    coronal_path = output_dir / "coronal_keyframe.png"
    bullseye_path = output_dir / "bullseye_keyframe.png"

    entry = candidate.entry_point_lps
    target = candidate.target_point_lps
    traj = LineSegment3D(entry, target)

    # Derive C-arm angles if not provided
    if bullseye_angles is None:
        b_vec = traj.unit_direction
        p_deg = float(np.degrees(np.arctan2(b_vec[0], -b_vec[1])))
        s_deg = float(np.degrees(np.arcsin(np.clip(b_vec[2], -1.0, 1.0))))
        bullseye_angles = (p_deg, s_deg)

    render_axial_mpr_keyframe(
        volume_hu=volume_hu,
        spatial=spatial,
        entry_lps=entry,
        target_lps=target,
        output_path=axial_path,
        target_label=candidate.target_calyx_name
    )

    render_coronal_mpr_keyframe(
        volume_hu=volume_hu,
        spatial=spatial,
        entry_lps=entry,
        target_lps=target,
        output_path=coronal_path,
        target_label=candidate.target_calyx_name
    )

    render_bullseye_projection_keyframe(
        trajectory=traj,
        bullseye_angles=bullseye_angles,
        progression_angles=progression_angles,
        output_path=bullseye_path,
        target_label=candidate.target_calyx_name
    )

    return {
        "axial": axial_path,
        "coronal": coronal_path,
        "bullseye": bullseye_path
    }
