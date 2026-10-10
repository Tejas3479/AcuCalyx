"""
AcuCalyx Automated Test Suite: Milestone M15 Endoscopic Reachability & Computed Endoluminal Rehearsal
Governed by ACU-M15-EXEC-PLAN-2026-V2.

Tests:
1. Milestone M15.0 Reference Phantoms & Validated Instrument Registry
2. Milestone M15.1 Centerline Graph, Continuous Frenet Frames & Morphometry
3. Milestone M15.2 Sheath-Coupled Rigid Corridor Reachability
4. Milestone M15.3 Device-Specific Flexible Kinematics & Uncertainty State Machine
5. Milestone M15.4 Geometric Stone-Access Coverage Mapping (f_geom)
6. Milestone M15.5 Computed Endoluminal Rehearsal Keyframes & Provenance HUD
7. Milestone M15.6 Descriptive Access-Caliber Compatibility Profiles (Mini vs Standard PCNL)
8. Milestone M15.7 Milestone M15-V Validation Gate (Agreement, ICC, Phantoms)
9. Endoscopy FastAPI Endpoints Integration
"""

import math
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from acucalyx.endoscopy.instrument_registry import (
    EndoscopeClass,
    WorkingChannelTool,
    ValidatedEndoscopeProfile,
    PhysicalPhantomSpecification,
    get_endoscope_profile,
    list_all_endoscopes,
    get_active_deflection,
    STANDARD_ENDOSCOPES,
    M15_REFERENCE_PHANTOMS,
    KARL_STORZ_27002BA,
    KARL_STORZ_MIP_27092,
    OLYMPUS_URF_V3,
    BOSTON_SCI_LITHOVUE,
)
from acucalyx.endoscopy.skeletonizer import (
    CenterlineNode,
    CrossSectionalGeometry,
    CenterlineEdge,
    CalyxMorphometry,
    CollectingSystemGraph,
    compute_frenet_frame,
    build_procedural_collecting_system_graph,
)
from acucalyx.endoscopy.reachability_engine import (
    ReachabilityStatus,
    CalyxReachabilityResult,
    TrajectoryReachabilityReport,
    evaluate_rigid_corridor_reachability,
    evaluate_flexible_kinematic_reachability,
    evaluate_trajectory_reachability,
)
from acucalyx.endoscopy.stone_coverage import (
    StoneAccessClass,
    StoneBurdenUnit,
    StoneCoverageItem,
    StoneAccessCoverageMap,
    evaluate_geometric_stone_coverage,
)
from acucalyx.endoscopy.tract_sizing import (
    AccessCaliberClass,
    AccessCaliberProfile,
    AccessCaliberComparisonReport,
    generate_access_caliber_profiles,
)
from acucalyx.endoscopy.virtual_nephroscopy import (
    EndoluminalKeyframe,
    ComputedEndoluminalRehearsalTrajectory,
    generate_endoluminal_rehearsal_trajectory,
)
from acucalyx.endoscopy.reachability_validator import (
    MorphometryValidationResult,
    ReachabilityClassificationMetrics,
    InterRaterReliabilityResult,
    PhysicalPhantomConcordanceResult,
    M15ValidationGateReport,
    compute_continuous_agreement,
    compute_classification_agreement,
    compute_icc_2_1,
    evaluate_m15_validation_gate,
)

client = TestClient(app)


# =============================================================================
# 1. Milestone M15.0: Instrument Registry & Reference Phantoms Tests
# =============================================================================

