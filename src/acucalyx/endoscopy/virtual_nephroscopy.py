"""
AcuCalyx Endoscopy: Computed Endoluminal Rehearsal (Virtual Nephroscopy)
Governed by ACU-M15-EXEC-PLAN-2026-V2 (Milestone M15.5).

Generates endoluminal camera trajectories and telemetry keyframes for procedural rehearsal.
Features:
- Centerline camera poses with smoothed Frenet-Serret framing and quaternion rotation
- Anatomical provenance tracking overlaid on each frame (DIRECT, PARTIAL, ESTIMATED, UNAVAILABLE)
- Scope deflection angle telemetry and lumen caliber HUD
- Explicit non-diagnostic synthetic visualization disclaimer
"""

from dataclasses import dataclass, field
import math
from typing import Dict, List, Optional, Tuple
import numpy as np

from acucalyx.endoscopy.instrument_registry import (
    ValidatedEndoscopeProfile,
    WorkingChannelTool,
    get_endoscope_profile,
)
from acucalyx.endoscopy.skeletonizer import (
    CollectingSystemGraph,
    CenterlineNode,
    CenterlineEdge,
    compute_frenet_frame,
)
from acucalyx.endoscopy.stone_coverage import StoneBurdenUnit


@dataclass
class EndoluminalKeyframe:
    """Individual rehearsal viewport keyframe with optical pose and clinical HUD telemetry."""
    frame_index: int
    arc_length_s: float
    camera_position_lps_mm: np.ndarray  # [x, y, z]
    camera_forward_vector: np.ndarray   # unit forward look vector
    camera_up_vector: np.ndarray        # unit camera up vector
    quaternion_orientation: np.ndarray  # [qx, qy, qz, qw]
    current_calyx_id: str
    current_calyx_group: str
    anatomy_provenance: str             # DIRECT, PARTIAL, ESTIMATED, UNAVAILABLE
    active_deflection_deg: float
    max_deflection_deg: float
    min_feret_diameter_mm: float
    visible_stone_ids: List[str]
    synthetic_rendering_disclaimer: str = "SYNTHETIC VISUALIZATION TEXTURE — NON-DIAGNOSTIC PROCEDURAL REHEARSAL ONLY"


@dataclass
class ComputedEndoluminalRehearsalTrajectory:
    """Full procedural fly-through sequence for WebGL/Three.js endoluminal viewer."""
    trajectory_id: str
    entered_calyx_id: str
    target_calyx_id: str
    instrument_model_id: str
    tool_configuration: str
    keyframes: List[EndoluminalKeyframe]
    total_path_length_mm: float
    field_of_view_deg: float
    direction_of_view_deg: float
    synthetic_rendering_notice: str = (
        "Notice: Endoluminal view is computationally synthesized from segmented CT DICOM images. "
        "Surface textures and colors are non-diagnostic aesthetic representations for operative rehearsal."
    )


def _matrix_to_quaternion(R: np.ndarray) -> np.ndarray:
    """Converts 3x3 rotation matrix to unit quaternion [qx, qy, qz, qw]."""
    tr = R[0, 0] + R[1, 1] + R[2, 2]
    if tr > 0.0:
        S = math.sqrt(tr + 1.0) * 2.0
        qw = 0.25 * S
        qx = (R[2, 1] - R[1, 2]) / S
        qy = (R[0, 2] - R[2, 0]) / S
        qz = (R[1, 0] - R[0, 1]) / S
    elif (R[0, 0] > R[1, 1]) and (R[0, 0] > R[2, 2]):
        S = math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2.0
        qw = (R[2, 1] - R[1, 2]) / S
        qx = 0.25 * S
        qy = (R[0, 1] + R[1, 0]) / S
        qz = (R[0, 2] + R[2, 0]) / S
    elif R[1, 1] > R[2, 2]:
        S = math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2.0
        qw = (R[0, 2] - R[2, 0]) / S
        qx = (R[0, 1] + R[1, 0]) / S
        qy = 0.25 * S
        qz = (R[1, 2] + R[2, 1]) / S
    else:
        S = math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2.0
        qw = (R[1, 0] - R[0, 1]) / S
        qx = (R[0, 2] + R[2, 0]) / S
        qy = (R[1, 2] + R[2, 1]) / S
        qz = 0.25 * S
    q = np.array([qx, qy, qz, qw], dtype=float)
    return q / (np.linalg.norm(q) + 1e-8)


