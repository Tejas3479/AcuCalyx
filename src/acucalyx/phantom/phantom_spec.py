"""
AcuCalyx Phantom: Multi-Material Anthropomorphic Torso Phantom Specification (Phase 5 / M3)

Governing Requirement: Frozen Plan v5.1 (Section 3 & Section 4)
Defines:
- Physical layer specifications, tissue-mimicking material recipes, target CT attenuation (HU),
  and acceptance tolerance bands.
- Metrology uncertainty budget (manufacturing, registration, and ground-truth measurement errors).
- Automated CT attenuation validation engine comparing measured phantom CT numbers against design targets.
"""

from dataclasses import dataclass, field
import math
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class PhantomTissueLayer:
    """Specification of an individual anatomical layer in the physical phantom."""
    name: str
    material_description: str
    target_hu: float
    acceptable_hu_range: Tuple[float, float]
    shore_hardness: Optional[str]
    fabrication_method: str
    functional_purpose: str

    def is_attenuation_valid(self, measured_hu: float) -> bool:
        """Checks if measured CT attenuation falls within the certified acceptance band."""
        low, high = self.acceptable_hu_range
        return low <= measured_hu <= high


@dataclass(frozen=True)
class MetrologyUncertaintyBudget:
    """
    Traceable error budget across the unbroken metrology chain:
    Omega_CT -> Omega_phantom -> Omega_carm -> Omega_GT
    """
    sigma_mfg_mm: float = 0.60   # Manufacturing & material shrinkage deviation
    sigma_reg_mm: float = 0.50   # Phantom-to-C-arm fiducial registration error (TRE)
    sigma_meas_mm: float = 0.25  # Ground truth measurement uncertainty (post-puncture CT/CMM)

    @property
    def cumulative_uncertainty_mm(self) -> float:
        """Combined standard uncertainty sigma_total = sqrt(sum sigma_i^2)."""
        return math.sqrt(self.sigma_mfg_mm**2 + self.sigma_reg_mm**2 + self.sigma_meas_mm**2)

    @property
    def expanded_uncertainty_k2_mm(self) -> float:
        """Expanded uncertainty U_95 at k=2 coverage factor (approx 95% confidence interval)."""
        return 2.0 * self.cumulative_uncertainty_mm

    def is_acceptable(self, max_expanded_mm: float = 2.0) -> bool:
        """Verifies if expanded metrology uncertainty is within the clinical validation budget."""
        return self.expanded_uncertainty_k2_mm <= max_expanded_mm

    def generate_uncertainty_report(self) -> Dict[str, Any]:
        """Produces a structured breakdown of the metrology budget."""
        comb = self.cumulative_uncertainty_mm
        return {
            "sigma_mfg_mm": self.sigma_mfg_mm,
            "sigma_reg_mm": self.sigma_reg_mm,
            "sigma_meas_mm": self.sigma_meas_mm,
            "combined_standard_uncertainty_mm": round(comb, 3),
            "expanded_uncertainty_k2_mm": round(self.expanded_uncertainty_k2_mm, 3),
            "is_acceptable": self.is_acceptable(),
            "confidence_level": "95% (k=2 coverage factor)"
        }


@dataclass
class AnthropomorphicPhantomSpec:
    """Complete specification of a patient-specific anthropomorphic flank phantom."""
    name: str
    layers: Dict[str, PhantomTissueLayer] = field(default_factory=dict)
    fiducial_count: int = 4
    fiducial_diameter_mm: float = 2.0
    fiducial_material: str = "Ceramic Silicon Nitride (Si3N4)"
    uncertainty_budget: MetrologyUncertaintyBudget = field(default_factory=MetrologyUncertaintyBudget)

    def validate_layer_attenuation(self, layer_name: str, measured_hu: float) -> Tuple[bool, str]:
        """Validates a single tissue layer's measured CT attenuation against specification."""
        if layer_name not in self.layers:
            return False, f"Unknown layer '{layer_name}' in phantom spec"
        layer = self.layers[layer_name]
        is_ok = layer.is_attenuation_valid(measured_hu)
        low, high = layer.acceptable_hu_range
        if is_ok:
            msg = f"PASS: Layer '{layer_name}' measured {measured_hu:.1f} HU is within [{low:.1f}, {high:.1f}] HU."
        else:
            msg = f"FAIL: Layer '{layer_name}' measured {measured_hu:.1f} HU is OUTSIDE [{low:.1f}, {high:.1f}] HU (target: {layer.target_hu:.1f} HU)."
        return is_ok, msg

    def validate_phantom_scan(self, ct_measurements: Dict[str, float]) -> Dict[str, Any]:
        """
        Validates all measured CT numbers from a post-fabrication verification scan.
        """
        results = {}
        all_passed = True
        for layer_name, measured_hu in ct_measurements.items():
            if layer_name in self.layers:
                is_valid, msg = self.validate_layer_attenuation(layer_name, measured_hu)
                results[layer_name] = {
                    "measured_hu": measured_hu,
                    "target_hu": self.layers[layer_name].target_hu,
                    "acceptable_range": list(self.layers[layer_name].acceptable_hu_range),
                    "passed": is_valid,
                    "message": msg
                }
                if not is_valid:
                    all_passed = False
            else:
                results[layer_name] = {
                    "measured_hu": measured_hu,
                    "passed": False,
                    "message": f"Unrecognized layer '{layer_name}'"
                }
                all_passed = False

        return {
            "phantom_name": self.name,
            "all_layers_passed": all_passed,
            "layer_results": results,
            "uncertainty_budget": self.uncertainty_budget.generate_uncertainty_report()
        }


