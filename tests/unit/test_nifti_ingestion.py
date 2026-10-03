"""
Unit tests for AcuCalyx research NIfTI ingestion and RAS-to-LPS conversion.
"""

import json
from pathlib import Path
import numpy as np
import pytest
import nibabel as nib

from acucalyx.ingestion.nifti import load_research_nifti, NIfTIIngestionError


def test_nifti_ingestion_ras_to_lps_conversion(tmp_path):
    """
    Verifies that NIfTI RAS affine is converted to standard DICOM LPS affine.
    In RAS: +X is Right, +Y is Anterior.
    In LPS: +X is Left (-X_ras), +Y is Posterior (-Y_ras).
    """
    vol_data = np.full((30, 30, 20), 40.0, dtype=np.float32)
    # Standard RAS affine: 1mm isotropic, origin at (10, 20, 30) in RAS
    affine_ras = np.diag([1.0, 1.0, 1.0, 1.0])
    affine_ras[0, 3] = 10.0  # +X_ras
    affine_ras[1, 3] = 20.0  # +Y_ras
    affine_ras[2, 3] = 30.0  # +Z_ras

    nii = nib.Nifti1Image(vol_data, affine_ras)
    nii.set_sform(affine_ras, code=1)  # sform_code = 1 (scanner anatomical)

    nii_path = tmp_path / "test_scan.nii.gz"
    nib.save(nii, str(nii_path))

    # Save sidecar
    sidecar_path = tmp_path / "test_scan.json"
    with open(sidecar_path, "w", encoding="utf-8") as f:
        json.dump({"scanner": "Siemens_Force", "kernel": "Qr40"}, f)

    res = load_research_nifti(nii_path, require_sidecar=True)

    assert res.provenance_mode == "RESEARCH_DERIVED"
    assert res.volume_hu.shape == (30, 30, 20)
    assert res.sidecar_metadata["scanner"] == "Siemens_Force"

    # In LPS, origin X should be -10.0 and Y should be -20.0, Z should be +30.0
    np.testing.assert_allclose(res.spatial_orientation.origin, [-10.0, -20.0, 30.0], atol=1e-5)


def test_nifti_ingestion_rejects_missing_sidecar_when_required(tmp_path):
    """Verifies that missing sidecar is rejected when required."""
    vol_data = np.zeros((10, 10, 10), dtype=np.float32)
    nii = nib.Nifti1Image(vol_data, np.eye(4))
    nii.set_sform(np.eye(4), code=1)

    nii_path = tmp_path / "naked_scan.nii.gz"
    nib.save(nii, str(nii_path))

    with pytest.raises(NIfTIIngestionError, match="Mandatory metadata sidecar"):
        load_research_nifti(nii_path, require_sidecar=True)


def test_nifti_ingestion_rejects_uncalibrated_qform(tmp_path):
    """Verifies rejection when sform_code and qform_code are both 0."""
    vol_data = np.zeros((10, 10, 10), dtype=np.float32)
    nii = nib.Nifti1Image(vol_data, np.eye(4))
    nii.set_sform(np.eye(4), code=0)
    nii.set_qform(np.eye(4), code=0)

    nii_path = tmp_path / "no_qform.nii.gz"
    nib.save(nii, str(nii_path))

    with pytest.raises(NIfTIIngestionError, match="lacks valid spatial orientation"):
        load_research_nifti(nii_path)
