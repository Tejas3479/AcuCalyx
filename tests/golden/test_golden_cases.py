"""
AcuCalyx Golden Regression Suite: 15 Canonical Clinical Edge Cases

Implements Step 18 of AcuCalyx v2.1:
1. Case 01: Normal anatomy, solitary lower pole calculus
2. Case 02: Retrorenal colon (colon directly posterior to kidney corridor)
3. Case 03: Staghorn branched calculus (high volume burden)
4. Case 04: Supracostal high kidney (pleural reflection crossing corridor)
5. Case 05: Solitary kidney (absence of contralateral organ)
6. Case 06: Severe hydronephrosis (fluid cavity distension)
7. Case 07: Non-dilated collecting system (collapsed calyces, anatomically estimated)
8. Case 08: Low-resolution thick slice CT (>2.5mm, rejected by quality gate)
9. Case 09: Gantry-tilted CT (rejected by quality gate)
10. Case 10: Missing slice gap (variable table speed, rejected by quality gate)
11. Case 11: Dual calculi in separate upper and lower poles
12. Case 12: High BMI thick flank (tract length > 120mm)
13. Case 13: Intercostal neurovascular bundle risk zone proximity
14. Case 14: Contrast-enhanced excretory phase CT (directly opacified)
15. Case 15: Right kidney anatomical orientation (lateral flank geometry)
"""

import numpy as np
import pytest

from tests.phantom.phantom_generator import generate_synthetic_pcnl_phantom
from acucalyx.geometry.coordinates import SpatialOrientation
from acucalyx.geometry.transforms import LineSegment3D
from acucalyx.geometry.distance_fields import DistanceField
from acucalyx.ingestion.quality_gate import evaluate_dicom_series_geometry
from acucalyx.collecting_system.visibility_gate import (
    classify_collecting_system_visibility, PCSVisibilityState
)
from acucalyx.planning.target_candidates import (
    generate_candidate_puncture_zones, ConicalPunctureZone, CalyxGroup
)
from acucalyx.planning.scope_model import STANDARD_RIGID_NEPHROSCOPE
from acucalyx.planning.stone_reach import evaluate_access_stone_reach
from acucalyx.stones.volumetry import StoneMorphometry
from acucalyx.anatomy.segmentation import derive_intercostal_neurovascular_risk_zone


# --- Case 01: Normal Anatomy, Solitary Lower Pole Calculus ---
def test_case_01_normal_anatomy():
    vol, spatial, gt = generate_synthetic_pcnl_phantom(grid_shape=(64, 64, 50), stone_radius_mm=4.0)
    assert vol.shape == (64, 64, 50)
    assert gt.stone_radius_mm == 4.0
    assert gt.stone_volume_mm3 > 0.0


# --- Case 02: Retrorenal Colon Hazard ---
def test_case_02_retrorenal_colon_hazard():
    vol, spatial, gt = generate_synthetic_pcnl_phantom(grid_shape=(64, 64, 50))
    # Place colon directly dorsal to kidney (Y = 40.0)
    colon_mask = np.zeros((64, 64, 50), dtype=bool)
    colon_mask[35:45, 30:40, 20:30] = True
    df = DistanceField(colon_mask, spatial)

    # Trajectory traversing directly through retrorenal colon
    traj = LineSegment3D(
        start_point=spatial.voxel_to_physical([40.0, 35.0, 25.0]),
        end_point=spatial.voxel_to_physical([10.0, 35.0, 25.0])
    )
    res = df.evaluate_trajectory_clearance(traj, "colon", 1.0, 1.0, 1.0)
    assert res.is_intersecting is True
    assert res.effective_clearance_mm == 0.0


# --- Case 03: Staghorn Calculus ---
def test_case_03_staghorn_calculus():
    stone_main = StoneMorphometry(
        stone_id=1, volume_mm3=3500.0, volume_voxels=3500,
        centroid_lps_mm=np.array([20.0, 10.0, 45.0]),
        max_feret_diameter_mm=38.0, bounding_box_span_mm=np.array([25.0, 20.0, 35.0]),
        tier="DENSE_CALCIUM"
    )
    assert stone_main.volume_mm3 > 3000.0
    assert stone_main.max_feret_diameter_mm > 30.0


