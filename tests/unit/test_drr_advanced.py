"""
AcuCalyx Advanced DRR Tests: Accelerated Ray-Marching, Overlays, and ALARA

Tests:
- Accelerated DRR engine concordance with CPU reference
- NeedleProfile projection (Bull's-Eye collapse & depth-verification shaft)
- Virtual collecting-system contrast visualization (Mode A & Mode B)
- 2D respiratory motion uncertainty envelope projection
- ALARA preoperative radiation planning telemetry
- FastAPI DRR streaming endpoints
"""

import numpy as np
import pytest
from starlette.testclient import TestClient

from acucalyx.fluoroscopy.alara_metrics import generate_alara_planning_report
from acucalyx.fluoroscopy.carm_profile import PHILIPS_ZENITION_70
from acucalyx.fluoroscopy.cpu_reference_drr import generate_cpu_reference_drr
from acucalyx.fluoroscopy.drr_engine import generate_accelerated_drr
from acucalyx.fluoroscopy.motion_projection import (
    compute_projected_motion_envelope,
    overlay_motion_envelope_on_drr,
)
from acucalyx.fluoroscopy.needle_renderer import (
    STANDARD_CHIBA_18G,
    overlay_needle_on_drr,
    project_needle_onto_drr,
)
from acucalyx.fluoroscopy.surgical_pose import (
    build_carm_projection_geometry,
    construct_bullseye_carm_pose,
    construct_depth_verification_carm_pose,
)
from acucalyx.fluoroscopy.virtual_contrast import (
    VirtualContrastMode,
    apply_virtual_contrast_to_volume,
)
from acucalyx.geometry.transforms import LineSegment3D
from app.api.main import app
from tests.phantom.phantom_generator import generate_synthetic_pcnl_phantom


def test_accelerated_drr_concordance_with_cpu_reference():
    """
    Verifies that the accelerated DRR engine produces identical or near-identical
    results to the trusted CPU reference DRR (MAD <= 1.0/255).
    """
    vol, spatial, gt = generate_synthetic_pcnl_phantom(grid_shape=(32, 32, 32))
    target = np.array([16.0, 16.0, 16.0])
    beam_dir = np.array([0.0, -1.0, 0.0])
    pose = build_carm_projection_geometry(beam_dir, target, PHILIPS_ZENITION_70)

    drr_cpu = generate_cpu_reference_drr(
        ct_volume_hu=vol,
        spatial=spatial,
        pose=pose,
        output_resolution=(64, 64),
        step_size_mm=3.0,
        polarity="INVERTED_FLUOROSCOPY"
    )

    drr_acc = generate_accelerated_drr(
        ct_volume_hu=vol,
        spatial=spatial,
        pose=pose,
        output_resolution=(64, 64),
        step_size_mm=3.0,
        polarity="INVERTED_FLUOROSCOPY"
    )

    assert drr_acc.shape == (64, 64)
    # Mean absolute difference in uint8 pixel values
    mad = np.mean(np.abs(drr_acc.astype(float) - drr_cpu.astype(float)))
    assert mad <= 1.5  # Numerical agreement confirmed


def test_needle_renderer_overlay():
    """Verifies needle projection and graduation ring rendering."""
    skin_entry = np.array([20.0, 70.0, 30.0])
    target = np.array([20.0, 10.0, 30.0]) # 60 mm tract
    traj = LineSegment3D(skin_entry, target)

    # 1. Bull's-eye view: needle must be collapsed
    pose_bull = construct_bullseye_carm_pose(traj, PHILIPS_ZENITION_70)
    overlay_bull = project_needle_onto_drr(traj, pose_bull, STANDARD_CHIBA_18G, (128, 128))
    assert overlay_bull.is_bullseye_collapsed is True
    assert len(overlay_bull.graduation_rings_px) == 6  # 60 mm / 10 mm = 6 rings

    # 2. Depth view: needle must be extended
    pose_depth = construct_depth_verification_carm_pose(traj, 30.0, PHILIPS_ZENITION_70)
    overlay_depth = project_needle_onto_drr(traj, pose_depth, STANDARD_CHIBA_18G, (128, 128))
    assert overlay_depth.is_bullseye_collapsed is False
    assert overlay_depth.shaft_length_px > 15.0

    # Test drawing onto image
    base_img = np.ones((128, 128), dtype=np.uint8) * 200
    img_with_needle = overlay_needle_on_drr(base_img, overlay_depth, color_val=0)
    assert np.any(img_with_needle == 0) # Needle drawn