class TestInstrumentRegistry:
    def test_registered_instruments_catalog(self):
        scopes = list_all_endoscopes()
        assert len(scopes) == 4
        model_ids = {s.model_id for s in scopes}
        assert "KARL_STORZ_27002BA" in model_ids
        assert "KARL_STORZ_MIP_27092" in model_ids
        assert "OLYMPUS_URF_V3" in model_ids
        assert "BOSTON_SCI_LITHOVUE" in model_ids

    def test_physical_dimensions_conformance(self):
        rigid = get_endoscope_profile("KARL_STORZ_27002BA")
        assert rigid.endoscope_class == EndoscopeClass.STANDARD_RIGID_NEPHROSCOPE
        assert rigid.tip_outer_diameter_fr == 24.0
        assert pytest.approx(rigid.tip_outer_diameter_mm, 0.01) == 8.0
        assert not rigid.is_flexible
        assert rigid.min_bend_radius_mm is None

        mini = get_endoscope_profile("KARL_STORZ_MIP_27092")
        assert mini.endoscope_class == EndoscopeClass.MINI_RIGID_NEPHROSCOPE
        assert mini.tip_outer_diameter_fr == 16.0
        assert pytest.approx(mini.tip_outer_diameter_mm, 0.01) == 5.33
        assert not mini.is_flexible

        olympus = get_endoscope_profile("OLYMPUS_URF_V3")
        assert olympus.endoscope_class == EndoscopeClass.FLEXIBLE_VIDEO_URETERO_NEPHROSCOPE
        assert olympus.tip_outer_diameter_fr == 8.4
        assert pytest.approx(olympus.tip_outer_diameter_mm, 0.01) == 2.8
        assert olympus.is_flexible
        assert olympus.min_bend_radius_mm == 9.0

        lithovue = get_endoscope_profile("BOSTON_SCI_LITHOVUE")
        assert lithovue.endoscope_class == EndoscopeClass.SINGLE_USE_DIGITAL_FLEXIBLE_URETEROSCOPE
        assert lithovue.tip_outer_diameter_fr == 7.4
        assert pytest.approx(lithovue.tip_outer_diameter_mm, 0.01) == 2.47
        assert lithovue.is_flexible
        assert lithovue.min_bend_radius_mm == 8.0

    def test_empirical_tool_loaded_deflection_degradation(self):
        """Validates that loaded deflection decreases monotonically with tool stiffness."""
        scope = get_endoscope_profile("OLYMPUS_URF_V3")
        def_empty = scope.get_max_deflection_deg(WorkingChannelTool.EMPTY)
        def_200 = scope.get_max_deflection_deg(WorkingChannelTool.LASER_FIBER_200UM)
        def_365 = scope.get_max_deflection_deg(WorkingChannelTool.LASER_FIBER_365UM)
        def_basket = scope.get_max_deflection_deg(WorkingChannelTool.NITINOL_BASKET_1_8FR)

        assert def_empty == 275.0
        assert def_200 == 254.0
        assert def_365 == 228.0
        assert def_basket == 242.0

        # Physical stiffness constraint: 365 um fiber restricts deflection more than 200 um fiber
        assert def_empty > def_200 > def_365
        assert def_empty > def_basket > def_365

    def test_reference_phantoms_truth_matrix(self):
        assert len(M15_REFERENCE_PHANTOMS) >= 3
        p1 = M15_REFERENCE_PHANTOMS["PHANTOM_M15_01_FAVORABLE"]
        assert p1.calyces["LP"].ipa_true_deg == 72.0
        assert p1.calyces["LP"].is_rigid_accessible_from_lower is True
        assert p1.calyces["MP"].is_flexible_accessible_unloaded is True

        p3 = M15_REFERENCE_PHANTOMS["PHANTOM_M15_03_ACUTE_CHALLENGE"]
        # Acute lower pole (28°) is stenotic (3.2 mm) -> flexible access restricted
        assert p3.calyces["LP"].ipa_true_deg == 28.0
        assert p3.calyces["LP"].is_flexible_accessible_unloaded is False


# =============================================================================
# 2. Milestone M15.1: Centerline Graph & Continuous Morphometry Tests
# =============================================================================

