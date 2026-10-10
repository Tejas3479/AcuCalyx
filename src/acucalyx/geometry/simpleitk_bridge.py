"""
AcuCalyx Geometry: SimpleITK Medical Imaging Bridge
Governed by ACU-M15-EXEC-PLAN-2026-V2.

Provides physical-space image processing using SimpleITK (2.5+):
- Isotropic resampling to physical millimeter grid
- Signed Maurer Distance Map computation for boundary collision
- Connected component analysis and largest island extraction
- Binary morphological dilation, erosion, opening, and closing
- Seamless NumPy <-> SimpleITK array and metadata conversion (LPS direction matrices)
"""

from dataclasses import dataclass
from typing import Any, Optional, Tuple
import numpy as np

try:
    import SimpleITK as sitk
    HAS_SITK = True
except ImportError:
    sitk = None
    HAS_SITK = False


@dataclass(frozen=True)
class SpatialImageMetadata:
    """Physical-space geometry metadata matching ITK LPS coordinate frame."""
    spacing_mm: Tuple[float, float, float]
    origin_lps_mm: Tuple[float, float, float]
    direction_matrix: Tuple[float, ...]
    dimensions: Tuple[int, int, int]


def numpy_to_sitk(
    arr: np.ndarray,
    spacing_mm: Tuple[float, float, float] = (1.0, 1.0, 1.0),
    origin_lps_mm: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    direction_matrix: Optional[Tuple[float, ...]] = None,
    is_label: bool = False,
) -> Optional[Any]:
    """Converts 3D numpy array [Z, Y, X] to SimpleITK Image with physical LPS metadata."""
    if not HAS_SITK:
        return None
    dtype = np.uint8 if is_label else (np.int16 if np.issubdtype(arr.dtype, np.integer) else np.float32)
    img = sitk.GetImageFromArray(arr.astype(dtype))
    # SimpleITK spacing and origin are ordered (X, Y, Z)
    img.SetSpacing((float(spacing_mm[0]), float(spacing_mm[1]), float(spacing_mm[2])))
    img.SetOrigin((float(origin_lps_mm[0]), float(origin_lps_mm[1]), float(origin_lps_mm[2])))
    if direction_matrix is not None and len(direction_matrix) == 9:
        img.SetDirection(direction_matrix)
    return img


def sitk_to_numpy(img: Any) -> Tuple[np.ndarray, SpatialImageMetadata]:
    """Converts SimpleITK Image to 3D numpy array [Z, Y, X] and extracts spatial metadata."""
    if not HAS_SITK or img is None:
        raise RuntimeError("SimpleITK is not available")
    arr = sitk.GetArrayFromImage(img)
    spacing = img.GetSpacing()
    origin = img.GetOrigin()
    direction = img.GetDirection()
    size = img.GetSize()
    meta = SpatialImageMetadata(
        spacing_mm=(float(spacing[0]), float(spacing[1]), float(spacing[2])),
        origin_lps_mm=(float(origin[0]), float(origin[1]), float(origin[2])),
        direction_matrix=tuple(direction),
        dimensions=(size[0], size[1], size[2]),
    )
    return arr, meta


def resample_to_isotropic(
    image_arr: np.ndarray,
    current_spacing_mm: Tuple[float, float, float],
    target_spacing_mm: float = 1.0,
    is_label: bool = False,
) -> np.ndarray:
    """
    Resamples a 3D volume to isotropic voxel spacing (e.g. 1.0 mm x 1.0 mm x 1.0 mm).
    Uses linear interpolation for continuous scalar CT volumes and nearest neighbor for labelmaps.
    """
    if not HAS_SITK:
        # Fallback using scipy.ndimage zoom if SimpleITK missing
        from scipy.ndimage import zoom
        factors = (
            current_spacing_mm[2] / target_spacing_mm,
            current_spacing_mm[1] / target_spacing_mm,
            current_spacing_mm[0] / target_spacing_mm,
        )
        order = 0 if is_label else 1
        return zoom(image_arr, factors, order=order)

    img = numpy_to_sitk(image_arr, spacing_mm=current_spacing_mm, is_label=is_label)
    orig_size = img.GetSize()
    orig_spacing = img.GetSpacing()

    new_spacing = (target_spacing_mm, target_spacing_mm, target_spacing_mm)
    new_size = [
        int(round(orig_size[i] * orig_spacing[i] / target_spacing_mm))
        for i in range(3)
    ]

    resample = sitk.ResampleImageFilter()
    resample.SetSize(new_size)
    resample.SetOutputSpacing(new_spacing)
    resample.SetOutputOrigin(img.GetOrigin())
    resample.SetOutputDirection(img.GetDirection())
    resample.SetInterpolator(sitk.sitkNearestNeighbor if is_label else sitk.sitkLinear)
    resampled_img = resample.Execute(img)

    return sitk.GetArrayFromImage(resampled_img)


