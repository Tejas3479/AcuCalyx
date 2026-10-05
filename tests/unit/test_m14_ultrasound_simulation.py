"""
AcuCalyx Automated Test Suite: Milestone M14 Multimodal Ultrasound Simulation & Positioning Uncertainty
Governed by ACU-M14-EXEC-PLAN-2026-V2.

Tests:
1. Milestone M14.0 Reference Data & Physical Phantom Specifications
2. Milestone M14A Positioning & Probe-Pressure Uncertainty Engine
3. Milestone M14B Physics-Informed Simulated Ultrasound (Acoustics, Probes, NAVI, Windows, B-Mode)
4. Milestone M14C Cross-Modal Phantom & Human Validation Gate
5. Milestone M14D API Endpoints via FastAPI TestClient
"""

import io
import math
import numpy as np
from PIL import Image
import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from acucalyx.ultrasound.reference_registry import (
    DualModalTissueProperty,
    DualModalPhantomSpecification,
    PairedUltrasoundCTCase,
    PCNLUltrasoundReferenceRegistry,
    STANDARD_DUAL_MODAL_PHANTOM_SPEC,
)
from acucalyx.ultrasound.position_uncertainty import (
    OperativePosition,
    PatientHabitus,
    VentilationMode,
    StratifiedPositioningCovarianceEngine,
    evaluate_monte_carlo_hazard_clearance,
)
from acucalyx.ultrasound.acoustic_properties import (
    AcousticTissueClass,
    CalibratedAcousticMedium,
    STANDARD_ACOUSTIC_MEDIA,
    classify_ct_voxel_to_acoustic_medium,
    compute_two_way_attenuation_intensity,
    compute_boundary_reflection,
    LN10_DIV_10,
)
from acucalyx.ultrasound.probe_profile import (
    TransducerProfile,
    TransducerType,
    CURVILINEAR_C5_2,
    LINEAR_L12_4,
    STANDARD_PROBES,
    UltrasoundProbePose,
    get_ultrasound_probe,
)
from acucalyx.ultrasound.needle_ultrasound import (
    calculate_needle_acoustic_visibility,
    NAVICategory,
)
from acucalyx.ultrasound.acoustic_window import (
    evaluate_flank_acoustic_window,
    AcousticWindowCategory,
)
from acucalyx.ultrasound.bmode_simulator import (
    BModeUltrasoundSimulator,
    generate_simulated_bmode_ultrasound,
)
from acucalyx.ultrasound.phantom_validator import (
    compute_cohens_kappa,
    compute_stone_shadow_iou,
    compute_binary_diagnostic_metrics,
    compute_pearson_correlation,
    evaluate_m14c_clinical_gate,
)


client = TestClient(app)


# ==============================================================================
# 1. Milestone M14.0: Reference Dataset & Phantom Metrology Tests
# ==============================================================================

def test_m14_0_standard_phantom_specification():
    """Validates physical TMM phantom specs for certified HU and acoustic parameters."""
    spec = STANDARD_DUAL_MODAL_PHANTOM_SPEC
    assert spec.phantom_id in ("ACU-PHANTOM-DM-2026", "PHANTOM_RENAL_DUAL_MODAL_V1")
    assert "parenchyma" in spec.layers
    assert "calculus_oxalate" in spec.layers
    assert "urine" in spec.layers
    assert "rib" in spec.layers

    parenchyma = spec.layers["parenchyma"]
    assert 1530.0 <= parenchyma.target_speed_of_sound_m_s <= 1560.0
    assert parenchyma.is_ct_valid(35.0)
    assert not parenchyma.is_ct_valid(150.0)
    assert parenchyma.is_acoustic_valid(1542.0, 0.52)
    assert not parenchyma.is_acoustic_valid(1650.0, 0.52)


def test_m14_0_reference_registry_cases():
    """Validates paired CT-to-US reference dataset registry."""
    registry = PCNLUltrasoundReferenceRegistry.create_standard_registry()
    cases = registry.list_cases()
    assert len(cases) >= 3

    case1 = registry.get_case("REF_PCNL_US_01")
    assert case1 is not None
    assert case1.operative_side == "LEFT"
    assert case1.calyx_visibility_state == "DIRECTLY_IDENTIFIED"
    assert case1.has_posterior_shadow is True
    assert len(case1.expert_reviews) == 2


# ==============================================================================
# 2. Milestone M14A: Positioning & Probe-Pressure Uncertainty Tests
# ==============================================================================

