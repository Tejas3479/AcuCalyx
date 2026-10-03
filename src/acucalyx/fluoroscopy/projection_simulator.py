"""
AcuCalyx Fluoroscopy: Virtual Projection Simulator

Implements:
- Virtual X-ray pinhole projection camera for fluoroscopy simulation
- Bull's-Eye Projection: Camera optical axis aligned directly along needle vector
- Progression Projection: Camera optical axis orthogonal to needle vector
- 2D projection of 3D landmarks (needle tip, shaft, stone centroid, rib contours)
- Simulated fluoroscopic viewing geometry independent of proprietary hardware APIs
"""

from dataclasses import dataclass
from typing import Tuple, Optional, Sequence
import numpy as np

from acucalyx.geometry.transforms import LineSegment3D, angle_between_vectors


@dataclass(frozen=True)
class VirtualFluoroscopyCamera:
    """
    Virtual C-arm fluoroscopy camera pose in patient physical space.
    """
    source_position: np.ndarray      # X-ray tube focal spot [x, y, z] mm
    detector_position: np.ndarray    # Center of image intensifier / flat panel [x, y, z] mm
    optical_axis: np.ndarray         # Unit vector from source to detector
    up_vector: np.ndarray            # Detector vertical orientation unit vector
    source_to_detector_distance_mm: float # Standard C-arm SID ~ 1000 mm
    source_to_isocenter_distance_mm: float # Source to patient isocenter ~ 600 mm


@dataclass(frozen=True)
class ProjectedTrajectoryView:
    """
    2D projection coordinates of needle and target in the fluoroscopic detector plane.
    """
    view_type: str                   # 'BULLS_EYE' or 'PROGRESSION'
    camera: VirtualFluoroscopyCamera
    projected_entry_2d_mm: np.ndarray # [u, v] on detector in mm
    projected_target_2d_mm: np.ndarray # [u, v] on detector in mm
    projected_needle_length_2d_mm: float # Near 0.0 for Bull's-eye view, >> 0.0 for Progression
    alignment_angle_deg: float       # Angle between optical axis and needle vector


def construct_bullseye_camera(
    trajectory: LineSegment3D,
    isocenter: Optional[np.ndarray] = None,
    sid_mm: float = 1000.0,
    sod_mm: float = 600.0
) -> VirtualFluoroscopyCamera:
    """
    Constructs a virtual C-arm pose where the central X-ray beam is aligned
    co-linearly with the needle trajectory vector (Skin -> Calyx Target).
    """
    needle_dir = trajectory.unit_direction
    
    # Isocenter defaults to trajectory midpoint or target
    iso = np.asarray(isocenter, dtype=np.float64) if isocenter is not None else trajectory.end_point
    
    # Optical axis points from skin towards target (along needle direction)
    optical_axis = needle_dir / np.linalg.norm(needle_dir)
    
    # Source is placed behind the skin along negative optical axis
    source_pos = iso - optical_axis * sod_mm
    detector_pos = source_pos + optical_axis * sid_mm
    
    # Arbitrary orthogonal up vector
    arbitrary = np.array([0.0, 0.0, 1.0])
    if np.isclose(abs(np.dot(optical_axis, arbitrary)), 1.0, atol=1e-3):
        arbitrary = np.array([0.0, 1.0, 0.0])
        
    right_vec = np.cross(optical_axis, arbitrary)
    right_vec = right_vec / np.linalg.norm(right_vec)
    up_vec = np.cross(right_vec, optical_axis)
    up_vec = up_vec / np.linalg.norm(up_vec)
    
    return VirtualFluoroscopyCamera(
        source_position=source_pos,
        detector_position=detector_pos,
        optical_axis=optical_axis,
        up_vector=up_vec,
        source_to_detector_distance_mm=sid_mm,
        source_to_isocenter_distance_mm=sod_mm
    )


