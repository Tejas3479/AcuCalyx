"""
AcuCalyx Endoscopy: Collecting System Centerline Graph & Continuous Morphometry
Governed by ACU-M15-EXEC-PLAN-2026-V2 (Milestone M15.1).

Converts pelvicalyceal lumen segmentation into a metric topological graph G = (V, E).
Features:
- Continuous Frenet-Serret framing (tangent, normal, binormal, curvature, torsion)
- Non-circular cross-sectional geometry (area, min/max Feret diameters, eccentricity)
- Continuous Infundibulopelvic Angle (IPA), Infundibular Width (IW), and Infundibular Length (IL)
- Eliminates single-point pelvis centroid turning hub in favor of volumetric luminal navigation
"""

from dataclasses import dataclass, field
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np


@dataclass(frozen=True)
class CenterlineNode:
    """Topological node in collecting system graph."""
    node_id: str
    position_lps_mm: np.ndarray  # [x, y, z] in LPS coordinates
    node_type: str               # "APEX", "IPJ", "PELVIS", "UPJ", "BRANCH"
    calyx_group: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "position_lps_mm": self.position_lps_mm.tolist(),
            "node_type": self.node_type,
            "calyx_group": self.calyx_group,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CenterlineNode":
        return cls(
            node_id=str(d["node_id"]),
            position_lps_mm=np.asarray(d["position_lps_mm"], dtype=float),
            node_type=str(d["node_type"]),
            calyx_group=d.get("calyx_group"),
        )


@dataclass(frozen=True)
class CrossSectionalGeometry:
    """Non-circular cross-sectional morphometry at arc-length point s."""
    arc_length_s: float
    centroid_lps_mm: np.ndarray
    cross_sectional_area_mm2: float
    min_feret_diameter_mm: float
    max_feret_diameter_mm: float
    eccentricity: float
    tangent_vector: np.ndarray
    normal_vector: np.ndarray
    binormal_vector: np.ndarray
    curvature: float
    torsion: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "arc_length_s": float(self.arc_length_s),
            "centroid_lps_mm": self.centroid_lps_mm.tolist(),
            "cross_sectional_area_mm2": float(self.cross_sectional_area_mm2),
            "min_feret_diameter_mm": float(self.min_feret_diameter_mm),
            "max_feret_diameter_mm": float(self.max_feret_diameter_mm),
            "eccentricity": float(self.eccentricity),
            "tangent_vector": self.tangent_vector.tolist(),
            "normal_vector": self.normal_vector.tolist(),
            "binormal_vector": self.binormal_vector.tolist(),
            "curvature": float(self.curvature),
            "torsion": float(self.torsion),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CrossSectionalGeometry":
        return cls(
            arc_length_s=float(d["arc_length_s"]),
            centroid_lps_mm=np.asarray(d["centroid_lps_mm"], dtype=float),
            cross_sectional_area_mm2=float(d["cross_sectional_area_mm2"]),
            min_feret_diameter_mm=float(d["min_feret_diameter_mm"]),
            max_feret_diameter_mm=float(d["max_feret_diameter_mm"]),
            eccentricity=float(d["eccentricity"]),
            tangent_vector=np.asarray(d["tangent_vector"], dtype=float),
            normal_vector=np.asarray(d["normal_vector"], dtype=float),
            binormal_vector=np.asarray(d["binormal_vector"], dtype=float),
            curvature=float(d["curvature"]),
            torsion=float(d["torsion"]),
        )