def test_m14_a_stratified_covariance_laterality_and_habitus():
    """Validates right vs left kidney displacement and BMI fat damping."""
    # Right kidney (liver splinted) vs Left kidney (free slump)
    engine_r = StratifiedPositioningCovarianceEngine(
        position=OperativePosition.PRONE_STANDARD,
        habitus=PatientHabitus.NORMAL_BMI,
        is_right_kidney=True,
    )
    engine_l = StratifiedPositioningCovarianceEngine(
        position=OperativePosition.PRONE_STANDARD,
        habitus=PatientHabitus.NORMAL_BMI,
        is_right_kidney=False,
    )

    sigma_r = engine_r.get_positioning_covariance()
    sigma_l = engine_l.get_positioning_covariance()

    # Left kidney has higher anterior-posterior slump variance (Y-axis, index 1,1)
    assert sigma_l[1, 1] > sigma_r[1, 1]

    # High BMI dampens mobile kidney excursion compared to Low BMI
    engine_high_bmi = StratifiedPositioningCovarianceEngine(
        habitus=PatientHabitus.HIGH_BMI,
        is_right_kidney=True,
    )
    engine_low_bmi = StratifiedPositioningCovarianceEngine(
        habitus=PatientHabitus.LOW_BMI,
        is_right_kidney=True,
    )
    assert np.trace(engine_high_bmi.get_positioning_covariance()) < np.trace(engine_low_bmi.get_positioning_covariance())


def test_m14_a_respiratory_apnea_clamping():
    """Validates end-expiratory apnea interlock clamps cranio-caudal variance <= 1.5 mm."""
    eng_tidal = StratifiedPositioningCovarianceEngine(ventilation=VentilationMode.MECHANICAL_TIDAL)
    eng_apnea = StratifiedPositioningCovarianceEngine(ventilation=VentilationMode.END_EXPIRATORY_APNEA)

    sigma_resp_tidal = eng_tidal.get_respiratory_covariance()
    sigma_resp_apnea = eng_apnea.get_respiratory_covariance()

    # Z-axis respiratory variance (index 2,2)
    assert sigma_resp_tidal[2, 2] > sigma_resp_apnea[2, 2]
    # Apnea standard deviation sqrt(var) <= 1.5 mm
    assert math.sqrt(sigma_resp_apnea[2, 2]) <= 1.5


def test_m14_a_probe_pressure_directional_covariance():
    """Validates transducer contact force covariance is aligned with probe acoustic axis normal."""
    eng = StratifiedPositioningCovarianceEngine()
    probe_normal = np.array([0.0, 1.0, 0.0])  # Normal along Y
    sigma_probe = eng.get_probe_pressure_covariance(probe_normal)

    # Variance should be concentrated along Y-axis
    assert sigma_probe[1, 1] > 0.0
    assert sigma_probe[0, 0] == 0.0
    assert sigma_probe[2, 2] == 0.0


def test_m14_a_monte_carlo_hazard_clearance_and_fail_closed():
    """Validates empirical clearance probability and fail-closed NO_PLAN interlock."""
    eng = StratifiedPositioningCovarianceEngine()
    total_cov = eng.get_total_covariance()

    # Safe clearances
    safe_hazards = {"Colon": 20.0, "Spleen": 30.0, "Lung": 25.0}
    safe_eval = evaluate_monte_carlo_hazard_clearance(safe_hazards, total_cov, n_samples=2000)
    assert safe_eval.passed is True
    assert safe_eval.clearance_probability >= 0.95
    assert safe_eval.safety_tier in ("PREFERRED", "FEASIBLE")

    # Hazardous clearances (Colon dangerously close at 1.0 mm)
    hazard_close = {"Colon": 1.0, "Spleen": 25.0, "Lung": 20.0}
    fail_eval = evaluate_monte_carlo_hazard_clearance(hazard_close, total_cov, n_samples=2000)
    assert fail_eval.clearance_probability < 0.80
    assert fail_eval.safety_tier == "NO_PLAN — POSITION UNCERTAINTY EXCEEDS VALIDATED ENVELOPE"
    assert fail_eval.passed is False


# ==============================================================================
# 3. Milestone M14B: Physics-Informed Simulated Ultrasound Tests
# ==============================================================================

def test_m14_b_acoustic_attenuation_scaling():
    """Validates dimensionally correct two-way attenuation scaling with ln(10)/10."""
    alpha_db = 0.54  # dB/(cm*MHz)
    freq_mhz = 3.5  # MHz
    depth_cm = 10.0  # cm
    cum_atten_db = alpha_db * depth_cm  # 5.4 dB/MHz

    # Manual calculation: I_roundtrip = I0 * 10^(-2 * cum_atten / 10) = 10^(-2 * 5.4 * 3.5 / 10) = 10^(-3.78)
    expected_intensity = 10.0 ** (-2.0 * (cum_atten_db * freq_mhz) / 10.0)
    computed_intensity = compute_two_way_attenuation_intensity(cum_atten_db, freq_mhz)

    assert pytest.approx(computed_intensity, rel=1e-5) == expected_intensity
    assert computed_intensity < 1.0
    assert computed_intensity > 0.0


