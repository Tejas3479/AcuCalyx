"""
AcuCalyx Unit Tests: Milestone M13-P Projection Metrology & Calibration Gate
Governed by ACU-M12V-M13-EXEC-PLAN-2026-V2.
"""

import numpy as np
import pytest

from acucalyx.fluoroscopy.carm_profile import (
    CArmProfile,
    PHILIPS_ZENITION_70,
    ProjectionConfidence,
    SIEMENS_CIOS_ALPHA,
    get_carm_profile
)
from acucalyx.fluoroscopy.rehearsal_simulator import (
    CarmTechnicianTransferCard,
    PunctureRehearsalSimulator
)
from acucalyx.fluoroscopy.surgical_pose import (
    build_carm_projection_geometry,
    construct_bullseye_carm_pose,
    construct_depth_verification_carm_pose
)
from acucalyx.geometry.coordinates import SpatialOrientation
from acucalyx.geometry.transforms import LineSegment3D
from acucalyx.validation.paired_drr_validator import (
    LandmarkObservation,
    PairedCarmDRRValidator,
    PairedFluoroscopyValidationReport
)
from tests.phantom.phantom_generator import generate_synthetic_pcnl_phantom


def test_calibrated_carm_profile_and_confidence_telemetry():
    """Verify that C-arm profiles carry calibration revision and confidence grades."""
    profile = get_carm_profile("philips_zenition_70")
    assert profile.manufacturer == "Philips"
    assert profile.projection_confidence == ProjectionConfidence.DEVICE_PROFILE_CALIBRATED
    assert profile.calibration_revision_id == "CAL-REV-2026A"
    assert profile.principal_point_px == (512.0, 512.0)


def test_technician_transfer_card_assumption_block():
    """Verify that technician transfer card mandates the virtual plan assumption block."""
    card = CarmTechnicianTransferCard(
        case_id="CASE_TEST_01",
        target_calyx="Posterior Lower",
        bullseye_view_label="Bull's-Eye (En-Face)",
        bullseye_primary_angle_deg=18.5,
        bullseye_secondary_angle_deg=12.0,
        depth_view_label="Depth-Verification (Oblique)",
        depth_primary_angle_deg=-15.0,
        depth_secondary_angle_deg=20.0,
        laterality="LEFT"
    )

    assert "VIRTUAL PREOPERATIVE PLAN ASSUMPTION BLOCK" in card.mandatory_assumption_block
    assert "Actual intraoperative gantry position must be independently verified" in card.mandatory_assumption_block
    assert card.projection_confidence == "DEVICE_PROFILE_CALIBRATED"
    assert card.laterality == "LEFT"


def test_depth_verification_pose_avoids_rigid_90_degree_orthodoxy():
    """
    Verify that depth-verification view can be configured to oblique angles (e.g. 30° to 60°)
    respecting C-arm gantry reachability rather than hardcoded 90°.
    """
    traj = LineSegment3D(
        start_point=np.array([40.0, 100.0, -40.0]),
        end_point=np.array([25.0, 20.0, -40.0])
    )

    # 30° oblique depth pose
    pose_30 = construct_depth_verification_carm_pose(
        trajectory=traj,
        oblique_angle_offset_deg=30.0,
        profile=PHILIPS_ZENITION_70
    )
    is_valid_30, reason_30 = PHILIPS_ZENITION_70.validate_gantry_angles(
        pose_30.gantry_primary_angle_deg,
        pose_30.gantry_secondary_angle_deg
    )
    assert is_valid_30 is True
    assert reason_30 is None

    # 45° oblique depth pose
    pose_45 = construct_depth_verification_carm_pose(
        trajectory=traj,
        oblique_angle_offset_deg=45.0,
        profile=PHILIPS_ZENITION_70
    )
    is_valid_45, reason_45 = PHILIPS_ZENITION_70.validate_gantry_angles(
        pose_45.gantry_primary_angle_deg,
        pose_45.gantry_secondary_angle_deg
    )
    assert is_valid_45 is True


def test_paired_physical_carm_drr_landmark_metrology_gate():
    """
    Verifies Protocol M3.3 Landmark Projection Error (LPE) metrology gate
    evaluating paired physical C-arm fiducials vs synthetic DRR projection.
    """
    pixel_pitch = (0.28, 0.28) # mm

    # Synthetic observations with sub-millimeter residuals (matching high-precision calibration)
    observations = [
        LandmarkObservation(
            landmark_id="FID_BEAD_01",
            anatomical_category="fiducial",
            physical_carm_coords_px=(512.0, 512.0),
            drr_projected_coords_px=(513.5, 512.8) # ~1.7 px * 0.28 mm ≈ 0.48 mm error
        ),
        LandmarkObservation(
            landmark_id="FID_BEAD_02",
            anatomical_category="fiducial",
            physical_carm_coords_px=(450.0, 600.0),
            drr_projected_coords_px=(451.2, 599.5) # ~1.3 px * 0.28 mm ≈ 0.36 mm error
        ),
        LandmarkObservation(
            landmark_id="STONE_CENTROID",
            anatomical_category="stone",
            physical_carm_coords_px=(520.0, 480.0),
            drr_projected_coords_px=(521.8, 481.0) # ~2.0 px * 0.28 mm ≈ 0.57 mm error
        ),
        LandmarkObservation(
            landmark_id="CALYX_APEX",
            anatomical_category="calyx_apex",
            physical_carm_coords_px=(505.0, 475.0),
            drr_projected_coords_px=(506.2, 476.1) # ~1.6 px * 0.28 mm ≈ 0.45 mm error
        )
    ]

    validator = PairedCarmDRRValidator(
        max_median_lpe_mm=1.8,
        max_p95_lpe_mm=3.5
    )

    report = validator.evaluate_paired_view(
        view_name="M13P_CALIBRATED_BULLSEYE",
        landmarks=observations,
        pixel_pitch_mm=pixel_pitch,
        gantry_primary_deg=18.5,
        gantry_secondary_deg=12.0
    )

    assert report.is_gate_passed is True
    assert report.median_lpe_mm < 1.0 # Far below 1.8 mm threshold
    assert report.p95_lpe_mm < 1.5   # Far below 3.5 mm threshold
    assert report.total_landmarks_evaluated == 4
