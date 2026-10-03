"""
AcuCalyx Stones: Descriptive Clinical Nephrolithometry Scoring Engine (Milestone M11)

Implements validated clinical complexity scoring systems for PCNL preoperative planning:
1. Guy's Stone Score (GSS Grades I–IV) per Thomas et al. (2011)
2. S.T.O.N.E. Nephrolithometry Score (5–13 points) per Okhunov et al. (2013)

FDA CDS & Scope Governance Invariant (Jan 2026 CDS Final Guidance):
- Outputs descriptive clinical morphometry and complexity stratification ONLY.
- Strictly PROHIBITS automated treatment selection (PCNL vs URS vs SWL).
- Strictly PROHIBITS predictive statistical claims (e.g. 'Predicted Stone-Free Rate: 84%')
  which require separate multi-center prospective validation and marketing authorization.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple
import numpy as np


class GuysStoneGrade(str, Enum):
    GRADE_I = "GRADE_I"     # Solitary stone in mid/lower pole or solitary pelvis stone with normal anatomy
    GRADE_II = "GRADE_II"   # Solitary stone in upper pole, multiple stones with normal anatomy, or solitary in bifid
    GRADE_III = "GRADE_III" # Multiple stones in abnormal anatomy, diverticulum, or partial staghorn
    GRADE_IV = "GRADE_IV"   # Full staghorn calculus or any calculus in spina bifida / spinal dysraphism


@dataclass(frozen=True)
class GuysStoneAssessment:
    """Descriptive Guy's Stone Score assessment."""
    grade: GuysStoneGrade
    description: str
    is_staghorn: bool
    calyces_involved_count: int
    anatomical_abnormality: bool
    clinical_note: str


@dataclass(frozen=True)
class StoneNephrolithometryAssessment:
    """
    Descriptive S.T.O.N.E. Nephrolithometry score (range: 5 to 13 points).
    
    Components:
    - S (Size): 1-4 points (<400 mm2=1, 400-799=2, 800-1599=3, >=1600=4)
    - T (Tract Length): 1-2 points (<=100 mm=1, >100 mm=2)
    - O (Obstruction): 1-2 points (None/Mild=1, Moderate/Severe=2)
    - N (Number of involved calyces): 1-3 points (1=1, 2-3=2, >3=3)
    - E (Essence / Mean HU): 1-2 points (<=950 HU=1, >950 HU=2)
    """
    total_score: int
    size_points: int
    tract_length_points: int
    obstruction_points: int
    number_calyces_points: int
    essence_points: int
    stone_surface_area_mm2: float
    tract_length_mm: float
    hydronephrosis_present: bool
    involved_calyces_count: int
    mean_hu: float
    complexity_tier: str  # 'LOW' (5-6), 'MODERATE' (7-8), 'HIGH' (9-13)
    regulatory_disclaimer: str


