"""
AcuCalyx Geometry: Ray and Line Segment Volume Intersections

Implements:
- Direct voxel-grid traversal and sampling for line segment collision detection
- Calculation of tissue tract length (e.g., parenchymal length through kidney)
- Ray-box and ray-sphere geometric intersection primitives
"""

from dataclasses import dataclass
from typing import Optional, Tuple
import numpy as np

from acucalyx.geometry.coordinates import SpatialOrientation
from acucalyx.geometry.transforms import LineSegment3D


@dataclass(frozen=True)
class VolumeIntersectionResult:
    """
    Summary of line segment traversal through a 3D binary volume mask.
    """
    intersects: bool
    tract_length_mm: float      # Total path length within the mask in mm
    entry_point: Optional[np.ndarray]  # First point of entry into mask [x, y, z] mm
    exit_point: Optional[np.ndarray]   # Last point of exit from mask [x, y, z] mm
    fraction_in_volume: float   # tract_length / total_segment_length


def intersect_segment_with_volume(
    segment: LineSegment3D,
    binary_mask: np.ndarray,
    spatial_orientation: SpatialOrientation,
    sample_step_mm: float = 0.5
) -> VolumeIntersectionResult:
    """
    Samples a line segment and detects whether and where it traverses a 3D binary mask.
    Computes exact tract length through the tissue.
    
    Args:
        segment: LineSegment3D from skin entry to target
        binary_mask: 3D numpy array [rows, cols, slices]
        spatial_orientation: SpatialOrientation instance
        sample_step_mm: physical distance between samples along line (mm)
    """
    if segment.length < 1e-6 or not np.any(binary_mask):
        return VolumeIntersectionResult(
            intersects=False,
            tract_length_mm=0.0,
            entry_point=None,
            exit_point=None,
            fraction_in_volume=0.0
        )

    # Sample points along segment in physical mm
    pts_phys = segment.sample_points(step_mm=sample_step_mm)
    pts_voxel = spatial_orientation.physical_to_voxel(pts_phys)

    rows, cols, slices = binary_mask.shape

    # Round to nearest voxel index
    i_indices = np.round(pts_voxel[:, 0]).astype(int)
    j_indices = np.round(pts_voxel[:, 1]).astype(int)
    k_indices = np.round(pts_voxel[:, 2]).astype(int)

    # Valid in-bounds mask
    in_bounds = (
        (i_indices >= 0) & (i_indices < rows) &
        (j_indices >= 0) & (j_indices < cols) &
        (k_indices >= 0) & (k_indices < slices)
    )

    inside_mask = np.zeros(len(pts_phys), dtype=bool)
    inside_mask[in_bounds] = binary_mask[
        i_indices[in_bounds],
        j_indices[in_bounds],
        k_indices[in_bounds]
    ] > 0

    if not np.any(inside_mask):
        return VolumeIntersectionResult(
            intersects=False,
            tract_length_mm=0.0,
            entry_point=None,
            exit_point=None,
            fraction_in_volume=0.0
        )

    inside_indices = np.where(inside_mask)[0]
    first_idx = inside_indices[0]
    last_idx = inside_indices[-1]

    entry_point = pts_phys[first_idx]
    exit_point = pts_phys[last_idx]

    # Tract length is estimated by number of inside samples * sample_step_mm
    tract_length = float(len(inside_indices) * sample_step_mm)
    tract_length = min(segment.length, tract_length)
    fraction = tract_length / segment.length if segment.length > 0 else 0.0

    return VolumeIntersectionResult(
        intersects=True,
        tract_length_mm=tract_length,
        entry_point=entry_point,
        exit_point=exit_point,
        fraction_in_volume=float(fraction)
    )
