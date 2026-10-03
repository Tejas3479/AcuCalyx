"""
AcuCalyx Geometry: Distance Fields and Hazard Clearance Calculation

Implements:
- Anisotropic Euclidean Distance Transform (EDT) using exact physical voxel spacing
- Signed Distance Field (SDF) computation (negative inside, positive outside)
- Minimum distance query between needle trajectory line segments and hazard volumes
- Effective clearance calculation with explicit uncertainty envelopes:
  C_effective = C_observed - U_geometry - U_segmentation - U_position
"""

from dataclasses import dataclass
from typing import Sequence, Tuple, Union, Optional
import numpy as np
from scipy import ndimage

from acucalyx.geometry.coordinates import SpatialOrientation
from acucalyx.geometry.transforms import LineSegment3D


@dataclass(frozen=True)
class HazardClearanceResult:
    """
    Quantified hazard clearance evaluation for a trajectory against an anatomical hazard.
    """
    hazard_name: str
    observed_clearance_mm: float  # Min distance from trajectory to hazard volume in mm
    effective_clearance_mm: float  # Observed clearance minus total uncertainty envelope
    is_intersecting: bool         # True if path intersects organ volume
    closest_path_point: np.ndarray  # [x, y, z] point on trajectory closest to hazard
    closest_hazard_point: Optional[np.ndarray]  # [x, y, z] point on hazard surface closest to trajectory
    total_uncertainty_mm: float   # Sum of uncertainty components
    confidence_level: str         # 'HIGH', 'MODERATE', 'LOW'


