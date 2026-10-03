"""
AcuCalyx Property-Based Invariant Tests

Verifies core geometric and optimization invariants:
1. Coordinate Invariant: Voxel -> Physical -> Voxel roundtrip precision < 1e-4 mm
2. Rigid Motion Invariant: Translation and rotation preserve pairwise distances and tract lengths
3. Distance Field Monotonicity: Dilation of an obstacle mask cannot increase clearance to outside points
4. Pareto Invariant: Strictly dominated trajectories are never included in the Pareto frontier
"""

import numpy as np
import pytest
from scipy import ndimage

from acucalyx.geometry.coordinates import SpatialOrientation
from acucalyx.geometry.transforms import LineSegment3D
from acucalyx.geometry.distance_fields import DistanceField
from acucalyx.planning.pareto_optimizer import (
    CandidateTrajectory, extract_pareto_frontier, is_dominated
)
from acucalyx.geometry.distance_fields import HazardClearanceResult


def test_voxel_to_physical_roundtrip_precision():
    """Invariant 1: Voxel -> Physical -> Voxel roundtrip error < 1e-4 mm."""
    rng = np.random.default_rng(seed=42)

    # Randomized DICOM parameters
    iop = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    origin = rng.uniform(-100.0, 100.0, size=3)
    pixel_spacing = [float(rng.uniform(0.5, 1.5)), float(rng.uniform(0.5, 1.5))]
    slice_spacing = float(rng.uniform(0.75, 2.5))

    spatial = SpatialOrientation.from_dicom_parameters(
        image_orientation_patient=iop,
        image_position_patient=origin,
        pixel_spacing=pixel_spacing,
        slice_spacing=slice_spacing
    )

    # 1000 randomized continuous voxel coordinates
    random_voxels = rng.uniform(0.0, 256.0, size=(1000, 3))

    phys = spatial.voxel_to_physical(random_voxels)
    roundtrip_voxels = spatial.physical_to_voxel(phys)

    # Max error in voxel space
    max_voxel_err = np.max(np.abs(random_voxels - roundtrip_voxels))
    assert max_voxel_err < 1e-6

    # Roundtrip physical points
    random_phys = rng.uniform(-150.0, 150.0, size=(1000, 3))
    vox = spatial.physical_to_voxel(random_phys)
    roundtrip_phys = spatial.voxel_to_physical(vox)

    max_phys_err = np.max(np.abs(random_phys - roundtrip_phys))
    assert max_phys_err < 1e-6, f"Max physical roundtrip error {max_phys_err} exceeded 1e-4 mm"


def test_rigid_transformation_distance_invariance():
    """Invariant 2: Translation and rotation preserve line segment length and pairwise distance."""
    rng = np.random.default_rng(seed=123)

    for _ in range(50):
        p1 = rng.uniform(-100.0, 100.0, size=3)
        p2 = rng.uniform(-100.0, 100.0, size=3)
        orig_seg = LineSegment3D(p1, p2)
        orig_length = orig_seg.length

        # Random 3D translation
        t = rng.uniform(-50.0, 50.0, size=3)
        p1_t = p1 + t
        p2_t = p2 + t
        t_seg = LineSegment3D(p1_t, p2_t)
        assert np.isclose(t_seg.length, orig_length, atol=1e-6)

        # Random 3D rotation (Rodrigues formula)
        axis = rng.normal(size=3)
        axis = axis / np.linalg.norm(axis)
        theta = float(rng.uniform(0.0, 2 * np.pi))

        def rotate_point(p):
            return p * np.cos(theta) + np.cross(axis, p) * np.sin(theta) + axis * np.dot(axis, p) * (1 - np.cos(theta))

        p1_r = rotate_point(p1)
        p2_r = rotate_point(p2)
        r_seg = LineSegment3D(p1_r, p2_r)
        assert np.isclose(r_seg.length, orig_length, atol=1e-5)


def test_distance_field_monotonicity_under_dilation():
    """
    Invariant 3: Expanding an obstacle (M2 >= M1) cannot increase clearance to outside points:
    For any point x outside M2, Distance(x, M2) <= Distance(x, M1).
    """
    shape = (40, 40, 40)
    iop = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    spatial = SpatialOrientation.from_dicom_parameters(
        image_orientation_patient=iop,
        image_position_patient=[0.0, 0.0, 0.0],
        pixel_spacing=[1.0, 1.0],
        slice_spacing=1.0
    )

    # Initial obstacle mask M1: small sphere in center
    i, j, k = np.indices(shape)
    dist_sq = (i - 20)**2 + (j - 20)**2 + (k - 20)**2
    mask_1 = dist_sq <= 5**2

    # Dilated obstacle mask M2: expanded sphere
    struct = ndimage.generate_binary_structure(3, 1)
    mask_2 = ndimage.binary_dilation(mask_1, structure=struct, iterations=3)

    df_1 = DistanceField(mask_1, spatial)
    df_2 = DistanceField(mask_2, spatial)

    # Sample trajectory completely outside M2
    traj = LineSegment3D(
        start_point=np.array([2.0, 2.0, 2.0]),
        end_point=np.array([2.0, 38.0, 2.0])
    )

    res_1 = df_1.evaluate_trajectory_clearance(traj, "hazard", 0.0, 0.0, 0.0)
    res_2 = df_2.evaluate_trajectory_clearance(traj, "hazard", 0.0, 0.0, 0.0)

    # Monotonicity assertion: expanding obstacle must decrease or equal clearance
    assert res_2.observed_clearance_mm <= res_1.observed_clearance_mm + 1e-5
    assert res_2.effective_clearance_mm <= res_1.effective_clearance_mm + 1e-5


def test_pareto_dominance_invariant():
    """Invariant 4: A strictly dominated candidate can never be present on the Pareto frontier."""
    c_superior = CandidateTrajectory(
        candidate_id="SUPERIOR",
        target_calyx_name="POSTERIOR_LOWER",
        entry_point_lps=np.array([20.0, 30.0, 20.0]),
        target_point_lps=np.array([20.0, 0.0, 20.0]),
        tract_length_mm=30.0,               # Shorter tract
        min_effective_clearance_mm=25.0,    # Higher clearance
        hazard_evaluations=[],
        reachable_stone_fraction=1.0,       # Complete reach
        required_scope_deflection_deg=0.0,  # Zero deflection
        access_rib_classification="SUBCOSTAL",
        is_pareto_optimal=False,
        confidence_tier="HIGH"
    )

    c_inferior = CandidateTrajectory(
        candidate_id="INFERIOR",
        target_calyx_name="POSTERIOR_LOWER",
        entry_point_lps=np.array([20.0, 50.0, 20.0]),
        target_point_lps=np.array([20.0, 0.0, 20.0]),
        tract_length_mm=50.0,               # Inferior in all aspects
        min_effective_clearance_mm=5.0,
        hazard_evaluations=[],
        reachable_stone_fraction=0.4,
        required_scope_deflection_deg=30.0,
        access_rib_classification="SUPRACOSTAL_11",
        is_pareto_optimal=False,
        confidence_tier="LOW"
    )

    frontier = extract_pareto_frontier([c_superior, c_inferior])
    optimal_ids = [c.candidate_id for c in frontier if c.is_pareto_optimal]

    assert "SUPERIOR" in optimal_ids
    assert "INFERIOR" not in optimal_ids
