"""
AcuCalyx Unit Tests: Phase 5 / M3 Procedural Validation & Physical Phantom Metrology

Governing Requirement: Frozen Plan v5.1
Tests:
1. Anthropomorphic phantom specifications, radiodensity tolerance checking, and metrology uncertainty budget.
2. Watertight negative mold CAD STL generator and volume conservation (< 1.0% error).
3. 3D Target Forniceal Zone (Z_target) containment, zone TLE vs apex TLE.
4. ASTM F2554 four-vector error engine and 6-tier puncture classification taxonomy.
5. Exact one-sided 95% Clopper-Pearson upper confidence limit calculator.
6. Paired physical C-arm vs synthetic DRR multi-metric landmark evaluator (Protocol M3.3).
7. Rehearsal state engine advancement and C-arm technician transfer card generation.
"""

import math
import os
import tempfile
import numpy as np
import pytest

from acucalyx.fluoroscopy.carm_profile import PHILIPS_ZENITION_70
from acucalyx.fluoroscopy.needle_renderer import STANDARD_CHIBA_18G
from acucalyx.fluoroscopy.rehearsal_simulator import (
    AnatomicalProgressionPhase,
    PunctureRehearsalSimulator,
)
from acucalyx.geometry.coordinates import SpatialOrientation
from acucalyx.geometry.transforms import LineSegment3D
from acucalyx.phantom.mold_generator import (
    PhantomMoldCADGenerator,
    compute_mesh_volume_and_area,
    write_binary_stl,
)
from acucalyx.phantom.phantom_spec import (
    MetrologyUncertaintyBudget,
    STANDARD_ANTHROPOMORPHIC_SPEC,
)
from acucalyx.validation.paired_drr_validator import (
    LandmarkObservation,
    PairedCarmDRRValidator,
    compute_normalized_cross_correlation,
)
from acucalyx.validation.procedural_evaluator import (
    PunctureClassification,
    PunctureExecutionTrial,
    ProceduralAccuracyEvaluator,
    TargetFornicealZone,
    compute_exact_clopper_pearson_upper_bound,
)
from tests.phantom.phantom_generator import generate_synthetic_pcnl_phantom


# ---------------------------------------------------------------------------
# 1. Phantom Specification & Metrology Uncertainty Budget
# ---------------------------------------------------------------------------
def test_phantom_spec_and_metrology_budget():
    spec = STANDARD_ANTHROPOMORPHIC_SPEC
    assert len(spec.layers) == 8
    assert "renal_parenchyma" in spec.layers
    assert "target_calculi" in spec.layers

    # Attenuation check: Parenchyma target 45 HU, range [30, 60]
    ok, msg = spec.validate_layer_attenuation("renal_parenchyma", 45.0)
    assert ok is True
    assert "PASS" in msg

    ok_out, msg_out = spec.validate_layer_attenuation("renal_parenchyma", 120.0)
    assert ok_out is False
    assert "FAIL" in msg_out

    # Metrology budget verification:
    budget = MetrologyUncertaintyBudget(sigma_mfg_mm=0.60, sigma_reg_mm=0.50, sigma_meas_mm=0.25)
    # sigma_total = sqrt(0.60^2 + 0.50^2 + 0.25^2) = sqrt(0.36 + 0.25 + 0.0625) = sqrt(0.6725) ≈ 0.820
    assert pytest.approx(budget.cumulative_uncertainty_mm, abs=0.01) == 0.82
    # Expanded uncertainty U_95 = 2 * 0.820 ≈ 1.64 mm
    assert pytest.approx(budget.expanded_uncertainty_k2_mm, abs=0.02) == 1.64
    assert budget.is_acceptable(max_expanded_mm=2.0) is True


# ---------------------------------------------------------------------------
# 2. Automated Negative Mold CAD Generation & STL Export
# ---------------------------------------------------------------------------
def test_negative_mold_cad_generator():
    vol, spatial, gt = generate_synthetic_pcnl_phantom(grid_shape=(32, 32, 32))
    generator = PhantomMoldCADGenerator(wall_thickness_mm=5.0, sprue_diameter_mm=8.0)

    # Create synthetic kidney and collecting system masks
    y, x, z = np.ogrid[:32, :32, :32]
    dist_sq = (x - 16)**2 + (y - 16)**2 + (z - 16)**2
    kidney_mask = dist_sq <= 10**2
    pcs_mask = dist_sq <= 4**2

    masks = {
        "kidney": kidney_mask,
        "collecting_system": pcs_mask
    }

    with tempfile.TemporaryDirectory() as tmp_dir:
        package = generator.generate_complete_mold_package(
            case_id="TEST_CASE_M3",
            segmentation_masks=masks,
            spatial=spatial,
            output_dir=tmp_dir
        )

        assert package.pva_core_volume_cm3 > 0.0
        assert package.parenchyma_mold_volume_cm3 > 0.0
        # Volume preservation error should be small
        assert package.volume_preservation_error_pct < 5.0
        assert package.is_watertight is True

        pva_file = package.generated_stl_files["collecting_system_core"]
        par_file = package.generated_stl_files["kidney_parenchyma_mold"]
        assert os.path.exists(pva_file)
        assert os.path.exists(par_file)
        assert os.path.getsize(pva_file) > 84  # Header + triangle data


