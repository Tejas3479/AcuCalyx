"""
AcuCalyx Validation: PCNL Challenge Set Registry & Stress Cohort (Frozen v3.1)

Implements Workstream H of Phase 3 (M1/M2 Milestone):
Dedicated benchmark cohort designed specifically to test boundary failure modes:
"Where does AcuCalyx fail or require clinical conditional flags?"
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence


class ChallengeCategory(str, Enum):
    RETRORENAL_COLON = "RETRORENAL_COLON"
    SUPRACOSTAL_ACCESS = "SUPRACOSTAL_ACCESS"
    HIGH_KIDNEY_T11_T12 = "HIGH_KIDNEY_T11_T12"
    SEVERE_SCOLIOSIS = "SEVERE_SCOLIOSIS"
    SEVERE_HYDRONEPHROSIS = "SEVERE_HYDRONEPHROSIS"
    NONDILATED_COLLAPSED_PCS = "NONDILATED_COLLAPSED_PCS"
    HORSESHOE_KIDNEY = "HORSESHOE_KIDNEY"
    MALROTATED_KIDNEY = "MALROTATED_KIDNEY"
    DUPLICATED_COLLECTING_SYSTEM = "DUPLICATED_COLLECTING_SYSTEM"
    LARGE_STAGHORN_CALCULUS = "LARGE_STAGHORN_CALCULUS"
    MULTIPLE_CALICEAL_CALCULI = "MULTIPLE_CALICEAL_CALCULI"
    SEVERE_MOTION_METAL_ARTIFACT = "SEVERE_MOTION_METAL_ARTIFACT"


@dataclass(frozen=True)
class PCNLChallengeCase:
    """A designated clinical challenge case evaluated for safety degradation."""
    case_id: str
    categories: List[ChallengeCategory]
    description: str
    scanner_vendor: str
    slice_thickness_mm: float
    expected_difficulty: str           # 'MODERATE', 'HIGH', 'EXTREME'
    primary_failure_mode_to_test: str


class ChallengeSetRegistry:
    """Manages the 12-category challenge set cases and subgroup metrics."""

    def __init__(self):
        self._cases: Dict[str, PCNLChallengeCase] = {}

    def register_case(self, case: PCNLChallengeCase) -> None:
        self._cases[case.case_id] = case

    def get_cases_by_category(self, category: ChallengeCategory) -> List[PCNLChallengeCase]:
        return [c for c in self._cases.values() if category in c.categories]

    def get_cases_by_vendor(self, vendor: str) -> List[PCNLChallengeCase]:
        return [c for c in self._cases.values() if c.scanner_vendor.lower() == vendor.lower()]

    @property
    def all_cases(self) -> List[PCNLChallengeCase]:
        return list(self._cases.values())


# Pre-configured canonical challenge case catalog
CANONICAL_CHALLENGE_REGISTRY = ChallengeSetRegistry()

CANONICAL_CHALLENGE_REGISTRY.register_case(PCNLChallengeCase(
    case_id="CHALLENGE_01_RETRORENAL",
    categories=[ChallengeCategory.RETRORENAL_COLON],
    description="Posterolateral descending colon wrapped directly behind lower pole calyx.",
    scanner_vendor="Siemens",
    slice_thickness_mm=1.0,
    expected_difficulty="HIGH",
    primary_failure_mode_to_test="Rejects posterior lower trajectories where C_eff < 0 mm. Emits alternative corridor or NO_PLAN_CRITICAL_HAZARD if all corridors blocked."
))

CANONICAL_CHALLENGE_REGISTRY.register_case(PCNLChallengeCase(
    case_id="CHALLENGE_02_SUPRACOSTAL",
    categories=[ChallengeCategory.SUPRACOSTAL_ACCESS],
    description="Subdiaphragmatic kidney requiring intercostal or supracostal puncture above 11th or 12th rib.",
    scanner_vendor="GE",
    slice_thickness_mm=1.25,
    expected_difficulty="HIGH",
    primary_failure_mode_to_test="Evaluates rib, pleura, and diaphragm independently; flags pleural transgression risk advisory."
))

CANONICAL_CHALLENGE_REGISTRY.register_case(PCNLChallengeCase(
    case_id="CHALLENGE_03_COLLAPSED_PCS",
    categories=[ChallengeCategory.NONDILATED_COLLAPSED_PCS],
    description="Non-dilated, non-contrast renal pelvic calyx with no urine pooling.",
    scanner_vendor="Philips",
    slice_thickness_mm=1.0,
    expected_difficulty="MODERATE",
    primary_failure_mode_to_test="Classifies PCS as ESTIMATED/UNAVAILABLE; disables false coordinate lock and mandates clinician target review."
))

CANONICAL_CHALLENGE_REGISTRY.register_case(PCNLChallengeCase(
    case_id="CHALLENGE_04_STAGHORN",
    categories=[ChallengeCategory.LARGE_STAGHORN_CALCULUS],
    description="Complete branched staghorn calculus occupying renal pelvis and multiple calyx groups.",
    scanner_vendor="Canon",
    slice_thickness_mm=0.8,
    expected_difficulty="HIGH",
    primary_failure_mode_to_test="Guy's IV classification; computes residual unreached stone volume and multi-tract requirement estimation."
))

CANONICAL_CHALLENGE_REGISTRY.register_case(PCNLChallengeCase(
    case_id="CHALLENGE_05_HORSESHOE",
    categories=[ChallengeCategory.HORSESHOE_KIDNEY],
    description="Anteriorly malrotated kidneys fused across midline isthmus with aberrant lower pole vasculature.",
    scanner_vendor="Siemens",
    slice_thickness_mm=1.0,
    expected_difficulty="EXTREME",
    primary_failure_mode_to_test="Adapts to anterior calyceal orientation and vascular arborization; refrains from applying normal-kidney posterior assumptions."
))

CANONICAL_CHALLENGE_REGISTRY.register_case(PCNLChallengeCase(
    case_id="CHALLENGE_06_MALROTATION",
    categories=[ChallengeCategory.MALROTATED_KIDNEY],
    description="Congenitally malrotated kidney with anteriorly directed renal pelvis and laterally oriented calyces.",
    scanner_vendor="GE",
    slice_thickness_mm=1.25,
    expected_difficulty="HIGH",
    primary_failure_mode_to_test="Computes patient-specific access vector based on actual calyx-neck axis rather than canonical Brodel plane."
))

CANONICAL_CHALLENGE_REGISTRY.register_case(PCNLChallengeCase(
    case_id="CHALLENGE_07_SCOLIOSIS",
    categories=[ChallengeCategory.SEVERE_SCOLIOSIS],
    description="Severe thoracolumbar scoliosis distorting costal margins and paraspinal musculature.",
    scanner_vendor="Philips",
    slice_thickness_mm=1.5,
    expected_difficulty="HIGH",
    primary_failure_mode_to_test="Calculates rib crossings and tract angles in true 3D space without assuming standard orthogonal planes."
))

CANONICAL_CHALLENGE_REGISTRY.register_case(PCNLChallengeCase(
    case_id="CHALLENGE_08_HYDRONEPHROSIS",
    categories=[ChallengeCategory.SEVERE_HYDRONEPHROSIS],
    description="Massively dilated collecting system with thin parenchymal mantle.",
    scanner_vendor="Canon",
    slice_thickness_mm=1.0,
    expected_difficulty="MODERATE",
    primary_failure_mode_to_test="Evaluates calyceal wall visibility dynamically (DIRECT/PARTIAL); does not assume volume alone guarantees infundibular identification."
))

CANONICAL_CHALLENGE_REGISTRY.register_case(PCNLChallengeCase(
    case_id="CHALLENGE_09_DUPLEX",
    categories=[ChallengeCategory.DUPLICATED_COLLECTING_SYSTEM],
    description="Complete duplex collecting system with separate upper and lower pole moieties.",
    scanner_vendor="Siemens",
    slice_thickness_mm=1.0,
    expected_difficulty="HIGH",
    primary_failure_mode_to_test="Evaluates stone location within specific moiety; scores Guy's score strictly per stone multiplicity and anatomical abnormality."
))

CANONICAL_CHALLENGE_REGISTRY.register_case(PCNLChallengeCase(
    case_id="CHALLENGE_10_MULTIPLE_CALCULI",
    categories=[ChallengeCategory.MULTIPLE_CALICEAL_CALCULI],
    description="Multiple discrete stones distributed across lower, middle, and upper pole calyces.",
    scanner_vendor="GE",
    slice_thickness_mm=1.25,
    expected_difficulty="HIGH",
    primary_failure_mode_to_test="Computes S.T.O.N.E. score (5-13); evaluates primary access calyx versus secondary flexible scope reach."
))

CANONICAL_CHALLENGE_REGISTRY.register_case(PCNLChallengeCase(
    case_id="CHALLENGE_11_HIGH_KIDNEY",
    categories=[ChallengeCategory.HIGH_KIDNEY_T11_T12],
    description="High intra-thoracic renal position with upper pole calyces projecting above T11/T12.",
    scanner_vendor="Philips",
    slice_thickness_mm=1.0,
    expected_difficulty="HIGH",
    primary_failure_mode_to_test="Evaluates all corridors; highlights intercostal/supracostal requirement and associated hazard clearance."
))

CANONICAL_CHALLENGE_REGISTRY.register_case(PCNLChallengeCase(
    case_id="CHALLENGE_12_MOTION_ARTIFACT",
    categories=[ChallengeCategory.SEVERE_MOTION_METAL_ARTIFACT],
    description="Significant respiratory motion blur and bilateral metallic hip prosthesis streak artifacts.",
    scanner_vendor="Canon",
    slice_thickness_mm=2.0,
    expected_difficulty="EXTREME",
    primary_failure_mode_to_test="Expands uncertainty envelope; if boundary cannot be resolved with clinical confidence, outputs NO_PLAN_UNCERTAINTY_EXCEEDED."
))
