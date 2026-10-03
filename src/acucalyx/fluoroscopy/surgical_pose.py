"""
AcuCalyx Fluoroscopy: Surgical Pose & SE(3) Projection Geometry (Frozen v4.1)

Implements Step 4.01 of Phase 4:
Establishes the formal geometric transformation chain:
CT Frame -> Surgical Table Pose -> World Frame -> C-Arm SE(3) Pose -> Detector Plane

Governing Principles:
- Replaces simplistic atan2/asin formulas with full SE(3) rigid transformations.
- Explicit Source -> Detector ray convention.
- Target renal calyx is positioned near the C-arm's physical isocenter.
- Constructs calibrated 3x4 projection matrix P = K [R | t].
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple, Union
import numpy as np

from acucalyx.fluoroscopy.carm_profile import CArmProfile, PHILIPS_ZENITION_70
from acucalyx.geometry.transforms import LineSegment3D


class SurgicalPatientPosition(str, Enum):
    PRONE_STANDARD = "PRONE_STANDARD"
    PRONE_SPLIT_LEG = "PRONE_SPLIT_LEG"
    FLANK_LATERAL = "FLANK_LATERAL"
    SUPINE_VALDIVIA = "SUPINE_VALDIVIA"


def compute_ct_to_surgical_transform(
    ct_scan_position: str = "HFS",      # DICOM Patient Position (Head First Supine)
    surgical_position: SurgicalPatientPosition = SurgicalPatientPosition.PRONE_STANDARD
) -> np.ndarray:
    """
    Constructs 4x4 rigid transformation matrix from CT acquisition pose
    to operative surgical table setup.
    """
    t_mat = np.eye(4, dtype=np.float64)

    scan_pos = ct_scan_position.upper()
    is_supine = ("SUPINE" in scan_pos) or (scan_pos in ["HFS", "FFS"])
    if is_supine and surgical_position in [
        SurgicalPatientPosition.PRONE_STANDARD,
        SurgicalPatientPosition.PRONE_SPLIT_LEG
    ]:
        t_mat[0, 0] = -1.0
        t_mat[1, 1] = -1.0
        t_mat[2, 2] = 1.0

    return t_mat


@dataclass(frozen=True)
class CArmPoseGeometry:
    """Rigorous SE(3) pose and projection geometry of a mobile C-arm."""
    profile: CArmProfile
    source_position_lps: np.ndarray      # X-ray tube focal spot s in mm
    isocenter_position_lps: np.ndarray   # Gantry rotational center in mm
    detector_center_lps: np.ndarray      # Detector panel center d in mm
    central_beam_unit_vector: np.ndarray # Explicit Source -> Detector vector b
    detector_u_axis: np.ndarray          # Horizontal detector axis unit vector
    detector_v_axis: np.ndarray          # Vertical detector axis unit vector
    gantry_primary_angle_deg: float      # LAO (+) / RAO (-) or Orbital
    gantry_secondary_angle_deg: float    # Cranial (+) / Caudal (-) or Angulation
    camera_intrinsic_matrix: np.ndarray  # 3x3 K
    camera_extrinsic_matrix: np.ndarray  # 4x4 [R | t]
    projection_matrix_3x4: np.ndarray    # P = K [R | t]

    def project_point_to_detector_px(self, point_lps: np.ndarray) -> Tuple[float, float, float]:
        """
        Projects a 3D physical LPS point into 2D detector pixel coordinates.
        
        Returns:
            u_px: Horizontal pixel coordinate [0, detector_width_px]
            v_px: Vertical pixel coordinate [0, detector_height_px]
            depth_mm: Distance from X-ray source along optical axis
        """
        pt_homog = np.array([point_lps[0], point_lps[1], point_lps[2], 1.0], dtype=np.float64)
        proj_homog = self.projection_matrix_3x4 @ pt_homog

        w = proj_homog[2]
        if abs(w) < 1e-6:
            return -999.0, -999.0, 0.0

        u_px = float(proj_homog[0] / w)
        v_px = float(proj_homog[1] / w)
        depth_mm = float(w)

        return u_px, v_px, depth_mm


def build_carm_projection_geometry(
    beam_direction_lps: np.ndarray,
    target_isocenter_lps: np.ndarray,
    profile: CArmProfile = PHILIPS_ZENITION_70,
    arbitrary_up_hint: Optional[np.ndarray] = None
) -> CArmPoseGeometry:
    """
    Constructs a complete SE(3) C-arm pose given a desired central beam direction.
    
    Beam direction points strictly from SOURCE to DETECTOR:
    b_central = (detector - source) / ||detector - source||
    """
    b = beam_direction_lps / (np.linalg.norm(beam_direction_lps) + 1e-9)

    # Position source and detector along the beam passing through isocenter
    sod = profile.source_to_isocenter_distance_mm
    sid = profile.source_to_detector_distance_mm
    oid = sid - sod  # Isocenter to detector distance

    source_pos = target_isocenter_lps - b * sod
    detector_pos = target_isocenter_lps + b * oid

    # Construct detector coordinate frame (u_det, v_det, w_det)
    # w_det is aligned with beam direction b
    w_det = b.copy()

    up_hint = arbitrary_up_hint if arbitrary_up_hint is not None else np.array([0.0, 0.0, 1.0])
    # If beam is parallel to up_hint, choose alternative perpendicular axis
    if abs(np.dot(b, up_hint)) > 0.95:
        up_hint = np.array([0.0, 1.0, 0.0])

    u_det = np.cross(up_hint, w_det)
    u_det = u_det / np.linalg.norm(u_det)
    v_det = np.cross(w_det, u_det)
    v_det = v_det / np.linalg.norm(v_det)

    # Derive positioner angles (LAO/RAO and Cranial/Caudal)
    # Primary rotation: transverse plane angle relative to AP (+Y direction in LPS)
    primary_deg = float(np.degrees(np.arctan2(b[0], -b[1])))
    # Secondary rotation: elevation relative to transverse plane (+Z direction)
    secondary_deg = float(np.degrees(np.arcsin(np.clip(b[2], -1.0, 1.0))))

    # Camera Extrinsic Matrix: World/LPS -> Camera Frame (origin at source)
    # R_cam = [u_det, v_det, w_det]^T
    R_cam = np.vstack([u_det, v_det, w_det])
    t_cam = -R_cam @ source_pos

    extrinsic_4x4 = np.eye(4, dtype=np.float64)
    extrinsic_4x4[0:3, 0:3] = R_cam
    extrinsic_4x4[0:3, 3] = t_cam

    # Camera Intrinsic Matrix: Focal length in pixels
    # fx = sid / pixel_pitch_x, fy = sid / pixel_pitch_y
    fx = sid / profile.pixel_pitch_mm[0]
    fy = sid / profile.pixel_pitch_mm[1]
    cx = profile.detector_width_px / 2.0
    cy = profile.detector_height_px / 2.0

    intrinsic_3x3 = np.array([
        [fx,  0.0, cx],
        [0.0, fy,  cy],
        [0.0, 0.0, 1.0]
    ], dtype=np.float64)

    # Projection Matrix P = K [R | t] (3x4)
    P_3x4 = intrinsic_3x3 @ extrinsic_4x4[0:3, :]

    return CArmPoseGeometry(
        profile=profile,
        source_position_lps=source_pos,
        isocenter_position_lps=target_isocenter_lps,
        detector_center_lps=detector_pos,
        central_beam_unit_vector=b,
        detector_u_axis=u_det,
        detector_v_axis=v_det,
        gantry_primary_angle_deg=primary_deg,
        gantry_secondary_angle_deg=secondary_deg,
        camera_intrinsic_matrix=intrinsic_3x3,
        camera_extrinsic_matrix=extrinsic_4x4,
        projection_matrix_3x4=P_3x4
    )


def construct_bullseye_carm_pose(
    trajectory: LineSegment3D,
    profile: CArmProfile = PHILIPS_ZENITION_70
) -> CArmPoseGeometry:
    """
    Constructs the Bull's-Eye (en-face) fluoroscopic view.
    
    The central ray points down the needle penetration vector:
    Beam vector = (Target - Entry) / ||Target - Entry||
    Isocenter is set to the target calyx papilla.
    """
    beam_dir = trajectory.unit_direction
    target_pt = trajectory.end_point
    return build_carm_projection_geometry(beam_dir, target_pt, profile)


def construct_depth_verification_carm_pose(
    trajectory: LineSegment3D,
    oblique_angle_offset_deg: float = 30.0,
    profile: CArmProfile = PHILIPS_ZENITION_70
) -> CArmPoseGeometry:
    """
    Constructs the Depth-Verification (Progression) view rotated by an oblique
    angle (typically 30° to 90°) to monitor needle advance and prevent counter-puncture.
    """
    needle_dir = trajectory.unit_direction
    target_pt = trajectory.end_point

    # Find orthogonal vector in transverse plane
    ortho = np.array([-needle_dir[1], needle_dir[0], 0.0])
    if np.linalg.norm(ortho) < 1e-4:
        ortho = np.array([1.0, 0.0, 0.0])
    ortho = ortho / np.linalg.norm(ortho)

    # Rotate beam vector around transverse axis by oblique_angle_offset_deg
    rad = np.radians(oblique_angle_offset_deg)
    rot_dir = np.cos(rad) * needle_dir + np.sin(rad) * ortho
    rot_dir = rot_dir / np.linalg.norm(rot_dir)

    return build_carm_projection_geometry(rot_dir, target_pt, profile)
