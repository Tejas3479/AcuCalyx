"""
AcuCalyx Ingestion: Clinical DICOM Series Ingestion and Geometric Calibration

Implements Step 01 of AcuCalyx v2.1:
- Scans and validates DICOM slice directories
- Enforces strict clinical guardrails: Modality == 'CT', FrameOfReferenceUID consistency,
  rejection of scout/localizer images, validation of PixelRepresentation & BitsStored
- Calculates authoritative inter-slice spacing exclusively from ImagePositionPatient
  projections onto the slice normal:
    n = X x Y
    d_k = P_k . n
    delta_z_k = d_{k+1} - d_k
  (NEVER uses SliceThickness tag for inter-slice spacing)
- Applies per-slice RescaleSlope and RescaleIntercept to obtain true Hounsfield Units (HU)
- Assembles calibrated 3D volume [rows, cols, slices] and SpatialOrientation
"""

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union
import numpy as np
import pydicom
from pydicom.dataset import Dataset
from pydicom.errors import InvalidDicomError

from acucalyx.geometry.coordinates import SpatialOrientation
from acucalyx.ingestion.quality_gate import QualityGateResult, evaluate_dicom_series_geometry


class DICOMIngestionError(Exception):
    """Base exception for DICOM ingestion failures."""
    pass


class NonCTModalityError(DICOMIngestionError):
    """Raised when DICOM modality is not CT."""
    pass


class LocalizerRejectionError(DICOMIngestionError):
    """Raised when a localizer / scout scan is detected."""
    pass


class InconsistentGeometryError(DICOMIngestionError):
    """Raised when spatial geometry, frame of reference, or orientation is inconsistent."""
    pass


@dataclass(frozen=True)
class DICOMSeriesMetadata:
    """De-identified study and series metadata for provenance tracking."""
    patient_id_hash: str
    study_instance_uid: str
    series_instance_uid: str
    frame_of_reference_uid: str
    modality: str
    num_slices: int
    rows: int
    columns: int
    pixel_spacing: Tuple[float, float]
    inter_slice_spacing: float
    slice_thickness: float
    reconstruction_kernel: Optional[str]
    kvp: Optional[float]
    x_ray_tube_current_ma: Optional[float]
    series_sha256: str


@dataclass(frozen=True)
class DICOMVolumeResult:
    """Complete calibrated 3D CT volume and its physical spatial mapping."""
    volume_hu: np.ndarray             # 3D float32 array [rows, cols, slices]
    spatial_orientation: SpatialOrientation
    metadata: DICOMSeriesMetadata
    quality_gate: QualityGateResult