class TestCollectingSystemGraphAndMorphometry:
    def test_procedural_graph_generation(self):
        graph = build_procedural_collecting_system_graph(case_id="TEST_CASE_01")
        assert len(graph.nodes) >= 6
        assert "PELVIS_CENTROID" in graph.nodes
        assert "UPJ" in graph.nodes
        assert "LP" in graph.calyces
        assert "MP" in graph.calyces
        assert "UP" in graph.calyces

    def test_continuous_frenet_frame_computation(self):
        # Helix curve with known analytical non-zero curvature and torsion
        t = np.linspace(0, 2 * np.pi, 50)
        pts = np.column_stack([np.cos(t), np.sin(t), t])
        tangents, normals, binormals, curvatures, torsions = compute_frenet_frame(pts)

        assert len(tangents) == 50
        # Unit vector orthogonality
        for i in range(10, 40):
            assert pytest.approx(np.linalg.norm(tangents[i]), 1e-4) == 1.0
            assert pytest.approx(np.linalg.norm(normals[i]), 1e-4) == 1.0
            assert pytest.approx(np.linalg.norm(binormals[i]), 1e-4) == 1.0
            assert pytest.approx(np.dot(tangents[i], normals[i]), abs=1e-3) == 0.0
            assert curvatures[i] > 0.0

    def test_continuous_non_circular_cross_sections(self):
        graph = build_procedural_collecting_system_graph(case_id="TEST_CASE_02")
        edge_lp = graph.edges["EDGE_LP"]
        assert len(edge_lp.cross_sections) > 0
        cs = edge_lp.cross_sections[10]

        assert cs.min_feret_diameter_mm > 0.0
        assert cs.max_feret_diameter_mm >= cs.min_feret_diameter_mm
        assert cs.cross_sectional_area_mm2 > 0.0
        assert 0.0 <= cs.eccentricity < 1.0

    def test_continuous_infundibulopelvic_angle(self):
        graph = build_procedural_collecting_system_graph(case_id="TEST_CASE_03")
        calyx_lp = graph.calyces["LP"]
        # IPA is continuous angle [0, 180]
        assert 0.0 <= calyx_lp.infundibulopelvic_angle_deg <= 180.0
        assert calyx_lp.infundibular_width_min_mm > 0.0
        assert calyx_lp.infundibular_length_mm > 0.0


# =============================================================================
# 3. Milestone M15.2: Sheath-Coupled Rigid Corridor Reachability Tests
# =============================================================================

class TestRigidCorridorWorkspace:
    def test_direct_coincident_rigid_access(self):
        scope = get_endoscope_profile("KARL_STORZ_27002BA")
        sheath_tip = np.array([45.0, -10.0, -32.0])
        target_pos = np.array([45.0, -10.0, -32.0])
        tract_vec = np.array([0.0, 0.0, 1.0])

        is_reach, dev, msg = evaluate_rigid_corridor_reachability(
            target_pos_lps=target_pos,
            sheath_tip_lps=sheath_tip,
            tract_unit_vector=tract_vec,
            scope=scope,
        )
        assert is_reach is True
        assert dev == 0.0

    def test_rigid_corridor_line_of_sight_cone(self):
        scope = get_endoscope_profile("KARL_STORZ_27002BA")
        sheath_tip = np.array([0.0, 0.0, 0.0])
        tract_vec = np.array([0.0, 0.0, 1.0])

        # Target 20 mm ahead along tract axis (slight 4° deviation)
        target_aligned = np.array([1.0, 0.5, 20.0])
        is_reach, dev, _ = evaluate_rigid_corridor_reachability(
            target_pos_lps=target_aligned,
            sheath_tip_lps=sheath_tip,
            tract_unit_vector=tract_vec,
            scope=scope,
            anatomical_neck_clearance_mm=7.0,
        )
        assert is_reach is True
        assert dev < 10.0

        # Target perpendicular to tract (90° deviation)
        target_perp = np.array([25.0, 0.0, 0.0])
        is_reach_perp, dev_perp, _ = evaluate_rigid_corridor_reachability(
            target_pos_lps=target_perp,
            sheath_tip_lps=sheath_tip,
            tract_unit_vector=tract_vec,
            scope=scope,
            anatomical_neck_clearance_mm=7.0,
        )
        assert is_reach_perp is False
        assert dev_perp > 80.0