def construct_progression_camera(
    trajectory: LineSegment3D,
    isocenter: Optional[np.ndarray] = None,
    sid_mm: float = 1000.0,
    sod_mm: float = 600.0
) -> VirtualFluoroscopyCamera:
    """
    Constructs a virtual C-arm pose orthogonal to the needle vector (90 degrees),
    allowing observation of needle advancement and penetration depth into the calyx.
    """
    needle_dir = trajectory.unit_direction
    iso = np.asarray(isocenter, dtype=np.float64) if isocenter is not None else trajectory.end_point
    
    # Find orthogonal direction in transverse plane
    arbitrary = np.array([0.0, 0.0, 1.0])
    if np.isclose(abs(np.dot(needle_dir, arbitrary)), 1.0, atol=1e-3):
        arbitrary = np.array([0.0, 1.0, 0.0])
        
    ortho_dir = np.cross(needle_dir, arbitrary)
    ortho_dir = ortho_dir / np.linalg.norm(ortho_dir)
    
    source_pos = iso - ortho_dir * sod_mm
    detector_pos = source_pos + ortho_dir * sid_mm
    
    up_vec = needle_dir / np.linalg.norm(needle_dir)
    
    return VirtualFluoroscopyCamera(
        source_position=source_pos,
        detector_position=detector_pos,
        optical_axis=ortho_dir,
        up_vector=up_vec,
        source_to_detector_distance_mm=sid_mm,
        source_to_isocenter_distance_mm=sod_mm
    )


def project_points_to_detector(
    camera: VirtualFluoroscopyCamera,
    points_3d: np.ndarray
) -> np.ndarray:
    """
    Performs central perspective projection of 3D physical points onto the 2D detector plane.
    Returns [u, v] in mm on detector centered at detector_position.
    """
    pts = np.asarray(points_3d, dtype=np.float64)
    is_single = pts.ndim == 1
    if is_single:
        pts = pts.reshape(1, 3)

    # Basis vectors of detector plane
    normal = camera.optical_axis
    up = camera.up_vector
    right = np.cross(normal, up)
    right = right / np.linalg.norm(right)

    # Vector from source to points
    v_source = pts - camera.source_position  # (N, 3)
    
    # Distance along optical axis from source
    d_along_axis = np.dot(v_source, normal)  # (N,)
    
    if np.any(d_along_axis <= 0.0):
        raise ValueError("Points behind X-ray source cannot be projected")

    # Scale factor for perspective projection to detector plane
    scale = camera.source_to_detector_distance_mm / d_along_axis[:, np.newaxis]
    
    # Piercing point on detector in 3D
    pierce_pts = camera.source_position + v_source * scale  # (N, 3)
    
    # Offset from detector center
    offset_from_center = pierce_pts - camera.detector_position
    
    u = np.dot(offset_from_center, right)
    v = np.dot(offset_from_center, up)
    
    coords_2d = np.column_stack([u, v])
    return coords_2d[0] if is_single else coords_2d


def simulate_trajectory_projection(
    trajectory: LineSegment3D,
    view_type: str = 'BULLS_EYE',
    isocenter: Optional[np.ndarray] = None
) -> ProjectedTrajectoryView:
    """
    Simulates fluoroscopic projection of a needle trajectory for Bull's-eye or Progression view.
    """
    if view_type == 'BULLS_EYE':
        cam = construct_bullseye_camera(trajectory, isocenter=isocenter)
    elif view_type == 'PROGRESSION':
        cam = construct_progression_camera(trajectory, isocenter=isocenter)
    else:
        raise ValueError(f"Unknown view_type: {view_type}")

    proj_entry = project_points_to_detector(cam, trajectory.start_point)
    proj_target = project_points_to_detector(cam, trajectory.end_point)
    
    proj_length = float(np.linalg.norm(proj_target - proj_entry))
    angle = angle_between_vectors(cam.optical_axis, trajectory.unit_direction)

    return ProjectedTrajectoryView(
        view_type=view_type,
        camera=cam,
        projected_entry_2d_mm=proj_entry,
        projected_target_2d_mm=proj_target,
        projected_needle_length_2d_mm=proj_length,
        alignment_angle_deg=angle
    )