class DistanceField:
    """
    Represents an anisotropic 3D distance field in physical millimeter space.
    """
    def __init__(
        self,
        binary_mask: np.ndarray,
        spatial_orientation: SpatialOrientation
    ):
        """
        Args:
            binary_mask: 3D boolean/uint8 array (shape: [rows, cols, slices])
            spatial_orientation: SpatialOrientation with affine transform and spacing (dx, dy, dz)
        """
        self.mask = (binary_mask > 0).astype(bool)
        self.spatial = spatial_orientation
        self.spacing = spatial_orientation.spacing  # [row_sp, col_sp, slice_sp] in mm

        # Compute Euclidean distance transform in physical mm
        # distance_transform_edt takes sampling parameter for physical distance
        # NOTE: mask is True where organ is present.
        # Background distance: distance to nearest True voxel
        if np.any(self.mask):
            self.distance_map_outside = ndimage.distance_transform_edt(
                ~self.mask,
                sampling=self.spacing
            )
            # Foreground distance: distance to nearest False voxel (interior depth)
            self.distance_map_inside = ndimage.distance_transform_edt(
                self.mask,
                sampling=self.spacing
            )
            # Signed distance field: positive outside, negative inside
            self.sdf = self.distance_map_outside - self.distance_map_inside
        else:
            # Empty mask: infinite distance outside
            self.distance_map_outside = np.full(self.mask.shape, np.inf, dtype=np.float64)
            self.distance_map_inside = np.zeros(self.mask.shape, dtype=np.float64)
            self.sdf = self.distance_map_outside

    def sample_distance_physical(self, physical_points: np.ndarray) -> np.ndarray:
        """
        Evaluates the distance field at continuous physical points [x, y, z] in mm.
        Returns distances in mm (negative if inside).
        """
        pts = np.asarray(physical_points, dtype=np.float64)
        is_single = pts.ndim == 1
        if is_single:
            pts = pts.reshape(1, 3)

        # Convert physical points to continuous voxel indices (row, col, slice)
        voxel_coords = self.spatial.physical_to_voxel(pts)

        # Sample distance map using trilinear interpolation
        # map_coordinates requires coordinates array shaped (3, N)
        coords_t = voxel_coords.T  # shape (3, N)
        distances = ndimage.map_coordinates(
            self.sdf,
            coords_t,
            order=1,
            mode='nearest'
        )

        return distances[0] if is_single else distances

    def evaluate_trajectory_clearance(
        self,
        trajectory: LineSegment3D,
        hazard_name: str,
        uncertainty_geometry: float = 1.0,
        uncertainty_segmentation: float = 2.0,
        uncertainty_position: float = 3.0,
        step_mm: float = 0.5
    ) -> HazardClearanceResult:
        """
        Evaluates the clearance between a line segment trajectory and the hazard.
        Calculates:
        C_effective = C_observed - U_geom - U_seg - U_pos
        """
        if not np.any(self.mask):
            return HazardClearanceResult(
                hazard_name=hazard_name,
                observed_clearance_mm=float('inf'),
                effective_clearance_mm=float('inf'),
                is_intersecting=False,
                closest_path_point=trajectory.start_point,
                closest_hazard_point=None,
                total_uncertainty_mm=0.0,
                confidence_level='HIGH'
            )

        # Sample points along the trajectory line segment
        sampled_points = trajectory.sample_points(step_mm=step_mm)
        distances = self.sample_distance_physical(sampled_points)

        min_idx = int(np.argmin(distances))
        min_dist = float(distances[min_idx])
        closest_point = sampled_points[min_idx]

        is_intersecting = min_dist <= 0.0
        observed_clearance = max(0.0, min_dist)

        total_uncertainty = float(
            uncertainty_geometry + uncertainty_segmentation + uncertainty_position
        )
        effective_clearance = max(0.0, observed_clearance - total_uncertainty)

        # Confidence categorization
        if effective_clearance > 15.0:
            confidence = 'HIGH'
        elif effective_clearance > 5.0:
            confidence = 'MODERATE'
        else:
            confidence = 'LOW'

        return HazardClearanceResult(
            hazard_name=hazard_name,
            observed_clearance_mm=observed_clearance,
            effective_clearance_mm=effective_clearance,
            is_intersecting=is_intersecting,
            closest_path_point=closest_point,
            closest_hazard_point=None,
            total_uncertainty_mm=total_uncertainty,
            confidence_level=confidence
        )

    def evaluate_minkowski_clearance(
        self,
        trajectory: LineSegment3D,
        hazard_name: str,
        uncertainty_geometry: float = 1.0,
        uncertainty_segmentation: float = 2.0,
        uncertainty_motion: float = 2.0,
        step_mm: float = 0.5
    ) -> HazardClearanceResult:
        """
        Evaluates clearance against Minkowski-expanded conservative hazard envelope:
        H_conservative = H_observed + B(sqrt(U_geom^2 + U_seg^2 + U_motion^2))
        
        Effective clearance can be negative if the trajectory penetrates the conservative envelope.
        """
        if not np.any(self.mask):
            return HazardClearanceResult(
                hazard_name=hazard_name,
                observed_clearance_mm=float('inf'),
                effective_clearance_mm=float('inf'),
                is_intersecting=False,
                closest_path_point=trajectory.start_point,
                closest_hazard_point=None,
                total_uncertainty_mm=0.0,
                confidence_level='HIGH'
            )

        sampled_points = trajectory.sample_points(step_mm=step_mm)
        distances = self.sample_distance_physical(sampled_points)

        min_idx = int(np.argmin(distances))
        min_dist = float(distances[min_idx])
        closest_point = sampled_points[min_idx]

        is_physical_intersecting = min_dist <= 0.0
        observed_clearance = max(0.0, min_dist)

        # Minkowski geometric dilation envelope combining uncertainties in quadrature
        minkowski_uncertainty = float(np.sqrt(
            uncertainty_geometry ** 2 + uncertainty_segmentation ** 2 + uncertainty_motion ** 2
        ))
        effective_clearance = observed_clearance - minkowski_uncertainty

        # If effective clearance < 0, trajectory violates conservative envelope
        is_intersecting = is_physical_intersecting or (effective_clearance < 0.0)

        if effective_clearance > 15.0:
            confidence = 'HIGH'
        elif effective_clearance > 5.0:
            confidence = 'MODERATE'
        else:
            confidence = 'LOW'

        return HazardClearanceResult(
            hazard_name=hazard_name,
            observed_clearance_mm=observed_clearance,
            effective_clearance_mm=effective_clearance,
            is_intersecting=is_intersecting,
            closest_path_point=closest_point,
            closest_hazard_point=None,
            total_uncertainty_mm=minkowski_uncertainty,
            confidence_level=confidence
        )

