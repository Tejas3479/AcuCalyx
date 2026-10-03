"""
Unit tests for AcuCalyx DICOM quality gate and geometric integrity validation.
"""

import numpy as np
import pytest

from acucalyx.ingestion.quality_gate import evaluate_dicom_series_geometry


def test_quality_gate_ideal_series():
    """Verify ideal thin-slice axial CT series passes with HIGH quality."""
    n_slices = 50
    iop = [[1.0, 0.0, 0.0, 0.0, 1.0, 0.0]] * n_slices
    # Positions advancing uniformly by 1.0mm along Z
    ipp = [[-100.0, -100.0, float(k) * 1.0] for k in range(n_slices)]
    pixel_spacing = [[0.7, 0.7]] * n_slices
    thickness = [1.0] * n_slices

    res = evaluate_dicom_series_geometry(
        image_positions=ipp,
        image_orientations=iop,
        pixel_spacings=pixel_spacing,
        slice_thicknesses=thickness
    )

    assert res.passed is True
    assert len(res.rejection_reasons) == 0
    assert res.overall_quality_tier == 'HIGH'
    assert np.isclose(res.slice_spacing_mm, 1.0)


def test_quality_gate_rejects_gantry_tilt():
    """Verify series with tilted gantry fails closed."""
    n_slices = 30
    iop = [[1.0, 0.0, 0.0, 0.0, 1.0, 0.0]] * n_slices
    ipp = [[0.0, 0.0, float(k)] for k in range(n_slices)]
    tilts = [15.0] * n_slices  # 15 degree gantry tilt

    res = evaluate_dicom_series_geometry(
        image_positions=ipp,
        image_orientations=iop,
        pixel_spacings=[[0.8, 0.8]] * n_slices,
        slice_thicknesses=[1.0] * n_slices,
        gantry_tilts=tilts
    )

    assert res.passed is False
    assert any("Gantry tilt" in r for r in res.rejection_reasons)


def test_quality_gate_rejects_missing_slices():
    """Verify non-uniform slice spacing (missing slice) fails closed."""
    n_slices = 30
    iop = [[1.0, 0.0, 0.0, 0.0, 1.0, 0.0]] * n_slices
    # Missing slice at index 15 (step jumps from 1.0 to 3.0)
    z_coords = list(range(15)) + [k + 2 for k in range(15, 30)]
    ipp = [[0.0, 0.0, float(z)] for z in z_coords]

    res = evaluate_dicom_series_geometry(
        image_positions=ipp,
        image_orientations=iop,
        pixel_spacings=[[0.8, 0.8]] * n_slices,
        slice_thicknesses=[1.0] * n_slices
    )

    assert res.passed is False
    assert any("Non-uniform slice spacing" in r for r in res.rejection_reasons)


def test_quality_gate_rejects_excessive_thickness():
    """Verify thick slices (>2.5mm) fail closed."""
    n_slices = 20
    iop = [[1.0, 0.0, 0.0, 0.0, 1.0, 0.0]] * n_slices
    ipp = [[0.0, 0.0, float(k) * 3.0] for k in range(n_slices)]

    res = evaluate_dicom_series_geometry(
        image_positions=ipp,
        image_orientations=iop,
        pixel_spacings=[[0.8, 0.8]] * n_slices,
        slice_thicknesses=[3.0] * n_slices  # 3.0mm thick slices
    )

    assert res.passed is False
    assert any("exceeds safe limit" in r for r in res.rejection_reasons)
