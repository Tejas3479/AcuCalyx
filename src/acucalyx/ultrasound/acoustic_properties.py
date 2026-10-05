"""
AcuCalyx Ultrasound: Calibrated Tissue Acoustic Properties & Attenuation Models
Governed by Milestone M14B of ACU-M14-EXEC-PLAN-2026-V2.

Provides:
1. Calibrated tissue acoustic properties (sound speed, density, impedance, attenuation, backscatter).
2. Two-stage CT classification mapping (HU + organ priors).
3. Physics-correct roundtrip acoustic attenuation with ln(10)/10 scaling.
4. Acoustic reflection and transmission coefficients at tissue boundaries.
"""

from dataclasses import dataclass
import enum
import math
from typing import Dict, Optional, Tuple


class AcousticTissueClass(str, enum.Enum):
    AIR_GAS = "AIR_GAS"
    FAT = "FAT"
    MUSCLE = "MUSCLE"
    RENAL_PARENCHYMA = "RENAL_PARENCHYMA"
    URINE_FLUID = "URINE_FLUID"
    CORTICAL_BONE = "CORTICAL_BONE"
    CALCULUS_OXALATE = "CALCULUS_OXALATE"
    CALCULUS_URIC = "CALCULUS_URIC"
    BLOOD_VESSEL = "BLOOD_VESSEL"


@dataclass(frozen=True)
class CalibratedAcousticMedium:
    """
    Physical acoustic parameters of a biological medium calibrated against
    IEC 60601-2-37 literature and NIST-traceable standards.
    """
    tissue_class: AcousticTissueClass
    speed_of_sound_m_s: float
    density_g_cm3: float
    attenuation_db_cm_mhz: float
    attenuation_exponent: float  # Frequency power law exponent n (typically 1.0 - 1.2)
    backscatter_coefficient: float  # Relative diffuse scattering intensity (0.0 to 1.0)
    nominal_hu: float

    @property
    def acoustic_impedance_mrayl(self) -> float:
        """Acoustic impedance Z = rho * c in MRayl (10^6 kg/(m^2*s))."""
        return (self.density_g_cm3 * 1000.0) * self.speed_of_sound_m_s * 1e-6


# Aliases
TissueAcousticProperties = CalibratedAcousticMedium


# Standard Calibrated Media Registry (IEC 60601-2-37 & ICRU Report 44 Reference Values)
STANDARD_ACOUSTIC_MEDIA: Dict[AcousticTissueClass, CalibratedAcousticMedium] = {
    AcousticTissueClass.AIR_GAS: CalibratedAcousticMedium(
        tissue_class=AcousticTissueClass.AIR_GAS,
        speed_of_sound_m_s=343.0,
        density_g_cm3=0.0012,
        attenuation_db_cm_mhz=12.0,  # Extreme acoustic absorption
        attenuation_exponent=1.2,
        backscatter_coefficient=0.01,
        nominal_hu=-950.0,
    ),
    AcousticTissueClass.FAT: CalibratedAcousticMedium(
        tissue_class=AcousticTissueClass.FAT,
        speed_of_sound_m_s=1450.0,
        density_g_cm3=0.92,
        attenuation_db_cm_mhz=0.63,
        attenuation_exponent=1.0,
        backscatter_coefficient=0.35,
        nominal_hu=-100.0,
    ),
    AcousticTissueClass.MUSCLE: CalibratedAcousticMedium(
        tissue_class=AcousticTissueClass.MUSCLE,
        speed_of_sound_m_s=1580.0,
        density_g_cm3=1.06,
        attenuation_db_cm_mhz=1.09,
        attenuation_exponent=1.0,
        backscatter_coefficient=0.50,
        nominal_hu=45.0,
    ),
    AcousticTissueClass.RENAL_PARENCHYMA: CalibratedAcousticMedium(
        tissue_class=AcousticTissueClass.RENAL_PARENCHYMA,
        speed_of_sound_m_s=1560.0,
        density_g_cm3=1.05,
        attenuation_db_cm_mhz=0.54,
        attenuation_exponent=1.0,
        backscatter_coefficient=0.45,
        nominal_hu=38.0,
    ),
    AcousticTissueClass.URINE_FLUID: CalibratedAcousticMedium(
        tissue_class=AcousticTissueClass.URINE_FLUID,
        speed_of_sound_m_s=1490.0,
        density_g_cm3=1.00,
        attenuation_db_cm_mhz=0.02,  # Very low attenuation -> distal enhancement
        attenuation_exponent=1.0,
        backscatter_coefficient=0.03,  # Anechoic
        nominal_hu=5.0,
    ),
    AcousticTissueClass.CORTICAL_BONE: CalibratedAcousticMedium(
        tissue_class=AcousticTissueClass.CORTICAL_BONE,
        speed_of_sound_m_s=3500.0,
        density_g_cm3=1.90,
        attenuation_db_cm_mhz=6.50,  # High attenuation + impedance mismatch -> acoustic shadow
        attenuation_exponent=1.1,
        backscatter_coefficient=0.85,
        nominal_hu=900.0,
    ),
    AcousticTissueClass.CALCULUS_OXALATE: CalibratedAcousticMedium(
        tissue_class=AcousticTissueClass.CALCULUS_OXALATE,
        speed_of_sound_m_s=3800.0,
        density_g_cm3=2.10,
        attenuation_db_cm_mhz=15.0,  # Severe acoustic extinction -> dense posterior shadow cone
        attenuation_exponent=1.1,
        backscatter_coefficient=0.95,
        nominal_hu=1200.0,
    ),
    AcousticTissueClass.CALCULUS_URIC: CalibratedAcousticMedium(
        tissue_class=AcousticTissueClass.CALCULUS_URIC,
        speed_of_sound_m_s=2800.0,
        density_g_cm3=1.55,
        attenuation_db_cm_mhz=8.0,
        attenuation_exponent=1.0,
        backscatter_coefficient=0.80,
        nominal_hu=450.0,
    ),
    AcousticTissueClass.BLOOD_VESSEL: CalibratedAcousticMedium(
        tissue_class=AcousticTissueClass.BLOOD_VESSEL,
        speed_of_sound_m_s=1570.0,
        density_g_cm3=1.06,
        attenuation_db_cm_mhz=0.18,
        attenuation_exponent=1.2,
        backscatter_coefficient=0.15,
        nominal_hu=40.0,
    ),
}

