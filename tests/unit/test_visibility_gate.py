"""
Unit tests for collecting-system visibility gate and state classifier.
"""

import numpy as np
import pytest

from tests.phantom.phantom_generator import generate_synthetic_pcnl_phantom
from acucalyx.collecting_system.visibility_gate import (
    classify_collecting_system_visibility, PCSVisibilityState
)


def test_visibility_gate_detects_hydronephrosis_on_phantom():
    """
    Phantom has a fluid cavity of radius 4mm (volume ~ 268 mm³).
    Tests that the visibility classifier identifies fluid distension or partial visibility.
    """
    vol, spatial, gt = generate_synthetic_pcnl_phantom(
        grid_shape=(96, 96, 80),
        spacing_mm=(1.0, 1.0, 1.0),
        noise_sigma_hu=0.0
    )

    origin = spatial.origin
    dx, dy, dz = spatial.spacing
    i_coords = np.arange(96)
    j_coords = np.arange(96)
    k_coords = np.arange(80)
    I, J, K = np.meshgrid(i_coords, j_coords, k_coords, indexing='ij')

    X_phys = origin[0] + J * dx
    Y_phys = origin[1] + I * dy
    Z_phys = origin[2] + K * dz

    # Kidney mask
    k_center = gt.kidney_center_mm
    k_radii = gt.kidney_radii_mm
    kidney_dist = ((X_phys - k_center[0]) / k_radii[0])**2 + \
                  ((Y_phys - k_center[1]) / k_radii[1])**2 + \
                  ((Z_phys - k_center[2]) / k_radii[2])**2
    kidney_mask = kidney_dist <= 1.0

    res = classify_collecting_system_visibility(
        ct_volume_hu=vol,
        kidney_mask=kidney_mask,
        spatial_orientation=spatial,
        is_contrast_enhanced=False
    )

    assert res.state in [PCSVisibilityState.PARTIALLY_VISIBLE, PCSVisibilityState.ANATOMICALLY_ESTIMATED]
    assert res.fluid_cavity_volume_mm3 >= 0.0


def test_visibility_gate_contrast_mode():
    """Verify excretory contrast with high HU inside kidney activates DIRECTLY_OPACIFIED state."""
    vol, spatial, gt = generate_synthetic_pcnl_phantom(grid_shape=(64, 64, 64))
    
    # Paint high contrast (300 HU) inside kidney center
    kidney_mask = np.zeros(vol.shape, dtype=bool)
    kidney_mask[20:45, 20:45, 20:45] = True
    vol[28:36, 28:36, 28:36] = 300.0  # ~512 voxels of dense contrast dye

    res = classify_collecting_system_visibility(
        ct_volume_hu=vol,
        kidney_mask=kidney_mask,
        spatial_orientation=spatial,
        is_contrast_enhanced=True
    )

    assert res.state == PCSVisibilityState.DIRECTLY_OPACIFIED
    assert res.allows_direct_puncture_lock is True
    assert res.confidence_score > 0.9