def compute_signed_maurer_distance_map(
    binary_mask: np.ndarray,
    spacing_mm: Tuple[float, float, float] = (1.0, 1.0, 1.0),
    inside_is_positive: bool = True,
) -> np.ndarray:
    """
    Computes exact Euclidean Signed Maurer Distance Map in physical millimeters.
    If inside_is_positive is True:
        Positive values represent physical distance inside the object boundary.
        Negative values represent distance outside into surrounding tissue.
    """
    if not HAS_SITK:
        from scipy.ndimage import distance_transform_edt
        # Scipy fallback
        d_in = distance_transform_edt(binary_mask > 0, sampling=(spacing_mm[2], spacing_mm[1], spacing_mm[0]))
        d_out = distance_transform_edt(binary_mask == 0, sampling=(spacing_mm[2], spacing_mm[1], spacing_mm[0]))
        return (d_in - d_out) if inside_is_positive else (d_out - d_in)

    img = numpy_to_sitk(binary_mask > 0, spacing_mm=spacing_mm, is_label=True)
    maurer = sitk.SignedMaurerDistanceMapImageFilter()
    maurer.SetSquaredDistance(False)
    maurer.SetUseImageSpacing(True)
    maurer.SetInsideIsPositive(inside_is_positive)
    dist_img = maurer.Execute(img)
    return sitk.GetArrayFromImage(dist_img)


def extract_largest_connected_component(binary_mask: np.ndarray) -> np.ndarray:
    """Extracts the largest connected 3D anatomical component, removing spurious floating islands."""
    if not HAS_SITK:
        from scipy.ndimage import label
        labeled, num_features = label(binary_mask > 0)
        if num_features == 0:
            return binary_mask
        counts = np.bincount(labeled.flat)
        counts[0] = 0
        largest_label = counts.argmax()
        return (labeled == largest_label).astype(np.uint8)

    img = numpy_to_sitk(binary_mask > 0, is_label=True)
    cc = sitk.ConnectedComponent(img)
    relabeled = sitk.RelabelComponent(cc)
    largest = sitk.Equal(relabeled, 1)
    return sitk.GetArrayFromImage(largest).astype(np.uint8)


def binary_morphology(
    binary_mask: np.ndarray,
    radius_voxels: int = 2,
    operation: str = "closing",
) -> np.ndarray:
    """
    Applies mathematical morphology (dilation, erosion, opening, closing).
    Uses spherical structuring element.
    """
    if not HAS_SITK:
        from scipy.ndimage import binary_dilation, binary_erosion, binary_closing, binary_opening
        struct = np.ones((radius_voxels * 2 + 1, radius_voxels * 2 + 1, radius_voxels * 2 + 1), dtype=bool)
        if operation == "dilation":
            return binary_dilation(binary_mask > 0, structure=struct).astype(np.uint8)
        elif operation == "erosion":
            return binary_erosion(binary_mask > 0, structure=struct).astype(np.uint8)
        elif operation == "opening":
            return binary_opening(binary_mask > 0, structure=struct).astype(np.uint8)
        else:
            return binary_closing(binary_mask > 0, structure=struct).astype(np.uint8)

    img = numpy_to_sitk(binary_mask > 0, is_label=True)
    if operation == "dilation":
        res = sitk.BinaryDilate(img, [radius_voxels, radius_voxels, radius_voxels], sitk.sitkBall)
    elif operation == "erosion":
        res = sitk.BinaryErode(img, [radius_voxels, radius_voxels, radius_voxels], sitk.sitkBall)
    elif operation == "opening":
        res = sitk.BinaryMorphologicalOpening(img, [radius_voxels, radius_voxels, radius_voxels], sitk.sitkBall)
    else:
        res = sitk.BinaryMorphologicalClosing(img, [radius_voxels, radius_voxels, radius_voxels], sitk.sitkBall)
    return sitk.GetArrayFromImage(res).astype(np.uint8)
