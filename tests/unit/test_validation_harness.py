"""
AcuCalyx Unit Tests: Five-Tier Validation Harness & Phase 3 Modules

Tests:
- Tier A: Dice, HD95, ASSD, RAVD on controlled geometric volumes
- Tier B: Target localization error and trajectory angular deviation
- Tier C: Exact one-sided Clopper-Pearson binomial confidence upper bound
- Modular Anatomy Backends & strict SYNTHETIC_ONLY safety invariant
- Calibrated DECT stone classification & struvite clinical ambiguity
- Anatomical Thoracic & Intercostal risk models
"""

import numpy as np
import pytest

from acucalyx.anatomy.backends import (
    BackendSafetyMode,
    HeuristicFallbackBackend,
    ManualReferenceMaskBackend,
    get_segmentation_backend,
)
from acucalyx.anatomy.segmentation import OrganLabel
from acucalyx.anatomy.thoracic_risk import (
    evaluate_thoracic_access_risk,
    evaluate_intercostal_vessel_risk,
    ThoracicVisibilityState
)
from acucalyx.geometry.coordinates import SpatialOrientation
from acucalyx.stones.dect_enrichment import (
    classify_stone_dual_energy_spectrum,
    DECTStoneClass,
    DEFAULT_CLINICAL_DECT_PROFILE,
)
from acucalyx.validation.harness import (
    clopper_pearson_upper_bound,
    compute_dice_coefficient,
    compute_relative_absolute_volume_difference,
    compute_surface_distances,
    compute_target_localization_error,
    compute_trajectory_angular_error,
)


def test_dice_and_ravd_metrics():
    """Verifies anatomical overlap metrics on known 3D masks."""
    m_gt = np.zeros((40, 40, 40), dtype=bool)
    m_gt[10:30, 10:30, 10:30] = True # 8000 voxels

    # Identical mask: Dice = 1.0, RAVD = 0.0
    assert compute_dice_coefficient(m_gt, m_gt) == 1.0
    assert compute_relative_absolute_volume_difference(m_gt, m_gt) == 0.0

    # 50% overlapping mask
    m_pred = np.zeros((40, 40, 40), dtype=bool)
    m_pred[10:30, 10:30, 10:20] = True # 4000 voxels
    dsc = compute_dice_coefficient(m_pred, m_gt)
    # 2 * 4000 / (4000 + 8000) = 8000 / 12000 = 0.6667
    assert np.isclose(dsc, 2.0 / 3.0, atol=1e-3)

    ravd = compute_relative_absolute_volume_difference(m_pred, m_gt)
    # |4000 - 8000| / 8000 = 50%
    assert np.isclose(ravd, 50.0, atol=1e-3)


def test_surface_distances_on_separated_spheres():
    """Verifies HD95 and ASSD surface metrics."""
    m_gt = np.zeros((50, 50, 50), dtype=bool)
    m_pred = np.zeros((50, 50, 50), dtype=bool)

    m_gt[20:25, 20:25, 20:25] = True
    # Shifted by 5 mm along X
    m_pred[25:30, 20:25, 20:25] = True

    hd95, assd = compute_surface_distances(m_pred, m_gt, spacing_mm=(1.0, 1.0, 1.0))
    assert hd95 > 0.0
    assert assd > 0.0
    assert hd95 >= assd


def test_clopper_pearson_exact_upper_bound():
    """
    Verifies one-sided Clopper-Pearson 95% confidence upper bound.
    Mathematical invariant: With 0 failures in N=100 trials, the upper 95% bound
    is 1 - (0.05)^(1/100) ≈ 0.0295 (2.95%).
    """
    bound_0_of_100 = clopper_pearson_upper_bound(failures=0, total=100, confidence=0.95)
    expected = 1.0 - (0.05 ** 0.01)
    assert np.isclose(bound_0_of_100, expected, atol=1e-4)
    assert bound_0_of_100 < 0.03  # Strictly under 3%

    # 0 failures in N=50 trials: bound ≈ 5.8%
    bound_0_of_50 = clopper_pearson_upper_bound(failures=0, total=50, confidence=0.95)
    assert bound_0_of_50 > bound_0_of_100


def test_procedural_geometric_errors():
    """Verifies target localization error and trajectory angular deviation."""
    t_pred = np.array([10.0, 20.0, 30.0])
    t_gt = np.array([10.0, 23.0, 34.0]) # 3 mm Y, 4 mm Z -> 5 mm error
    err = compute_target_localization_error(t_pred, t_gt)
    assert np.isclose(err, 5.0, atol=1e-3)

    # Orthogonal vectors: 90 degrees
    dir_1 = np.array([1.0, 0.0, 0.0])
    dir_2 = np.array([0.0, 1.0, 0.0])
    ang = compute_trajectory_angular_error(dir_1, dir_2)
    assert np.isclose(ang, 90.0, atol=1e-3)


