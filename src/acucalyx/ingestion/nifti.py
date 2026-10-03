"""
AcuCalyx Ingestion: Research NIfTI Loader and Spatial Validation

Implements Step 02 of AcuCalyx v2.1:
- Treats NIfTI (.nii, .nii.gz) explicitly as a RESEARCH_DERIVED input mode
- Enforces strict qform/sform validation and affine matrix sanity
- Normalizes coordinates from NIfTI RAS convention to DICOM LPS patient space:
    LPS = [-X_ras, -Y_ras, Z_ras]
- Validates accompanying JSON metadata sidecars (<name>.json)
"""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union
import numpy as np
import nibabel as nib

from acucalyx.geometry.coordinates import SpatialOrientation


class NIfTIIngestionError(Exception):
    """Raised when NIfTI file is corrupted, singular, or lacks valid spatial headers."""
    pass


@dataclass(frozen=True)
class NIfTIVolumeResult:
    """Calibrated 3D volume loaded from research NIfTI with provenance sidecar."""
    volume_hu: np.ndarray             # 3D float32 array [rows, cols, slices]
    spatial_orientation: SpatialOrientation
    provenance_mode: str              # Always 'RESEARCH_DERIVED'
    source_filepath: Path
    sidecar_metadata: Dict[str, Any]


def load_research_nifti(
    nifti_path: Union[str, Path],
    require_sidecar: bool = False
) -> NIfTIVolumeResult:
    """
    Loads and validates a research NIfTI volume, converting RAS coordinates to standard LPS.
    
    Args:
        nifti_path: Path to .nii or .nii.gz file
        require_sidecar: If True, asserts an accompanying .json file exists
    """
    p = Path(nifti_path)
    if not p.is_file():
        raise NIfTIIngestionError(f"File not found: {p}")

    try:
        nii = nib.load(str(p))
    except Exception as e:
        raise NIfTIIngestionError(f"Failed to load NIfTI file: {e}")

    # Step 1: Validate qform/sform
    sform_code = int(nii.header.get('sform_code', 0))
    qform_code = int(nii.header.get('qform_code', 0))

    if sform_code == 0 and qform_code == 0:
        raise NIfTIIngestionError(
            "NIfTI header lacks valid spatial orientation (both sform_code and qform_code are 0)."
        )

    # Use best affine (RAS coordinates)
    affine_ras = nii.affine
    if np.isclose(np.linalg.det(affine_ras[0:3, 0:3]), 0.0):
        raise NIfTIIngestionError("NIfTI affine matrix is singular (determinant is zero).")

    # Step 2: Convert RAS affine to LPS patient coordinate space
    # In RAS: +X is Right, +Y is Anterior, +Z is Superior
    # In LPS: +X is Left,  +Y is Posterior, +Z is Superior
    # Conversion matrix: diag([-1, -1, 1, 1])
    ras_to_lps = np.diag([-1.0, -1.0, 1.0, 1.0])
    affine_lps = ras_to_lps @ affine_ras

    # Extract voxel spacing (norm of column vectors)
    dx = float(np.linalg.norm(affine_lps[0:3, 0]))
    dy = float(np.linalg.norm(affine_lps[0:3, 1]))
    dz = float(np.linalg.norm(affine_lps[0:3, 2]))
    origin_lps = affine_lps[0:3, 3]

    # Normalize direction matrix
    dir_matrix = np.eye(3, dtype=np.float64)
    dir_matrix[:, 0] = affine_lps[0:3, 0] / dx
    dir_matrix[:, 1] = affine_lps[0:3, 1] / dy
    dir_matrix[:, 2] = affine_lps[0:3, 2] / dz

    inv_affine_lps = np.linalg.inv(affine_lps)

    spatial = SpatialOrientation(
        affine_matrix=affine_lps,
        inv_affine_matrix=inv_affine_lps,
        origin=origin_lps,
        spacing=np.array([dx, dy, dz], dtype=np.float64),
        direction=dir_matrix
    )

    # Step 3: Load volume data as float32
    raw_data = nii.get_fdata(dtype=np.float32)
    if raw_data.ndim != 3:
        raise NIfTIIngestionError(f"Expected 3D NIfTI volume, found {raw_data.ndim}D.")

    # Step 4: Load sidecar if present or required
    # Strip both .nii and .nii.gz extensions to find sidecar
    base_name = p.name
    if base_name.endswith(".nii.gz"):
        stem_name = base_name[:-7]
    elif base_name.endswith(".nii"):
        stem_name = base_name[:-4]
    else:
        stem_name = p.stem

    sidecar_path = p.parent / f"{stem_name}.json"
    sidecar_dict: Dict[str, Any] = {}

    if sidecar_path.is_file():
        try:
            with open(sidecar_path, "r", encoding="utf-8") as f:
                sidecar_dict = json.load(f)
        except Exception as e:
            raise NIfTIIngestionError(f"Failed to read metadata sidecar {sidecar_path}: {e}")
    elif require_sidecar:
        raise NIfTIIngestionError(
            f"Mandatory metadata sidecar {sidecar_path} missing for research NIfTI {p.name}"
        )

    return NIfTIVolumeResult(
        volume_hu=raw_data,
        spatial_orientation=spatial,
        provenance_mode="RESEARCH_DERIVED",
        source_filepath=p,
        sidecar_metadata=sidecar_dict
    )
