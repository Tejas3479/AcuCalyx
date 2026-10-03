"""
Unit tests for AcuCalyx virtual fluoroscopy projection simulator.
"""

import numpy as np
import pytest

from acucalyx.geometry.transforms import LineSegment3D
from acucalyx.fluoroscopy.projection_simulator import (
    simulate_trajectory_projection, construct_bullseye_camera, construct_progression_camera
)


def test_bullseye_projection_collapses_needle_axis():
    """
    In the Bull's-eye view, the central beam is coaxial with the needle,
    so entry and target project to nearly the identical point (apparent length ~ 0 mm).
    """
    traj = LineSegment3D(
        start_point=np.array([20.0, 50.0, 30.0]),
        end_point=np.array([20.0, 10.0, 30.0])  # Length = 40mm along -Y
    )

    view = simulate_trajectory_projection(traj, view_type='BULLS_EYE')

    assert np.isclose(view.alignment_angle_deg, 0.0, atol=1e-3)
    # 2D projected distance between entry and target should be virtually 0
    assert view.projected_needle_length_2d_mm < 0.1


def test_progression_projection_shows_full_length_magnified():
    """
    In the Progression view, the camera is orthogonal (90 degrees),
    and the needle projects with full magnification M = SID / SOD.
    """
    traj = LineSegment3D(
        start_point=np.array([20.0, 50.0, 30.0]),
        end_point=np.array([20.0, 10.0, 30.0])  # Length = 40mm along -Y
    )

    view = simulate_trajectory_projection(traj, view_type='PROGRESSION')

    assert np.isclose(view.alignment_angle_deg, 90.0, atol=1e-3)
    # Needle length must be visible and magnified
    # Nominal magnification M = 1000 / 600 = 1.667 -> 40 * 1.667 ~ 66.7 mm
    assert view.projected_needle_length_2d_mm > 35.0