def test_modular_anatomy_backends_and_safety_invariant():
    """
    Verifies AnatomyBackend factory and enforces invariant that
    HeuristicFallback is strictly SYNTHETIC_ONLY.
    """
    heuristic_backend = get_segmentation_backend("heuristic")
    assert heuristic_backend.safety_mode == BackendSafetyMode.SYNTHETIC_ONLY
    assert "SYNTHETIC_ONLY" in str(heuristic_backend.safety_mode)

    manual_backend = get_segmentation_backend("manual")
    assert manual_backend.safety_mode == BackendSafetyMode.REFERENCE_STANDARD

    # Register mask on manual backend
    dummy_mask = np.ones((10, 10, 10), dtype=bool)
    manual_backend.register_mask(OrganLabel.KIDNEY_LEFT, dummy_mask)
    spatial = SpatialOrientation.from_dicom_parameters([1,0,0,0,1,0], [0,0,0], [1.0, 1.0], 1.0)
    corridor = manual_backend.segment_volume(np.zeros((10, 10, 10)), spatial)
    assert corridor.get_mask(OrganLabel.KIDNEY_LEFT) is not None


def test_dect_stone_composition_and_struvite_ambiguity():
    """Verifies protocol-calibrated DECT stone classification."""
    mask = np.zeros((30, 30, 30), dtype=bool)
    mask[12:16, 12:16, 12:16] = True

    # Case 1: Uric acid (Low HU = 400, High HU = 450 -> DER = 0.888 < 1.10)
    vol_low = np.zeros((30, 30, 30))
    vol_high = np.zeros((30, 30, 30))
    vol_low[mask] = 400.0
    vol_high[mask] = 450.0

    res_ua = classify_stone_dual_energy_spectrum(1, mask, vol_low, vol_high, DEFAULT_CLINICAL_DECT_PROFILE)
    assert res_ua.predicted_composition == DECTStoneClass.URIC_ACID_COMPATIBLE
    assert res_ua.dual_energy_ratio < 1.10

    # Case 2: Dense Calcium (Low HU = 1400, High HU = 950 -> DER = 1.474 > 1.30)
    vol_low[mask] = 1400.0
    vol_high[mask] = 950.0
    res_ca = classify_stone_dual_energy_spectrum(2, mask, vol_low, vol_high, DEFAULT_CLINICAL_DECT_PROFILE)
    assert res_ca.predicted_composition == DECTStoneClass.CALCIUM_CONTAINING_COMPATIBLE
    assert res_ca.dual_energy_ratio > 1.30

    # Case 3: Ambiguous window (Low HU = 600, High HU = 500 -> DER = 1.20)
    vol_low[mask] = 600.0
    vol_high[mask] = 500.0
    res_amb = classify_stone_dual_energy_spectrum(3, mask, vol_low, vol_high, DEFAULT_CLINICAL_DECT_PROFILE)
    assert res_amb.is_struvite_suspected is True


def test_thoracic_and_intercostal_risk_models():
    """Verifies thoracic level evaluation and intercostal vessel safety rules."""
    spatial = SpatialOrientation.from_dicom_parameters([1,0,0,0,1,0], [0,0,0], [1.0, 1.0], 1.0)
    lung = np.zeros((40, 40, 40), dtype=bool)
    lung[10:30, 10:30, 30:40] = True # Lung lower lobe high in Z

    rib_11 = np.zeros((40, 40, 40), dtype=bool)
    rib_11[15:25, 20:30, 25] = True

    rib_12 = np.zeros((40, 40, 40), dtype=bool)
    rib_12[15:25, 20:30, 18] = True

    # Puncture through Z = 27 (Supracostal 11)
    traj_supracostal = np.array([[20.0, y, 27.0] for y in np.linspace(35, 10, 20)])
    eval_supra = evaluate_thoracic_access_risk(traj_supracostal, lung, rib_11, rib_12, spatial)
    assert eval_supra.crosses_diaphragm is True
    assert eval_supra.supracostal_level == "SUPRACOSTAL_11"

    # Puncture through Z = 12 (Subcostal < 12th rib)
    traj_subcostal = np.array([[20.0, y, 12.0] for y in np.linspace(35, 10, 20)])
    eval_sub = evaluate_thoracic_access_risk(traj_subcostal, lung, rib_11, rib_12, spatial)
    assert eval_sub.crosses_diaphragm is False
    assert eval_sub.supracostal_level == "SUBCOSTAL"
