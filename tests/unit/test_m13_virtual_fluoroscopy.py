"""
AcuCalyx Unit Tests: Milestone M13 Calibrated Virtual Fluoroscopy & Rehearsal Simulator
Governed by ACU-M12V-M13-EXEC-PLAN-2026-V2.

Verifies:
1. Standardized C-arm technician transfer card with mandatory assumption block and calibration metadata.
2. Continuous needle advancement state synchronization (0.0 to 1.0) across 4 views.
3. ALARA radiation-exposure planning & workflow support with dose telemetry disclaimers.
4. FastAPI endpoints for technician card, rehearsal state, and dual DRR streaming.
5. Virtual pyelogram contrast boost fidelity.
"""

import numpy as np
import pytest
from starlette.testclient import TestClient

from acucalyx.fluoroscopy.alara_metrics import (
    ALARAPlanningReport,
    generate_alara_planning_report
)
from acucalyx.fluoroscopy.carm_profile import (
    CArmProfile,
    PHILIPS_ZENITION_70,
    ProjectionConfidence,
    SIEMENS_CIOS_ALPHA,
    get_carm_profile
)
from acucalyx.fluoroscopy.needle_renderer import STANDARD_CHIBA_18G
from acucalyx.fluoroscopy.rehearsal_simulator import (
    AnatomicalProgressionPhase,
    CarmTechnicianTransferCard,
    PunctureRehearsalSimulator,
    RehearsalState
)
from acucalyx.fluoroscopy.surgical_pose import (
    construct_bullseye_carm_pose,
    construct_depth_verification_carm_pose
)
from acucalyx.fluoroscopy.virtual_contrast import (
    VirtualContrastMode,
    apply_virtual_contrast_to_volume
)
from acucalyx.geometry.coordinates import SpatialOrientation
from acucalyx.geometry.transforms import LineSegment3D
from acucalyx.validation.procedural_evaluator import TargetFornicealZone
from app.api.main import app


def test_technician_transfer_card_with_metrology_and_assumption_block():
    """Verifies that the technician card contains calibrated metrology and mandatory assumption block."""
    sim = PunctureRehearsalSimulator(carm_profile=PHILIPS_ZENITION_70)
    traj = LineSegment3D(
        start_point=np.array([30.0, -90.0, 30.0]),
        end_point=np.array([25.0, 10.0, 35.0])
    )

    card = sim.generate_transfer_card(
        case_id="CASE_M13_001",
        target_calyx_name="Posterior Lower Pole",
        planned_trajectory=traj,
        laterality="RIGHT",
        oblique_angle_deg=40.0
    )

    assert card.case_id == "CASE_M13_001"
    assert card.target_calyx == "Posterior Lower Pole"
    assert card.laterality == "RIGHT"
    assert card.carm_model == "Zenition_70_Flat_Detector"
    assert card.calibration_revision == "CAL-REV-2026A"
    assert card.projection_confidence == "DEVICE_PROFILE_CALIBRATED"
    assert "40° Oblique" in card.depth_view_label
    assert "VIRTUAL PREOPERATIVE PLAN ASSUMPTION BLOCK" in card.mandatory_assumption_block
    assert "independently verified" in card.mandatory_assumption_block
    assert len(card.procedural_checklist) >= 5