# =============================================================================
# 4. Milestone M15.3: Device-Specific Flexible Kinematics Tests
# =============================================================================

class TestFlexibleKinematicsWorkspace:
    def test_flexible_secondary_calyx_navigation(self):
        graph = build_procedural_collecting_system_graph("TEST_FLEX_01")
        scope = get_endoscope_profile("OLYMPUS_URF_V3")
        sheath_tip = np.array([45.0, -10.0, -32.0])
        tract_vec = np.array([0.0, 0.8, 0.6])
        tract_vec /= np.linalg.norm(tract_vec)

        # Entering Lower Posterior (LP), evaluating reachability of Middle Posterior (MP)
        res_mp = evaluate_flexible_kinematic_reachability(
            graph=graph,
            entered_calyx_id="LP",
            target_calyx_id="MP",
            sheath_tip_lps=sheath_tip,
            tract_unit_vector=tract_vec,
            scope=scope,
            tool=WorkingChannelTool.LASER_FIBER_200UM,
        )
        assert res_mp.is_reachable is True
        assert res_mp.status == ReachabilityStatus.FLEXIBLE_ACCESSIBLE
        assert res_mp.clearance_margin_mm > 0.0
        assert res_mp.required_deflection_deg <= res_mp.active_deflection_limit_deg

    def test_restricted_geometry_narrow_neck(self):
        # Create custom graph with a stenotic infundibulum (2.0 mm < scope tip 2.8 mm)
        custom_specs = [
            {
                "calyx_id": "LP",
                "calyx_group": "LOWER_POSTERIOR",
                "apex_lps": np.array([45.0, -10.0, -32.0]),
                "ipj_lps": np.array([32.0, 5.0, -15.0]),
                "min_feret_mm": 6.8,
            },
            {
                "calyx_id": "STENOTIC",
                "calyx_group": "MIDDLE_ANTERIOR",
                "apex_lps": np.array([48.0, 35.0, 2.0]),
                "ipj_lps": np.array([30.0, 22.0, 1.0]),
                "min_feret_mm": 2.0,  # Stenotic neck
            },
        ]
        graph = build_procedural_collecting_system_graph("TEST_STENOTIC", calyx_specs=custom_specs)
        scope = get_endoscope_profile("OLYMPUS_URF_V3")  # OD 2.8 mm

        sheath_tip = np.array([45.0, -10.0, -32.0])
        tract_vec = np.array([0.0, 1.0, 0.0])

        res = evaluate_flexible_kinematic_reachability(
            graph=graph,
            entered_calyx_id="LP",
            target_calyx_id="STENOTIC",
            sheath_tip_lps=sheath_tip,
            tract_unit_vector=tract_vec,
            scope=scope,
        )
        assert res.is_reachable is False
        assert res.status == ReachabilityStatus.RESTRICTED_GEOMETRY
        assert len(res.alternative_strategies) > 0

    def test_uncertain_geometry_evidence_state(self):
        custom_specs = [
            {
                "calyx_id": "LP",
                "calyx_group": "LOWER_POSTERIOR",
                "apex_lps": np.array([45.0, -10.0, -32.0]),
                "ipj_lps": np.array([32.0, 5.0, -15.0]),
                "min_feret_mm": 6.8,
                "visibility_state": "DIRECT",
            },
            {
                "calyx_id": "UNCERTAIN_CALYX",
                "calyx_group": "UPPER_POSTERIOR",
                "apex_lps": np.array([40.0, -8.0, 36.0]),
                "ipj_lps": np.array([28.0, 8.0, 18.0]),
                "min_feret_mm": 5.0,
                "visibility_state": "PARTIAL",  # Low confidence CT evidence
            },
        ]
        graph = build_procedural_collecting_system_graph("TEST_UNCERTAIN", calyx_specs=custom_specs)
        scope = get_endoscope_profile("OLYMPUS_URF_V3")

        sheath_tip = np.array([45.0, -10.0, -32.0])
        tract_vec = np.array([0.0, 1.0, 0.0])

        res = evaluate_flexible_kinematic_reachability(
            graph=graph,
            entered_calyx_id="LP",
            target_calyx_id="UNCERTAIN_CALYX",
            sheath_tip_lps=sheath_tip,
            tract_unit_vector=tract_vec,
            scope=scope,
        )
        assert res.is_reachable is False
        assert res.status == ReachabilityStatus.UNCERTAIN_GEOMETRY
        assert res.confidence_score < 0.50