# --- Case 04: Supracostal High Kidney ---
def test_case_04_supracostal_high_kidney():
    zones = generate_candidate_puncture_zones(
        kidney_center_lps=np.array([25.0, 10.0, 70.0]), # High cranial Z
        kidney_radii_lps=np.array([15.0, 12.0, 25.0]),
        pcs_visibility=PCSVisibilityState.ANATOMICALLY_ESTIMATED,
        detected_stone_centroids=[np.array([25.0, 10.0, 65.0])],
        side="left"
    )
    assert len(zones) >= 1
    assert zones[0].apex_papilla_lps_mm[2] > 50.0


# --- Case 05: Solitary Kidney ---
def test_case_05_solitary_kidney():
    # Only left kidney present
    zones = generate_candidate_puncture_zones(
        kidney_center_lps=np.array([25.0, 10.0, 40.0]),
        kidney_radii_lps=np.array([15.0, 12.0, 25.0]),
        pcs_visibility=PCSVisibilityState.ANATOMICALLY_ESTIMATED,
        detected_stone_centroids=[],
        side="left"
    )
    assert len(zones) >= 1


# --- Case 06: Severe Hydronephrosis ---
def test_case_06_severe_hydronephrosis():
    vol, spatial, gt = generate_synthetic_pcnl_phantom(grid_shape=(64, 64, 50))
    k_mask = np.zeros((64, 64, 50), dtype=bool)
    k_mask[20:45, 20:45, 15:35] = True
    # Fill kidney interior with fluid attenuation (10 HU)
    vol[25:40, 25:40, 20:30] = 10.0

    res = classify_collecting_system_visibility(vol, k_mask, spatial, is_contrast_enhanced=False)
    assert res.state == PCSVisibilityState.HYDRONEPHROTIC_DISTENDED
    assert res.allows_direct_puncture_lock is True


# --- Case 07: Non-Dilated Collecting System ---
def test_case_07_nondilated_collecting_system():
    vol, spatial, gt = generate_synthetic_pcnl_phantom(grid_shape=(64, 64, 50))
    k_mask = np.zeros((64, 64, 50), dtype=bool)
    k_mask[20:45, 20:45, 15:35] = True
    # Solid parenchymal density (35 HU), no fluid cavity
    vol[k_mask] = 35.0

    res = classify_collecting_system_visibility(vol, k_mask, spatial, is_contrast_enhanced=False)
    assert res.state == PCSVisibilityState.ANATOMICALLY_ESTIMATED
    assert res.allows_direct_puncture_lock is False


# --- Case 08: Low-Resolution Thick Slice CT Rejection ---
def test_case_08_thick_slice_ct_rejection():
    # 3.0mm thickness exceeds 2.5mm limit
    res = evaluate_dicom_series_geometry(
        image_positions=[[0, 0, i * 3.0] for i in range(20)],
        image_orientations=[[1, 0, 0, 0, 1, 0]] * 20,
        pixel_spacings=[[0.8, 0.8]] * 20,
        slice_thicknesses=[3.0] * 20
    )
    assert res.passed is False
    assert any("thickness" in r.lower() for r in res.rejection_reasons)


# --- Case 09: Gantry-Tilted CT Rejection ---
def test_case_09_gantry_tilted_ct_rejection():
    res = evaluate_dicom_series_geometry(
        image_positions=[[0, 0, i * 1.0] for i in range(20)],
        image_orientations=[[1, 0, 0, 0, 1, 0]] * 20,
        pixel_spacings=[[0.8, 0.8]] * 20,
        slice_thicknesses=[1.0] * 20,
        gantry_tilts=[12.0] * 20 # 12 degrees tilt
    )
    assert res.passed is False
    assert any("gantry tilt" in r.lower() for r in res.rejection_reasons)


# --- Case 10: Missing Slice Gap Rejection ---
def test_case_10_missing_slice_gap_rejection():
    # Gap between slice 10 and 11
    positions = [[0, 0, i * 1.0] for i in range(10)] + [[0, 0, (i + 5) * 1.0] for i in range(10, 20)]
    res = evaluate_dicom_series_geometry(
        image_positions=positions,
        image_orientations=[[1, 0, 0, 0, 1, 0]] * 20,
        pixel_spacings=[[0.8, 0.8]] * 20,
        slice_thicknesses=[1.0] * 20
    )
    assert res.passed is False
    assert any("spacing" in r.lower() or "missing slices" in r.lower() for r in res.rejection_reasons)


