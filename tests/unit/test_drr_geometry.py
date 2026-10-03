"""
AcuCalyx Unit Tests: C-Arm Geometry Contract & CPU Reference DRR (Phase 4)

Tests:
- C-Arm hardware profiles (Philips, Siemens, GE) and mechanical angle limits
- Surgical table pose transformation (Supine to Prone)
- Full SE(3) pose and projection matrix P = K [R | t]
- Bull's-Eye View: Needle axis collapses into en-face focal dot
- Depth-Verification View: Needle projects full shaft length
- Trusted CPU Reference DRR generation & transmission contrast
"""

import numpy as np
import pytest

from acucalyx.fluoroscopy.carm_profile import (
    CARM_PROFILE_REGISTRY,
    PHILIPS_ZENITION_70,
    SIEMENS_CIOS_ALPHA,
    get_carm_profile,
)
from acucalyx.fluoroscopy.cpu_reference_drr import (
    generate_cpu_reference_drr,
    hu_to_linear_attenuation,
)
from acucalyx.fluoroscopy.surgical_pose import (
    SurgicalPatientPosition,
    build_carm_projection_geometry,
    compute_ct_to_surgical_transform,
    construct_bullseye_carm_pose,
    construct_depth_verification_carm_pose,
)
from acucalyx.geometry.coordinates import SpatialOrientation
from acucalyx.geometry.transforms import LineSegment3D
from tests.phantom.phantom_generator import generate_synthetic_pcnl_phantom


def test_carm_device_profiles_and_kinematic_limits():
    """Verifies C-arm profiles and gantry reachability validation."""
    philips = get_carm_profile("philips_zenition_70")
    assert philips.manufacturer == "Philips"
    assert philips.source_to_detector_distance_mm == 993.0

    # Within mechanical limits: Orbital 30°, Angulation 15°
    is_ok, msg = philips.validate_gantry_angles(30.0, 15.0)
    assert is_ok is True
    assert msg is None

    # Exceeding primary limit: Orbital 120° (> 90°)
    is_ok_exceed, msg_exceed = philips.validate_gantry_angles(120.0, 0.0)
    assert is_ok_exceed is False
    assert "exceeds" in msg_exceed.lower()

    # All registry profiles have valid physical dimensions
    for name, p in CARM_PROFILE_REGISTRY.items():
        assert p.detector_physical_width_mm > 200.0
        assert p.source_to_isocenter_distance_mm >= 600.0


def test_surgical_pose_transformation_supine_to_prone():
    """Verifies that supine-to-prone transformation rotates around Z axis."""
    t_mat = compute_ct_to_surgical_transform("HFS", SurgicalPatientPosition.PRONE_STANDARD)
    # 180° rotation: X -> -X, Y -> -Y, Z -> Z
    assert t_mat[0, 0] == -1.0
    assert t_mat[1, 1] == -1.0
    assert t_mat[2, 2] == 1.0

    # Test point transformation
    pt_supine = np.array([25.0, 30.0, 50.0, 1.0])
    pt_prone = t_mat @ pt_supine
    assert np.allclose(pt_prone[0:3], [-25.0, -30.0, 50.0])


def test_carm_projection_matrix_construction():
    """Verifies SE(3) pose and 3x4 projection matrix construction."""
    beam_dir = np.array([0.0, -1.0, 0.0]) # Anterior to posterior beam
    isocenter = np.array([0.0, 0.0, 0.0])
    profile = PHILIPS_ZENITION_70

    pose = build_carm_projection_geometry(beam_dir, isocenter, profile)

    assert pose.projection_matrix_3x4.shape == (3, 4)
    # Source position is behind the isocenter along negative beam direction
    assert np.allclose(pose.source_position_lps, [0.0, 750.0, 0.0])
    # Detector center is in front of isocenter
    assert np.allclose(pose.detector_center_lps, [0.0, -(993.0 - 750.0), 0.0])

    # Project the isocenter: must project exactly to detector center (cx, cy)
    u_px, v_px, depth = pose.project_point_to_detector_px(isocenter)
    assert np.isclose(u_px, profile.detector_width_px / 2.0, atol=1e-2)
    assert np.isclose(v_px, profile.detector_height_px / 2.0, atol=1e-2)
    assert np.isclose(depth, 750.0, atol=1e-2)


