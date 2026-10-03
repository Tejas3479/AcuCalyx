"""
AcuCalyx Planning: Skin Surface Extraction and Hierarchical Flank Sampling

Implements Step 05 of AcuCalyx v2.1:
- Extracts posterior flank body surface using air-tissue thresholding (-300 HU)
- Implements hierarchical multi-stage sampling:
  * Stage 1: Coarse grid (15mm spacing) across posterior-lateral flank
  * Stage 2: Local refinement (5mm spacing) around viable candidate clusters
- Classifies candidate skin points anatomically:
  * SUBCOSTAL: inferior to 12th rib margin
  * INTERCOSTAL_11_12: between 11th and 12th ribs
  * SUPRACOSTAL_11: superior to 11th rib
"""

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple
import numpy as np
from scipy import ndimage

from acucalyx.geometry.coordinates import SpatialOrientation
from acucalyx.anatomy.segmentation import AnatomicalCorridorMasks, OrganLabel


@dataclass(frozen=True)
class FlankSkinPoint:
    """A candidate skin entry point on the patient's posterior-lateral flank."""
    point_id: str
    physical_lps_mm: np.ndarray       # [x, y, z] in mm
    surface_normal_lps: np.ndarray    # Unit normal pointing outward from skin
    rib_approach_classification: str  # 'SUBCOSTAL', 'INTERCOSTAL_11_12', 'SUPRACOSTAL_11'
    distance_to_midline_mm: float    # Distance from spinal midline in mm
    side: str                         # 'left' or 'right'


def extract_body_surface_mask(
    ct_volume_hu: np.ndarray,
    threshold_hu: float = -300.0
) -> np.ndarray:
    """
    Extracts the patient's outer skin contour by thresholding air vs tissue.
    Fills internal cavities to isolate the true external skin boundary.
    """
    # Tissue mask
    tissue = ct_volume_hu > threshold_hu
    
    # Fill 2D slice-wise cavities (e.g. lung air, bowel gas)
    filled = np.zeros_like(tissue, dtype=bool)
    struct = ndimage.generate_binary_structure(2, 1)
    
    for k in range(tissue.shape[2]):
        slice_mask = tissue[:, :, k]
        if np.any(slice_mask):
            filled[:, :, k] = ndimage.binary_fill_holes(slice_mask, structure=struct)
            
    # Surface is the single-voxel outer shell
    struct_3d = ndimage.generate_binary_structure(3, 1)
    eroded = ndimage.binary_erosion(filled, structure=struct_3d)
    skin_surface = filled & (~eroded)
    return skin_surface


def sample_hierarchical_flank_points(
    skin_surface_mask: np.ndarray,
    spatial_orientation: SpatialOrientation,
    anatomy_masks: AnatomicalCorridorMasks,
    side: str = "left",
    coarse_step_mm: float = 15.0
) -> List[FlankSkinPoint]:
    """
    Samples candidate skin entry points on the posterior flank using Stage 1 coarse sampling.
    """
    skin_indices = np.argwhere(skin_surface_mask)
    if len(skin_indices) == 0:
        return []

    phys_points = spatial_orientation.voxel_to_physical(skin_indices)
    
    # Determine bounds based on targeted side (LPS: +X is Left, -X is Right, +Y is Posterior)
    if side.lower() == "left":
        side_filter = (phys_points[:, 0] > 10.0) & (phys_points[:, 0] < 80.0)
    else:
        side_filter = (phys_points[:, 0] < -10.0) & (phys_points[:, 0] > -80.0)

    # Posterior flank only: +Y must be positive (dorsal side)
    posterior_filter = phys_points[:, 1] > 0.0
    flank_indices = np.where(side_filter & posterior_filter)[0]
    
    if len(flank_indices) == 0:
        return []

    flank_points = phys_points[flank_indices]

    # Grid subsampling at coarse_step_mm
    # Find bounding box
    min_xyz = np.min(flank_points, axis=0)
    max_xyz = np.max(flank_points, axis=0)
    
    grid_x = np.arange(min_xyz[0], max_xyz[0], coarse_step_mm)
    grid_y = np.arange(min_xyz[1], max_xyz[1], coarse_step_mm)
    grid_z = np.arange(min_xyz[2], max_xyz[2], coarse_step_mm)

    rib_12 = anatomy_masks.get_mask(OrganLabel.RIB_LEFT_12 if side == "left" else OrganLabel.RIB_RIGHT_12)
    rib_11 = anatomy_masks.get_mask(OrganLabel.RIB_LEFT_11 if side == "left" else OrganLabel.RIB_RIGHT_11)

    rib12_z_min = float('inf')
    if rib_12 is not None and np.any(rib_12):
        rib12_phys = spatial_orientation.voxel_to_physical(np.argwhere(rib_12))
        rib12_z_min = float(np.min(rib12_phys[:, 2]))

    rib11_z_min = float('inf')
    if rib_11 is not None and np.any(rib_11):
        rib11_phys = spatial_orientation.voxel_to_physical(np.argwhere(rib_11))
        rib11_z_min = float(np.min(rib11_phys[:, 2]))

    sampled: List[FlankSkinPoint] = []
    point_counter = 1

    # Select closest skin point to each coarse grid node
    for gz in grid_z:
        for gx in grid_x:
            # Find points within 10mm in X and Z
            box_mask = (abs(flank_points[:, 0] - gx) < coarse_step_mm / 2.0) & \
                       (abs(flank_points[:, 2] - gz) < coarse_step_mm / 2.0)
            if np.any(box_mask):
                sub_pts = flank_points[box_mask]
                # Pick the most posterior point (largest Y)
                best_idx = np.argmax(sub_pts[:, 1])
                chosen_pt = sub_pts[best_idx]

                # Rib classification based on cranial-caudal (Z) level
                z_level = chosen_pt[2]
                if z_level < rib12_z_min:
                    rib_class = "SUBCOSTAL"
                elif z_level < rib11_z_min:
                    rib_class = "INTERCOSTAL_11_12"
                else:
                    rib_class = "SUPRACOSTAL_11"

                dist_midline = float(abs(chosen_pt[0]))
                
                # Approximate normal: points posteriorly and laterally
                normal = np.array([np.sign(chosen_pt[0]) * 0.4, 0.9, 0.1])
                normal = normal / np.linalg.norm(normal)

                sampled.append(FlankSkinPoint(
                    point_id=f"SKIN_{point_counter:03d}",
                    physical_lps_mm=chosen_pt,
                    surface_normal_lps=normal,
                    rib_approach_classification=rib_class,
                    distance_to_midline_mm=dist_midline,
                    side=side.lower()
                ))
                point_counter += 1

    return sampled