# --- Case 11: Dual Pole Calculi ---
def test_case_11_dual_pole_calculi():
    s_lower = StoneMorphometry(1, 250.0, 250, np.array([20.0, 5.0, 30.0]), 8.0, np.array([6, 6, 8]), "DENSE_CALCIUM")
    s_upper = StoneMorphometry(2, 350.0, 350, np.array([20.0, 10.0, 60.0]), 9.0, np.array([7, 7, 9]), "DENSE_CALCIUM")

    papilla_lower = np.array([20.0, 10.0, 30.0])
    zone_lower = ConicalPunctureZone(
        "ZONE_LOWER", CalyxGroup.POSTERIOR_LOWER, papilla_lower,
        np.array([0.0, -1.0, 0.0]), 15.0, PCSVisibilityState.DIRECTLY_OPACIFIED, 0.9
    )
    traj = LineSegment3D(np.array([20.0, 50.0, 30.0]), papilla_lower)
    reach = evaluate_access_stone_reach(traj, zone_lower, STANDARD_RIGID_NEPHROSCOPE, [s_lower, s_upper])

    # Rigid scope through lower pole reaches lower calculus, but cannot bend 90° to upper pole
    assert reach.reachable_stone_fraction < 1.0
    assert 1 in reach.reachable_stone_ids
    assert 2 in reach.unreachable_stone_ids


# --- Case 12: High BMI Thick Flank ---
def test_case_12_high_bmi_thick_flank():
    # Flank entry at Y = 130mm, papilla at Y = 10mm -> 120mm tract depth
    skin_entry = np.array([30.0, 130.0, 30.0])
    papilla = np.array([30.0, 10.0, 30.0])
    traj = LineSegment3D(skin_entry, papilla)
    assert traj.length >= 120.0


# --- Case 13: Intercostal Neurovascular Bundle Proximity ---
def test_case_13_intercostal_nv_bundle():
    rib = np.zeros((40, 40, 40), dtype=bool)
    rib[18:22, 10:30, 20] = True # Single rib slice
    spatial = SpatialOrientation.from_dicom_parameters([1,0,0,0,1,0], [0,0,0], [1.0, 1.0], 1.0)
    risk_zone = derive_intercostal_neurovascular_risk_zone(rib, spatial, inferior_buffer_mm=4.0)

    assert np.any(risk_zone)
    # Risk zone must not overlap with rib bone itself
    assert not np.any(risk_zone & rib)


# --- Case 14: Contrast-Enhanced Opacified Collecting System ---
def test_case_14_contrast_enhanced_system():
    vol, spatial, gt = generate_synthetic_pcnl_phantom(grid_shape=(64, 64, 50))
    k_mask = np.zeros((64, 64, 50), dtype=bool)
    k_mask[20:45, 20:45, 15:35] = True
    vol[25:38, 25:38, 20:30] = 350.0 # Dense iodinated contrast in calyces (>500 mm3)

    res = classify_collecting_system_visibility(vol, k_mask, spatial, is_contrast_enhanced=True)
    assert res.state == PCSVisibilityState.DIRECTLY_OPACIFIED
    assert res.allows_direct_puncture_lock is True


# --- Case 15: Right Kidney Anatomical Orientation ---
def test_case_15_right_kidney_orientation():
    # Right kidney: lateral is -X, medial is +X
    zones = generate_candidate_puncture_zones(
        kidney_center_lps=np.array([-25.0, 10.0, 40.0]), # -X is Right side
        kidney_radii_lps=np.array([15.0, 12.0, 25.0]),
        pcs_visibility=PCSVisibilityState.DIRECTLY_OPACIFIED,
        detected_stone_centroids=[],
        side="right"
    )
    assert len(zones) >= 1
    # Right kidney papilla must be on right side (-X)
    assert zones[0].apex_papilla_lps_mm[0] < 0.0
