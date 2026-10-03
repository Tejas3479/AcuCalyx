"""
AcuCalyx Stone Engine: Attenuation Profiling and Density Characterization

Adheres strictly to the AcuCalyx v2 clinical guidelines:
- Measures CT attenuation distribution in Hounsfield Units (HU)
- Extracts mean, median, peak, and standard deviation HU
- Categorizes density profile into Low (<500), Intermediate (500-1000), and High (>1000) fractions
- Explicitly flags composition inference as 'Not validated / unavailable'
  unless validated dual-energy or spectroscopy imaging is supplied.
"""

from dataclasses import dataclass
from typing import Dict, Any
import numpy as np

from acucalyx.stones.candidate_detection import RawStoneCandidate


@dataclass(frozen=True)
class StoneAttenuationProfile:
    """Quantitative attenuation statistics of a kidney stone."""
    stone_id: int
    mean_hu: float
    median_hu: float
    peak_hu: float
    std_hu: float
    min_hu: float
    fraction_low_under_500hu: float       # < 500 HU (soft matrix / low density)
    fraction_intermediate_500_1000hu: float # 500 - 1000 HU
    fraction_high_over_1000hu: float      # > 1000 HU (dense calcium / brushite)
    composition_inference: str           # Must be 'Not validated / unavailable' in v2 baseline


def compute_stone_attenuation(
    candidate: RawStoneCandidate,
    ct_volume_hu: np.ndarray
) -> StoneAttenuationProfile:
    """
    Extracts CT attenuation distribution of voxels inside the candidate mask.
    """
    mask = candidate.voxel_mask
    stone_hu_values = ct_volume_hu[mask].astype(np.float64)
    
    if len(stone_hu_values) == 0:
        return StoneAttenuationProfile(
            stone_id=candidate.candidate_id,
            mean_hu=0.0,
            median_hu=0.0,
            peak_hu=0.0,
            std_hu=0.0,
            min_hu=0.0,
            fraction_low_under_500hu=0.0,
            fraction_intermediate_500_1000hu=0.0,
            fraction_high_over_1000hu=0.0,
            composition_inference="Not validated / unavailable"
        )
        
    mean_val = float(np.mean(stone_hu_values))
    median_val = float(np.median(stone_hu_values))
    peak_val = float(np.max(stone_hu_values))
    std_val = float(np.std(stone_hu_values))
    min_val = float(np.min(stone_hu_values))
    
    n_total = len(stone_hu_values)
    frac_low = float(np.sum(stone_hu_values < 500.0) / n_total)
    frac_inter = float(np.sum((stone_hu_values >= 500.0) & (stone_hu_values <= 1000.0)) / n_total)
    frac_high = float(np.sum(stone_hu_values > 1000.0) / n_total)
    
    return StoneAttenuationProfile(
        stone_id=candidate.candidate_id,
        mean_hu=mean_val,
        median_hu=median_val,
        peak_hu=peak_val,
        std_hu=std_val,
        min_hu=min_val,
        fraction_low_under_500hu=frac_low,
        fraction_intermediate_500_1000hu=frac_inter,
        fraction_high_over_1000hu=frac_high,
        composition_inference="Not validated / unavailable"
    )