def refine_local_flank_clusters(
    seed_points: Sequence[FlankSkinPoint],
    skin_surface_mask: np.ndarray,
    spatial_orientation: SpatialOrientation,
    refinement_step_mm: float = 5.0,
    search_radius_mm: float = 12.0
) -> List[FlankSkinPoint]:
    """
    Stage 2 (Refinement): Dense 5mm local grid search around promising candidate entry points.
    """
    skin_indices = np.argwhere(skin_surface_mask)
    if len(skin_indices) == 0 or not seed_points:
        return list(seed_points)

    phys_points = spatial_orientation.voxel_to_physical(skin_indices)
    refined: List[FlankSkinPoint] = []
    seen_coords = set()

    sub_counter = 1
    for sp in seed_points:
        # Physical coordinates of seed
        s_xyz = sp.physical_lps_mm
        dist_sq = np.sum((phys_points - s_xyz)**2, axis=1)
        nearby_indices = np.where(dist_sq <= (search_radius_mm**2))[0]
        if len(nearby_indices) == 0:
            refined.append(sp)
            continue

        cluster_pts = phys_points[nearby_indices]
        # Fine grid around seed
        min_xyz = np.min(cluster_pts, axis=0)
        max_xyz = np.max(cluster_pts, axis=0)

        gx_range = np.arange(min_xyz[0], max_xyz[0] + 1e-3, refinement_step_mm)
        gz_range = np.arange(min_xyz[2], max_xyz[2] + 1e-3, refinement_step_mm)

        for gz in gz_range:
            for gx in gx_range:
                box = (abs(cluster_pts[:, 0] - gx) < refinement_step_mm / 2.0) & \
                      (abs(cluster_pts[:, 2] - gz) < refinement_step_mm / 2.0)
                if np.any(box):
                    pts_in_cell = cluster_pts[box]
                    # Select most dorsal / posterior point
                    best = pts_in_cell[np.argmax(pts_in_cell[:, 1])]
                    key = (round(best[0], 1), round(best[1], 1), round(best[2], 1))
                    if key not in seen_coords:
                        seen_coords.add(key)
                        refined.append(FlankSkinPoint(
                            point_id=f"{sp.point_id}_REF_{sub_counter:02d}",
                            physical_lps_mm=best,
                            surface_normal_lps=sp.surface_normal_lps,
                            rib_approach_classification=sp.rib_approach_classification,
                            distance_to_midline_mm=float(abs(best[0])),
                            side=sp.side
                        ))
                        sub_counter += 1

    return refined if refined else list(seed_points)


def optimize_continuous_entry_point(
    initial_point: FlankSkinPoint,
    target_papilla: np.ndarray,
    skin_surface_mask: np.ndarray,
    spatial_orientation: SpatialOrientation,
    max_step_mm: float = 8.0,
    iterations: int = 15
) -> FlankSkinPoint:
    """
    Stage 3 (Continuous): Sub-millimeter projection on the skin surface manifold
    minimizing tract length to the target calyx papilla.
    """
    skin_indices = np.argwhere(skin_surface_mask)
    if len(skin_indices) == 0:
        return initial_point

    phys_points = spatial_orientation.voxel_to_physical(skin_indices)
    curr_pt = initial_point.physical_lps_mm.copy()

    # Gradient step along vector from entry to target, projected onto skin surface
    for _ in range(iterations):
        grad = target_papilla - curr_pt
        # Move along surface towards target projection
        step = grad * 0.05
        step_len = np.linalg.norm(step)
        if step_len > 1.0:
            step = step / step_len * 1.0

        trial_pt = curr_pt + step
        # Project trial point back to closest true skin surface point
        dists = np.sum((phys_points - trial_pt)**2, axis=1)
        closest_idx = np.argmin(dists)
        proj_pt = phys_points[closest_idx]

        if np.linalg.norm(proj_pt - initial_point.physical_lps_mm) > max_step_mm:
            break
        curr_pt = proj_pt

    return FlankSkinPoint(
        point_id=f"{initial_point.point_id}_OPT",
        physical_lps_mm=curr_pt,
        surface_normal_lps=initial_point.surface_normal_lps,
        rib_approach_classification=initial_point.rib_approach_classification,
        distance_to_midline_mm=float(abs(curr_pt[0])),
        side=initial_point.side
    )
