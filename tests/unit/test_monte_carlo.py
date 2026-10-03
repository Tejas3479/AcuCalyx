"""
Unit tests for Monte Carlo uncertainty propagation and collision risk analysis.
"""

import numpy as np
import pytest

from tests.phantom.phantom_generator import generate_synthetic_pcnl_phantom
from acucalyx.geometry.distance_fields import DistanceField
from acucalyx.geometry.transforms import LineSegment3D
from acucalyx.uncertainty.monte_carlo import run_monte_carlo_clearance_analysis


def test_monte_carlo_near_hazard_shows_higher_collision_risk():
    """
    Trajectory passing only 2mm away from colon hazard should exhibit high
    collision probability under 2.5mm perturbation noise.
    Trajectory passing 25mm away should exhibit ~0% collision probability.
    """
    vol, spatial, gt = generate_synthetic_pcnl_phantom(grid_shape=(96, 96, 80), noise_sigma_hu=0.0)

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

    # Path 1: Tangential graze (only 2mm away from boundary)
    # Colon is at X = 42, Y = 25, R = 10 -> boundary is at X = 32
    # Graze path at X = 30.5
    traj_graze = LineSegment3D(
        start_point=np.array([30.5, 40.0, 40.0]),
        end_point=np.array([30.5, 10.0, 40.0])
    )

    risk_graze = run_monte_carlo_clearance_analysis(
        trajectory=traj_graze,
        distance_field=df,
        hazard_name="colon",
        num_iterations=200,
        sigma_pos_mm=3.0
    )

    # Due to 3mm noise, a 1.5mm clearance will collide in a large fraction of iterations
    assert risk_graze.collision_probability > 0.15
    assert risk_graze.risk_category in ['MODERATE', 'CRITICAL']

    # Path 2: Far path (25mm away at X = 5.0)
    traj_far = LineSegment3D(
        start_point=np.array([5.0, 40.0, 40.0]),
        end_point=np.array([5.0, 10.0, 40.0])
    )

    risk_far = run_monte_carlo_clearance_analysis(
        trajectory=traj_far,
        distance_field=df,
        hazard_name="colon",
        num_iterations=200,
        sigma_pos_mm=3.0
    )

    assert risk_far.collision_probability == 0.0
    assert risk_far.risk_category == 'LOW'