def compute_guys_stone_score(
    stone_count: int,
    stone_locations: List[str],
    is_staghorn: bool = False,
    is_partial_staghorn: bool = False,
    in_calyceal_diverticulum: bool = False,
    has_spina_bifida_or_dysraphism: bool = False,
    has_abnormal_anatomy: bool = False,
    is_bifid_system: bool = False,
) -> GuysStoneAssessment:
    """
    Computes Guy's Stone Score strictly following the Thomas et al. (2011) grading rules.
    """
    unique_calyces = len(set(loc.lower() for loc in stone_locations))

    # Grade IV: Full staghorn OR any stone in spinal dysraphism / spina bifida
    if is_staghorn or has_spina_bifida_or_dysraphism:
        grade = GuysStoneGrade.GRADE_IV
        desc = "Full staghorn calculus or calculus in patient with neurogenic/spinal dysraphic anatomy."
        note = "High procedural complexity. Multiple tracts or staged procedures frequently required."

    # Grade III: Multiple stones in abnormal anatomy, calyceal diverticulum, or partial staghorn
    elif is_partial_staghorn or in_calyceal_diverticulum or (stone_count > 1 and has_abnormal_anatomy):
        grade = GuysStoneGrade.GRADE_III
        desc = "Partial staghorn calculus, stone in calyceal diverticulum, or multiple stones with anatomical anomaly."
        note = "Moderate-to-high complexity. Puncture planning must account for abnormal infundibular drainage."

    # Grade II: Solitary stone in upper pole, multiple stones in normal anatomy, or solitary in bifid system
    elif (
        (stone_count == 1 and any("upper" in loc.lower() for loc in stone_locations))
        or (stone_count > 1 and not has_abnormal_anatomy)
        or (stone_count == 1 and is_bifid_system)
    ):
        grade = GuysStoneGrade.GRADE_II
        desc = "Solitary upper pole stone, multiple calculi in normal anatomy, or solitary stone in bifid collecting system."
        note = "Moderate complexity. Intercostal or flexible nephroscopy reachability assessment recommended."

    # Grade I: Solitary stone in mid/lower pole or solitary pelvis stone with normal anatomy
    else:
        grade = GuysStoneGrade.GRADE_I
        desc = "Solitary stone in renal pelvis or mid/lower calyx with normal renal anatomy."
        note = "Favorable procedural complexity for standard lower pole percutaneous access."

    return GuysStoneAssessment(
        grade=grade,
        description=desc,
        is_staghorn=is_staghorn or is_partial_staghorn,
        calyces_involved_count=unique_calyces,
        anatomical_abnormality=has_abnormal_anatomy or has_spina_bifida_or_dysraphism,
        clinical_note=note
    )


def compute_stone_nephrolithometry(
    stone_surface_area_mm2: float,
    tract_length_mm: float,
    has_hydronephrosis_or_obstruction: bool,
    involved_calyces_count: int,
    mean_hu: float
) -> StoneNephrolithometryAssessment:
    """
    Computes S.T.O.N.E. Nephrolithometry score (range: 5 to 13 points) per Okhunov et al. (2013).
    """
    # S (Size in mm2)
    if stone_surface_area_mm2 < 400.0:
        s_pts = 1
    elif stone_surface_area_mm2 < 800.0:
        s_pts = 2
    elif stone_surface_area_mm2 < 1600.0:
        s_pts = 3
    else:
        s_pts = 4

    # T (Tract Length in mm)
    t_pts = 1 if tract_length_mm <= 100.0 else 2

    # O (Obstruction / Hydronephrosis)
    o_pts = 2 if has_hydronephrosis_or_obstruction else 1

    # N (Number of involved calyces)
    if involved_calyces_count <= 1:
        n_pts = 1
    elif involved_calyces_count <= 3:
        n_pts = 2
    else:
        n_pts = 3

    # E (Essence / HU density)
    e_pts = 1 if mean_hu <= 950.0 else 2

    total = s_pts + t_pts + o_pts + n_pts + e_pts
    assert 5 <= total <= 13, f"S.T.O.N.E. score must be between 5 and 13, got {total}"

    if total <= 6:
        tier = "LOW"
    elif total <= 8:
        tier = "MODERATE"
    else:
        tier = "HIGH"

    disclaimer = (
        "Descriptive nephrolithometry score only per Okhunov et al. (2013). "
        "Does not constitute an autonomous treatment recommendation or statistical stone-free prediction."
    )

    return StoneNephrolithometryAssessment(
        total_score=total,
        size_points=s_pts,
        tract_length_points=t_pts,
        obstruction_points=o_pts,
        number_calyces_points=n_pts,
        essence_points=e_pts,
        stone_surface_area_mm2=float(stone_surface_area_mm2),
        tract_length_mm=float(tract_length_mm),
        hydronephrosis_present=bool(has_hydronephrosis_or_obstruction),
        involved_calyces_count=int(involved_calyces_count),
        mean_hu=float(mean_hu),
        complexity_tier=tier,
        regulatory_disclaimer=disclaimer
    )
