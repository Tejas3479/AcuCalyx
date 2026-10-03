"""
AcuCalyx Uncertainty: Monte Carlo Perturbation and Empirical Collision Risk

Implements Module 10 of AcuCalyx v2:
Propagates spatial uncertainties across:
- Segmentation boundary variations (sigma_seg)
- Patient positioning and respiratory shifts (sigma_pos)
- Target and skin localization errors (sigma_geom)

Outputs:
- Empirical collision probability: P(Collision | Perturbations)
- 95% worst-case clearance (5th percentile effective distance)
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
import numpy as np

from acucalyx.geometry.transforms import LineSegment3D
from acucalyx.geometry.distance_fields import DistanceField


@dataclass(frozen=True)
class MonteCarloRiskAssessment:
    """Quantitative risk profile derived from Monte Carlo perturbation analysis."""
    hazard_name: str
    num_iterations: int
    collision_probability: float        # P(distance <= 0) [0.0, 1.0]
    nominal_clearance_mm: float
    percentile_5th_clearance_mm: float  # 95% worst-case clearance
    mean_perturbed_clearance_mm: float
    risk_category: str                  # 'LOW', 'MODERATE', 'CRITICAL'


def run_monte_carlo_clearance_analysis(
    trajectory: LineSegment3D,
    distance_field: DistanceField,
    hazard_name: str,
    num_iterations: int = 500,
    sigma_geom_mm: float = 1.0,
    sigma_seg_mm: float = 1.5,
    sigma_pos_mm: float = 2.5,
    random_seed: int = 42
) -> MonteCarloRiskAssessment:
    """
    Simulates stochastic perturbations on needle trajectory and hazard boundaries.
    """
    rng = np.random.default_rng(seed=random_seed)
    
    # Combined variance for spatial displacement
    # Needle start (skin) has geom + pos error
    # Needle target has geom + pos + organ motion error
    total_sigma_transverse = np.sqrt(sigma_geom_mm**2 + sigma_pos_mm**2)
    
    sampled_distances: List[float] = []
    collisions = 0
    
    # Sample points along nominal trajectory
    nominal_points = trajectory.sample_points(step_mm=1.0)
    nominal_dist = float(np.min(distance_field.sample_distance_physical(nominal_points)))
    nominal_clearance = max(0.0, nominal_dist)

    for _ in range(num_iterations):
        # Perturb trajectory start point
        perturb_start = rng.normal(0.0, total_sigma_transverse, size=3)
        # Perturb trajectory end point
        perturb_end = rng.normal(0.0, total_sigma_transverse, size=3)
        
        perturbed_seg = LineSegment3D(
            start_point=trajectory.start_point + perturb_start,
            end_point=trajectory.end_point + perturb_end
        )
        
        # Sample perturbed line segment
        pts = perturbed_seg.sample_points(step_mm=1.0)
        
        # Base distances from distance field
        raw_dists = distance_field.sample_distance_physical(pts)
        
        # Perturb hazard boundary itself (segmentation boundary noise)
        seg_noise = rng.normal(0.0, sigma_seg_mm)
        min_perturbed_dist = float(np.min(raw_dists)) - seg_noise
        
        if min_perturbed_dist <= 0.0:
            collisions += 1
            sampled_distances.append(0.0)
        else:
            sampled_distances.append(min_perturbed_dist)

    p_collision = float(collisions / num_iterations)
    p5_clearance = float(np.percentile(sampled_distances, 5.0))
    mean_clearance = float(np.mean(sampled_distances))

    if p_collision > 0.05 or p5_clearance < 2.0:
        category = 'CRITICAL'
    elif p_collision > 0.01 or p5_clearance < 7.0:
        category = 'MODERATE'
    else:
        category = 'LOW'

    return MonteCarloRiskAssessment(
        hazard_name=hazard_name,
        num_iterations=num_iterations,
        collision_probability=p_collision,
        nominal_clearance_mm=nominal_clearance,
        percentile_5th_clearance_mm=p5_clearance,
        mean_perturbed_clearance_mm=mean_clearance,
        risk_category=category
    )