# Constant factor: ln(10) / 10 for converting dB to natural nepers/linear power scale
LN10_DIV_10: float = math.log(10.0) / 10.0  # Approx 0.2302585092994046


def classify_ct_voxel_to_acoustic_medium(
    hu_value: float,
    segmented_organ: Optional[str] = None,
) -> CalibratedAcousticMedium:
    """
    Two-stage classifier: incorporates organ prior label if available,
    falling back to verified CT Hounsfield range thresholds.
    """
    if segmented_organ is not None:
        organ_clean = segmented_organ.lower()
        if "stone" in organ_clean or "calculus" in organ_clean:
            if hu_value < 600.0:
                return STANDARD_ACOUSTIC_MEDIA[AcousticTissueClass.CALCULUS_URIC]
            return STANDARD_ACOUSTIC_MEDIA[AcousticTissueClass.CALCULUS_OXALATE]
        if "rib" in organ_clean or "bone" in organ_clean or "skeleton" in organ_clean:
            return STANDARD_ACOUSTIC_MEDIA[AcousticTissueClass.CORTICAL_BONE]
        if "kidney" in organ_clean or "parenchyma" in organ_clean:
            return STANDARD_ACOUSTIC_MEDIA[AcousticTissueClass.RENAL_PARENCHYMA]
        if "urine" in organ_clean or "calyx" in organ_clean or "pelvis" in organ_clean or "fluid" in organ_clean:
            return STANDARD_ACOUSTIC_MEDIA[AcousticTissueClass.URINE_FLUID]
        if "vessel" in organ_clean or "artery" in organ_clean or "vein" in organ_clean:
            return STANDARD_ACOUSTIC_MEDIA[AcousticTissueClass.BLOOD_VESSEL]
        if "bowel" in organ_clean and hu_value < -200:
            return STANDARD_ACOUSTIC_MEDIA[AcousticTissueClass.AIR_GAS]

    # HU-based thresholding
    if hu_value < -500.0:
        return STANDARD_ACOUSTIC_MEDIA[AcousticTissueClass.AIR_GAS]
    elif -180.0 <= hu_value < -20.0:
        return STANDARD_ACOUSTIC_MEDIA[AcousticTissueClass.FAT]
    elif -20.0 <= hu_value <= 18.0:
        return STANDARD_ACOUSTIC_MEDIA[AcousticTissueClass.URINE_FLUID]
    elif 18.0 < hu_value <= 60.0:
        return STANDARD_ACOUSTIC_MEDIA[AcousticTissueClass.RENAL_PARENCHYMA]
    elif 60.0 < hu_value <= 250.0:
        return STANDARD_ACOUSTIC_MEDIA[AcousticTissueClass.MUSCLE]
    elif 250.0 < hu_value <= 700.0:
        return STANDARD_ACOUSTIC_MEDIA[AcousticTissueClass.CALCULUS_URIC]
    elif hu_value > 700.0:
        return STANDARD_ACOUSTIC_MEDIA[AcousticTissueClass.CALCULUS_OXALATE]
    else:
        return STANDARD_ACOUSTIC_MEDIA[AcousticTissueClass.MUSCLE]


get_calibrated_tissue_acoustics = classify_ct_voxel_to_acoustic_medium


def compute_two_way_attenuation_intensity(
    integrated_attenuation_db_cm: float,
    frequency_mhz: float,
    initial_intensity: float = 1.0,
) -> float:
    """
    Computes linear two-way acoustic roundtrip intensity transmission with
    dimensionally correct conversion from dB to natural exponential.

    I_roundtrip = I_0 * exp(-2 * (ln(10) / 10) * integral(alpha_dB * f^n * ds))
    """
    if integrated_attenuation_db_cm < 0:
        integrated_attenuation_db_cm = 0.0

    exponent = 2.0 * LN10_DIV_10 * integrated_attenuation_db_cm * frequency_mhz
    if exponent > 60.0:  # Prevent underflow
        return 0.0
    return initial_intensity * math.exp(-exponent)


def compute_boundary_reflection(
    z1_mrayl: float,
    z2_mrayl: float,
) -> Tuple[float, float, float]:
    """
    Computes reflection and transmission at normal incidence across an acoustic interface.
    Returns:
    - amplitude_reflection_r: (Z2 - Z1) / (Z2 + Z1)
    - power_reflection_R: r^2
    - power_transmission_T: 1 - R
    """
    denom = z2_mrayl + z1_mrayl
    if denom <= 1e-9:
        return 0.0, 0.0, 1.0

    r = (z2_mrayl - z1_mrayl) / denom
    R = r * r
    T = max(0.0, 1.0 - R)
    return r, R, T
