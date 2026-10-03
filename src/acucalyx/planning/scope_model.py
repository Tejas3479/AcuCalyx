"""
AcuCalyx Planning: Parameterized Endoscopic Instrument Model

Implements Module 8 of AcuCalyx v2:
Replaces hardcoded scope assumptions with parameterized instrument profiles
specifying physical reach, rigid look angles, and flexible deflection limits.
"""

from dataclasses import dataclass
from typing import Optional, Tuple
import numpy as np

from acucalyx.geometry.transforms import angle_between_vectors


@dataclass(frozen=True)
class InstrumentProfile:
    """Mechanical and optical specifications of an endoscope."""
    name: str
    working_length_mm: float
    max_deflection_deg: float         # 0.0 for rigid, 90-270 for flexible
    rigid_look_angle_deg: float       # 0, 12, or 30 degrees
    sheath_diameter_fr: float         # French gauge (1 Fr = 1/3 mm)
    is_flexible: bool

    @property
    def outer_diameter_mm(self) -> float:
        """Physical outer diameter in millimeters."""
        return self.sheath_diameter_fr / 3.0

    def evaluate_target_reachability(
        self,
        calyx_entry_point: np.ndarray,
        trajectory_unit_vector: np.ndarray,
        stone_centroid: np.ndarray
    ) -> Tuple[bool, float, float]:
        """
        Evaluates whether a stone is within mechanical reach of this instrument.
        
        Returns:
            is_reachable: bool
            required_deflection_deg: float
            distance_from_entry_mm: float
        """
        vec_to_stone = stone_centroid - calyx_entry_point
        dist_mm = float(np.linalg.norm(vec_to_stone))
        
        if dist_mm > self.working_length_mm:
            return False, 180.0, dist_mm
            
        if dist_mm < 1e-3:
            return True, 0.0, dist_mm

        # Angle between trajectory vector (line of sight) and stone vector
        angle_deg = angle_between_vectors(trajectory_unit_vector, vec_to_stone)
        
        # Required deflection relative to the instrument's optical/mechanical axis
        req_deflection = max(0.0, angle_deg - self.rigid_look_angle_deg)
        
        is_reachable = req_deflection <= self.max_deflection_deg
        return is_reachable, float(req_deflection), dist_mm


# Pre-defined clinical instrument profiles
STANDARD_RIGID_NEPHROSCOPE = InstrumentProfile(
    name="Standard_Rigid_Nephroscope_24Fr",
    working_length_mm=220.0,
    max_deflection_deg=15.0,  # Slight torque/angulation tolerance
    rigid_look_angle_deg=0.0,
    sheath_diameter_fr=24.0,
    is_flexible=False
)

FLEXIBLE_CYSTONEPHROSCOPE = InstrumentProfile(
    name="Flexible_Nephroscope_16Fr",
    working_length_mm=380.0,
    max_deflection_deg=210.0, # High active deflection
    rigid_look_angle_deg=0.0,
    sheath_diameter_fr=16.0,
    is_flexible=True
)
