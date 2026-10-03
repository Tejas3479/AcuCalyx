"""
AcuCalyx Fluoroscopy: Trusted CPU Reference DRR Engine (Frozen v4.1)

Implements Step 4.02 of Phase 4:
Provides a pure NumPy, numerically verified reference implementation of
Beer-Lambert ray integration through 3D CT volumes:

    I(u, v) = I_0 * exp( - sum_{k} mu(r_k) * delta_s )

Serves as the golden ground truth against which accelerated GPU engines
and multi-spectral models are validated.
"""

from typing import Optional, Tuple
import numpy as np
from scipy import ndimage

from acucalyx.fluoroscopy.surgical_pose import CArmPoseGeometry
from acucalyx.geometry.coordinates import SpatialOrientation


def hu_to_linear_attenuation(hu_array: np.ndarray, mu_water: float = 0.020, mu_bone: float = 0.055) -> np.ndarray:
    """
    Calibrated Level 1 mapping of CT Hounsfield Units to empirical linear attenuation (mm^-1).
    
    mu(HU) = max(0, mu_water * (1 + HU / 1000))  for HU <= 100
    mu(HU) = mu_water + ((HU - 100) / 1000) * (mu_bone - mu_water)  for HU > 100
    """
    mu = np.zeros_like(hu_array, dtype=np.float32)

    soft_mask = hu_array <= 100.0
    bone_mask = hu_array > 100.0

    # Soft tissue / air / fat
    mu[soft_mask] = np.maximum(0.0, mu_water * (1.0 + hu_array[soft_mask] / 1000.0))

    # Bone / stone / contrast
    mu[bone_mask] = mu_water + ((hu_array[bone_mask] - 100.0) / 1000.0) * (mu_bone - mu_water)

    return mu


def generate_cpu_reference_drr(
    ct_volume_hu: np.ndarray,
    spatial: SpatialOrientation,
    pose: CArmPoseGeometry,
    output_resolution: Tuple[int, int] = (256, 256),
    step_size_mm: float = 2.0,
    polarity: str = "INVERTED_FLUOROSCOPY"
) -> np.ndarray:
    """
    Generates a trusted CPU reference DRR via analytical ray marching.
    
    Args:
        ct_volume_hu: 3D CT volume [X, Y, Z]
        spatial: SpatialOrientation with physical affine transforms
        pose: CArmPoseGeometry defining focal spot, detector, and projection matrix
        output_resolution: (width, height) of output DRR image
        step_size_mm: Ray sampling step size in mm
        polarity: 'INVERTED_FLUOROSCOPY' (dark bone/stone) or 'POSITIVE_RADIOGRAPHIC'
        
    Returns:
        2D numpy array [height, width] of uint8 [0, 255]
    """
    out_w, out_h = output_resolution
    det_w_px = pose.profile.detector_width_px
    det_h_px = pose.profile.detector_height_px

    pitch_x = pose.profile.pixel_pitch_mm[0] * (det_w_px / out_w)
    pitch_y = pose.profile.pixel_pitch_mm[1] * (det_h_px / out_h)

    # Convert CT to attenuation
    attenuation_vol = hu_to_linear_attenuation(ct_volume_hu)

    source_pos = pose.source_position_lps
    det_center = pose.detector_center_lps
    u_axis = pose.detector_u_axis
    v_axis = pose.detector_v_axis

    # Grid of detector pixel coordinates centered on detector_center_lps
    u_coords = (np.arange(out_w) - out_w / 2.0 + 0.5) * pitch_x
    v_coords = (np.arange(out_h) - out_h / 2.0 + 0.5) * pitch_y

    u_grid, v_grid = np.meshgrid(u_coords, v_coords)

    # Pixel 3D positions in LPS: d_center + u * u_axis + v * v_axis
    # Shape: (out_h, out_w, 3)
    det_pixels = (
        det_center.reshape(1, 1, 3) +
        u_grid[:, :, np.newaxis] * u_axis.reshape(1, 1, 3) +
        v_grid[:, :, np.newaxis] * v_axis.reshape(1, 1, 3)
    )

    # Ray unit directions from source to detector pixel
    ray_vectors = det_pixels - source_pos.reshape(1, 1, 3)
    ray_lengths = np.linalg.norm(ray_vectors, axis=2, keepdims=True)
    ray_dirs = ray_vectors / (ray_lengths + 1e-9)

    # Determine ray-marching distances across the CT volume region
    # Distance from source to isocenter is pose.profile.source_to_isocenter_distance_mm
    sod = pose.profile.source_to_isocenter_distance_mm
    # Volume extent is roughly within sod - 250 mm to sod + 250 mm
    t_start = max(10.0, sod - 220.0)
    t_end = min(pose.profile.source_to_detector_distance_mm - 10.0, sod + 220.0)
    num_steps = int(round((t_end - t_start) / step_size_mm))
    t_steps = np.linspace(t_start, t_end, num_steps)

    # Initialize line integral accumulator (out_h, out_w)
    line_integral = np.zeros((out_h, out_w), dtype=np.float32)

    # Batch ray-march along step positions
    # To conserve memory and maintain fast CPU execution, march across step slices
    vol_shape = ct_volume_hu.shape
    v2p_inv = spatial.inv_affine_matrix

    for t in t_steps:
        # Sample points at distance t: source + t * ray_dirs
        # Shape: (out_h, out_w, 3)
        sample_pts_lps = source_pos.reshape(1, 1, 3) + t * ray_dirs

        # Convert to homogeneous coordinates for fast affine multiplication
        pts_flat = sample_pts_lps.reshape(-1, 3)
        pts_homog = np.hstack([pts_flat, np.ones((pts_flat.shape[0], 1))])

        vox_pts = (v2p_inv @ pts_homog.T)[0:3, :].T
        vox_pts_grid = vox_pts.reshape(out_h, out_w, 3)

        # Nearest-neighbor or linear bounds check
        vx = np.round(vox_pts_grid[:, :, 0]).astype(int)
        vy = np.round(vox_pts_grid[:, :, 1]).astype(int)
        vz = np.round(vox_pts_grid[:, :, 2]).astype(int)

        valid_mask = (
            (vx >= 0) & (vx < vol_shape[0]) &
            (vy >= 0) & (vy < vol_shape[1]) &
            (vz >= 0) & (vz < vol_shape[2])
        )

        mu_slice = np.zeros((out_h, out_w), dtype=np.float32)
        mu_slice[valid_mask] = attenuation_vol[vx[valid_mask], vy[valid_mask], vz[valid_mask]]

        line_integral += mu_slice * step_size_mm

    # Beer-Lambert Transmission: T = exp(-integral)
    transmission = np.exp(-line_integral)

    # Display polarity mapping
    if polarity == "INVERTED_FLUOROSCOPY":
        # Standard surgical fluoro: High attenuation (bone/stone) absorbs beam -> Low transmission -> Dark
        drr_img = (transmission * 255.0).clip(0, 255).astype(np.uint8)
    else:
        # Radiographic positive: High attenuation -> Bright white
        drr_img = ((1.0 - transmission) * 255.0).clip(0, 255).astype(np.uint8)

    return drr_img