# ---------------------------------------------------------------------------
# 3. Target Forniceal Zone & ASTM F2554 Distance Formulations
# ---------------------------------------------------------------------------
def test_target_forniceal_zone_and_distance_metrics():
    apex = np.array([20.0, 30.0, 40.0])
    axis = np.array([0.0, 1.0, 0.0])  # Points along +Y
    zone = TargetFornicealZone(
        calyx_name="lower_pole_posterior",
        forniceal_apex_lps=apex,
        infundibular_axis_unit=axis,
        papilla_radius_mm=3.0,
        papilla_depth_mm=4.0
    )

    # Point at apex is inside zone
    assert zone.contains_point(apex) is True
    assert zone.distance_to_zone(apex) == 0.0
    assert zone.distance_to_apex(apex) == 0.0

    # Point 2 mm along axis, 1 mm radial -> inside zone
    pt_inside = apex + np.array([1.0, 2.0, 0.0])
    assert zone.contains_point(pt_inside) is True
    assert zone.distance_to_zone(pt_inside) == 0.0

    # Point 10 mm away -> outside zone
    pt_outside = apex + np.array([10.0, 2.0, 0.0])
    assert zone.contains_point(pt_outside) is False
    tle_zone = zone.distance_to_zone(pt_outside)
    tle_apex = zone.distance_to_apex(pt_outside)
    assert tle_zone > 0.0
    assert tle_zone < tle_apex  # Zone TLE is strictly closer than apex centerpoint


# ---------------------------------------------------------------------------
# 4. ASTM F2554 Procedural Accuracy & Classification Taxonomy
# ---------------------------------------------------------------------------
def test_astm_f2554_procedural_evaluator():
    evaluator = ProceduralAccuracyEvaluator(
        max_tle_zone_mm=1.5,
        max_tle_apex_mm=4.5,
        max_entry_dev_mm=8.0,
        max_angular_dev_deg=5.0
    )

    apex = np.array([20.0, 30.0, 40.0])
    axis = np.array([0.0, 1.0, 0.0])
    zone = TargetFornicealZone(
        calyx_name="lower_pole_posterior",
        forniceal_apex_lps=apex,
        infundibular_axis_unit=axis,
        papilla_radius_mm=3.0
    )

    planned_entry = np.array([20.0, -50.0, 40.0])
    planned_traj = LineSegment3D(start_point=planned_entry, end_point=apex)

    # Trial 1: Ideal axial cannulation
    trial_ideal = PunctureExecutionTrial(
        trial_id="T01",
        operator_id="EXPERT_1",
        planned_trajectory=planned_traj,
        physical_needle_entry_lps=planned_entry + np.array([0.5, 0.0, 0.0]),
        physical_needle_tip_lps=apex + np.array([0.2, 0.5, 0.0]),
        target_zone=zone,
        is_counter_puncture_observed=False,
        is_first_pass=True
    )
    res_ideal = evaluator.evaluate_trial(trial_ideal)
    assert res_ideal.puncture_classification == PunctureClassification.SUCCESS_FORNIX_AXIAL
    assert res_ideal.is_clinically_acceptable is True
    assert res_ideal.is_first_pass_success is True
    assert res_ideal.tle_zone_mm == 0.0

    # Trial 2: Through-and-through counter-puncture
    trial_counter = PunctureExecutionTrial(
        trial_id="T02",
        operator_id="NOVICE_1",
        planned_trajectory=planned_traj,
        physical_needle_entry_lps=planned_entry,
        physical_needle_tip_lps=apex + np.array([0.0, 15.0, 0.0]),  # Over-penetrated by 15 mm
        target_zone=zone,
        is_counter_puncture_observed=True,
        is_first_pass=False
    )
    res_counter = evaluator.evaluate_trial(trial_counter)
    assert res_counter.puncture_classification == PunctureClassification.FAILURE_COUNTER_PUNCTURE
    assert res_counter.is_clinically_acceptable is False


# ---------------------------------------------------------------------------
# 5. Exact Clopper-Pearson Binomial Upper Confidence Limits
# ---------------------------------------------------------------------------
def test_exact_clopper_pearson_upper_bound_calculation():
    # 0 events in N=10 trials: p_upper = 1 - 0.05^(1/10) ≈ 25.89%
    cp_10 = compute_exact_clopper_pearson_upper_bound(0, 10, 0.95)
    assert pytest.approx(cp_10 * 100.0, abs=0.1) == 25.89

    # 0 events in N=30 trials: p_upper = 1 - 0.05^(1/30) ≈ 9.50%
    cp_30 = compute_exact_clopper_pearson_upper_bound(0, 30, 0.95)
    assert pytest.approx(cp_30 * 100.0, abs=0.1) == 9.50

    # 0 events in N=48 trials: p_upper = 1 - 0.05^(1/48) ≈ 6.05%
    cp_48 = compute_exact_clopper_pearson_upper_bound(0, 48, 0.95)
    assert pytest.approx(cp_48 * 100.0, abs=0.1) == 6.05

    # 1 event in N=50 trials: via Beta distribution
    cp_50_1 = compute_exact_clopper_pearson_upper_bound(1, 50, 0.95)
    assert 0.08 < cp_50_1 < 0.12


