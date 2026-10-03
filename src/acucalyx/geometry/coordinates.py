"""
AcuCalyx Geometry: Coordinate Systems and Mappings

Strict implementation of patient-based coordinate systems in accordance with
DICOM Part 3 (C.7.6.2.1.1).

Defines transforms between:
- Discrete Voxel Space: (row, col, slice) -> (i, j, k)
- Physical Patient Space: LPS (Left, Posterior, Superior) [mm]
- Prone Operative Space: Transformed for prone surgical positioning
- Graphic / Visualization Space: Three.js coordinates
"""

from dataclasses import dataclass
from typing import Tuple, Union, Sequence
import numpy as np


@dataclass(frozen=True)
class SpatialOrientation:
    """
    Defines the affine mapping between voxel indices (i, j, k) and
    patient physical space coordinates (x, y, z) in millimeters (LPS).
    """
    affine_matrix: np.ndarray  # 4x4 matrix
    inv_affine_matrix: np.ndarray  # 4x4 matrix
    origin: np.ndarray  # 3D vector [x, y, z]
    spacing: np.ndarray  # 3D vector [dx, dy, dz] in mm
    direction: np.ndarray  # 3x3 direction cosines matrix (columns are X, Y, Z axes)

    @property
    def affine(self) -> np.ndarray:
        return self.affine_matrix

    @classmethod
    def from_dicom_parameters(
        cls,
        image_orientation_patient: Sequence[float],
        image_position_patient: Sequence[float],
        pixel_spacing: Sequence[float],
        slice_spacing: float,
        slice_direction: Union[Sequence[float], None] = None
    ) -> "SpatialOrientation":
        """
        Builds affine transformation from DICOM metadata.
        
        Args:
            image_orientation_patient: 6 elements [Xx, Xy, Xz, Yx, Yy, Yz]
            image_position_patient: 3 elements [Sx, Sy, Sz] for slice 0
            pixel_spacing: 2 elements [delta_row, delta_col] in mm
            slice_spacing: distance between consecutive slices in mm
            slice_direction: optional unit vector for slice direction (Z = X x Y if None)
        """
        iop = np.array(image_orientation_patient, dtype=np.float64)
        if len(iop) != 6:
            raise ValueError("image_orientation_patient must have 6 values")

        x_dir = iop[0:3]
        y_dir = iop[3:6]

        # Normalize direction vectors
        x_norm = np.linalg.norm(x_dir)
        y_norm = np.linalg.norm(y_dir)
        if not np.isclose(x_norm, 1.0, atol=1e-3) or not np.isclose(y_norm, 1.0, atol=1e-3):
            raise ValueError(f"Direction cosines not unit vectors: |X|={x_norm}, |Y|={y_norm}")

        x_dir = x_dir / x_norm
        y_dir = y_dir / y_norm

        # Check orthogonality between X and Y
        ortho_dot = np.dot(x_dir, y_dir)
        if not np.isclose(ortho_dot, 0.0, atol=1e-3):
            raise ValueError(f"X and Y direction vectors are not orthogonal (dot product = {ortho_dot})")

        # Z direction is cross product X x Y unless explicitly provided
        if slice_direction is not None:
            z_dir = np.array(slice_direction, dtype=np.float64)
            z_dir = z_dir / np.linalg.norm(z_dir)
        else:
            z_dir = np.cross(x_dir, y_dir)
            z_dir = z_dir / np.linalg.norm(z_dir)

        origin = np.array(image_position_patient, dtype=np.float64)
        delta_row, delta_col = float(pixel_spacing[0]), float(pixel_spacing[1])
        delta_slice = float(slice_spacing)

        # Build 3x3 direction matrix: columns are unit vectors
        direction_matrix = np.column_stack([x_dir, y_dir, z_dir])

        # Voxel order: [row, col, slice] = [i, j, k]
        # In DICOM, col step j corresponds to X direction (delta_col)
        # Row step i corresponds to Y direction (delta_row)
        # Slice step k corresponds to Z direction (delta_slice)
        affine = np.eye(4, dtype=np.float64)
        affine[0:3, 0] = y_dir * delta_row   # index 0: row (i)
        affine[0:3, 1] = x_dir * delta_col   # index 1: col (j)
        affine[0:3, 2] = z_dir * delta_slice # index 2: slice (k)
        affine[0:3, 3] = origin

        inv_affine = np.linalg.inv(affine)

        spacing = np.array([delta_row, delta_col, delta_slice], dtype=np.float64)

        return cls(
            affine_matrix=affine,
            inv_affine_matrix=inv_affine,
            origin=origin,
            spacing=spacing,
            direction=direction_matrix
        )

    def voxel_to_physical(self, ijk: Union[Sequence[float], np.ndarray]) -> np.ndarray:
        """
        Converts voxel coordinates (row, col, slice) to physical LPS coordinates (x, y, z) in mm.
        Supports single 3D point or (N, 3) array.
        """
        coords = np.asarray(ijk, dtype=np.float64)
        is_single = coords.ndim == 1
        if is_single:
            coords = coords.reshape(1, 3)

        # Homogeneous coordinates
        n_points = coords.shape[0]
        homog = np.ones((n_points, 4), dtype=np.float64)
        homog[:, 0:3] = coords

        phys = (self.affine_matrix @ homog.T).T[:, 0:3]
        return phys[0] if is_single else phys

    def physical_to_voxel(self, xyz: Union[Sequence[float], np.ndarray]) -> np.ndarray:
        """
        Converts physical LPS coordinates (x, y, z) in mm to continuous voxel indices (row, col, slice).
        Supports single 3D point or (N, 3) array.
        """
        coords = np.asarray(xyz, dtype=np.float64)
        is_single = coords.ndim == 1
        if is_single:
            coords = coords.reshape(1, 3)

        n_points = coords.shape[0]
        homog = np.ones((n_points, 4), dtype=np.float64)
        homog[:, 0:3] = coords

        voxels = (self.inv_affine_matrix @ homog.T).T[:, 0:3]
        return voxels[0] if is_single else voxels