def test_bullseye_needle_en_face_collapse():
    """
    Mathematical Invariant:
    In the Bull's-Eye projection, the needle is aligned with the beam axis.
    The projected 2D distance between skin entry and target papilla must collapse (< 0.5 mm).
    """
    skin_entry = np.array([20.0, 60.0, 30.0])
    calyx_target = np.array([20.0, 10.0, 30.0]) # 50 mm straight tract
    traj = LineSegment3D(skin_entry, calyx_target)

    pose = construct_bullseye_carm_pose(traj, PHILIPS_ZENITION_70)

    u_entry, v_entry, _ = pose.project_point_to_detector_px(skin_entry)
    u_target, v_target, _ = pose.project_point_to_detector_px(calyx_target)

    # Pixel distance
    px_dist = np.hypot(u_entry - u_target, v_entry - v_target)
    # Physical mm on detector
    mm_dist = px_dist * PHILIPS_ZENITION_70.pixel_pitch_mm[0]

    assert mm_dist < 0.5  # Needle collapses into en-face focal dot!


def test_depth_verification_view_shows_extended_needle():
    """
    Mathematical Invariant:
    In the Depth-Verification view, the C-arm is rotated into an oblique view.
    The projected needle must be visible along its shaft (> 20 mm).
    """
    skin_entry = np.array([20.0, 60.0, 30.0])
    calyx_target = np.array([20.0, 10.0, 30.0])
    traj = LineSegment3D(skin_entry, calyx_target)

    pose_depth = construct_depth_verification_carm_pose(traj, oblique_angle_offset_deg=30.0, profile=PHILIPS_ZENITION_70)

    u_entry, v_entry, _ = pose_depth.project_point_to_detector_px(skin_entry)
    u_target, v_target, _ = pose_depth.project_point_to_detector_px(calyx_target)

    px_dist = np.hypot(u_entry - u_target, v_entry - v_target)
    mm_dist = px_dist * PHILIPS_ZENITION_70.pixel_pitch_mm[0]

    assert mm_dist > 20.0  # Full shaft length clearly visible for depth monitoring!


def test_cpu_reference_drr_execution():
    """Verifies analytical CPU reference DRR generation on synthetic phantom volume."""
    vol, spatial, gt = generate_synthetic_pcnl_phantom(grid_shape=(40, 40, 40))

    # Add dense stone (+1000 HU) in the phantom
    vol[18:22, 18:22, 18:22] = 1000.0

    target = np.array([20.0, 20.0, 20.0])
    beam_dir = np.array([0.0, -1.0, 0.0])
    pose = build_carm_projection_geometry(beam_dir, target, PHILIPS_ZENITION_70)

    # Generate 128x128 DRR
    drr = generate_cpu_reference_drr(
        ct_volume_hu=vol,
        spatial=spatial,
        pose=pose,
        output_resolution=(128, 128),
        step_size_mm=3.0,
        polarity="INVERTED_FLUOROSCOPY"
    )

    assert drr.shape == (128, 128)
    assert drr.dtype == np.uint8
    # Image must have dynamic range (not blank)
    assert np.min(drr) < np.max(drr)

    # Test positive polarity
    drr_pos = generate_cpu_reference_drr(
        ct_volume_hu=vol,
        spatial=spatial,
        pose=pose,
        output_resolution=(128, 128),
        step_size_mm=3.0,
        polarity="POSITIVE_RADIOGRAPHIC"
    )
    assert drr_pos.shape == (128, 128)
    # Polarities should be inverse
    assert np.isclose(np.mean(drr.astype(float) + drr_pos.astype(float)), 255.0, atol=10.0)