# Standard Presets per Frozen Plan v5.1 Section 4
STANDARD_ANTHROPOMORPHIC_SPEC = AnthropomorphicPhantomSpec(
    name="AcuCalyx_Standard_Anthropomorphic_Flank_Phantom_v5.1",
    layers={
        "skin_fat": PhantomTissueLayer(
            name="skin_fat",
            material_description="Shore 00-30 Platinum Silicone or 10% w/v Ballistics Gelatin",
            target_hu=-10.0,
            acceptable_hu_range=(-50.0, 20.0),
            shore_hardness="Shore 00-30",
            fabrication_method="Cast in negative flank shell",
            functional_purpose="Realistic skin compliance, fascial 'pop', and self-healing needle track"
        ),
        "rib_cage": PhantomTissueLayer(
            name="rib_cage",
            material_description="3D-printed PETG/PLA doped with 15% CaCO3 / BaSO4 powder",
            target_hu=850.0,
            acceptable_hu_range=(600.0, 1100.0),
            shore_hardness="Shore 75D",
            fabrication_method="FDM 3D printing at 0.15 mm layer height",
            functional_purpose="True radiographic shadow and rigid bony deflection barrier (10th-12th ribs)"
        ),
        "renal_parenchyma": PhantomTissueLayer(
            name="renal_parenchyma",
            material_description="Platinum-cure translucent silicone (Shore 10A)",
            target_hu=45.0,
            acceptable_hu_range=(30.0, 60.0),
            shore_hardness="Shore 10A",
            fabrication_method="Vacuum degassed casting in 2-part clamp mold",
            functional_purpose="Realistic capsular puncture resistance and optical post-puncture inspection"
        ),
        "collecting_system": PhantomTissueLayer(
            name="collecting_system",
            material_description="Hollow cast cavity filled with saline or dilute iodinated contrast",
            target_hu=10.0,
            acceptable_hu_range=(0.0, 350.0),
            shore_hardness=None,
            fabrication_method="Lost-core soluble PVA infundibular tree casting (dissolved at 40°C)",
            functional_purpose="Exact 3D lumen of calyces and pelvis with Luer-lock retrograde port"
        ),
        "target_calculi": PhantomTissueLayer(
            name="target_calculi",
            material_description="Dental stone / Plaster of Paris doped with 10% BaSO4 beads",
            target_hu=1400.0,
            acceptable_hu_range=(1200.0, 1700.0),
            shore_hardness="Shore 85D",
            fabrication_method="Precision silicone micro-molding and embedding",
            functional_purpose="Acoustic shadowing, high radiopacity, and tactile 'clink' upon needle contact"
        ),
        "retrorenal_colon": PhantomTissueLayer(
            name="retrorenal_colon",
            material_description="Hollow silicone tube filled with air lumen and methylcellulose",
            target_hu=-800.0,
            acceptable_hu_range=(-900.0, -600.0),
            shore_hardness="Shore 20A",
            fabrication_method="Extrusion and casting in flank chassis",
            functional_purpose="Hazard avoidance barrier to evaluate retrorenal colon perforation"
        ),
        "pleural_lung_base": PhantomTissueLayer(
            name="pleural_lung_base",
            material_description="Closed-cell flexible polyurethane foam",
            target_hu=-750.0,
            acceptable_hu_range=(-850.0, -650.0),
            shore_hardness="Shore 15A",
            fabrication_method="Pre-formed insert mounted above 10th rib",
            functional_purpose="Thoracic boundary to evaluate pneumothorax / hydrothorax risk on supracostal access"
        ),
        "fiducials": PhantomTissueLayer(
            name="fiducials",
            material_description="Precision grade ceramic (Si3N4) spheres, Ø 2.00 ± 0.01 mm",
            target_hu=3000.0,
            acceptable_hu_range=(2500.0, 4000.0),
            shore_hardness="Rigid Ceramic",
            fabrication_method="Press-fit into calibrated chassis sockets",
            functional_purpose="Sub-millimeter rigid registration ground truth without metallic bloom artifact"
        )
    },
    fiducial_count=4,
    fiducial_diameter_mm=2.0,
    fiducial_material="Ceramic Silicon Nitride (Si3N4)",
    uncertainty_budget=MetrologyUncertaintyBudget(sigma_mfg_mm=0.6, sigma_reg_mm=0.5, sigma_meas_mm=0.25)
)
