"""
AcuCalyx Stones: Protocol-Calibrated DECT Stone Intelligence Enrichment

Implements Workstream E of Phase 3 (M1 Milestone):
Optional enrichment module activated only when Dual-Energy CT (DECT) data
(e.g., 80/140 kVp or Sn100/Sn140) is available.

Governing Principles (Frozen v3.1):
- Not mandatory for core PCNL access planning.
- Employs a protocol/scanner-calibrated classifier, rejecting universal cutoffs.
- Classifies: Uric-acid compatible, Calcium-containing compatible, Cystine-compatible,
  or Indeterminate / Mixed / Uncertain.
- Clinically honest: explicitly marks struvite and mixed apatite with high uncertainty
  per peer-reviewed in-vivo literature limitations.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple
import numpy as np


class DECTStoneClass(str, Enum):
    URIC_ACID_COMPATIBLE = "URIC_ACID_COMPATIBLE"
    CALCIUM_CONTAINING_COMPATIBLE = "CALCIUM_CONTAINING_COMPATIBLE"
    CYSTINE_COMPATIBLE = "CYSTINE_COMPATIBLE"
    INDETERMINATE_MIXED_UNCERTAIN = "INDETERMINATE_MIXED_UNCERTAIN"


@dataclass(frozen=True)
class DECTCalibrationProfile:
    """Scanner- and kVp-pair specific calibration parameters."""
    profile_id: str
    scanner_model: str
    low_energy_kvp: float   # e.g., 80 or Sn100
    high_energy_kvp: float  # e.g., 140 or Sn140
    uric_acid_cutoff_max: float      # e.g., 1.10
    cystine_cutoff_min: float        # e.g., 1.15
    cystine_cutoff_max: float        # e.g., 1.25
    calcium_cutoff_min: float        # e.g., 1.30


# Baseline clinical literature profile (Siemens Somatom Definition Flash 80/140 kVp)
DEFAULT_CLINICAL_DECT_PROFILE = DECTCalibrationProfile(
    profile_id="SIEMENS_FLASH_80_140",
    scanner_model="Siemens_Dual_Source_Flash",
    low_energy_kvp=80.0,
    high_energy_kvp=140.0,
    uric_acid_cutoff_max=1.10,
    cystine_cutoff_min=1.15,
    cystine_cutoff_max=1.28,
    calcium_cutoff_min=1.30
)


@dataclass(frozen=True)
class DECTStoneAnalysisResult:
    """Enrichment report for a calculus evaluated with Dual-Energy CT."""
    stone_id: int
    mean_hu_low_energy: float
    mean_hu_high_energy: float
    dual_energy_ratio: float
    predicted_composition: DECTStoneClass
    confidence_score: float             # [0.0, 1.0] calibrated probability
    is_struvite_suspected: bool         # Flags in-vivo classification ambiguity
    clinical_notice: str
    calibration_profile_used: str


def classify_stone_dual_energy_spectrum(
    stone_id: int,
    stone_mask: np.ndarray,
    volume_low_kvp_hu: np.ndarray,
    volume_high_kvp_hu: np.ndarray,
    calibration: DECTCalibrationProfile = DEFAULT_CLINICAL_DECT_PROFILE
) -> DECTStoneAnalysisResult:
    """
    Computes protocol-calibrated Dual-Energy Ratio (DER) and classifies composition.
    
    DER = Mean_HU(low_energy) / Mean_HU(high_energy)
    """
    if not np.any(stone_mask):
        return DECTStoneAnalysisResult(
            stone_id=stone_id,
            mean_hu_low_energy=0.0,
            mean_hu_high_energy=0.0,
            dual_energy_ratio=1.0,
            predicted_composition=DECTStoneClass.INDETERMINATE_MIXED_UNCERTAIN,
            confidence_score=0.0,
            is_struvite_suspected=False,
            clinical_notice="Stone mask is empty; cannot evaluate dual-energy spectrum.",
            calibration_profile_used=calibration.profile_id
        )

    hu_low = volume_low_kvp_hu[stone_mask].astype(np.float64)
    hu_high = volume_high_kvp_hu[stone_mask].astype(np.float64)

    mean_low = float(np.mean(hu_low))
    mean_high = float(np.mean(hu_high))

    # Guard against division by low/negative values
    if mean_high < 50.0:
        der = 1.0
        predicted = DECTStoneClass.INDETERMINATE_MIXED_UNCERTAIN
        conf = 0.2
        notice = "High-energy CT attenuation is too low (<50 HU) for reliable dual-energy ratio estimation."
    else:
        der = mean_low / mean_high

        if der <= calibration.uric_acid_cutoff_max:
            predicted = DECTStoneClass.URIC_ACID_COMPATIBLE
            conf = 0.92
            notice = (
                f"Dual-energy ratio ({der:.2f}) is consistent with pure or predominantly uric acid calculus. "
                "Potential candidate for oral chemolysis if clinically indicated."
            )
        elif calibration.cystine_cutoff_min <= der <= calibration.cystine_cutoff_max:
            predicted = DECTStoneClass.CYSTINE_COMPATIBLE
            conf = 0.75
            notice = (
                f"Dual-energy ratio ({der:.2f}) falls in the cystine spectral window. "
                "Intermediate density calculus; correlate with 24-hour urine cystine if indicated."
            )
        elif der >= calibration.calcium_cutoff_min:
            predicted = DECTStoneClass.CALCIUM_CONTAINING_COMPATIBLE
            conf = 0.95
            notice = (
                f"Dual-energy ratio ({der:.2f}) demonstrates pronounced photoelectric absorption "
                "characteristic of dense calcium oxalate / calcium phosphate mineralization."
            )
        else:
            predicted = DECTStoneClass.INDETERMINATE_MIXED_UNCERTAIN
            conf = 0.45
            notice = (
                f"Dual-energy ratio ({der:.2f}) falls in an overlapping spectral transition zone. "
                "Mixed composition, low-density calcium, or struvite suspected."
            )

    # In-vivo struvite clinical check: struvite frequently overlaps between 1.10 and 1.25
    struvite_ambiguity = (1.08 <= der <= 1.28) and (300.0 <= mean_low <= 900.0)

    return DECTStoneAnalysisResult(
        stone_id=stone_id,
        mean_hu_low_energy=mean_low,
        mean_hu_high_energy=mean_high,
        dual_energy_ratio=float(der),
        predicted_composition=predicted,
        confidence_score=conf,
        is_struvite_suspected=struvite_ambiguity,
        clinical_notice=notice,
        calibration_profile_used=calibration.profile_id
    )
