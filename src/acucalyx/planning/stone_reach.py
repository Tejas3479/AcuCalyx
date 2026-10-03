"""
AcuCalyx Planning: Stone Reachability and Coverage Model

Implements Step 09 of AcuCalyx v2.1:
- Evaluates reachable stone burden for a specific puncture corridor and endoscope profile
- Computes reachable stone volume percentage:
    Coverage = Sum(V_reachable_stones) / Sum(V_total_stones)
- Enforces device length and flexible deflection limits from InstrumentProfile
"""

from dataclasses import dataclass
from typing import List, Tuple
import numpy as np

from acucalyx.geometry.transforms import LineSegment3D, angle_between_vectors
from acucalyx.planning.scope_model import InstrumentProfile
from acucalyx.planning.target_candidates import ConicalPunctureZone
from acucalyx.stones.volumetry import StoneMorphometry


@dataclass(frozen=True)
class StoneReachabilityAssessment:
    """Quantitative stone coverage evaluation for an access corridor."""
    total_stone_volume_mm3: float
    reachable_stone_volume_mm3: float
    reachable_stone_fraction: float          # [0.0, 1.0]
    reachable_stone_ids: List[int]
    unreachable_stone_ids: List[int]
    max_required_deflection_deg: float
    instrument_name: str
    is_needle_length_sufficient: bool        # True if tract <= needle_length - margin


def evaluate_access_stone_reach(
    trajectory: LineSegment3D,
    puncture_zone: ConicalPunctureZone,
    instrument: InstrumentProfile,
    stones: List[StoneMorphometry],
    needle_max_length_mm: float = 160.0,
    working_margin_mm: float = 20.0
) -> StoneReachabilityAssessment:
    """
    Evaluates how much stone volume can be reached from a candidate puncture corridor.
    """
    total_vol = sum(s.volume_mm3 for s in stones)
    if total_vol < 1e-3:
        return StoneReachabilityAssessment(
            total_stone_volume_mm3=0.0,
            reachable_stone_volume_mm3=0.0,
            reachable_stone_fraction=1.0,
            reachable_stone_ids=[],
            unreachable_stone_ids=[],
            max_required_deflection_deg=0.0,
            instrument_name=instrument.name,
            is_needle_length_sufficient=True
        )

    tract_len = trajectory.length
    max_allowable_tract = needle_max_length_mm - working_margin_mm
    is_length_ok = tract_len <= max_allowable_tract

    needle_dir = trajectory.unit_direction
    papilla_target = puncture_zone.apex_papilla_lps_mm

    reachable_ids: List[int] = []
    unreachable_ids: List[int] = []
    reachable_vol = 0.0
    max_deflection = 0.0

    for stone in stones:
        is_reach, req_deflection, dist_mm = instrument.evaluate_target_reachability(
            calyx_entry_point=papilla_target,
            trajectory_unit_vector=needle_dir,
            stone_centroid=stone.centroid_lps_mm
        )
        
        if is_reach:
            reachable_ids.append(stone.stone_id)
            reachable_vol += stone.volume_mm3
            max_deflection = max(max_deflection, req_deflection)
        else:
            unreachable_ids.append(stone.stone_id)

    coverage_fraction = float(reachable_vol / total_vol)

    return StoneReachabilityAssessment(
        total_stone_volume_mm3=total_vol,
        reachable_stone_volume_mm3=reachable_vol,
        reachable_stone_fraction=coverage_fraction,
        reachable_stone_ids=reachable_ids,
        unreachable_stone_ids=unreachable_ids,
        max_required_deflection_deg=max_deflection,
        instrument_name=instrument.name,
        is_needle_length_sufficient=is_length_ok
    )
