"""
AcuCalyx Fluoroscopy: Virtual Collecting-System Contrast Visualization

Implements Step 4.06 of Phase 4 (Frozen v4.1):
Provides simulated pelvicalyceal contrast delineation for PCNL fluoroscopic rehearsal:
- Mode A (Mask Contour): Projects boundary wireframe of calyces.
- Mode B (Attenuation Boost): Elevates collecting-system voxel values (+400 to +600 HU)
  to simulate iodinated contrast (retrograde pyelogram / RP).
- Mode C (Baseline): Standard non-contrast CT attenuation.

Clinical Disclosure Invariant:
Explicitly labeled 'Virtual Collecting-System Contrast Visualization' to clarify that
it is a geometric/attenuation visualization rather than a computational fluid-dynamics simulation.
"""

from enum import Enum
from typing import Optional, Tuple
import numpy as np
from scipy import ndimage


class VirtualContrastMode(str, Enum):
    MODE_A_MASK_CONTOUR = "MODE_A_MASK_CONTOUR"
    MODE_B_ATTENUATION_BOOST = "MODE_B_ATTENUATION_BOOST"
    MODE_C_BASELINE_NONCONTRAST = "MODE_C_BASELINE_NONCONTRAST"


def apply_virtual_contrast_to_volume(
    ct_volume_hu: np.ndarray,
    collecting_system_mask: Optional[np.ndarray],
    mode: VirtualContrastMode = VirtualContrastMode.MODE_B_ATTENUATION_BOOST,
    contrast_hu_boost: float = 500.0
) -> np.ndarray:
    """
    Applies synthetic radiopaque contrast to the collecting system subvolume.
    """
    if collecting_system_mask is None or not np.any(collecting_system_mask):
        return ct_volume_hu.copy()

    if mode == VirtualContrastMode.MODE_C_BASELINE_NONCONTRAST:
        return ct_volume_hu.copy()

    vol = ct_volume_hu.copy()
    pcs_mask = collecting_system_mask > 0

    if mode == VirtualContrastMode.MODE_B_ATTENUATION_BOOST:
        # Boost attenuation inside collecting cavity to simulate iodinated contrast
        vol[pcs_mask] = np.maximum(vol[pcs_mask], contrast_hu_boost)

    elif mode == VirtualContrastMode.MODE_A_MASK_CONTOUR:
        # Boost only the boundary shell of the cavity to produce a hollow wireframe
        struct = ndimage.generate_binary_structure(3, 1)
        eroded = ndimage.binary_erosion(pcs_mask, structure=struct)
        boundary = pcs_mask & (~eroded)
        vol[boundary] = np.maximum(vol[boundary], contrast_hu_boost)

    return vol