def test_m14_b_tissue_boundary_reflection():
    """Validates acoustic impedance mismatch reflection at tissue boundaries."""
    # Soft tissue (Z ~ 1.63 MRayl) to Bowel Gas (Z ~ 0.00041 MRayl)
    z_tissue = 1.63
    z_gas = 0.00041
    r, R, T = compute_boundary_reflection(z_tissue, z_gas)
    assert R > 0.998  # Almost 100% power reflected -> acoustic blackout
    assert T < 0.002

    # Renal parenchyma (Z ~ 1.638) to Fluid (Z ~ 1.490)
    z_fluid = 1.490
    r_tf, R_tf, T_tf = compute_boundary_reflection(z_tissue, z_fluid)
    assert R_tf < 0.01  # Very low reflection -> smooth acoustic transmission
    assert T_tf > 0.99


def test_m14_b_navi_specular_incidence_angle():
    """Validates NAVI specular angle drop-off and normal incidence peak."""
    beam_dir = np.array([0.0, 0.0, 1.0])

    # Perpendicular needle (tangent along X: 90 deg relative to beam) -> Maximal NAVI
    needle_perp = np.array([1.0, 0.0, 0.0])
    res_perp = calculate_needle_acoustic_visibility(needle_perp, beam_dir)
    assert res_perp.specular_component == pytest.approx(1.0, abs=1e-4)
    assert res_perp.navi_score >= 0.70
    assert res_perp.category == NAVICategory.OPTIMAL_ACOUSTIC_ALIGNMENT

    # Parallel needle (tangent along Z: 0 deg relative to beam) -> Vanishing NAVI
    needle_par = np.array([0.0, 0.0, 1.0])
    res_par = calculate_needle_acoustic_visibility(needle_par, beam_dir)
    assert res_par.specular_component == pytest.approx(0.0, abs=1e-4)
    assert res_par.navi_score < 0.05
    assert res_par.category == NAVICategory.SEVERE_SPECULAR_DROPOFF


def test_m14_b_navi_elevational_slice_thickness_dropoff():
    """Validates Gaussian elevational out-of-plane drop-off."""
    beam_dir = np.array([0.0, 0.0, 1.0])
    needle_perp = np.array([1.0, 0.0, 0.0])

    # In-plane (offset = 0)
    res_in = calculate_needle_acoustic_visibility(needle_perp, beam_dir, elevational_offset_mm=0.0)
    # Out-of-plane (offset = 4.0 mm with 3.0 mm FWHM slice thickness)
    res_out = calculate_needle_acoustic_visibility(needle_perp, beam_dir, elevational_offset_mm=4.0, elevational_slice_fwhm_mm=3.0)

    assert res_in.elevational_component == 1.0
    assert res_out.elevational_component < 0.20
    assert res_out.is_in_plane is False


def test_m14_b_flank_acoustic_window_planner():
    """Validates multi-factor flank window categorization (GOOD vs POOR vs UNAVAILABLE)."""
    entry = np.array([100.0, -150.0, -50.0])
    target = np.array([80.0, -110.0, -60.0])

    # Clear window with no rib obstacles
    good_report = evaluate_flank_acoustic_window(entry, target, rib_surface_points=None, pleural_reflection_z_mm=-10.0)
    assert good_report.window_category == AcousticWindowCategory.GOOD
    assert good_report.corridor_rib_occlusion_pct == 0.0
    assert good_report.target_calyx_visible is True

    # Puncture crossing pleural line (pleura at Z = -80 mm, entry at Z = -50 mm)
    pleural_breach = evaluate_flank_acoustic_window(entry, target, pleural_reflection_z_mm=-80.0)
    assert pleural_breach.window_category == AcousticWindowCategory.UNAVAILABLE
    assert pleural_breach.pleural_clearance_mm < 0.0


def test_m14_b_simulated_bmode_renderer():
    """Validates B-mode simulator generates stone shadow cones, speckle, and 8-bit PNG."""
    sim = BModeUltrasoundSimulator(probe=CURVILINEAR_C5_2, dynamic_range_db=65.0)
    res = sim.simulate_synthetic_phantom(has_stone=True, has_needle=True)

    assert isinstance(res.image_uint8, np.ndarray)
    assert res.image_uint8.dtype == np.uint8
    assert res.image_uint8.shape == (256, 128)
    assert res.stone_shadow_detected is True
    assert res.fluid_enhancement_detected is True
    assert res.needle_rendered is True

    # Convert to PNG bytes
    png_bytes = res.to_png_bytes()
    assert len(png_bytes) > 1000
    # Verify PIL can open it
    img = Image.open(io.BytesIO(png_bytes))
    assert img.size == (128, 256)
    assert img.mode == "L"


# ==============================================================================
# 4. Milestone M14C: Cross-Modal Phantom & Human Clinical Validation Gate
# ==============================================================================