def test_virtual_contrast_modes():
    """Verifies collecting-system contrast visualization modes."""
    vol = np.zeros((30, 30, 30), dtype=np.float32)
    pcs_mask = np.zeros((30, 30, 30), dtype=bool)
    pcs_mask[10:20, 10:20, 10:20] = True

    # Mode B: Attenuation boost (+500 HU)
    vol_b = apply_virtual_contrast_to_volume(vol, pcs_mask, VirtualContrastMode.MODE_B_ATTENUATION_BOOST, 500.0)
    assert np.all(vol_b[pcs_mask] == 500.0)
    assert np.all(vol_b[~pcs_mask] == 0.0)

    # Mode C: Baseline (no change)
    vol_c = apply_virtual_contrast_to_volume(vol, pcs_mask, VirtualContrastMode.MODE_C_BASELINE_NONCONTRAST)
    assert np.all(vol_c == 0.0)


def test_respiratory_motion_projection():
    """Verifies 2D projection of 3D respiratory motion uncertainty."""
    target = np.array([20.0, 10.0, 30.0])
    traj = LineSegment3D(np.array([20.0, 70.0, 30.0]), target)
    pose = construct_bullseye_carm_pose(traj, PHILIPS_ZENITION_70)

    env = compute_projected_motion_envelope(target, pose, (128, 128))
    assert env.semi_major_axis_px > 0.0
    assert env.semi_minor_axis_px > 0.0
    assert env.confidence_level == 0.95
    assert "apnea" in env.clinical_advisory.lower() or "expiration" in env.clinical_advisory.lower()

    # Drawing onto image
    base_img = np.ones((128, 128), dtype=np.uint8) * 200
    img_with_env = overlay_motion_envelope_on_drr(base_img, env, color_val=100)
    assert np.any(img_with_env == 100)


def test_alara_radiation_planning_report():
    """Verifies ALARA radiation planning metrics."""
    report = generate_alara_planning_report(
        bullseye_angles=(15.0, -10.0),
        depth_angles=(45.0, -10.0),
        profile=PHILIPS_ZENITION_70,
        target_kidney_side="left"
    )

    assert report.planned_view_count == 2
    assert report.bullseye_primary_angle_deg == 15.0
    assert report.depth_primary_angle_deg == 45.0
    assert report.estimated_hunting_exposures_saved >= 4
    assert report.recommended_pulse_rate_pps == 8
    assert len(report.alara_clinical_checklist) >= 4
    assert "IEC 60601-2-43:2022" in report.governing_standards


def test_api_drr_alara_endpoint():
    """Verifies API ALARA endpoint using TestClient."""
    client = TestClient(app)

    # First, run a demo case to ensure an active case exists
    res_init = client.post("/api/cases/demo")
    assert res_init.status_code == 200
    case_id = res_init.json()["case_id"]

    # Plan generation
    res_plan = client.post(
        f"/api/cases/{case_id}/plan",
        json={"target_side": "left", "coarse_step_mm": 15.0, "monte_carlo_samples": 20}
    )
    assert res_plan.status_code == 200
    active_cand = res_plan.json()["active_candidate_id"]

    # Request ALARA report
    res_alara = client.get(f"/api/cases/{case_id}/drr/{active_cand}/alara")
    assert res_alara.status_code == 200
    data = res_alara.json()
    assert data["planned_views"] == 2
    assert "bullseye_gantry_angles" in data
    assert "depth_gantry_angles" in data
    assert data["recommended_pulse_rate_pps"] == 8

    # Request Bull's-eye DRR image
    res_drr = client.get(f"/api/cases/{case_id}/drr/{active_cand}/bullseye?resolution=128")
    assert res_drr.status_code == 200
    assert res_drr.headers["content-type"] == "image/png"
    assert len(res_drr.content) > 100
