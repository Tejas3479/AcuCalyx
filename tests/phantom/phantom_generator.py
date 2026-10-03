"""
AcuCalyx Synthetic Calibration Phantom Generator

Generates a mathematically calibrated 3D CT volume with known analytical ground truth:
- Spherical stones of exact radii: V = (4/3) * pi * r^3
- Ellipsoidal kidney parenchyma (35 HU)
- Fluid-distended calyx cavity (10 HU)
- Cylindrical colon hazard with air lumen (-1000 HU) and soft-tissue wall (35 HU)
- Bone ribs (1000 HU)
- Fat and body surface (-100 HU)

Outputs both 3D volume (as NIfTI or NumPy) and GroundTruthMetadata for deterministic verification.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Tuple
import numpy as np
import nibabel as nib

from acucalyx.geometry.coordinates import SpatialOrientation


@dataclass
class PhantomGroundTruth:
    """Analytical ground truth parameters of the synthetic phantom."""
    stone_center_mm: np.ndarray      # [x, y, z] in mm
    stone_radius_mm: float           # radius r in mm
    stone_volume_mm3: float          # (4/3) * pi * r^3
    stone_mean_hu: float             # nominal HU
    
    calyx_center_mm: np.ndarray      # [x, y, z] target calyx in mm
    kidney_center_mm: np.ndarray     # [x, y, z] in mm
    kidney_radii_mm: np.ndarray      # [rx, ry, rz] in mm
    
    colon_axis_start_mm: np.ndarray  # line axis of colon cylinder
    colon_axis_end_mm: np.ndarray
    colon_radius_mm: float
    
    rib_axis_start_mm: np.ndarray
    rib_axis_end_mm: np.ndarray
    rib_radius_mm: float
    
    grid_shape: Tuple[int, int, int] # (rows, cols, slices)
    spacing_mm: np.ndarray           # (dx, dy, dz)
    origin_mm: np.ndarray            # [x, y, z]


def generate_synthetic_pcnl_phantom(
    grid_shape: Tuple[int, int, int] = (128, 128, 96),
    spacing_mm: Tuple[float, float, float] = (1.0, 1.0, 1.0),
    stone_radius_mm: float = 5.0,
    noise_sigma_hu: float = 5.0
) -> Tuple[np.ndarray, SpatialOrientation, PhantomGroundTruth]:
    """
    Generates an analytical synthetic PCNL CT volume with exact ground truth.
    
    Coordinate space: LPS [mm]
    Origin: (-64.0, -64.0, 0.0)
    """
    rows, cols, slices = grid_shape
    dx, dy, dz = spacing_mm
    
    # Establish orientation: standard axial scan (LPS)
    # IOP: Row is +X (Left), Col is +Y (Posterior)
    iop = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    origin = np.array([-cols * dx / 2.0, -rows * dy / 2.0, 0.0], dtype=np.float64)
    
    spatial = SpatialOrientation.from_dicom_parameters(
        image_orientation_patient=iop,
        image_position_patient=origin,
        pixel_spacing=[dy, dx],  # row spacing, col spacing
        slice_spacing=dz
    )
    
    # Background is air (-1000 HU)
    volume = np.full(grid_shape, -1000.0, dtype=np.float32)
    
    # Create coordinate grid in physical space (mm)
    # i: rows (dy), j: cols (dx), k: slices (dz)
    i_coords = np.arange(rows)
    j_coords = np.arange(cols)
    k_coords = np.arange(slices)
    
    I, J, K = np.meshgrid(i_coords, j_coords, k_coords, indexing='ij')
    
    # Convert voxel grid to physical space
    # (row i -> Y, col j -> X, slice k -> Z)
    X_phys = origin[0] + J * dx
    Y_phys = origin[1] + I * dy
    Z_phys = origin[2] + K * dz
    
    # 1. Body trunk (large ellipse centered in scan, HU = -100 fat, 40 muscle)
    body_mask = ((X_phys / 55.0)**2 + (Y_phys / 45.0)**2 <= 1.0) & (Z_phys >= 5.0) & (Z_phys <= (slices * dz - 5.0))
    volume[body_mask] = -100.0  # Subcutaneous fat
    
    # Muscle layer
    muscle_mask = ((X_phys / 50.0)**2 + (Y_phys / 40.0)**2 <= 1.0) & (Z_phys >= 10.0) & (Z_phys <= (slices * dz - 10.0))
    volume[muscle_mask] = 40.0
    
    # 2. Kidney (ellipsoid on left side: X in [10, 35], Y in [0, 25], Z in [25, 75])
    k_center = np.array([20.0, 10.0, 50.0])
    k_radii = np.array([14.0, 10.0, 22.0])
    kidney_dist = ((X_phys - k_center[0]) / k_radii[0])**2 + \
                  ((Y_phys - k_center[1]) / k_radii[1])**2 + \
                  ((Z_phys - k_center[2]) / k_radii[2])**2
    kidney_mask = kidney_dist <= 1.0
    volume[kidney_mask] = 35.0  # Renal parenchyma
    
    # 3. Calyx / Collecting system cavity (lower pole posterior calyx, fluid = 10 HU)
    calyx_center = np.array([22.0, 14.0, 38.0])
    calyx_radius = 4.0
    calyx_mask = ((X_phys - calyx_center[0])**2 + \
                  (Y_phys - calyx_center[1])**2 + \
                  (Z_phys - calyx_center[2])**2) <= (calyx_radius**2)
    volume[calyx_mask] = 10.0  # Fluid
    
    # 4. Stone (placed inside/near the lower pole calyx, 1200 HU)
    stone_center = np.array([22.0, 14.0, 38.0])
    stone_dist_sq = (X_phys - stone_center[0])**2 + \
                    (Y_phys - stone_center[1])**2 + \
                    (Z_phys - stone_center[2])**2
    stone_mask = stone_dist_sq <= (stone_radius_mm**2)
    volume[stone_mask] = 1200.0  # Calcium stone
    
    analytical_volume = (4.0 / 3.0) * np.pi * (stone_radius_mm**3)
    
    # 5. Colon Hazard (descending colon cylinder running longitudinally along Z)
    # Placed posterolateral to kidney: X = 42.0, Y = 25.0
    colon_axis_start = np.array([42.0, 25.0, 0.0])
    colon_axis_end = np.array([42.0, 25.0, float(slices * dz)])
    colon_radius = 10.0
    colon_dist_sq = (X_phys - colon_axis_start[0])**2 + (Y_phys - colon_axis_start[1])**2
    colon_wall_mask = (colon_dist_sq <= colon_radius**2) & body_mask
    colon_lumen_mask = (colon_dist_sq <= (colon_radius - 2.0)**2) & body_mask
    volume[colon_wall_mask] = 35.0   # Soft tissue wall
    volume[colon_lumen_mask] = -1000.0 # Air lumen
    
    # 6. Rib Obstacle (bone bar running laterally, Z = 55.0, Y = 32.0, X in [0, 50])
    rib_axis_start = np.array([0.0, 32.0, 55.0])
    rib_axis_end = np.array([50.0, 32.0, 55.0])
    rib_radius = 5.0
    # Distance from point to line segment
    rib_dist_sq = (Y_phys - rib_axis_start[1])**2 + (Z_phys - rib_axis_start[2])**2
    rib_mask = (rib_dist_sq <= rib_radius**2) & (X_phys >= 0.0) & (X_phys <= 50.0)
    volume[rib_mask] = 1000.0  # Cortical bone
    
    # Add mild Gaussian noise
    if noise_sigma_hu > 0:
        rng = np.random.default_rng(seed=42)
        noise = rng.normal(0.0, noise_sigma_hu, size=grid_shape).astype(np.float32)
        volume += noise
    
    ground_truth = PhantomGroundTruth(
        stone_center_mm=stone_center,
        stone_radius_mm=stone_radius_mm,
        stone_volume_mm3=analytical_volume,
        stone_mean_hu=1200.0,
        calyx_center_mm=calyx_center,
        kidney_center_mm=k_center,
        kidney_radii_mm=k_radii,
        colon_axis_start_mm=colon_axis_start,
        colon_axis_end_mm=colon_axis_end,
        colon_radius_mm=colon_radius,
        rib_axis_start_mm=rib_axis_start,
        rib_axis_end_mm=rib_axis_end,
        rib_radius_mm=rib_radius,
        grid_shape=grid_shape,
        spacing_mm=np.array(spacing_mm, dtype=np.float64),
        origin_mm=origin
    )
    
    return volume, spatial, ground_truth


def save_phantom_to_nifti(
    volume: np.ndarray,
    spatial: SpatialOrientation,
    output_path: Path
) -> Path:
    """Saves synthetic phantom as a standard NIfTI (.nii.gz) file in RAS coordinates."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Standard NIfTI convention uses RAS; convert from LPS
    lps_to_ras = np.diag([-1.0, -1.0, 1.0, 1.0])
    affine_ras = lps_to_ras @ spatial.affine_matrix
    nii = nib.Nifti1Image(volume, affine_ras)
    nii.set_sform(affine_ras, code=1)
    nib.save(nii, str(output_path))
    return output_path
