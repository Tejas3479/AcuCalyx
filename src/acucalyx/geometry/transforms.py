"""
AcuCalyx Geometry: Spatial Transformations and Vector Math

Implements:
- Supine to Prone patient orientation transformation matrices
- Ray and Line segment geometric primitives
- Vector projections, angles, and spatial alignment utilities
"""

from dataclasses import dataclass
from typing import Tuple, Union
import numpy as np


@dataclass(frozen=True)
class Ray3D:
    """
    Parametric 3D ray: P(t) = origin + t * direction, t >= 0
    where direction is a normalized unit vector.
    """
    origin: np.ndarray  # [x, y, z] in mm
    direction: np.ndarray  # [dx, dy, dz] normalized unit vector

    def __post_init__(self):
        norm = np.linalg.norm(self.direction)
        if np.isclose(norm, 0.0):
            raise ValueError("Ray direction cannot be a zero vector")
        if not np.isclose(norm, 1.0, atol=1e-5):
            # Enforce unit vector
            object.__setattr__(self, "direction", self.direction / norm)

    def point_at(self, t: float) -> np.ndarray:
        """Returns the 3D point at parameter distance t (in mm)."""
        return self.origin + t * self.direction


@dataclass(frozen=True)
class LineSegment3D:
    """
    Finite 3D line segment between start_point and end_point.
    Useful for representing needle shafts and trajectory tracts.
    """
    start_point: np.ndarray  # [x, y, z] in mm (e.g. skin entry point)
    end_point: np.ndarray    # [x, y, z] in mm (e.g. calyx target)

    @property
    def vector(self) -> np.ndarray:
        """Vector from start to end."""
        return self.end_point - self.start_point

    @property
    def length(self) -> float:
        """Length of line segment in mm."""
        return float(np.linalg.norm(self.vector))

    @property
    def unit_direction(self) -> np.ndarray:
        """Normalized unit direction vector."""
        l = self.length
        if np.isclose(l, 0.0):
            raise ValueError("Zero-length line segment has undefined direction")
        return self.vector / l

    def sample_points(self, step_mm: float = 1.0) -> np.ndarray:
        """
        Samples equidistant 3D points along the segment from start to end.
        Returns (N, 3) array.
        """
        l = self.length
        if l < 1e-6:
            return np.array([self.start_point], dtype=np.float64)
        n_samples = max(2, int(np.ceil(l / step_mm)) + 1)
        t_values = np.linspace(0.0, 1.0, n_samples)
        return self.start_point + t_values[:, np.newaxis] * self.vector


def create_supine_to_prone_matrix() -> np.ndarray:
    """
    Returns a 4x4 affine matrix representing a 180-degree yaw rotation around
    the patient longitudinal cranial-caudal axis (Z in LPS space).
    
    LPS space:
    +X: Left
    +Y: Posterior
    +Z: Superior (Cranial)
    
    When patient rotates 180 degrees from Supine to Prone:
    - Left becomes Right (X -> -X)
    - Posterior becomes Anterior (Y -> -Y)
    - Superior remains Superior (Z -> Z)
    
    NOTE: Real clinical prone positioning introduces non-rigid organ shifts (10-30mm),
    so this rigid matrix is used for nominal coordinate alignment and must be
    supplemented by uncertainty bounds or prone CT verification.
    """
    mat = np.eye(4, dtype=np.float64)
    mat[0, 0] = -1.0
    mat[1, 1] = -1.0
    mat[2, 2] = 1.0
    return mat


def transform_points(points: np.ndarray, transform_matrix: np.ndarray) -> np.ndarray:
    """
    Applies a 4x4 affine matrix to an (N, 3) array or single 3D vector.
    """
    pts = np.asarray(points, dtype=np.float64)
    is_single = pts.ndim == 1
    if is_single:
        pts = pts.reshape(1, 3)

    n_pts = pts.shape[0]
    homog = np.ones((n_pts, 4), dtype=np.float64)
    homog[:, 0:3] = pts

    transformed = (transform_matrix @ homog.T).T[:, 0:3]
    return transformed[0] if is_single else transformed


def angle_between_vectors(v1: np.ndarray, v2: np.ndarray) -> float:
    """
    Returns angle between two 3D vectors in degrees [0, 180].
    """
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    if np.isclose(norm1, 0.0) or np.isclose(norm2, 0.0):
        raise ValueError("Cannot calculate angle with zero-length vector")

    cos_theta = np.clip(np.dot(v1, v2) / (norm1 * norm2), -1.0, 1.0)
    return float(np.degrees(np.arccos(cos_theta)))