# =============================================================================
# 5. Milestone M15.4: Geometric Stone-Access Coverage Mapping Tests
# =============================================================================

class TestGeometricStoneAccessCoverage:
    def test_volumetric_coverage_calculation(self):
        graph = build_procedural_collecting_system_graph("TEST_STONE_01")
        scope = get_endoscope_profile("OLYMPUS_URF_V3")
        sheath_tip = np.array([45.0, -10.0, -32.0])
        tract_vec = np.array([0.0, 0.6, 0.8])

        reach_report = evaluate_trajectory_reachability(
            graph=graph,
            trajectory_id="CAND_01",
            entered_calyx_id="LP",
            sheath_tip_lps=sheath_tip,
            tract_unit_vector=tract_vec,
            instrument_model_id="OLYMPUS_URF_V3",
            tool=WorkingChannelTool.LASER_FIBER_200UM,
        )

        stones = [
            StoneBurdenUnit(stone_id="S1", calyx_id="LP", volume_mm3=800.0, max_caliper_mm=12.0, centroid_lps_mm=np.array([45.0, -10.0, -32.0])),
            StoneBurdenUnit(stone_id="S2", calyx_id="MP", volume_mm3=400.0, max_caliper_mm=8.0, centroid_lps_mm=np.array([52.0, -5.0, 5.0])),
        ]

        cov_map = evaluate_geometric_stone_coverage(reach_report, stones, graph)
        assert cov_map.total_stone_volume_mm3 == 1200.0
        assert cov_map.geometric_coverage_estimate_percent == 100.0
        assert "S1" in cov_map.fully_accessible_stone_ids
        assert "S2" in cov_map.fully_accessible_stone_ids

    def test_partial_stone_access_branched_calculus(self):
        graph = build_procedural_collecting_system_graph("TEST_STONE_PARTIAL")
        reach_report = evaluate_trajectory_reachability(
            graph=graph,
            trajectory_id="CAND_02",
            entered_calyx_id="LP",
            sheath_tip_lps=np.array([45.0, -10.0, -32.0]),
            tract_unit_vector=np.array([0.0, 0.6, 0.8]),
            instrument_model_id="KARL_STORZ_27002BA",  # Rigid scope (can only reach LP)
            tool=WorkingChannelTool.EMPTY,
        )

        # 1000 mm³ staghorn stone with 600 mm³ in LP and 400 mm³ in MP
        sub_regions = [
            (np.array([45.0, -10.0, -32.0]), 600.0),
            (np.array([52.0, -5.0, 5.0]), 400.0),
        ]
        stones = [
            StoneBurdenUnit(
                stone_id="STAGHORN_01",
                calyx_id="LP",
                volume_mm3=1000.0,
                max_caliper_mm=26.0,
                centroid_lps_mm=np.array([47.0, -8.0, -20.0]),
                sub_regions=sub_regions,
            )
        ]

        cov_map = evaluate_geometric_stone_coverage(reach_report, stones, graph)
        assert cov_map.total_stone_volume_mm3 == 1000.0
        assert pytest.approx(cov_map.total_accessible_volume_mm3, 1.0) == 600.0
        assert pytest.approx(cov_map.geometric_coverage_estimate_percent, 1.0) == 60.0
        assert "STAGHORN_01" in cov_map.partially_accessible_stone_ids


# =============================================================================
# 6. Milestone M15.5: Computed Endoluminal Rehearsal Tests
# =============================================================================

