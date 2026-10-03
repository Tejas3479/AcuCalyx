"""
Unit tests for AcuCalyx hierarchical flank sampling, conical puncture zones, and stone reachability.
"""

import numpy as np
import pytest

from tests.phantom.phantom_generator import generate_synthetic_pcnl_phantom
from acucalyx.geometry.transforms import LineSegment3D
from acucalyx.anatomy.segmentation import AnatomicalCorridorMasks, OrganLabel
from acucalyx.planning.entry_regions import extract_body_surface_mask, sample_hierarchical_flank_points
from acucalyx.planning.target_candidates import (
    ConicalPunctureZone, CalyxGroup, generate_candidate_puncture_zones
)
from acucalyx.planning.scope_model import STANDARD_RIGID_NEPHROSCOPE, FLEXIBLE_CYSTONEPHROSCOPE
from acucalyx.planning.stone_reach import evaluate_access_stone_reach
from acucalyx.stones.volumetry import StoneMorphometry
from acucalyx.collecting_system.visibility_gate import PCSVisibilityState


def test_skin_surface_and_flank_sampling():
    """Verify body surface mask extraction and hierarchical posterior flank points."""
    vol, spatial, gt = generate_synthetic_pcnl_phantom(grid_shape=(96, 96, 80), noise_sigma_hu=0.0)

    skin_mask = extract_body_surface_mask(vol, threshold_hu=-300.0)
    assert np.any(skin_mask)

    # Empty anatomy container for testing sampling bounds
    anatomy = AnatomicalCorridorMasks(spatial_orientation=spatial)
    
    # Left flank points
    flank_pts = sample_hierarchical_flank_points(
        skin_surface_mask=skin_mask,
        spatial_orientation=spatial,
        anatomy_masks=anatomy,
        side="left",
        coarse_step_mm=15.0
    )

    assert len(flank_pts) >= 4
    # All sampled points on left side must have X > 0 and Y > 0 (posterior)
    for p in flank_pts:
        assert p.physical_lps_mm[0] > 0.0
        assert p.physical_lps_mm[1] > 0.0
        assert p.side == "left"


def test_conical_puncture_zone_coaxial_validation():
    """Verify conical zone accepts trajectories coaxial to infundibulum and rejects orthogonal ones."""
    papilla = np.array([20.0, 10.0, 30.0])
    # Axis points along -Y into pelvis
    axis = np.array([0.0, -1.0, 0.0])
    
    zone = ConicalPunctureZone(
        zone_id="TEST_ZONE",
        calyx_group=CalyxGroup.POSTERIOR_LOWER,
        apex_papilla_lps_mm=papilla,
        infundibular_axis_unit=axis,
        cone_half_angle_deg=15.0,
        visibility_state=PCSVisibilityState.DIRECTLY_OPACIFIED,
        confidence_score=0.9
    )

    # Needle advancing from posterior skin [20, 50, 30] towards papilla [20, 10, 30]
    # Unit direction is [0, -1, 0], perfectly coaxial!
    needle_dir_coaxial = np.array([0.0, -1.0, 0.0])
    is_valid, angle = zone.is_trajectory_coaxial(needle_dir_coaxial)
    assert is_valid is True
    assert np.isclose(angle, 0.0)

    # Needle advancing from lateral side [60, 10, 30] towards papilla [20, 10, 30]
    # Direction is [-1, 0, 0], orthogonal (90 degrees)!
    needle_dir_ortho = np.array([-1.0, 0.0, 0.0])
    is_valid_ortho, angle_ortho = zone.is_trajectory_coaxial(needle_dir_ortho)
    assert is_valid_ortho is False
    assert np.isclose(angle_ortho, 90.0)


def test_stone_reach_with_rigid_vs_flexible_scope():
    """Verify rigid scope reaches in-line stones, while flexible scope reaches off-axis stones."""
    target_papilla = np.array([20.0, 10.0, 30.0])
    skin_entry = np.array([20.0, 60.0, 30.0])
    traj = LineSegment3D(start_point=skin_entry, end_point=target_papilla)

    zone = ConicalPunctureZone(
        zone_id="TEST_ZONE",
        calyx_group=CalyxGroup.POSTERIOR_LOWER,
        apex_papilla_lps_mm=target_papilla,
        infundibular_axis_unit=np.array([0.0, -1.0, 0.0]),
        cone_half_angle_deg=15.0,
        visibility_state=PCSVisibilityState.DIRECTLY_OPACIFIED,
        confidence_score=0.9
    )

    # Stone 1: Directly in-line (along -Y at [20, 0, 30], 10mm from papilla)
    stone_inline = StoneMorphometry(
        stone_id=1,
        volume_mm3=300.0,
        volume_voxels=300,
        centroid_lps_mm=np.array([20.0, 0.0, 30.0]),
        max_feret_diameter_mm=8.0,
        bounding_box_span_mm=np.array([8.0, 8.0, 8.0]),
        tier="DENSE_CALCIUM"
    )

    # Stone 2: Located in upper pole at [20.0, 5.0, 60.0] (large 70 degree deflection required)
    stone_upper = StoneMorphometry(
        stone_id=2,
        volume_mm3=500.0,
        volume_voxels=500,
        centroid_lps_mm=np.array([20.0, 5.0, 60.0]),
        max_feret_diameter_mm=10.0,
        bounding_box_span_mm=np.array([10.0, 10.0, 10.0]),
        tier="DENSE_CALCIUM"
    )

    stones = [stone_inline, stone_upper]

    # Rigid nephroscope: max deflection 15 degrees
    reach_rigid = evaluate_access_stone_reach(traj, zone, STANDARD_RIGID_NEPHROSCOPE, stones)
    # Can only reach Stone 1 (inline)
    assert reach_rigid.reachable_stone_ids == [1]
    assert np.isclose(reach_rigid.reachable_stone_fraction, 300.0 / 800.0)

    # Flexible nephroscope: max deflection 210 degrees
    reach_flex = evaluate_access_stone_reach(traj, zone, FLEXIBLE_CYSTONEPHROSCOPE, stones)
    # Can reach both stones
    assert 1 in reach_flex.reachable_stone_ids
    assert 2 in reach_flex.reachable_stone_ids
    assert np.isclose(reach_flex.reachable_stone_fraction, 1.0)
