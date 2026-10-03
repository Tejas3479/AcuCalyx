"""
AcuCalyx Geometry: 3D Surface Synthesis, Smoothing, and Mesh Export Engine

Implements Step 13 of AcuCalyx v2.1:
- Marching cubes polygonization using exact physical voxel spacing (dx, dy, dz)
- Volume-preserving Laplacian smoothing (for visual presentation only)
- Face decimation for smooth 60 FPS Three.js WebGL browser rendering
- GLB (glTF 2.0 Binary) export with distinct anatomical PBR materials
- STL binary export for surgical rehearsal 3D printing
- Mandatory Metadata Notice: Meshes are for display/rehearsal only and are non-sterile
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
import numpy as np
from skimage.measure import marching_cubes
import trimesh

from acucalyx.geometry.coordinates import SpatialOrientation


@dataclass(frozen=True)
class MeshExportResult:
    """Metadata describing generated 3D surface mesh."""
    organ_name: str
    vertex_count: int
    face_count: int
    surface_area_mm2: float
    volume_mm3: float
    file_path: Path
    is_watertight: bool
    intended_use_disclaimer: str = "For visualization and surgical rehearsal only. Non-sterile. Not for geometric measurements."


# Standard surgical visualization color palette (RGBA [0.0 - 1.0])
ANATOMICAL_COLOR_PALETTE = {
    "kidney": [0.85, 0.25, 0.25, 0.40],      # Translucent renal parenchyma
    "stones": [1.00, 0.85, 0.00, 1.00],      # Bright opaque yellow
    "ribs": [0.95, 0.95, 0.90, 0.90],        # Ivory bone
    "colon": [0.90, 0.50, 0.15, 0.45],       # Orange/brown semi-translucent
    "small_bowel": [0.80, 0.45, 0.25, 0.40], # Tan
    "liver": [0.60, 0.20, 0.20, 0.40],       # Dark red
    "spleen": [0.50, 0.15, 0.40, 0.40],      # Purple
    "lung": [0.40, 0.70, 0.90, 0.30],        # Translucent light blue
    "calyx": [0.20, 0.60, 1.00, 0.70]        # Blue collecting system
}


def mask_to_surface_mesh(
    binary_mask: np.ndarray,
    spatial_orientation: SpatialOrientation,
    target_faces: Optional[int] = 20000,
    smoothing_iterations: int = 5
) -> trimesh.Trimesh:
    """
    Extracts an isotropic 3D surface mesh from a binary mask in continuous physical space (mm).
    
    Args:
        binary_mask: 3D boolean/uint8 array [rows, cols, slices]
        spatial_orientation: SpatialOrientation instance
        target_faces: Optional target face count for decimation
        smoothing_iterations: Number of Laplacian smoothing passes
    """
    if not np.any(binary_mask):
        # Return empty mesh
        return trimesh.Trimesh()

    spacing = spatial_orientation.spacing  # [row_sp, col_sp, slice_sp] in mm

    # Step 1: Marching Cubes in voxel-scaled grid
    # step_size=1 ensures full resolution extraction
    verts, faces, normals, _ = marching_cubes(
        binary_mask > 0,
        level=0.5,
        spacing=spacing,
        method='lewiner'
    )

    # Step 2: Transform vertices from voxel space to physical LPS space
    # verts is array of [row*dy, col*dx, slice*dz]
    # We map continuous voxel indices back through affine matrix
    ijk = verts / spacing  # back to continuous (i, j, k)
    phys_vertices = spatial_orientation.voxel_to_physical(ijk)

    # Step 3: Construct Trimesh object
    mesh = trimesh.Trimesh(
        vertices=phys_vertices,
        faces=faces,
        vertex_normals=normals,
        process=True
    )

    # Step 4: Volume-preserving Laplacian smoothing (for visual presentation)
    if smoothing_iterations > 0 and len(mesh.faces) > 0:
        trimesh.smoothing.filter_laplacian(mesh, iterations=smoothing_iterations)

    # Step 5: Decimation if face count exceeds target
    if target_faces is not None and len(mesh.faces) > target_faces:
        try:
            # Fast quadratic decimation
            mesh = mesh.simplify_quadric_decimation(target_faces)
        except Exception:
            pass  # Fall back to unsimplified mesh if simplification fails

    return mesh


def export_mesh_glb(
    mesh: trimesh.Trimesh,
    output_path: Path,
    organ_name: str = "kidney"
) -> MeshExportResult:
    """
    Exports mesh to glTF 2.0 Binary (.glb) with embedded anatomical PBR material.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Apply anatomical material color
    color_rgba = ANATOMICAL_COLOR_PALETTE.get(organ_name.lower(), [0.7, 0.7, 0.7, 1.0])
    color_255 = [int(round(c * 255)) for c in color_rgba]
    
    mesh.visual.vertex_colors = np.full((len(mesh.vertices), 4), color_255, dtype=np.uint8)

    scene = trimesh.Scene(mesh)
    glb_bytes = trimesh.exchange.gltf.export_glb(scene)
    
    with open(output_path, "wb") as f:
        f.write(glb_bytes)

    surf_area = float(mesh.area) if hasattr(mesh, "area") else 0.0
    vol = float(mesh.volume) if mesh.is_watertight else 0.0

    return MeshExportResult(
        organ_name=organ_name,
        vertex_count=len(mesh.vertices),
        face_count=len(mesh.faces),
        surface_area_mm2=surf_area,
        volume_mm3=vol,
        file_path=output_path,
        is_watertight=bool(mesh.is_watertight)
    )


def export_mesh_stl(
    mesh: trimesh.Trimesh,
    output_path: Path,
    organ_name: str = "kidney"
) -> MeshExportResult:
    """
    Exports mesh to watertight binary STL for 3D printing and physical surgical rehearsal.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mesh.export(str(output_path), file_type="stl")

    surf_area = float(mesh.area) if hasattr(mesh, "area") else 0.0
    vol = float(mesh.volume) if mesh.is_watertight else 0.0

    return MeshExportResult(
        organ_name=organ_name,
        vertex_count=len(mesh.vertices),
        face_count=len(mesh.faces),
        surface_area_mm2=surf_area,
        volume_mm3=vol,
        file_path=output_path,
        is_watertight=bool(mesh.is_watertight)
    )
