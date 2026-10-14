"""
AcuCalyx Synthetic Calibration Phantom Generator (Test Interface)

Re-exports from acucalyx.synthetic.phantom_generator for backward-compatibility with tests.
"""

from acucalyx.synthetic.phantom_generator import (
    PhantomGroundTruth,
    generate_synthetic_pcnl_phantom,
    save_phantom_to_nifti
)

__all__ = [
    "PhantomGroundTruth",
    "generate_synthetic_pcnl_phantom",
    "save_phantom_to_nifti"
]