@dataclass(frozen=True)
class CenterlineEdge:
    """Parametric curve connecting two nodes in collecting system graph."""
    edge_id: str
    start_node_id: str
    end_node_id: str
    points_lps_mm: np.ndarray            # [N, 3] points
    arc_lengths_mm: np.ndarray          # [N] cumulative arc length
    total_length_mm: float
    cross_sections: List[CrossSectionalGeometry]
    min_feret_diameter_mm: float
    mean_feret_diameter_mm: float
    max_curvature: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "start_node_id": self.start_node_id,
            "end_node_id": self.end_node_id,
            "points_lps_mm": self.points_lps_mm.tolist(),
            "arc_lengths_mm": self.arc_lengths_mm.tolist(),
            "total_length_mm": float(self.total_length_mm),
            "cross_sections": [cs.to_dict() for cs in self.cross_sections],
            "min_feret_diameter_mm": float(self.min_feret_diameter_mm),
            "mean_feret_diameter_mm": float(self.mean_feret_diameter_mm),
            "max_curvature": float(self.max_curvature),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CenterlineEdge":
        return cls(
            edge_id=str(d["edge_id"]),
            start_node_id=str(d["start_node_id"]),
            end_node_id=str(d["end_node_id"]),
            points_lps_mm=np.asarray(d["points_lps_mm"], dtype=float),
            arc_lengths_mm=np.asarray(d["arc_lengths_mm"], dtype=float),
            total_length_mm=float(d["total_length_mm"]),
            cross_sections=[CrossSectionalGeometry.from_dict(cs) for cs in d.get("cross_sections", [])],
            min_feret_diameter_mm=float(d["min_feret_diameter_mm"]),
            mean_feret_diameter_mm=float(d["mean_feret_diameter_mm"]),
            max_curvature=float(d["max_curvature"]),
        )


@dataclass(frozen=True)
class CalyxMorphometry:
    """Continuous patient-specific calyceal and infundibular morphometry."""
    calyx_id: str
    apex_node_id: str
    ipj_node_id: str
    calyx_group: str
    infundibulopelvic_angle_deg: float  # Continuous IPA [0, 180]
    infundibular_length_mm: float       # Total path length apex -> IPJ
    infundibular_width_min_mm: float    # Min Feret diameter along infundibulum
    infundibular_width_mean_mm: float   # Mean Feret diameter
    mean_eccentricity: float            # Deviation from circular cross-section
    max_curvature: float                # Maximum curvature along infundibulum
    visibility_state: str = "DIRECT"    # DIRECT, PARTIAL, ESTIMATED, UNAVAILABLE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "calyx_id": self.calyx_id,
            "apex_node_id": self.apex_node_id,
            "ipj_node_id": self.ipj_node_id,
            "calyx_group": self.calyx_group,
            "infundibulopelvic_angle_deg": float(self.infundibulopelvic_angle_deg),
            "infundibular_length_mm": float(self.infundibular_length_mm),
            "infundibular_width_min_mm": float(self.infundibular_width_min_mm),
            "infundibular_width_mean_mm": float(self.infundibular_width_mean_mm),
            "mean_eccentricity": float(self.mean_eccentricity),
            "max_curvature": float(self.max_curvature),
            "visibility_state": self.visibility_state,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CalyxMorphometry":
        return cls(
            calyx_id=str(d["calyx_id"]),
            apex_node_id=str(d["apex_node_id"]),
            ipj_node_id=str(d["ipj_node_id"]),
            calyx_group=str(d["calyx_group"]),
            infundibulopelvic_angle_deg=float(d["infundibulopelvic_angle_deg"]),
            infundibular_length_mm=float(d["infundibular_length_mm"]),
            infundibular_width_min_mm=float(d["infundibular_width_min_mm"]),
            infundibular_width_mean_mm=float(d["infundibular_width_mean_mm"]),
            mean_eccentricity=float(d["mean_eccentricity"]),
            max_curvature=float(d["max_curvature"]),
            visibility_state=d.get("visibility_state", "DIRECT"),
        )