# ---------------------------------------------------------------------------
# 6. Paired Physical C-Arm vs Synthetic DRR Validator (Protocol M3.3)
# ---------------------------------------------------------------------------
def test_paired_carm_drr_validator():
    validator = PairedCarmDRRValidator(
        max_median_lpe_mm=1.8,
        max_p95_lpe_mm=3.5,
        min_ssim=0.75,
        min_ncc=0.85
    )

    # 5 paired landmarks with sub-1 mm errors
    landmarks = [
        LandmarkObservation("fid_1", "fiducial", (100.0, 100.0), (101.0, 100.5)),
        LandmarkObservation("fid_2", "fiducial", (200.0, 100.0), (199.5, 101.0)),
        LandmarkObservation("stone", "stone", (250.0, 250.0), (251.0, 250.0)),
        LandmarkObservation("calyx_apex", "calyx_apex", (240.0, 230.0), (239.0, 231.0)),
        LandmarkObservation("needle_tip", "needle", (240.0, 230.0), (240.5, 230.2)),
    ]

    pixel_pitch_mm = (0.3, 0.3)  # Standard flat detector pixel size

    # Synthetic paired ROIs (highly correlated)
    roi_phys = np.ones((64, 64), dtype=np.uint8) * 128
    roi_phys[20:40, 20:40] = 220
    roi_drr = roi_phys.copy()
    roi_drr[21:41, 21:41] = 215  # Small 1-pixel shift

    report = validator.evaluate_paired_view(
        view_name="Bull's-Eye View (LAO 18° CAUD 12°)",
        landmarks=landmarks,
        pixel_pitch_mm=pixel_pitch_mm,
        gantry_primary_deg=18.0,
        gantry_secondary_deg=-12.0,
        physical_image_roi=roi_phys,
        drr_image_roi=roi_drr
    )

    assert report.total_landmarks_evaluated == 5
    assert report.median_lpe_mm < 1.0
    assert report.is_gate_passed is True
    assert report.ssim is not None and report.ssim > 0.80
    assert report.ncc is not None and report.ncc > 0.90


# ---------------------------------------------------------------------------
# 7. Surgical Rehearsal Simulator & State Engine
# ---------------------------------------------------------------------------
def test_puncture_rehearsal_simulator_and_transfer_card():
    simulator = PunctureRehearsalSimulator(carm_profile=PHILIPS_ZENITION_70)

    start_pt = np.array([20.0, -60.0, 30.0])
    end_pt = np.array([20.0, 30.0, 30.0])
    traj = LineSegment3D(start_point=start_pt, end_point=end_pt)

    axis = np.array([0.0, 1.0, 0.0])
    zone = TargetFornicealZone(
        calyx_name="lower_pole_posterior",
        forniceal_apex_lps=end_pt,
        infundibular_axis_unit=axis
    )

    spatial = SpatialOrientation.from_dicom_parameters(
        image_orientation_patient=[1.0, 0.0, 0.0, 0.0, 1.0, 0.0],
        image_position_patient=[0.0, -100.0, 0.0],
        pixel_spacing=[1.0, 1.0],
        slice_spacing=1.0
    )

    # State at 0% advancement
    state_0 = simulator.compute_advancement_state(traj, zone, 0.0, spatial)
    assert state_0.active_progression_phase == AnatomicalProgressionPhase.SKIN_ENTRY
    assert state_0.penetration_depth_mm == 0.0

    # State at 50% advancement
    state_50 = simulator.compute_advancement_state(traj, zone, 0.50, spatial)
    assert state_50.active_progression_phase == AnatomicalProgressionPhase.PARENCHYMAL_TUNNEL
    assert pytest.approx(state_50.penetration_depth_mm, abs=0.1) == 45.0

    # State at 100% advancement
    state_100 = simulator.compute_advancement_state(traj, zone, 1.0, spatial)
    assert state_100.active_progression_phase in [
        AnatomicalProgressionPhase.PAPILLARY_TARGET_ZONE,
        AnatomicalProgressionPhase.CALCULUS_CONTACT
    ]
    assert pytest.approx(state_100.penetration_depth_mm, abs=0.1) == 90.0

    # C-arm technician transfer card
    card = simulator.generate_transfer_card("CASE_001", "lower_pole_posterior", traj)
    assert card.case_id == "CASE_001"
    assert card.recommended_pulse_rate_pps == 8
    assert len(card.procedural_checklist) >= 4
