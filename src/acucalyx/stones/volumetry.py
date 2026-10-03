"""
AcuCalyx Stone Engine: Volumetric and Morphometric Analysis

Implements:
- True physical volume integration in cubic millimeters (mm³)
- 3D physical center of mass (centroid) in LPS patient space
- Maximum 3D Feret diameter computation (longest axis in physical space)
- Physical bounding box span in mm
"""

from dataclasses import dataclass
from typing import List, Tuple
import numpy as np
from scipy import ndimage
from scipy.spatial.distance import pdist

from acucalyx.geometry.coordinates import SpatialOrientation
from acucalyx.stones.candidate_detection import RawStoneCandidate


@dataclass(frozen=True)
class StoneMorphometry:
    """Quantitative morphometry of a single kidney stone."""
    stone_id: int
    volume_mm3: float               # True physical volume
    volume_voxels: int             # Total voxel count
    centroid_lps_mm: np.ndarray    # [x, y, z] centroid in physical LPS coordinates
    max_feret_diameter_mm: float   # Longest 3D diameter
    bounding_box_span_mm: np.ndarray # [dx, dy, dz] physical box dimensions
    tier: str


def compute_stone_morphometry(
    candidate: RawStoneCandidate,
    spatial_orientation: SpatialOrientation
) -> StoneMorphometry:
    """
    Computes rigorous physical morphometrics for a detected stone candidate.
    """
    mask = candidate.voxel_mask
    spacing = spatial_orientation.spacing  # [row_sp, col_sp, slice_sp] in mm
    voxel_vol_mm3 = float(spacing[0] * spacing[1] * spacing[2])
    
    n_voxels = candidate.voxel_count
    total_volume_mm3 = float(n_voxels * voxel_vol_mm3)
    
    # Get coordinates of all positive voxels (row i, col j, slice k)
    ijk_indices = np.argwhere(mask)  # shape (N, 3)
    
    # Convert all positive voxel indices to physical LPS coordinates (mm)
    phys_points = spatial_orientation.voxel_to_physical(ijk_indices)
    
    # 3D Center of Mass (centroid in mm)
    centroid_mm = np.mean(phys_points, axis=0)
    
    # Physical bounding box span
    min_coords = np.min(phys_points, axis=0)
    max_coords = np.max(phys_points, axis=0)
    span_mm = max_coords - min_coords
    
    # Maximum 3D Feret diameter
    # If N is small to moderate (<= 2000 points), compute exact pairwise distance on surface/convex hull
    # Otherwise downsample surface points for tractability
    if len(phys_points) <= 1:
        max_feret_mm = float(np.max(spacing))
    elif len(phys_points) < 1500:
        dists = pdist(phys_points)
        max_feret_mm = float(np.max(dists))
    else:
        # Extract surface voxels only using erosion
        struct = ndimage.generate_binary_structure(3, 1)
        eroded = ndimage.binary_erosion(mask, structure=struct)
        surface_mask = mask & (~eroded)
        surf_ijk = np.argwhere(surface_mask)
        surf_phys = spatial_orientation.voxel_to_physical(surf_ijk)
        
        if len(surf_phys) > 2000:
            # Subsample 1500 surface points randomly
            rng = np.random.default_rng(seed=42)
            indices = rng.choice(len(surf_phys), size=1500, replace=False)
            surf_phys = surf_phys[indices]
            
        dists = pdist(surf_phys)
        max_feret_mm = float(np.max(dists)) if len(dists) > 0 else float(np.max(span_mm))
        
    return StoneMorphometry(
        stone_id=candidate.candidate_id,
        volume_mm3=total_volume_mm3,
        volume_voxels=n_voxels,
        centroid_lps_mm=centroid_mm,
        max_feret_diameter_mm=max_feret_mm,
        bounding_box_span_mm=span_mm,
        tier=candidate.tier
    )
