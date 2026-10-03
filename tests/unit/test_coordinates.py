"""
Unit tests for AcuCalyx coordinate transforms and spatial orientation.
"""

import numpy as np
import pytest

from acucalyx.geometry.coordinates import SpatialOrientation
from acucalyx.geometry.transforms import (
    Ray3D, LineSegment3D, create_supine_to_prone_matrix, transform_points, angle_between_vectors
)


def test_dicom_affine_construction():
    """Verify affine matrix maps (0,0,0) to origin and advances correctly along axes."""
    iop = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]  # Axial LPS: row is +X, col is +Y
    origin = [10.0, 20.0, 30.0]
    pixel_spacing = [0.5, 0.5]  # row, col
    slice_spacing = 1.0

    spatial = SpatialOrientation.from_dicom_parameters(
        image_orientation_patient=iop,
        image_position_patient=origin,
        pixel_spacing=pixel_spacing,
        slice_spacing=slice_spacing
    )

    # Voxel (0, 0, 0) must be physical origin
    phys_0 = spatial.voxel_to_physical([0, 0, 0])
    np.testing.assert_allclose(phys_0, origin, atol=1e-5)

    # Invert back
    vox_0 = spatial.physical_to_voxel(origin)
    np.testing.assert_allclose(vox_0, [0, 0, 0], atol=1e-5)

    # Advance 10 slices along Z
    phys_k = spatial.voxel_to_physical([0, 0, 10])
    np.testing.assert_allclose(phys_k, [10.0, 20.0, 40.0], atol=1e-5)


def test_supine_to_prone_transformation():
    """Verify 180-degree yaw rotation inverts X and Y while preserving Z."""
    mat = create_supine_to_prone_matrix()
    pt_supine = np.array([15.0, 25.0, 50.0])
    pt_prone = transform_points(pt_supine, mat)

    np.testing.assert_allclose(pt_prone, [-15.0, -25.0, 50.0], atol=1e-5)


def test_line_segment_sampling():
    """Verify line segment samples uniformly along its vector."""
    start = np.array([0.0, 0.0, 0.0])
    end = np.array([10.0, 0.0, 0.0])
    seg = LineSegment3D(start_point=start, end_point=end)

    assert np.isclose(seg.length, 10.0)
    samples = seg.sample_points(step_mm=2.0)
    assert len(samples) == 6  # 0, 2, 4, 6, 8, 10
    np.testing.assert_allclose(samples[0], start)
    np.testing.assert_allclose(samples[-1], end)


def test_angle_between_vectors():
    """Verify trigonometric angle computation."""
    v1 = np.array([1.0, 0.0, 0.0])
    v2 = np.array([0.0, 1.0, 0.0])
    assert np.isclose(angle_between_vectors(v1, v2), 90.0)

    v3 = np.array([-1.0, 0.0, 0.0])
    assert np.isclose(angle_between_vectors(v1, v3), 180.0)