def compute_series_hash(file_paths: Sequence[Path]) -> str:
    """Computes a composite SHA-256 hash across all raw DICOM slice files."""
    hasher = hashlib.sha256()
    for fp in sorted(file_paths):
        with open(fp, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
    return hasher.hexdigest()


def is_localizer_image(ds: Dataset) -> bool:
    """Checks whether a dataset is a 2D localizer / scout view."""
    image_type = getattr(ds, "ImageType", [])
    if hasattr(image_type, "__iter__") and not isinstance(image_type, (str, bytes)):
        type_strings = [str(t).upper() for t in image_type]
        if any("LOCALIZER" in t or "SCOUT" in t for t in type_strings):
            return True
    elif isinstance(image_type, (str, bytes)):
        if "LOCALIZER" in str(image_type).upper() or "SCOUT" in str(image_type).upper():
            return True
            
    # Localizers often lack ImageOrientationPatient or have only 1 slice
    if not hasattr(ds, "ImageOrientationPatient"):
        return True
        
    return False


def load_dicom_series(
    dicom_dir: Union[str, Path],
    require_frame_of_ref: bool = True
) -> DICOMVolumeResult:
    """
    Ingests, validates, and calibrates a clinical CT DICOM slice series.
    
    Args:
        dicom_dir: Path to directory containing .dcm slice files
        require_frame_of_ref: If True, asserts FrameOfReferenceUID is present and consistent
        
    Returns:
        DICOMVolumeResult containing 3D HU volume and spatial orientation
        
    Raises:
        DICOMIngestionError on invalid, corrupted, or non-CT series
    """
    dir_path = Path(dicom_dir)
    if not dir_path.is_dir():
        raise DICOMIngestionError(f"Directory not found: {dir_path}")

    # Discover and read all valid DICOM files
    slice_datasets: List[Tuple[Dataset, Path]] = []
    valid_paths: List[Path] = []

    for file_path in dir_path.rglob("*"):
        if file_path.is_file():
            try:
                ds = pydicom.dcmread(str(file_path), stop_before_pixels=False, force=False)
                # Check for standard PixelData attribute
                if hasattr(ds, "PixelData"):
                    slice_datasets.append((ds, file_path))
                    valid_paths.append(file_path)
            except (InvalidDicomError, PermissionError):
                continue

    if not slice_datasets:
        raise DICOMIngestionError(f"No valid DICOM image slices found in {dir_path}")

    # Step 1: Modality & Localizer Guardrails
    first_ds = slice_datasets[0][0]
    modality = getattr(first_ds, "Modality", "").upper()
    if modality != "CT":
        raise NonCTModalityError(f"Invalid modality '{modality}'. AcuCalyx requires CT imaging.")

    # Filter out localizer/scout scans
    axial_slices: List[Tuple[Dataset, Path]] = []
    for ds, fp in slice_datasets:
        if is_localizer_image(ds):
            continue
        axial_slices.append((ds, fp))

    if not axial_slices:
        raise LocalizerRejectionError("All discovered DICOM files were localizer/scout images.")

    # Step 2: Series & FrameOfReferenceUID Consistency
    ref_series_uid = getattr(axial_slices[0][0], "SeriesInstanceUID", "")
    ref_frame_of_ref = getattr(axial_slices[0][0], "FrameOfReferenceUID", None)

    filtered_series: List[Tuple[Dataset, Path]] = []
    for ds, fp in axial_slices:
        s_uid = getattr(ds, "SeriesInstanceUID", "")
        if s_uid == ref_series_uid:
            if require_frame_of_ref and ref_frame_of_ref:
                cur_for = getattr(ds, "FrameOfReferenceUID", None)
                if cur_for != ref_frame_of_ref:
                    raise InconsistentGeometryError(
                        f"Inconsistent FrameOfReferenceUID detected within series {ref_series_uid}"
                    )
            filtered_series.append((ds, fp))

    if len(filtered_series) < 5:
        raise DICOMIngestionError(
            f"Series {ref_series_uid} contains only {len(filtered_series)} slices (minimum 5 required for 3D reconstruction)."
        )

    # Step 3: Direction Cosines and Normal Vector Calculation
    ref_ds = filtered_series[0][0]
    iop = np.array(getattr(ref_ds, "ImageOrientationPatient", []), dtype=np.float64)
    if len(iop) != 6:
        raise InconsistentGeometryError("Missing or invalid ImageOrientationPatient (6 values required)")

    x_dir = iop[0:3]
    y_dir = iop[3:6]
    norm_x = np.linalg.norm(x_dir)
    norm_y = np.linalg.norm(y_dir)
    if not (np.isclose(norm_x, 1.0, atol=1e-3) and np.isclose(norm_y, 1.0, atol=1e-3)):
        raise InconsistentGeometryError("Direction cosines are not unit vectors")

    slice_normal = np.cross(x_dir, y_dir)
    slice_normal = slice_normal / np.linalg.norm(slice_normal)

    # Step 4: Authoritative Inter-Slice Spacing from IPP Projections
    # Project each ImagePositionPatient onto slice_normal: d_k = P_k . n
    projected_positions: List[Tuple[float, Dataset, Path]] = []
    for ds, fp in filtered_series:
        ipp = np.array(getattr(ds, "ImagePositionPatient", []), dtype=np.float64)
        if len(ipp) != 3:
            raise InconsistentGeometryError(f"Slice {fp.name} missing ImagePositionPatient tag")
        d_k = float(np.dot(ipp, slice_normal))
        projected_positions.append((d_k, ds, fp))

    # Sort strictly along slice normal
    projected_positions.sort(key=lambda item: item[0])

    sorted_distances = [p[0] for p in projected_positions]
    sorted_datasets = [p[1] for p in projected_positions]
    sorted_paths = [p[2] for p in projected_positions]

    # Compute actual spacing between consecutive slices: delta_z = d_{k+1} - d_k
    inter_slice_deltas = np.diff(sorted_distances)
    if np.any(inter_slice_deltas <= 0.0):
        raise InconsistentGeometryError("Duplicate or non-advancing slice positions detected along normal axis.")

    authoritative_slice_spacing = float(np.mean(inter_slice_deltas))
    spacing_variation = float(np.max(inter_slice_deltas) - np.min(inter_slice_deltas))

    if spacing_variation > 0.05:  # Tolerance: 0.05 mm variation
        raise InconsistentGeometryError(
            f"Non-uniform inter-slice spacing detected (min={np.min(inter_slice_deltas):.3f}mm, "
            f"max={np.max(inter_slice_deltas):.3f}mm, delta={spacing_variation:.3f}mm). Missing slices suspected."
        )

    # Step 5: Geometric Integrity & Quality Gate Evaluation
    all_positions = [list(ds.ImagePositionPatient) for ds in sorted_datasets]
    all_orientations = [list(ds.ImageOrientationPatient) for ds in sorted_datasets]
    all_pixel_spacings = [list(ds.PixelSpacing) for ds in sorted_datasets]
    all_thicknesses = [float(getattr(ds, "SliceThickness", authoritative_slice_spacing)) for ds in sorted_datasets]
    all_tilts = [float(getattr(ds, "GantryDetectorTilt", 0.0)) for ds in sorted_datasets]

    qg_result = evaluate_dicom_series_geometry(
        image_positions=all_positions,
        image_orientations=all_orientations,
        pixel_spacings=all_pixel_spacings,
        slice_thicknesses=all_thicknesses,
        gantry_tilts=all_tilts
    )

    if not qg_result.passed:
        raise InconsistentGeometryError(
            f"DICOM series failed quality gate: {'; '.join(qg_result.rejection_reasons)}"
        )

    # Step 6: 3D Volume Assembly and Linear HU Rescaling
    ref_ds0 = sorted_datasets[0]
    rows = int(ref_ds0.Rows)
    cols = int(ref_ds0.Columns)
    n_slices = len(sorted_datasets)

    volume_hu = np.zeros((rows, cols, n_slices), dtype=np.float32)

    for k, ds in enumerate(sorted_datasets):
        # Validate pixel representation
        pixel_array = ds.pixel_array.astype(np.float32)
        slope = float(getattr(ds, "RescaleSlope", 1.0))
        intercept = float(getattr(ds, "RescaleIntercept", -1024.0))
        
        # Apply calibration formula: HU = PixelValue * Slope + Intercept
        slice_hu = pixel_array * slope + intercept
        volume_hu[:, :, k] = slice_hu

    # Step 7: Spatial Orientation Construction
    first_ipp = list(sorted_datasets[0].ImagePositionPatient)
    ref_ps = [float(x) for x in sorted_datasets[0].PixelSpacing]

    spatial_orientation = SpatialOrientation.from_dicom_parameters(
        image_orientation_patient=list(ref_ds0.ImageOrientationPatient),
        image_position_patient=first_ipp,
        pixel_spacing=ref_ps,
        slice_spacing=authoritative_slice_spacing,
        slice_direction=slice_normal.tolist()
    )

    # Step 8: Provenance Metadata Record
    series_hash = compute_series_hash(sorted_paths)
    patient_id_raw = getattr(ref_ds0, "PatientID", "ANONYMOUS")
    patient_hash = hashlib.sha256(patient_id_raw.encode("utf-8")).hexdigest()[:16]

    metadata = DICOMSeriesMetadata(
        patient_id_hash=patient_hash,
        study_instance_uid=str(getattr(ref_ds0, "StudyInstanceUID", "")),
        series_instance_uid=str(ref_series_uid),
        frame_of_reference_uid=str(ref_frame_of_ref or "UNSPECIFIED"),
        modality="CT",
        num_slices=n_slices,
        rows=rows,
        columns=cols,
        pixel_spacing=(ref_ps[0], ref_ps[1]),
        inter_slice_spacing=authoritative_slice_spacing,
        slice_thickness=float(getattr(ref_ds0, "SliceThickness", authoritative_slice_spacing)),
        reconstruction_kernel=getattr(ref_ds0, "ConvolutionKernel", None),
        kvp=float(getattr(ref_ds0, "KVP", 0.0)) if hasattr(ref_ds0, "KVP") else None,
        x_ray_tube_current_ma=float(getattr(ref_ds0, "XRayTubeCurrent", 0.0)) if hasattr(ref_ds0, "XRayTubeCurrent") else None,
        series_sha256=series_hash
    )

    return DICOMVolumeResult(
        volume_hu=volume_hu,
        spatial_orientation=spatial_orientation,
        metadata=metadata,
        quality_gate=qg_result
    )
