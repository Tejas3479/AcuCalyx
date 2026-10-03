"""
Unit tests for AcuCalyx clinical DICOM series ingestion engine.
"""

from pathlib import Path
import numpy as np
import pytest
import pydicom
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from acucalyx.ingestion.dicom import (
    load_dicom_series, NonCTModalityError, LocalizerRejectionError, InconsistentGeometryError
)


def create_synthetic_dicom_slice(
    filename: Path,
    study_uid: str,
    series_uid: str,
    frame_of_ref_uid: str,
    slice_index: int,
    z_position_mm: float,
    slice_thickness_mm: float = 2.0,
    modality: str = "CT",
    image_type: str = "ORIGINAL\\PRIMARY\\AXIAL",
    rows: int = 32,
    cols: int = 32
) -> Path:
    """Helper creating a minimal valid synthetic DICOM slice on disk."""
    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.2"  # CT Image Storage
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

    ds = Dataset()
    ds.file_meta = file_meta
    ds.is_little_endian = True
    ds.is_implicit_VR = False

    ds.SOPClassUID = file_meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
    ds.StudyInstanceUID = study_uid
    ds.SeriesInstanceUID = series_uid
    ds.FrameOfReferenceUID = frame_of_ref_uid
    ds.Modality = modality
    ds.ImageType = image_type.split("\\")
    ds.PatientID = "SYNTH_PATIENT_001"

    ds.Rows = rows
    ds.Columns = cols
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 1  # Signed 2's complement
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"

    ds.ImageOrientationPatient = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    ds.ImagePositionPatient = [-16.0, -16.0, float(z_position_mm)]
    ds.PixelSpacing = [1.0, 1.0]
    ds.SliceThickness = float(slice_thickness_mm)
    ds.RescaleSlope = 1.0
    ds.RescaleIntercept = -1024.0

    # Synthetic raw pixel data (e.g. constant 1024 -> HU = 0.0)
    raw_pixels = np.full((rows, cols), 1024, dtype=np.int16)
    ds.PixelData = raw_pixels.tobytes()

    ds.save_as(str(filename), write_like_original=False)
    return filename


def test_dicom_ingestion_authoritative_spacing(tmp_path):
    """
    CRITICAL TEST: Verifies that inter-slice spacing is derived strictly
    from ImagePositionPatient (1.0 mm) and NOT from SliceThickness (2.5 mm).
    """
    study_uid = generate_uid()
    series_uid = generate_uid()
    for_uid = generate_uid()

    # Create 10 slices spaced by exactly 1.0 mm along Z
    for k in range(10):
        fp = tmp_path / f"slice_{k:03d}.dcm"
        create_synthetic_dicom_slice(
            filename=fp,
            study_uid=study_uid,
            series_uid=series_uid,
            frame_of_ref_uid=for_uid,
            slice_index=k,
            z_position_mm=float(k) * 1.0,
            slice_thickness_mm=2.5  # Deliberately different from 1.0mm spacing
        )

    res = load_dicom_series(tmp_path)

    assert res.volume_hu.shape == (32, 32, 10)
    # The authoritative inter_slice_spacing must be 1.0, NOT 2.5!
    assert np.isclose(res.metadata.inter_slice_spacing, 1.0, atol=1e-3)
    assert np.isclose(res.metadata.slice_thickness, 2.5, atol=1e-3)
    # Pixels: raw 1024 * 1.0 + (-1024.0) = 0.0 HU (water attenuation)
    assert np.allclose(res.volume_hu, 0.0)


def test_dicom_ingestion_rejects_non_ct(tmp_path):
    """Verifies that non-CT modalities (e.g. MR) are rejected."""
    fp = tmp_path / "slice_000.dcm"
    create_synthetic_dicom_slice(
        filename=fp,
        study_uid=generate_uid(),
        series_uid=generate_uid(),
        frame_of_ref_uid=generate_uid(),
        slice_index=0,
        z_position_mm=0.0,
        modality="MR"
    )

    with pytest.raises(NonCTModalityError):
        load_dicom_series(tmp_path)


def test_dicom_ingestion_rejects_localizer(tmp_path):
    """Verifies that localizer/scout scans are rejected."""
    fp = tmp_path / "localizer.dcm"
    create_synthetic_dicom_slice(
        filename=fp,
        study_uid=generate_uid(),
        series_uid=generate_uid(),
        frame_of_ref_uid=generate_uid(),
        slice_index=0,
        z_position_mm=0.0,
        image_type="ORIGINAL\\PRIMARY\\LOCALIZER"
    )

    with pytest.raises(LocalizerRejectionError):
        load_dicom_series(tmp_path)


def test_dicom_ingestion_rejects_inconsistent_frame_of_reference(tmp_path):
    """Verifies that mismatched FrameOfReferenceUID within a series is rejected."""
    study_uid = generate_uid()
    series_uid = generate_uid()
    for_uid_1 = generate_uid()
    for_uid_2 = generate_uid()

    for k in range(5):
        fp = tmp_path / f"slice_{k:03d}.dcm"
        create_synthetic_dicom_slice(
            filename=fp,
            study_uid=study_uid,
            series_uid=series_uid,
            frame_of_ref_uid=for_uid_1 if k < 3 else for_uid_2,
            slice_index=k,
            z_position_mm=float(k) * 1.0
        )

    with pytest.raises(InconsistentGeometryError):
        load_dicom_series(tmp_path)