class TestComputedEndoluminalRehearsal:
    def test_endoluminal_keyframe_trajectory_generation(self):
        graph = build_procedural_collecting_system_graph("TEST_REHEARSAL_01")
        sheath_tip = np.array([45.0, -10.0, -32.0])
        tract_vec = np.array([0.0, 0.6, 0.8])

        traj = generate_endoluminal_rehearsal_trajectory(
            graph=graph,
            trajectory_id="CAND_REHEARSAL",
            entered_calyx_id="LP",
            target_calyx_id="MP",
            sheath_tip_lps=sheath_tip,
            tract_unit_vector=tract_vec,
            instrument_model_id="OLYMPUS_URF_V3",
            tool=WorkingChannelTool.LASER_FIBER_200UM,
        )

        assert len(traj.keyframes) >= 8
        assert traj.total_path_length_mm > 20.0
        assert traj.field_of_view_deg == 120.0

        for kf in traj.keyframes:
            assert len(kf.camera_position_lps_mm) == 3
            assert pytest.approx(np.linalg.norm(kf.camera_forward_vector), 1e-4) == 1.0
            assert pytest.approx(np.linalg.norm(kf.quaternion_orientation), 1e-4) == 1.0
            assert kf.anatomy_provenance in ("DIRECT", "PARTIAL", "ESTIMATED", "UNAVAILABLE")
            assert "NON-DIAGNOSTIC" in kf.synthetic_rendering_disclaimer


# =============================================================================
# 7. Milestone M15.6: Descriptive Access-Caliber Profiles Tests
# =============================================================================

class TestDescriptiveAccessCaliberProfiles:
    def test_non_prescriptive_comparative_profiles(self):
        graph = build_procedural_collecting_system_graph("TEST_SIZING_01")
        report = generate_access_caliber_profiles(
            case_id="CASE_SIZING",
            candidate_id="CAND_01",
            target_calyx_id="LP",
            graph=graph,
            total_stone_volume_mm3=1800.0,
            max_stone_caliper_mm=19.5,
        )

        assert "MINI_PCNL" in report.profiles
        assert "STANDARD_PCNL" in report.profiles

        mini = report.profiles["MINI_PCNL"]
        std = report.profiles["STANDARD_PCNL"]

        assert mini.sheath_french == 16.0
        assert std.sheath_french == 28.0

        # Non-prescriptive verification: neither profile issues an autonomous surgical command
        assert "Does not constitute a clinical directive" in mini.clinical_governance_notice
        assert "Does not constitute a clinical directive" in std.clinical_governance_notice

        # Clinical trade-offs are grounded in 2026 EAU guideline
        assert "bleeding_and_transfusion_risk" in mini.relative_operative_tradeoffs
        assert "evacuation_dynamics" in std.relative_operative_tradeoffs

        # Intrarenal pressure contextual notice present without CFD overclaim
        assert "intrarenal pressure" in report.intrarenal_pressure_context.lower()
        assert "not modeled computationally" in report.intrarenal_pressure_context.lower()


# =============================================================================
# 8. Milestone M15.7: Validation Gate (Statistical Agreement) Tests
# =============================================================================