def test_continuous_rehearsal_state_synchronization():
    """Verifies 4-view synchronized surgical state across advancement continuum (0.0 to 1.0)."""
    sim = PunctureRehearsalSimulator(carm_profile=PHILIPS_ZENITION_70)
    traj = LineSegment3D(
        start_point=np.array([25.0, -80.0, 35.0]),
        end_point=np.array([22.0, 15.0, 40.0])
    )
    zone = TargetFornicealZone(
        calyx_name="lower_pole_posterior",
        forniceal_apex_lps=traj.end_point,
        infundibular_axis_unit=np.array([0.0, 1.0, 0.0]),
        papilla_radius_mm=3.0,
        papilla_depth_mm=4.0
    )
    spatial = SpatialOrientation.from_dicom_parameters(
        image_orientation_patient=[1.0, 0.0, 0.0, 0.0, 1.0, 0.0],
        image_position_patient=[-64.0, -64.0, 0.0],
        pixel_spacing=[1.0, 1.0],
        slice_spacing=1.0
    )

    # 1. Skin entry (0.0)
    state_0 = sim.compute_advancement_state(traj, zone, advancement_fraction=0.0, spatial=spatial)
    assert state_0.active_progression_phase == AnatomicalProgressionPhase.SKIN_ENTRY
    assert state_0.penetration_depth_mm == 0.0
    assert state_0.total_planned_depth_mm > 90.0
    assert state_0.projected_bullseye.is_bullseye_collapsed is True

    # 2. Parenchymal tunnel (0.50)
    state_50 = sim.compute_advancement_state(traj, zone, advancement_fraction=0.50, spatial=spatial)
    assert state_50.active_progression_phase == AnatomicalProgressionPhase.PARENCHYMAL_TUNNEL
    assert pytest.approx(state_50.penetration_depth_mm, abs=1.0) == state_50.total_planned_depth_mm * 0.50
    assert state_50.projected_depth_view.shaft_length_px > 0.0

    # 3. Target papilla zone (0.90)
    state_90 = sim.compute_advancement_state(traj, zone, advancement_fraction=0.90, spatial=spatial)
    assert state_90.active_progression_phase in (
        AnatomicalProgressionPhase.PAPILLARY_TARGET_ZONE,
        AnatomicalProgressionPhase.COLLECTING_SYSTEM_LUMEN
    )

    # 4. Calculus contact / papilla arrival (1.00)
    state_100 = sim.compute_advancement_state(traj, zone, advancement_fraction=1.0, spatial=spatial)
    assert state_100.active_progression_phase in (
        AnatomicalProgressionPhase.CALCULUS_CONTACT,
        AnatomicalProgressionPhase.PAPILLARY_TARGET_ZONE
    )
    assert pytest.approx(state_100.penetration_depth_mm, abs=0.1) == state_100.total_planned_depth_mm


def test_alara_workflow_and_telemetry_disclaimers():
    """Verifies that ALARA report includes protocol guidance and live telemetry disclaimer."""
    report = generate_alara_planning_report(
        bullseye_angles=(20.0, -12.0),
        depth_angles=(50.0, -12.0),
        profile=PHILIPS_ZENITION_70,
        target_kidney_side="right"
    )

    assert report.planned_view_count == 2
    assert "RIGHT" in report.collimation_advisory
    assert "does not ingest real-time exposure telemetry" in report.dose_telemetry_disclaimer
    assert "lowest clinically acceptable" in report.pulse_rate_protocol_hint.lower()
    assert "IEC 62304 / ISO 14971" in report.governing_standards
    assert "IEC 60601-2-43:2022 Reference" in report.governing_standards


def test_rehearsal_and_transfer_card_api_endpoints():
    """Verifies FastAPI rehearsal endpoints return full transfer card and step telemetry."""
    client = TestClient(app)

    # Transfer Card Endpoint
    res_card = client.get("/api/cases/demo_case_01/rehearsal/transfer-card?carm_model=philips_zenition_70&oblique_angle_deg=35.0")
    assert res_card.status_code == 200
    card_data = res_card.json()
    assert "mandatory_assumption_block" in card_data
    assert "VIRTUAL PREOPERATIVE PLAN ASSUMPTION BLOCK" in card_data["mandatory_assumption_block"]
    assert card_data["carm_model"] == "Zenition_70_Flat_Detector"
    assert card_data["projection_confidence"] == "DEVICE_PROFILE_CALIBRATED"

    # Rehearsal Step Endpoint
    res_step = client.get("/api/cases/demo_case_01/rehearsal/state?advancement=0.45")
    assert res_step.status_code == 200
    step_data = res_step.json()
    assert step_data["advancement_fraction"] == 0.45
    assert step_data["active_progression_phase"] == "PARENCHYMAL_TUNNEL"
    assert "bullseye_projection" in step_data
    assert "depth_projection" in step_data
    assert len(step_data["current_tip_lps"]) == 3


def test_virtual_pyelogram_contrast_boost_invariance():
    """Verifies that Virtual Contrast Boost modifies collecting system while keeping other CT HU unchanged."""
    vol = np.zeros((32, 32, 32), dtype=np.float32)
    pcs_mask = np.zeros((32, 32, 32), dtype=bool)
    pcs_mask[10:15, 10:15, 10:15] = True

    boosted = apply_virtual_contrast_to_volume(vol, pcs_mask, VirtualContrastMode.MODE_B_ATTENUATION_BOOST)
    assert np.all(boosted[pcs_mask] == 500.0)
    assert np.all(boosted[~pcs_mask] == 0.0)
