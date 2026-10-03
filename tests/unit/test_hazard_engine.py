"""
Unit tests for distance fields and hazard clearance engine.
"""

import numpy as np
import pytest

from tests.phantom.phantom_generator import generate_synthetic_pcnl_phantom
from acucalyx.geometry.distance_fields import DistanceField
from acucalyx.geometry.transforms import LineSegment3D
from acucalyx.geometry.intersections import intersect_segment_with_volume


def test_hazard_clearance_and_intersection():
    """
    Validates distance fields, intersection tests, and effective clearance equations
    using synthetic colon hazard.
    """
    vol, spatial, gt = generate_synthetic_pcnl_phantom(
        grid_shape=(96, 96, 80),
        spacing_mm=(1.0, 1.0, 1.0),
        noise_sigma_hu=0.0
    )

    # Segment colon hazard: air lumen (-1000) or wall (35) near the known colon axis
    # Colon axis is X = 32, Y = 22, radius = 10
    origin = spatial.origin
    dx, dy, dz = spatial.spacing

    i_coords = np.arange(96)
    j_coords = np.arange(96)
    k_coords = np.arange(80)
    I, J, K = np.meshgrid(i_coords, j_coords, k_coords, indexing='ij')

    X_phys = origin[0] + J * dx
    Y_phys = origin[1] + I * dy
    colon_dist_sq = (X_phys - gt.colon_axis_start_mm[0])**2 + (Y_phys - gt.colon_axis_start_mm[1])**2
    colon_mask = colon_dist_sq <= (gt.colon_radius_mm**2)

    df = DistanceField(binary_mask=colon_mask, spatial_orientation=spatial)

    # Trajectory 1: Piercing directly through colon center (X = 42.0, Y = 25.0)
    traj_pierce = LineSegment3D(
        start_point=np.array([42.0, 40.0, 40.0]),
        end_point=np.array([42.0, 10.0, 40.0])
    )

    res_pierce = df.evaluate_trajectory_clearance(
        trajectory=traj_pierce,
        hazard_name="colon",
        uncertainty_geometry=1.0,
        uncertainty_segmentation=2.0,
        uncertainty_position=3.0
    )

    assert res_pierce.is_intersecting is True
    assert res_pierce.observed_clearance_mm == 0.0
    assert res_pierce.effective_clearance_mm == 0.0

    # Volume intersection test must also confirm collision
    intersect_res = intersect_segment_with_volume(
        segment=traj_pierce,
        binary_mask=colon_mask,
        spatial_orientation=spatial
    )
    assert intersect_res.intersects is True
    assert intersect_res.tract_length_mm > 0.0

    # Trajectory 2: Safe path running medial to colon
    # Colon is at X = 32, Y = 22, R = 10. Boundary reaches X = 22 at closest.
    # Safe path runs at X = 10.0 (distance ~12 mm from colon boundary)
    traj_safe = LineSegment3D(
        start_point=np.array([10.0, 40.0, 40.0]),
        end_point=np.array([10.0, 0.0, 40.0])
    )

    res_safe = df.evaluate_trajectory_clearance(
        trajectory=traj_safe,
        hazard_name="colon",
        uncertainty_geometry=1.0,
        uncertainty_segmentation=1.5,
        uncertainty_position=2.0
    )

    assert res_safe.is_intersecting is False
    assert res_safe.observed_clearance_mm > 8.0
    # Effective clearance = Observed - sum(uncertainties)
    expected_effective = max(0.0, res_safe.observed_clearance_mm - (1.0 + 1.5 + 2.0))
    np.testing.assert_allclose(res_safe.effective_clearance_mm, expected_effective, atol=1e-3)
