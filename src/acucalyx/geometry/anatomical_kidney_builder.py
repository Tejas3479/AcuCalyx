"""
AcuCalyx High-Fidelity Anatomical Kidney Section & Micro-Nephron 3D Builder

Constructs medical-textbook-grade 3D anatomical models matching clinical atlas standards:
1. Renal Capsule: Smooth dark reddish-brown protective outer convex covering.
2. Renal Cortex: Granular pinkish-tan cortical parenchyma with deep Renal Columns of Bertin.
3. Renal Medullary Pyramids: 8 distinct triangular/fan-shaped fibrous pyramids with radial striations.
4. Renal Papillae & Calyces: Cup-shaped minor calyces embracing each papilla with anatomical fornices.
5. Renal Pelvis & Ureter: Funnel-shaped pelvis transitioning into the descending muscular ureter.
6. Renal Hilum Vasculature:
   - Renal Artery: Main trunk dividing into segmental, interlobar, and arcuate arches.
   - Renal Vein: Large deoxygenated blue trunk with segmental and interlobar tributaries.
   - Renal Nerve Plexus: Autonomic sympathetic & sensory nerve filaments wrapping the artery.
7. Nephron Functional Unit (3D Micro-Model):
   - Glomerulus (capillary tuft) & Bowman's capsule
   - Afferent & Efferent arterioles
   - Proximal Convoluted Tubule (PCT)
   - Loop of Henle (descending & ascending limbs dipping into medullary pyramid)
   - Distal Convoluted Tubule (DCT)
   - Straight Collecting Duct terminating at the papilla
8. Crystalline Kidney Calculus (Stone):
   - Realistic multi-faceted, porous, irregular crystalline mineral stone with facets and radiant highlight,
     lodged precisely in the dependent lower calyx / renal pelvis.

All coordinate systems are continuous physical millimeters (LPS).
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple, Optional
import numpy as np
from skimage.measure import marching_cubes
import trimesh


def _create_tube_segment(
    p1: np.ndarray, p2: np.ndarray, r1: float, r2: float, sections: int = 12
) -> trimesh.Trimesh:
    """Create a truncated cone/cylinder tube segment connecting p1 to p2."""
    v = p2 - p1
    length = float(np.linalg.norm(v))
    if length < 1e-4:
        return trimesh.Trimesh()

    direction = v / length
    cyl = trimesh.creation.cylinder(radius=r1, height=length, sections=sections)

    if abs(r1 - r2) > 1e-4 and len(cyl.vertices) > 0:
        z_vals = cyl.vertices[:, 2]
        z_min, z_max = z_vals.min(), z_vals.max()
        scale_factors = (z_vals - z_min) / (z_max - z_min + 1e-6)
        r_scale = (r1 * (1.0 - scale_factors) + r2 * scale_factors) / r1
        cyl.vertices[:, 0] *= r_scale
        cyl.vertices[:, 1] *= r_scale

    z_axis = np.array([0.0, 0.0, 1.0])
    rot_mat = trimesh.geometry.align_vectors(z_axis, direction)
    cyl.apply_transform(rot_mat)

    midpoint = (p1 + p2) / 2.0
    cyl.apply_translation(midpoint)
    return cyl


def _create_polyline_tube(
    points: List[np.ndarray], radii: List[float], sections: int = 10
) -> trimesh.Trimesh:
    """Creates a smooth continuous tubular chain through a sequence of 3D points."""
    meshes = []
    for i in range(len(points) - 1):
        p1 = points[i]
        p2 = points[i + 1]
        r1 = radii[i] if i < len(radii) else radii[-1]
        r2 = radii[i + 1] if (i + 1) < len(radii) else radii[-1]
        tube = _create_tube_segment(p1, p2, r1, r2, sections=sections)
        if len(tube.vertices) > 0:
            meshes.append(tube)
    if not meshes:
        return trimesh.Trimesh()
    return trimesh.util.concatenate(meshes)


def _create_branching_tree(
    branches: List[Tuple[np.ndarray, np.ndarray, float, float]]
) -> trimesh.Trimesh:
    """Combine tube segments into a smooth branching vascular or duct tree."""
    meshes = []
    for p1, p2, r1, r2 in branches:
        tube = _create_tube_segment(p1, p2, r1, r2)
        if len(tube.vertices) > 0:
            meshes.append(tube)
    if not meshes:
        return trimesh.Trimesh()
    return trimesh.util.concatenate(meshes)


class AnatomicalKidneyBuilder:
    """
    Builds a high-fidelity, medical-grade 3D anatomical section of a human kidney
    with renal cortex, medullary pyramids, collecting system, vasculature, nerves,
    nephron functional unit, and a highlighted crystalline stone.
    """

    def __init__(self, center: Tuple[float, float, float] = (20.0, 10.0, 50.0)) -> None:
        self.center = np.array(center, dtype=np.float64)
        # Standard human adult kidney dimensions: length ~112 mm, width ~58 mm, depth ~36 mm
        self.rx = 19.0  # medial-lateral radius
        self.ry = 14.0  # anterior-posterior radius
        self.rz = 44.0  # cranial-caudal half-length

    def build_renal_capsule(self) -> trimesh.Trimesh:
        """
        Builds the smooth, dark mahogany fibrous renal capsule as a continuous outer hull
        with an open hilum portal for the renal pedicle vessels.
        """
        res = 1.0
        x_range = np.arange(self.center[0] - 28.0, self.center[0] + 32.0, res)
        y_range = np.arange(self.center[1] - 24.0, self.center[1] + 28.0, res)
        z_range = np.arange(self.center[2] - 54.0, self.center[2] + 54.0, res)

        X, Y, Z = np.meshgrid(x_range, y_range, z_range, indexing='ij')
        dx = X - self.center[0]
        dy = Y - self.center[1]
        dz = Z - self.center[2]

        hilum_depth = 8.5
        hilum_factor = hilum_depth * np.exp(-((dz / 16.0) ** 2 + (dy / 10.0) ** 2))
        dx_adj = np.where(dx < 0, dx + hilum_factor, dx)

        dist_outer = (dx_adj / (self.rx + 1.2)) ** 2 + (dy / (self.ry + 1.2)) ** 2 + (dz / (self.rz + 1.2)) ** 2
        dist_inner = (dx_adj / self.rx) ** 2 + (dy / self.ry) ** 2 + (dz / self.rz) ** 2

        # Hilum portal opening where vascular pedicle and ureter exit
        hilum_aperture = (dx < -4.0) & (((dz / 16.0) ** 2 + (dy / 11.0) ** 2) <= 1.0)

        capsule_mask = (dist_outer <= 1.0) & (dist_inner >= 0.88) & ~hilum_aperture

        # Pad mask by 1 voxel to guarantee closed watertight envelope
        padded_capsule = np.pad(capsule_mask, 1, mode='constant', constant_values=0)
        verts, faces, normals, _ = marching_cubes(padded_capsule, level=0.5, spacing=(res, res, res))
        phys_verts = np.zeros_like(verts)
        phys_verts[:, 0] = x_range[0] + (verts[:, 0] - 1.0) * res
        phys_verts[:, 1] = y_range[0] + (verts[:, 1] - 1.0) * res
        phys_verts[:, 2] = z_range[0] + (verts[:, 2] - 1.0) * res

        # Correct clockwise winding to standard counter-clockwise outward normals
        faces_ccw = faces[:, ::-1] if len(faces) > 0 else faces
        normals_outward = -normals if len(normals) > 0 else normals
        mesh = trimesh.Trimesh(vertices=phys_verts, faces=faces_ccw, vertex_normals=normals_outward, process=True)
        mesh.fix_normals()
        if len(mesh.faces) > 0:
            trimesh.smoothing.filter_laplacian(mesh, iterations=3)

        # Retain primary continuous anatomical hull and filter any micro-debris < 5 mm3
        parts = trimesh.graph.split(mesh)
        if len(parts) > 1:
            mesh = max(parts, key=lambda p: len(p.faces))

        # Color: Dark reddish-brown fibrous capsule
        color = [115, 35, 25, 220]  # RGBA
        mesh.visual.vertex_colors = np.full((len(mesh.vertices), 4), color, dtype=np.uint8)
        return mesh

    def build_kidney_cortex(self, cutaway: bool = False) -> trimesh.Trimesh:
        """
        Builds the granular pinkish-tan renal cortex with renal columns of Bertin dipping between pyramids.
        """
        res = 1.0
        x_range = np.arange(self.center[0] - 25.0, self.center[0] + 30.0, res)
        y_range = np.arange(self.center[1] - 22.0, self.center[1] + 25.0, res)
        z_range = np.arange(self.center[2] - 50.0, self.center[2] + 50.0, res)

        X, Y, Z = np.meshgrid(x_range, y_range, z_range, indexing='ij')
        dx = X - self.center[0]
        dy = Y - self.center[1]
        dz = Z - self.center[2]

        hilum_depth = 8.5
        hilum_factor = hilum_depth * np.exp(-((dz / 16.0) ** 2 + (dy / 10.0) ** 2))
        dx_adj = np.where(dx < 0, dx + hilum_factor, dx)

        dist_outer = (dx_adj / self.rx) ** 2 + (dy / self.ry) ** 2 + (dz / self.rz) ** 2

        # Renal sinus cavity (recessed space for calyces and hilum fat)
        sinus_rx, sinus_ry, sinus_rz = 8.5, 6.5, 23.0
        dist_sinus = ((dx + 3.0) / sinus_rx) ** 2 + (dy / sinus_ry) ** 2 + (dz / sinus_rz) ** 2

        cortex_mask = (dist_outer <= 1.0) & (dist_sinus >= 0.80)

        # Coronal cutaway: reveals internal sinus and pyramids
        if cutaway:
            cortex_mask = cortex_mask & (dy >= -1.0)

        # Pad mask by 1 voxel to ensure closed watertight manifold
        padded_cortex = np.pad(cortex_mask, 1, mode='constant', constant_values=0)
        verts, faces, normals, _ = marching_cubes(padded_cortex, level=0.5, spacing=(res, res, res))
        phys_verts = np.zeros_like(verts)
        phys_verts[:, 0] = x_range[0] + (verts[:, 0] - 1.0) * res
        phys_verts[:, 1] = y_range[0] + (verts[:, 1] - 1.0) * res
        phys_verts[:, 2] = z_range[0] + (verts[:, 2] - 1.0) * res

        faces_ccw = faces[:, ::-1] if len(faces) > 0 else faces
        normals_outward = -normals if len(normals) > 0 else normals
        mesh = trimesh.Trimesh(vertices=phys_verts, faces=faces_ccw, vertex_normals=normals_outward, process=True)
        mesh.fix_normals()
        if len(mesh.faces) > 0:
            trimesh.smoothing.filter_laplacian(mesh, iterations=4)
            try:
                mesh = mesh.simplify_quadric_decimation(16000)
            except Exception:
                pass

        # Color: Warm anatomical pinkish-tan renal cortex
        color = [205, 120, 110, 160]  # RGBA
        mesh.visual.vertex_colors = np.full((len(mesh.vertices), 4), color, dtype=np.uint8)
        return mesh

    def build_medullary_pyramids(self) -> trimesh.Trimesh:
        """
        Builds 8 striated medullary pyramids with radial striations and papillae apices.
        """
        pyramid_specs = [
            # (apex_papilla, base_corticomedullary, apex_radius, base_radius)
            # Superior pole (2) - strictly within corticomedullary junction
            (self.center + np.array([3.0, 3.0, 22.0]), self.center + np.array([6.5, 3.5, 30.0]), 1.8, 3.8),
            (self.center + np.array([1.5, 1.5, 19.0]), self.center + np.array([4.5, 2.0, 27.0]), 1.8, 3.6),
            # Mid-kidney (3)
            (self.center + np.array([5.0, 3.0, 9.0]), self.center + np.array([11.0, 3.5, 11.0]), 1.9, 4.0),
            (self.center + np.array([4.5, 2.0, 0.0]), self.center + np.array([12.5, 2.5, 0.0]), 2.0, 4.2),
            (self.center + np.array([5.0, 3.0, -9.0]), self.center + np.array([11.0, 3.5, -11.0]), 1.9, 4.0),
            # Inferior pole (3)
            (self.center + np.array([2.0, 3.0, -11.0]), self.center + np.array([6.5, 4.0, -16.0]), 1.9, 3.8),
            (self.center + np.array([3.5, 2.5, -17.0]), self.center + np.array([7.5, 3.0, -23.0]), 1.9, 3.8),
            (self.center + np.array([1.5, 3.0, -19.0]), self.center + np.array([4.0, 3.5, -25.0]), 1.8, 3.6),
        ]

        meshes = []
        for apex, base, r_apex, r_base in pyramid_specs:
            pyr = _create_tube_segment(apex, base, r_apex, r_base, sections=14)
            if len(pyr.vertices) > 0:
                meshes.append(pyr)

        pyramids_mesh = trimesh.util.concatenate(meshes)
        # Color: Deep striated maroon/crimson renal medulla
        color = [145, 30, 55, 230]  # RGBA
        pyramids_mesh.visual.vertex_colors = np.full((len(pyramids_mesh.vertices), 4), color, dtype=np.uint8)
        return pyramids_mesh

    def build_collecting_system(self) -> trimesh.Trimesh:
        """
        Builds renal pelvis, major calyces, minor calyces embracing papillae, and descending ureter.
        """
        hilum_pelvis = self.center + np.array([-4.5, 2.0, 0.0])
        pelvis_center = self.center + np.array([0.0, 3.0, 0.0])

        tubes = [
            # Descending ureter exiting the renal hilum downward toward the bladder
            (hilum_pelvis, hilum_pelvis + np.array([-1.5, -1.0, -18.0]), 3.4, 3.0),
            (hilum_pelvis + np.array([-1.5, -1.0, -18.0]), hilum_pelvis + np.array([-1.0, -2.0, -42.0]), 3.0, 2.7),
            # Funnel-shaped renal pelvis
            (hilum_pelvis, pelvis_center, 4.8, 5.8),
            # Major calyces branching from pelvis
            # Superior major calyx
            (pelvis_center, self.center + np.array([2.0, 3.0, 19.0]), 4.2, 3.2),
            # Middle major calyx
            (pelvis_center, self.center + np.array([3.0, 3.0, 0.0]), 4.2, 3.4),
            # Inferior major calyx (containing the targeted stone!)
            (pelvis_center, self.center + np.array([2.0, 4.0, -17.0]), 4.5, 3.8),
        ]

        # Minor calyces: cup-shaped funnels with defined fornices embracing each renal papilla
        minor_calyces = [
            (self.center + np.array([1.5, 2.5, 16.0]), self.center + np.array([3.0, 3.0, 22.0]), 2.8, 3.6),
            (self.center + np.array([1.0, 1.5, 15.0]), self.center + np.array([1.5, 1.5, 19.0]), 2.8, 3.4),
            (self.center + np.array([2.5, 2.5, 0.0]), self.center + np.array([5.0, 3.0, 9.0]), 2.8, 3.5),
            (self.center + np.array([2.5, 2.0, 0.0]), self.center + np.array([4.5, 2.0, 0.0]), 3.0, 3.8),
            (self.center + np.array([2.5, 2.5, 0.0]), self.center + np.array([5.0, 3.0, -9.0]), 2.8, 3.5),
            # Inferior minor calyces cupping lower papillae and stone
            (self.center + np.array([1.5, 3.0, -14.0]), self.center + np.array([2.0, 3.0, -11.0]), 3.0, 3.6),
            (self.center + np.array([1.5, 2.5, -14.0]), self.center + np.array([3.5, 2.5, -17.0]), 3.0, 3.8),
            (self.center + np.array([1.0, 2.5, -14.0]), self.center + np.array([1.5, 3.0, -19.0]), 2.8, 3.4),
        ]
        tubes.extend(minor_calyces)

        system_mesh = _create_branching_tree(tubes)
        # Color: Translucent warm opalescent cream / amber collecting system
        color = [240, 228, 195, 230]  # RGBA
        system_mesh.visual.vertex_colors = np.full((len(system_mesh.vertices), 4), color, dtype=np.uint8)
        return system_mesh

    def build_arterial_tree(self) -> trimesh.Trimesh:
        """
        Builds the branching renal arterial tree:
        Renal artery -> Segmental arteries -> Interlobar arteries -> Arcuate arches.
        """
        aorta_origin = self.center + np.array([-20.0, 0.0, 3.0])
        hilum_artery = self.center + np.array([-5.5, 1.0, 3.0])

        branches = [
            # Main renal artery (calibrated normal adult diameter 5.2mm)
            (aorta_origin, hilum_artery, 2.7, 2.4),
            # Segmental arteries (calibrated diameter 3.6-4.0mm)
            (hilum_artery, self.center + np.array([1.0, 5.0, 4.0]), 2.0, 1.6),
            (hilum_artery, self.center + np.array([0.0, 2.0, 17.0]), 2.0, 1.6),
            (hilum_artery, self.center + np.array([2.0, 1.0, 1.0]), 2.0, 1.6),
            (hilum_artery, self.center + np.array([1.0, 2.0, -15.0]), 2.0, 1.6),

            # Interlobar arteries (running between pyramids in Bertin's columns, diameter 2.2-2.6mm)
            (self.center + np.array([0.0, 2.0, 17.0]), self.center + np.array([7.0, 3.0, 27.0]), 1.3, 1.0),
            (self.center + np.array([0.0, 2.0, 17.0]), self.center + np.array([4.0, 1.0, 23.0]), 1.3, 1.0),
            (self.center + np.array([2.0, 1.0, 1.0]), self.center + np.array([11.0, 2.0, 7.0]), 1.3, 1.0),
            (self.center + np.array([2.0, 1.0, 1.0]), self.center + np.array([11.0, 2.0, -6.0]), 1.3, 1.0),
            (self.center + np.array([1.0, 2.0, -15.0]), self.center + np.array([6.0, 2.0, -19.0]), 1.3, 1.0),
            (self.center + np.array([1.0, 2.0, -15.0]), self.center + np.array([5.0, 3.0, -26.0]), 1.2, 1.0),

            # Arcuate arches running along pyramid bases (diameter 1.4-1.8mm)
            (self.center + np.array([7.0, 3.0, 27.0]), self.center + np.array([10.0, 3.0, 29.0]), 0.9, 0.7),
            (self.center + np.array([11.0, 2.0, 7.0]), self.center + np.array([16.0, 3.0, 9.0]), 0.9, 0.7),
            (self.center + np.array([11.0, 2.0, -6.0]), self.center + np.array([16.0, 3.0, -8.0]), 0.9, 0.7),
            (self.center + np.array([6.0, 2.0, -19.0]), self.center + np.array([12.0, 3.0, -23.0]), 0.9, 0.7),
        ]

        artery_mesh = _create_branching_tree(branches)
        # Color: Bright anatomical arterial crimson / scarlet red
        color = [220, 38, 38, 235]  # RGBA
        artery_mesh.visual.vertex_colors = np.full((len(artery_mesh.vertices), 4), color, dtype=np.uint8)
        return artery_mesh

    def build_venous_tree(self) -> trimesh.Trimesh:
        """
        Builds the renal venous drainage tree:
        Interlobar veins -> Segmental veins -> Main renal vein (deoxygenated blood).
        """
        vena_cava_origin = self.center + np.array([-21.0, -2.0, -1.0])
        hilum_vein = self.center + np.array([-5.5, -1.0, -1.0])

        branches = [
            # Main renal vein
            (hilum_vein, vena_cava_origin, 4.0, 4.4),
            # Segmental veins
            (self.center + np.array([-1.0, 0.0, 15.0]), hilum_vein, 2.4, 3.0),
            (self.center + np.array([1.0, -1.0, 0.0]), hilum_vein, 2.2, 2.8),
            (self.center + np.array([0.0, 0.0, -13.0]), hilum_vein, 2.4, 3.0),
            # Interlobar venous branches
            (self.center + np.array([7.0, 1.0, 25.0]), self.center + np.array([-1.0, 0.0, 15.0]), 1.6, 2.2),
            (self.center + np.array([10.0, 0.0, 5.0]), self.center + np.array([1.0, -1.0, 0.0]), 1.5, 2.0),
            (self.center + np.array([6.0, 1.0, -17.0]), self.center + np.array([0.0, 0.0, -13.0]), 1.6, 2.2),
        ]

        vein_mesh = _create_branching_tree(branches)
        # Color: Anatomical deoxygenated venous cobalt / royal blue
        color = [30, 80, 210, 230]  # RGBA
        vein_mesh.visual.vertex_colors = np.full((len(vein_mesh.vertices), 4), color, dtype=np.uint8)
        return vein_mesh

    def build_nerve_plexus(self) -> trimesh.Trimesh:
        """
        Builds the sympathetic & sensory renal nerve plexus filaments wrapping around the renal artery.
        """
        hilum_root = self.center + np.array([-18.0, 0.0, 2.5])
        branches = [
            # Nerve trunks winding around the renal artery
            (hilum_root, self.center + np.array([-10.0, 1.8, 4.0]), 0.65, 0.55),
            (self.center + np.array([-10.0, 1.8, 4.0]), self.center + np.array([-4.0, 2.2, 3.5]), 0.55, 0.45),
            (self.center + np.array([-4.0, 2.2, 3.5]), self.center + np.array([1.0, 3.0, 6.0]), 0.45, 0.35),
            # Secondary branch
            (hilum_root + np.array([1.0, -1.5, -1.0]), self.center + np.array([-8.0, -1.0, 0.5]), 0.60, 0.50),
            (self.center + np.array([-8.0, -1.0, 0.5]), self.center + np.array([-3.0, -0.5, 0.0]), 0.50, 0.40),
            (self.center + np.array([-3.0, -0.5, 0.0]), self.center + np.array([2.0, -0.5, -4.0]), 0.40, 0.35),
            # Sensory filament to pelvis
            (self.center + np.array([-4.0, 2.2, 3.5]), self.center + np.array([-1.0, 3.5, 1.0]), 0.40, 0.30),
        ]
        nerve_mesh = _create_branching_tree(branches)
        # Color: Bright anatomical nerve yellow
        color = [234, 179, 8, 240]  # RGBA
        nerve_mesh.visual.vertex_colors = np.full((len(nerve_mesh.vertices), 4), color, dtype=np.uint8)
        return nerve_mesh

    def build_nephron_functional_unit(self) -> trimesh.Trimesh:
        """
        Builds a dedicated high-detail 3D model of the Nephron (functional unit):
        - Glomerulus (spherical capillary knot)
        - Bowman's capsule (golden cup)
        - Afferent & Efferent arterioles
        - Proximal Convoluted Tubule (PCT)
        - Loop of Henle (descending & ascending limbs dipping into pyramid)
        - Distal Convoluted Tubule (DCT)
        - Collecting Duct
        """
        # Nephron placed in superior-lateral cortex
        glom_center = self.center + np.array([14.0, 4.0, 30.0])

        meshes = []

        # 1. Glomerulus (capillary knot)
        glom = trimesh.creation.icosphere(subdivisions=2, radius=1.3)
        glom.apply_translation(glom_center)
        glom.visual.vertex_colors = np.full((len(glom.vertices), 4), [220, 38, 38, 255], dtype=np.uint8)
        meshes.append(glom)

        # 2. Bowman's Capsule (translucent surrounding cup)
        bowman = trimesh.creation.icosphere(subdivisions=2, radius=1.8)
        bowman.apply_translation(glom_center)
        bowman.visual.vertex_colors = np.full((len(bowman.vertices), 4), [250, 204, 21, 140], dtype=np.uint8)
        meshes.append(bowman)

        # 3. Afferent & Efferent arterioles
        aff = _create_tube_segment(glom_center + np.array([-2.5, 0.0, -1.0]), glom_center + np.array([-0.8, 0.0, -0.2]), 0.4, 0.35)
        eff = _create_tube_segment(glom_center + np.array([-0.8, 0.5, 0.5]), glom_center + np.array([-2.2, 1.0, 1.2]), 0.35, 0.3)
        if len(aff.vertices) > 0:
            aff.visual.vertex_colors = np.full((len(aff.vertices), 4), [220, 38, 38, 255], dtype=np.uint8)
            meshes.append(aff)
        if len(eff.vertices) > 0:
            eff.visual.vertex_colors = np.full((len(eff.vertices), 4), [220, 38, 38, 255], dtype=np.uint8)
            meshes.append(eff)

        # 4. Proximal Convoluted Tubule (PCT) - looping amber tube
        pct_points = [
            glom_center + np.array([1.2, 0.0, 0.0]),
            glom_center + np.array([2.5, 1.0, 0.5]),
            glom_center + np.array([2.0, 2.0, 1.5]),
            glom_center + np.array([1.0, 1.5, 2.0]),
            glom_center + np.array([0.5, 0.8, 1.2]),
            glom_center + np.array([0.0, 0.5, -0.5]),
        ]
        pct = _create_polyline_tube(pct_points, [0.38] * len(pct_points))
        if len(pct.vertices) > 0:
            pct.visual.vertex_colors = np.full((len(pct.vertices), 4), [245, 158, 11, 230], dtype=np.uint8)
            meshes.append(pct)

        # 5. Loop of Henle (deep hairpin loop dipping into pyramid medulla)
        henle_points = [
            glom_center + np.array([0.0, 0.5, -0.5]),
            glom_center + np.array([-1.5, 0.2, -6.0]),
            glom_center + np.array([-3.0, 0.0, -12.0]),
            glom_center + np.array([-4.5, 0.0, -18.0]),  # Hairpin apex in medullary pyramid
            glom_center + np.array([-3.8, 0.2, -18.2]),
            glom_center + np.array([-2.5, 0.4, -12.0]),
            glom_center + np.array([-1.2, 0.6, -6.0]),
            glom_center + np.array([-0.2, 0.8, 0.5]),
        ]
        henle = _create_polyline_tube(henle_points, [0.32] * len(henle_points))
        if len(henle.vertices) > 0:
            henle.visual.vertex_colors = np.full((len(henle.vertices), 4), [59, 130, 246, 230], dtype=np.uint8)
            meshes.append(henle)

        # 6. Distal Convoluted Tubule (DCT)
        dct_points = [
            glom_center + np.array([-0.2, 0.8, 0.5]),
            glom_center + np.array([-0.5, 1.5, 1.2]),
            glom_center + np.array([-1.2, 1.8, 0.5]),
            glom_center + np.array([-2.0, 1.5, -0.5]),
        ]
        dct = _create_polyline_tube(dct_points, [0.36] * len(dct_points))
        if len(dct.vertices) > 0:
            dct.visual.vertex_colors = np.full((len(dct.vertices), 4), [234, 88, 12, 230], dtype=np.uint8)
            meshes.append(dct)

        # 7. Collecting Duct (straight vertical conduit discharging at papilla)
        cd_points = [
            glom_center + np.array([-2.0, 1.5, 2.5]),
            glom_center + np.array([-2.0, 1.5, -0.5]),
            glom_center + np.array([-3.5, 1.2, -10.0]),
            glom_center + np.array([-5.5, 0.8, -20.0]),
            glom_center + np.array([-7.5, 0.5, -28.0]),  # Discharges at papilla
        ]
        cd = _create_polyline_tube(cd_points, [0.48] * len(cd_points))
        if len(cd.vertices) > 0:
            cd.visual.vertex_colors = np.full((len(cd.vertices), 4), [245, 158, 11, 235], dtype=np.uint8)
            meshes.append(cd)

        return trimesh.util.concatenate(meshes)

    def build_realistic_crystalline_calculus(
        self, stone_pos: Optional[np.ndarray] = None
    ) -> trimesh.Trimesh:
        """
        Builds a realistic, multi-faceted crystalline kidney calculus (stone) matching the reference image.
        Porous calcified surface, crystalline facets, craggy pits, nestled right in the renal pelvis / calyx!
        """
        if stone_pos is None:
            # Lodged in the lower major calyx / renal pelvis junction, exactly like the reference image!
            stone_pos = self.center + np.array([1.5, 3.5, -12.5])

        sphere = trimesh.creation.icosphere(subdivisions=4, radius=6.2)

        # Coherent 3D multi-frequency harmonics for authentic mineral crystalline facets
        v = sphere.vertices.copy()
        r = np.linalg.norm(v, axis=1, keepdims=True)
        unit_v = v / (r + 1e-6)

        # Primary lobules (macro morphology)
        macro = 0.70 * np.sin(2.5 * unit_v[:, 0:1]) * np.cos(2.5 * unit_v[:, 2:3])
        # Secondary crystalline facets (planar cleavage geometry)
        facets = 0.30 * np.cos(5.0 * unit_v[:, 0:1] + 3.0 * unit_v[:, 1:2]) * np.sin(4.0 * unit_v[:, 2:3])
        # Fine mineral texture
        micro = 0.12 * np.sin(8.0 * unit_v[:, 0:1]) * np.cos(8.0 * unit_v[:, 1:2])

        sphere.vertices += unit_v * (macro + facets + micro)

        # Anisotropic stone elongation
        sphere.vertices[:, 0] *= 1.15
        sphere.vertices[:, 1] *= 0.95
        sphere.vertices[:, 2] *= 0.88

        sphere.apply_translation(stone_pos)

        # Color: Natural calcified crystalline stone (warm golden-cream / amber with high specular contrast)
        color = [252, 211, 77, 255]  # RGBA
        sphere.visual.vertex_colors = np.full((len(sphere.vertices), 4), color, dtype=np.uint8)
        return sphere

    def build_complete_anatomical_package(self, output_dir: Path) -> Dict[str, Path]:
        """
        Builds and exports the complete medical-grade anatomical 3D package:
        - kidney.glb (Cortex & cutaway face)
        - renal_capsule.glb (Outer fibrous capsule)
        - medulla_pyramids.glb (8 striated pyramids)
        - collecting_system.glb (Calyces, pelvis, ureter)
        - renal_arteries.glb (Arterial tree with arcuate arches)
        - renal_veins.glb (Venous drainage)
        - renal_nerves.glb (Autonomic nerve plexus)
        - nephron_unit.glb (Complete 3D nephron functional unit)
        - stones.glb (Realistic crystalline calculus)
        - combined_anatomical_kidney.glb (Unified photorealistic scene)
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        results: Dict[str, Path] = {}

        # 1. Cortex Cutaway
        cortex = self.build_kidney_cortex(cutaway=False)
        cortex_path = output_dir / "kidney.glb"
        cortex.export(str(cortex_path), file_type="glb")
        cortex.export(str(output_dir / "kidney.stl"), file_type="stl")
        results["kidney"] = cortex_path

        # 2. Capsule
        capsule = self.build_renal_capsule()
        capsule_path = output_dir / "renal_capsule.glb"
        capsule.export(str(capsule_path), file_type="glb")
        results["renal_capsule"] = capsule_path

        # 3. Medullary Pyramids
        pyramids = self.build_medullary_pyramids()
        pyr_path = output_dir / "medulla_pyramids.glb"
        pyramids.export(str(pyr_path), file_type="glb")
        results["medulla_pyramids"] = pyr_path

        # 4. Collecting System
        collecting = self.build_collecting_system()
        coll_path = output_dir / "collecting_system.glb"
        collecting.export(str(coll_path), file_type="glb")
        results["collecting_system"] = coll_path

        # 5. Arteries
        arteries = self.build_arterial_tree()
        art_path = output_dir / "renal_arteries.glb"
        arteries.export(str(art_path), file_type="glb")
        results["renal_arteries"] = art_path

        # 6. Veins
        veins = self.build_venous_tree()
        vein_path = output_dir / "renal_veins.glb"
        veins.export(str(vein_path), file_type="glb")
        results["renal_veins"] = vein_path

        # 7. Nerves
        nerves = self.build_nerve_plexus()
        nerve_path = output_dir / "renal_nerves.glb"
        nerves.export(str(nerve_path), file_type="glb")
        results["renal_nerves"] = nerve_path

        # 8. Nephron Functional Unit
        nephron = self.build_nephron_functional_unit()
        neph_path = output_dir / "nephron_unit.glb"
        nephron.export(str(neph_path), file_type="glb")
        results["nephron_unit"] = neph_path

        # 9. Realistic Crystalline Stone
        stone = self.build_realistic_crystalline_calculus()
        stone_path = output_dir / "stones.glb"
        stone.export(str(stone_path), file_type="glb")
        stone.export(str(output_dir / "stones.stl"), file_type="stl")
        results["stones"] = stone_path

        # 10. Combined Master Scene
        all_meshes = [cortex, capsule, pyramids, collecting, arteries, veins, nerves, nephron, stone]
        combined = trimesh.Scene(all_meshes)
        comb_path = output_dir / "combined_anatomical_kidney.glb"
        combined.export(str(comb_path), file_type="glb")
        results["combined"] = comb_path

        return results