def test_m14_c_validation_metrics_and_gate():
    """Validates Cohen's kappa, shadow IoU, calyx sensitivity, FLE, and Pearson r against M14C gate."""
    # Synthetic concordance datasets matching benchmarks
    ratings_expert = ["GOOD", "GOOD", "CONDITIONAL", "POOR", "GOOD", "CONDITIONAL", "POOR", "GOOD"] * 4
    ratings_model = ["GOOD", "GOOD", "CONDITIONAL", "POOR", "GOOD", "CONDITIONAL", "POOR", "GOOD"] * 4

    kappa = compute_cohens_kappa(ratings_model, ratings_expert)
    assert kappa >= 0.80

    shadow_ious = [0.82, 0.79, 0.85, 0.78, 0.80]
    calyx_preds = [True, True, True, False, True, True, False]
    calyx_gts = [True, True, True, False, True, True, False]
    rib_fles = [1.2, 1.4, 0.9, 1.5, 1.1]
    navis = [0.2, 0.4, 0.6, 0.8, 0.95]
    snrs = [5.1, 10.2, 14.8, 19.5, 23.9]

    report = evaluate_m14c_clinical_gate(
        window_predictions=ratings_model,
        window_expert_ground_truth=ratings_expert,
        shadow_ious=shadow_ious,
        calyx_vis_predictions=calyx_preds,
        calyx_vis_ground_truth=calyx_gts,
        rib_boundary_fles_mm=rib_fles,
        predicted_navis=navis,
        measured_phantom_snrs=snrs,
    )

    assert report.window_passed is True
    assert report.stone_shadow_passed is True
    assert report.calyx_visibility_passed is True
    assert report.rib_shadow_passed is True
    assert report.navi_passed is True
    assert report.overall_certified is True


# ==============================================================================
# 5. Milestone M14D: API Endpoints Integration Tests
# ==============================================================================

def test_api_ultrasound_probes():
    """Validates GET /api/cases/{case_id}/us/probes."""
    resp = client.get("/api/cases/test_case/us/probes")
    assert resp.status_code == 200
    data = resp.json()
    assert "probes" in data
    assert len(data["probes"]) >= 2
    probe_ids = [p["probe_id"] for p in data["probes"]]
    assert "CURV_C5_2" in probe_ids
    assert "LIN_L12_4" in probe_ids


def test_api_ultrasound_reference_registry():
    """Validates GET /api/cases/{case_id}/us/reference-registry."""
    resp = client.get("/api/cases/test_case/us/reference-registry")
    assert resp.status_code == 200
    data = resp.json()
    assert "phantom_spec" in data
    assert "reference_cases" in data
    assert data["reference_cases_count"] >= 3


def test_api_ultrasound_bmode_image_streaming():
    """Validates GET /api/cases/{case_id}/us/{cand_id}/simulated-bmode streaming PNG and safety headers."""
    resp = client.get("/api/cases/test_case/us/candidate_a/simulated-bmode?insertion_depth_mm=35.0")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.headers["x-ultrasound-mode"] == "SIMULATED"
    assert "NOT LIVE ULTRASOUND" in resp.headers["x-safety-notice"]
    assert "x-navi-score" in resp.headers

    img = Image.open(io.BytesIO(resp.content))
    assert img.format == "PNG"
    assert img.size[0] > 0 and img.size[1] > 0


def test_api_ultrasound_acoustic_window():
    """Validates GET /api/cases/{case_id}/us/{cand_id}/acoustic-window."""
    resp = client.get("/api/cases/test_case/us/candidate_a/acoustic-window")
    assert resp.status_code == 200
    data = resp.json()
    assert "window_category" in data
    assert data["window_category"] in ("GOOD", "CONDITIONAL", "POOR", "UNAVAILABLE")
    assert "corridor_rib_occlusion_pct" in data
    assert "pleural_clearance_mm" in data
    assert "skin_contact_conformance_pct" in data
    assert "navi_score" in data
    assert "SIMULATED" in data["disclaimer"]


def test_api_ultrasound_position_uncertainty():
    """Validates GET /api/cases/{case_id}/us/{cand_id}/position-uncertainty."""
    resp = client.get(
        "/api/cases/test_case/us/candidate_a/position-uncertainty"
        "?position=PRONE_STANDARD&habitus=NORMAL_BMI&ventilation=MECHANICAL_TIDAL"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "covariance_breakdown_mm2" in data
    assert "monte_carlo_clearance" in data
    mc = data["monte_carlo_clearance"]
    assert mc["samples_drawn"] == 2000
    assert 0.0 <= mc["overall_clearance_probability"] <= 1.0
    assert data["safety_tier"] in ("PREFERRED", "FEASIBLE", "CONDITIONAL", "NO_PLAN — POSITION UNCERTAINTY EXCEEDS VALIDATED ENVELOPE")