class TestMilestoneM15ValidationGate:
    def test_continuous_agreement_metrics(self):
        # Known synthetic data with controlled MAE = 2.0 and bias = 0.5
        ref = np.linspace(30.0, 80.0, 30)
        pred = ref + 2.0
        res = compute_continuous_agreement(pred, ref, "IPA", mae_threshold=5.0)

        assert res.sample_size == 30
        assert pytest.approx(res.mean_absolute_error, 1e-4) == 2.0
        assert pytest.approx(res.systematic_bias, 1e-4) == 2.0
        assert res.passed is True

    def test_cohens_kappa_and_classification(self):
        ref = np.array([True] * 25 + [False] * 15)
        pred = np.array([True] * 24 + [False] * 1 + [False] * 14 + [True] * 1)
        res = compute_classification_agreement(pred, ref, kappa_threshold=0.80)

        assert res.accuracy > 0.90
        assert res.sensitivity > 0.90
        assert res.specificity > 0.90
        assert res.cohens_kappa > 0.85
        assert res.passed is True

    def test_intraclass_correlation_icc_2_1(self):
        # 30 cases evaluated by 3 raters with high agreement
        np.random.seed(101)
        base = np.linspace(20.0, 75.0, 30)
        r1 = base + np.random.normal(0, 1.0, 30)
        r2 = base + np.random.normal(0, 1.0, 30)
        r3 = base + np.random.normal(0, 1.0, 30)
        matrix = np.column_stack([r1, r2, r3])

        icc_res = compute_icc_2_1(matrix, "IPA Annotation", icc_threshold=0.80)
        assert icc_res.icc_value >= 0.85
        assert icc_res.passed is True
        assert "Agreement" in icc_res.agreement_interpretation

    def test_comprehensive_validation_gate_execution(self):
        report = evaluate_m15_validation_gate()
        assert report.gate_identifier == "ACU-M15-V-GATE-2026"
        assert report.overall_gate_passed is True
        assert report.ipa_validation.passed is True
        assert report.iw_validation.passed is True
        assert report.classification_metrics.passed is True
        assert report.inter_rater_reliability.passed is True
        assert report.phantom_concordance.passed is True
        assert report.phantom_concordance.critical_discrepancies == 0


# =============================================================================
# 9. FastAPI Endpoints Integration Tests
# =============================================================================

class TestEndoscopyAPIEndpoints:
    def test_get_instruments_endpoint(self):
        resp = client.get("/api/cases/test_case/endoscopy/instruments")
        assert resp.status_code == 200
        data = resp.json()
        assert "instruments" in data
        assert len(data["instruments"]) == 4
        assert data["default_instrument_id"] == "OLYMPUS_URF_V3"

    def test_get_reference_phantoms_endpoint(self):
        resp = client.get("/api/cases/test_case/endoscopy/reference-phantoms")
        assert resp.status_code == 200
        data = resp.json()
        assert "reference_phantoms" in data
        assert len(data["reference_phantoms"]) >= 3

    def test_get_reachability_endpoint(self):
        resp = client.get(
            "/api/cases/test_case/endoscopy/CAND_01/reachability",
            params={"instrument_model_id": "OLYMPUS_URF_V3", "tool": "LASER_FIBER_200UM"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["candidate_id"] == "CAND_01"
        assert "overall_reachability_fraction" in data
        assert "calyces" in data
        assert len(data["calyces"]) >= 4

    def test_get_stone_coverage_endpoint(self):
        resp = client.get(
            "/api/cases/test_case/endoscopy/CAND_01/stone-coverage",
            params={"instrument_model_id": "OLYMPUS_URF_V3", "tool": "LASER_FIBER_200UM"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "geometric_coverage_estimate_percent" in data
        assert data["geometric_coverage_estimate_percent"] > 0.0
        assert "stones" in data
        assert "descriptive_notice" in data

    def test_get_access_caliber_profiles_endpoint(self):
        resp = client.get("/api/cases/test_case/endoscopy/CAND_01/access-caliber-profiles")
        assert resp.status_code == 200
        data = resp.json()
        assert "profiles" in data
        assert "MINI_PCNL" in data["profiles"]
        assert "STANDARD_PCNL" in data["profiles"]
        assert "intrarenal_pressure_context" in data

    def test_get_endoluminal_rehearsal_endpoint(self):
        resp = client.get(
            "/api/cases/test_case/endoscopy/CAND_01/endoluminal-rehearsal",
            params={"instrument_model_id": "OLYMPUS_URF_V3", "target_calyx_id": "MP"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "keyframes" in data
        assert data["keyframes_count"] >= 8
        assert "synthetic_rendering_notice" in data

    def test_get_validation_gate_endpoint(self):
        resp = client.get("/api/cases/test_case/endoscopy/validation-gate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["gate_identifier"] == "ACU-M15-V-GATE-2026"
        assert data["overall_gate_passed"] is True
        assert "ipa_agreement" in data
        assert "physical_phantom_concordance" in data
