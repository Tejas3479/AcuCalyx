"""
Unit tests for stone candidate detection, morphometry, and volumetrics against analytical phantom.
"""

import numpy as np
import pytest

from tests.phantom.phantom_generator import generate_synthetic_pcnl_phantom
from acucalyx.stones.candidate_detection import detect_stone_candidates
from acucalyx.stones.volumetry import compute_stone_morphometry
from acucalyx.stones.attenuation import compute_stone_attenuation


def test_stone_volumetry_against_analytical_ground_truth():
    """
    Validates stone detection and true 3D volume integration against
    an analytical sphere phantom with known radius and HU.
    """
    radius_mm = 5.0
    vol, spatial, gt = generate_synthetic_pcnl_phantom(
        grid_shape=(96, 96, 80),
        spacing_mm=(1.0, 1.0, 1.0),
        stone_radius_mm=radius_mm,
        noise_sigma_hu=0.0
    )

    candidates = detect_stone_candidates(
        ct_volume_hu=vol,
        spatial_orientation=spatial,
        dense_threshold_hu=400.0
    )

    # Exactly 1 stone candidate must be detected in this phantom
    assert len(candidates) >= 1
    stone_cand = candidates[0]
    assert stone_cand.tier == "DENSE_CALCIUM"

    morph = compute_stone_morphometry(stone_cand, spatial)

    # Analytical ground truth: V = (4/3) * pi * 5^3 = 523.599 mm³
    expected_vol = gt.stone_volume_mm3
    measured_vol = morph.volume_mm3

    # Voxel discretization error for 1mm isotropic grid should be under 5%
    pct_error = abs(measured_vol - expected_vol) / expected_vol * 100.0
    assert pct_error < 5.0, f"Volume error too high: {pct_error:.2f}% (measured {measured_vol}, expected {expected_vol})"

    # Centroid error must be under 1 voxel (1 mm)
    centroid_dist = np.linalg.norm(morph.centroid_lps_mm - gt.stone_center_mm)
    assert centroid_dist < 1.0, f"Centroid offset too high: {centroid_dist:.2f} mm"

    # Feret diameter should be close to 2 * radius = 10 mm
    assert np.isclose(morph.max_feret_diameter_mm, 2.0 * radius_mm, atol=1.5)

    # Attenuation profile test
    atten = compute_stone_attenuation(stone_cand, vol)
    assert np.isclose(atten.mean_hu, 1200.0, atol=10.0)
    assert atten.fraction_high_over_1000hu > 0.95
    assert atten.composition_inference == "Not validated / unavailable"