@dataclass
class CollectingSystemGraph:
    """Full metric topological graph of kidney collecting system."""
    case_id: str
    nodes: Dict[str, CenterlineNode]
    edges: Dict[str, CenterlineEdge]
    calyces: Dict[str, CalyxMorphometry]
    pelvis_bounding_box: Tuple[np.ndarray, np.ndarray]  # (min_xyz, max_xyz)
    pelvis_center_lps_mm: np.ndarray
    upj_position_lps_mm: np.ndarray

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": "1.0",
            "case_id": self.case_id,
            "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
            "edges": {k: v.to_dict() for k, v in self.edges.items()},
            "calyces": {k: v.to_dict() for k, v in self.calyces.items()},
            "pelvis_bounding_box": [
                self.pelvis_bounding_box[0].tolist(),
                self.pelvis_bounding_box[1].tolist(),
            ],
            "pelvis_center_lps_mm": self.pelvis_center_lps_mm.tolist(),
            "upj_position_lps_mm": self.upj_position_lps_mm.tolist(),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CollectingSystemGraph":
        nodes = {k: CenterlineNode.from_dict(v) for k, v in d.get("nodes", {}).items()}
        edges = {k: CenterlineEdge.from_dict(v) for k, v in d.get("edges", {}).items()}
        calyces = {k: CalyxMorphometry.from_dict(v) for k, v in d.get("calyces", {}).items()}
        bbox_raw = d.get("pelvis_bounding_box", [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]])
        bbox = (np.asarray(bbox_raw[0], dtype=float), np.asarray(bbox_raw[1], dtype=float))
        pelvis_center = np.asarray(d.get("pelvis_center_lps_mm", [0.0, 0.0, 0.0]), dtype=float)
        upj_pos = np.asarray(d.get("upj_position_lps_mm", [0.0, 0.0, 0.0]), dtype=float)

        return cls(
            case_id=str(d.get("case_id", "UNKNOWN")),
            nodes=nodes,
            edges=edges,
            calyces=calyces,
            pelvis_bounding_box=bbox,
            pelvis_center_lps_mm=pelvis_center,
            upj_position_lps_mm=upj_pos,
        )

    def save_to_json(self, file_path: Union[str, Path]) -> None:
        p = Path(file_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load_from_json(cls, file_path: Union[str, Path]) -> "CollectingSystemGraph":
        p = Path(file_path)
        if not p.is_file():
            raise FileNotFoundError(f"Collecting system graph file not found: {file_path}")
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    def get_path_points(self, start_calyx_id: str, target_calyx_id: str) -> np.ndarray:
        """
        Extracts continuous 3D coordinate path traversing through the renal pelvis lumen
        from entered calyx to secondary target calyx.
        """
        if start_calyx_id == target_calyx_id:
            edge = self.edges.get(f"EDGE_{start_calyx_id}")
            return edge.points_lps_mm if edge else np.empty((0, 3))

        start_edge = self.edges.get(f"EDGE_{start_calyx_id}")
        target_edge = self.edges.get(f"EDGE_{target_calyx_id}")

        if not start_edge or not target_edge:
            # Fallback direct interpolation if edge missing
            p_start = self.nodes[f"APEX_{start_calyx_id}"].position_lps_mm
            p_end = self.nodes[f"APEX_{target_calyx_id}"].position_lps_mm
            steps = 20
            return np.linspace(p_start, p_end, steps)

        # Path: Start Calyx Apex -> Start IPJ -> Pelvis Path -> Target IPJ -> Target Apex
        pts_in = start_edge.points_lps_mm[::-1]  # from apex to IPJ
        pts_out = target_edge.points_lps_mm      # from IPJ to apex

        # Pelvis internal bridge connecting start IPJ to target IPJ
        p_ipj_in = pts_in[-1]
        p_ipj_out = pts_out[0]
        # Intermediate curve passing through pelvis lumen
        mid_pelvis = self.pelvis_center_lps_mm
        # Quadratic Bezier or spline through pelvis interior
        t_vals = np.linspace(0.1, 0.9, 8)[:, np.newaxis]
        pelvis_bridge = (1.0 - t_vals)**2 * p_ipj_in + 2.0 * (1.0 - t_vals) * t_vals * mid_pelvis + t_vals**2 * p_ipj_out

        return np.vstack([pts_in, pelvis_bridge, pts_out])


def save_collecting_system_graph(graph: CollectingSystemGraph, file_path: Union[str, Path]) -> None:
    """Saves CollectingSystemGraph to JSON file."""
    graph.save_to_json(file_path)


def load_collecting_system_graph(file_path: Union[str, Path]) -> CollectingSystemGraph:
    """Loads CollectingSystemGraph from JSON file."""
    return CollectingSystemGraph.load_from_json(file_path)


# -----------------------------------------------------------------------------
# Metric Computation Utilities
# -----------------------------------------------------------------------------

def compute_frenet_frame(
    points: np.ndarray
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Computes smoothed continuous Frenet-Serret frame:
    Tangents, Normals, Binormals, Curvatures, and Torsions along points [N, 3].
    """
    n_pts = len(points)
    if n_pts < 3:
        tangents = np.tile([0.0, 0.0, 1.0], (n_pts, 1))
        normals = np.tile([1.0, 0.0, 0.0], (n_pts, 1))
        binormals = np.tile([0.0, 1.0, 0.0], (n_pts, 1))
        curvatures = np.zeros(n_pts)
        torsions = np.zeros(n_pts)
        return tangents, normals, binormals, curvatures, torsions

    # First derivatives (tangent)
    d1 = np.gradient(points, axis=0)
    d1_norm = np.linalg.norm(d1, axis=1, keepdims=True)
    d1_norm[d1_norm < 1e-6] = 1.0
    tangents = d1 / d1_norm

    # Second derivatives (curvature vector)
    d2 = np.gradient(d1, axis=0)
    cross_d1_d2 = np.cross(d1, d2)
    cross_norm = np.linalg.norm(cross_d1_d2, axis=1)

    curvatures = cross_norm / (np.linalg.norm(d1, axis=1)**3 + 1e-6)

    # Binormal
    binormals = np.zeros_like(tangents)
    for i in range(n_pts):
        if cross_norm[i] > 1e-6:
            binormals[i] = cross_d1_d2[i] / cross_norm[i]
        else:
            # Arbitrary orthogonal vector
            ref = np.array([0.0, 1.0, 0.0]) if abs(tangents[i, 1]) < 0.9 else np.array([1.0, 0.0, 0.0])
            b = np.cross(tangents[i], ref)
            binormals[i] = b / (np.linalg.norm(b) + 1e-6)

    # Normal vector = Binormal x Tangent
    normals = np.cross(binormals, tangents)
    normals /= (np.linalg.norm(normals, axis=1, keepdims=True) + 1e-6)

    # Third derivatives (torsion)
    d3 = np.gradient(d2, axis=0)
    torsions = np.zeros(n_pts)
    for i in range(n_pts):
        denom = cross_norm[i]**2
        if denom > 1e-6:
            torsions[i] = np.dot(cross_d1_d2[i], d3[i]) / denom

    return tangents, normals, binormals, curvatures, torsions


def build_procedural_collecting_system_graph(
    case_id: str,
    calyx_specs: Optional[List[Dict[str, any]]] = None,
    pelvis_center_lps: Optional[np.ndarray] = None,
    upj_lps: Optional[np.ndarray] = None,
) -> CollectingSystemGraph:
    """
    Procedurally constructs a physiologically realistic collecting system graph
    for testing, phantom validation, and synthetic kidney models.
    
    Default configuration includes:
    - Lower Posterior Calyx (standard target puncture)
    - Middle Posterior Calyx
    - Upper Posterior Calyx
    - Middle/Lower Anterior Calyces
    """
    if pelvis_center_lps is None:
        pelvis_center_lps = np.array([25.0, 15.0, 0.0], dtype=float)
    if upj_lps is None:
        upj_lps = np.array([20.0, 12.0, -25.0], dtype=float)

    if calyx_specs is None:
        # Standard realistic anatomical calyceal configuration
        calyx_specs = [
            {
                "calyx_id": "LP",
                "calyx_group": "LOWER_POSTERIOR",
                "apex_lps": np.array([45.0, -10.0, -32.0]),
                "ipj_lps": np.array([32.0, 5.0, -15.0]),
                "min_feret_mm": 6.8,
                "max_feret_mm": 8.2,
                "visibility_state": "DIRECT",
            },
            {
                "calyx_id": "MP",
                "calyx_group": "MIDDLE_POSTERIOR",
                "apex_lps": np.array([52.0, -5.0, 5.0]),
                "ipj_lps": np.array([35.0, 8.0, 2.0]),
                "min_feret_mm": 5.4,
                "max_feret_mm": 6.6,
                "visibility_state": "DIRECT",
            },
            {
                "calyx_id": "UP",
                "calyx_group": "UPPER_POSTERIOR",
                "apex_lps": np.array([40.0, -8.0, 36.0]),
                "ipj_lps": np.array([28.0, 8.0, 18.0]),
                "min_feret_mm": 4.8,
                "max_feret_mm": 6.0,
                "visibility_state": "DIRECT",
            },
            {
                "calyx_id": "MA",
                "calyx_group": "MIDDLE_ANTERIOR",
                "apex_lps": np.array([48.0, 35.0, 2.0]),
                "ipj_lps": np.array([30.0, 22.0, 1.0]),
                "min_feret_mm": 4.2,
                "max_feret_mm": 5.5,
                "visibility_state": "DIRECT",
            },
        ]

    nodes: Dict[str, CenterlineNode] = {}
    edges: Dict[str, CenterlineEdge] = {}
    calyces: Dict[str, CalyxMorphometry] = {}

    # Pelvis Centroid & UPJ Nodes
    nodes["PELVIS_CENTROID"] = CenterlineNode(
        node_id="PELVIS_CENTROID",
        position_lps_mm=pelvis_center_lps,
        node_type="PELVIS",
    )
    nodes["UPJ"] = CenterlineNode(
        node_id="UPJ",
        position_lps_mm=upj_lps,
        node_type="UPJ",
    )

    # UPJ Vector (representing pelvic drainage axis for IPA calculation)
    pelvic_drainage_axis = (upj_lps - pelvis_center_lps)
    pelvic_drainage_axis /= (np.linalg.norm(pelvic_drainage_axis) + 1e-6)

    all_edge_points = [pelvis_center_lps, upj_lps]

    for spec in calyx_specs:
        cid = spec["calyx_id"]
        cgroup = spec["calyx_group"]
        apex_pos = np.array(spec["apex_lps"], dtype=float)
        ipj_pos = np.array(spec["ipj_lps"], dtype=float)
        min_feret = float(spec.get("min_feret_mm", 5.5))
        max_feret = float(spec.get("max_feret_mm", 7.0))
        vis_state = spec.get("visibility_state", "DIRECT")

        nodes[f"APEX_{cid}"] = CenterlineNode(
            node_id=f"APEX_{cid}",
            position_lps_mm=apex_pos,
            node_type="APEX",
            calyx_group=cgroup,
        )
        nodes[f"IPJ_{cid}"] = CenterlineNode(
            node_id=f"IPJ_{cid}",
            position_lps_mm=ipj_pos,
            node_type="IPJ",
            calyx_group=cgroup,
        )

        # Discretize curved infundibulum between IPJ and Apex (N = 25 points)
        n_points = 25
        t_vals = np.linspace(0.0, 1.0, n_points)
        # Add slight natural physiological anatomical curvature
        mid_arc = (ipj_pos + apex_pos) * 0.5 + np.array([2.0, 1.0, -1.5])
        pts = np.zeros((n_points, 3), dtype=float)
        for i, t in enumerate(t_vals):
            pts[i] = (1.0 - t)**2 * ipj_pos + 2.0 * (1.0 - t) * t * mid_arc + t**2 * apex_pos

        all_edge_points.append(pts)

        # Cumulative arc lengths
        dists = np.linalg.norm(np.diff(pts, axis=0), axis=1)
        arc_lengths = np.insert(np.cumsum(dists), 0, 0.0)
        total_length = float(arc_lengths[-1])

        # Frenet frame computation
        tangents, normals, binormals, curvatures, torsions = compute_frenet_frame(pts)

        # Cross sections
        cross_sections: List[CrossSectionalGeometry] = []
        eccentricity = math.sqrt(max(0.0, 1.0 - (min_feret / max_feret)**2))
        area = math.pi * (min_feret * 0.5) * (max_feret * 0.5)

        for i in range(n_points):
            # Slight neck narrowing along infundibulum
            neck_factor = 1.0 - 0.15 * math.sin(t_vals[i] * math.pi)
            cur_min = min_feret * neck_factor
            cur_max = max_feret * neck_factor
            cur_area = math.pi * (cur_min * 0.5) * (cur_max * 0.5)
            cur_ecc = math.sqrt(max(0.0, 1.0 - (cur_min / cur_max)**2))

            cs = CrossSectionalGeometry(
                arc_length_s=float(arc_lengths[i]),
                centroid_lps_mm=pts[i],
                cross_sectional_area_mm2=cur_area,
                min_feret_diameter_mm=cur_min,
                max_feret_diameter_mm=cur_max,
                eccentricity=cur_ecc,
                tangent_vector=tangents[i],
                normal_vector=normals[i],
                binormal_vector=binormals[i],
                curvature=float(curvatures[i]),
                torsion=float(torsions[i]),
            )
            cross_sections.append(cs)

        min_edge_feret = min(cs.min_feret_diameter_mm for cs in cross_sections)
        mean_edge_feret = float(np.mean([cs.min_feret_diameter_mm for cs in cross_sections]))
        max_curv = float(np.max(curvatures))

        edge = CenterlineEdge(
            edge_id=f"EDGE_{cid}",
            start_node_id=f"IPJ_{cid}",
            end_node_id=f"APEX_{cid}",
            points_lps_mm=pts,
            arc_lengths_mm=arc_lengths,
            total_length_mm=total_length,
            cross_sections=cross_sections,
            min_feret_diameter_mm=min_edge_feret,
            mean_feret_diameter_mm=mean_edge_feret,
            max_curvature=max_curv,
        )
        edges[edge.edge_id] = edge

        # Infundibular Axis Vector (from IPJ towards Apex)
        infundibular_axis = (apex_pos - ipj_pos)
        infundibular_axis /= (np.linalg.norm(infundibular_axis) + 1e-6)

        # Infundibulopelvic Angle (IPA) formulation
        # Continuous angle between central infundibular axis and ureteropelvic drainage axis
        cos_ipa = float(np.dot(infundibular_axis, pelvic_drainage_axis))
        cos_ipa = np.clip(cos_ipa, -1.0, 1.0)
        ipa_deg = float(np.degrees(np.arccos(cos_ipa)))

        calyces[cid] = CalyxMorphometry(
            calyx_id=cid,
            apex_node_id=f"APEX_{cid}",
            ipj_node_id=f"IPJ_{cid}",
            calyx_group=cgroup,
            infundibulopelvic_angle_deg=ipa_deg,
            infundibular_length_mm=total_length,
            infundibular_width_min_mm=min_edge_feret,
            infundibular_width_mean_mm=mean_edge_feret,
            mean_eccentricity=eccentricity,
            max_curvature=max_curv,
            visibility_state=vis_state,
        )

    all_pts_flat = np.vstack(all_edge_points) if len(all_edge_points) > 2 else np.array([pelvis_center_lps])
    bbox_min = np.min(all_pts_flat, axis=0) - 5.0
    bbox_max = np.max(all_pts_flat, axis=0) + 5.0

    return CollectingSystemGraph(
        case_id=case_id,
        nodes=nodes,
        edges=edges,
        calyces=calyces,
        pelvis_bounding_box=(bbox_min, bbox_max),
        pelvis_center_lps_mm=pelvis_center_lps,
        upj_position_lps_mm=upj_lps,
    )