def generate_endoluminal_rehearsal_trajectory(
    graph: CollectingSystemGraph,
    trajectory_id: str,
    entered_calyx_id: str,
    target_calyx_id: str,
    sheath_tip_lps: np.ndarray,
    tract_unit_vector: np.ndarray,
    instrument_model_id: str,
    tool: WorkingChannelTool = WorkingChannelTool.EMPTY,
    stones: Optional[List[StoneBurdenUnit]] = None,
    sample_spacing_mm: float = 2.0,
) -> ComputedEndoluminalRehearsalTrajectory:
    """
    Constructs a sequential keyframe fly-through along the continuous 3D lumen path
    from the percutaneous sheath tip into the entered calyx, through the renal pelvis,
    and navigating into the target secondary calyx.
    """
    scope = get_endoscope_profile(instrument_model_id)
    max_deflect = scope.get_max_deflection_deg(tool)

    # 1. Extract continuous 3D path points from sheath tip to target calyx apex
    target_calyx = graph.calyces[target_calyx_id]
    target_apex_pos = graph.nodes[target_calyx.apex_node_id].position_lps_mm

    raw_path = graph.get_path_points(entered_calyx_id, target_calyx_id)
    if len(raw_path) < 2:
        raw_path = np.linspace(sheath_tip_lps, target_apex_pos, 20)

    # Prepend sheath tip position to path
    full_path_pts = np.vstack([sheath_tip_lps, raw_path])

    # Resample path at equidistant steps (sample_spacing_mm)
    diffs = np.diff(full_path_pts, axis=0)
    seg_lens = np.linalg.norm(diffs, axis=1)
    cum_lens = np.insert(np.cumsum(seg_lens), 0, 0.0)
    total_len = float(cum_lens[-1])

    n_samples = max(8, int(total_len / max(0.5, sample_spacing_mm)))
    sample_s = np.linspace(0.0, total_len, n_samples)
    resampled_pts = np.zeros((n_samples, 3), dtype=float)

    for i, s in enumerate(sample_s):
        idx = int(np.searchsorted(cum_lens, s, side="right")) - 1
        idx = min(len(cum_lens) - 2, max(0, idx))
        seg_ratio = (s - cum_lens[idx]) / max(1e-4, cum_lens[idx + 1] - cum_lens[idx])
        resampled_pts[i] = full_path_pts[idx] * (1.0 - seg_ratio) + full_path_pts[idx + 1] * seg_ratio

    # 2. Compute smooth Frenet-Serret framing
    tangents, normals, binormals, curvatures, _ = compute_frenet_frame(resampled_pts)

    keyframes: List[EndoluminalKeyframe] = []

    for i in range(n_samples):
        pos = resampled_pts[i]
        fwd = tangents[i]
        up = normals[i]
        right = binormals[i]

        # Orthogonal rotation matrix: columns are [right, up, forward]
        R = np.column_stack([right, up, fwd])
        quat = _matrix_to_quaternion(R)

        # Telemetry: current calyx context
        # Determine whether camera is currently in entered calyx, pelvis, or target calyx
        dist_to_sheath = float(np.linalg.norm(pos - sheath_tip_lps))
        dist_to_target = float(np.linalg.norm(pos - target_apex_pos))
        dist_to_pelvis = float(np.linalg.norm(pos - graph.pelvis_center_lps_mm))

        if dist_to_target < 15.0 or (target_calyx_id == entered_calyx_id and dist_to_sheath > 15.0):
            cur_cid = target_calyx_id
            cur_group = target_calyx.calyx_group
            prov = target_calyx.visibility_state
            cur_feret = target_calyx.infundibular_width_min_mm
        elif dist_to_sheath < 15.0:
            cur_cid = entered_calyx_id
            entered_calyx = graph.calyces.get(entered_calyx_id, target_calyx)
            cur_group = entered_calyx.calyx_group
            prov = entered_calyx.visibility_state
            cur_feret = entered_calyx.infundibular_width_min_mm
        else:
            cur_cid = "RENAL_PELVIS"
            cur_group = "CENTRAL_PELVIS"
            prov = "DIRECT"
            cur_feret = 12.0  # Large pelvic chamber lumen

        # Current scope deflection angle relative to initial tract entry vector
        cos_dev = np.clip(float(np.dot(tract_unit_vector, fwd)), -1.0, 1.0)
        cur_deflect_deg = float(np.degrees(np.arccos(cos_dev)))

        # Find visible stones within camera forward cone (FOV: scope.field_of_view_deg, range: 35 mm)
        visible_stones: List[str] = []
        if stones:
            for s in stones:
                vec_s = s.centroid_lps_mm - pos
                d_s = float(np.linalg.norm(vec_s))
                if 1.0 < d_s < 35.0:
                    cos_s = np.dot(fwd, vec_s / d_s)
                    half_fov = scope.field_of_view_deg * 0.5
                    if math.degrees(math.acos(np.clip(cos_s, -1.0, 1.0))) <= half_fov:
                        visible_stones.append(s.stone_id)

        kf = EndoluminalKeyframe(
            frame_index=i,
            arc_length_s=float(sample_s[i]),
            camera_position_lps_mm=pos,
            camera_forward_vector=fwd,
            camera_up_vector=up,
            quaternion_orientation=quat,
            current_calyx_id=cur_cid,
            current_calyx_group=cur_group,
            anatomy_provenance=prov,
            active_deflection_deg=cur_deflect_deg,
            max_deflection_deg=max_deflect,
            min_feret_diameter_mm=cur_feret,
            visible_stone_ids=visible_stones,
        )
        keyframes.append(kf)

    return ComputedEndoluminalRehearsalTrajectory(
        trajectory_id=trajectory_id,
        entered_calyx_id=entered_calyx_id,
        target_calyx_id=target_calyx_id,
        instrument_model_id=instrument_model_id,
        tool_configuration=tool.value,
        keyframes=keyframes,
        total_path_length_mm=total_len,
        field_of_view_deg=scope.field_of_view_deg,
        direction_of_view_deg=scope.direction_of_view_deg,
    )
