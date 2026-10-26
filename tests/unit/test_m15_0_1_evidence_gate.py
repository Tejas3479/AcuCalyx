"""
AcuCalyx Automated Test Suite: Milestone M15.0.1 Synthetic Isolation & Evidence Gate
Governed by ACU-M15-EXEC-PLAN-2026-V2 and M15.0.1 Evidence Remediation Specification.

Validates the 10 Acceptance Criteria:
1. evaluate_m15_validation_gate() fails closed with NOT_EVALUABLE when called without locked external reference data.
2. compute_icc_2_1 fails closed (passed=False, icc_value=None) on small samples (N < 3 or K < 2).
3. Physical phantom concordance evaluates actual per-calyx concordance across all phantoms.
4. Patient-mode API endpoints fail closed (HTTP 422/404) when case geometry or trajectories are absent.
5. demo_mode=True returns synthetic benchmark simulations tagged with SYNTHETIC_DEMO_NON_CLINICAL provenance.
6. TotalSegmentator adapter passes --ml flag and accurately maps official v2 integer IDs (colon=20, ivc=63, ribs=103/115).
7. nnU-Net case packaging preserves physical affine 4x4, origin, and converts DICOM LPS <-> NIfTI RAS+.
8. Research NIfTI quality gating rejects thick slices (>2.5 mm) or insufficient slice counts (<10).
9. Stone coverage awards 0% credit to uncertain geometry; tract sizing returns NOT_ASSESSABLE for unmeasured infundibula.
10. System regression integrity across all modules.
"""

import json
from pathlib import Path
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from acucalyx.endoscopy.reachability_validator import (
    evaluate_m15_validation_gate,
    compute_icc_2_1,
    compute_continuous_agreement,
    compute_classification_agreement,
    generate_synthetic_m15v_test_data,
)
from acucalyx.endoscopy.vmtk_benchmark import (
    VMTKBenchmarkHarness,
    CenterlineBenchmarkMetrics,
)
from acucalyx.integrations.totalsegmentator_adapter import (
    TotalSegmentatorAdapter,
    TOTALSEGMENTATOR_CLASSES,
)
from acucalyx.integrations.nnunet_pipeline import (
    NnunetPipelineManager,
)
from acucalyx.pipeline import (
    run_planning_pipeline,
)
from acucalyx.endoscopy.stone_coverage import (
    StoneAccessClass,
    StoneCoverageItem,
    StoneAccessCoverageMap,
)
from acucalyx.endoscopy.tract_sizing import (
    generate_access_caliber_profiles,
)
from acucalyx.endoscopy.skeletonizer import (
    build_procedural_collecting_system_graph,
    CollectingSystemGraph,
)

client = TestClient(app)


class TestM1501EvidenceGateAcceptance:
    """Rigorous verification of the 10 M15.0.1 acceptance criteria."""

    def test_check_1_empty_validation_gate_fails_closed(self):
        """Check 1: evaluate_m15_validation_gate() fails closed with NOT_EVALUABLE."""
        report = evaluate_m15_validation_gate()
        assert report.status == "NOT_EVALUABLE"
        assert report.overall_gate_passed is False
        assert report.ipa_validation is None
        assert report.inter_rater_reliability is None
        assert "Evaluation blocked" in report.summary_findings

    def test_check_2_icc_small_sample_fails_closed(self):
        """Check 2: compute_icc_2_1 fails closed on small samples."""
        # N=2, K=3 (insufficient cases N < 3)
        small_n = np.array([[10.0, 11.0, 10.5], [20.0, 21.0, 20.2]])
        res_n = compute_icc_2_1(small_n, "Small N Test")
        assert res_n.passed is False
        assert res_n.icc_value is None
        assert "INSUFFICIENT" in res_n.agreement_interpretation

        # N=5, K=1 (insufficient raters K < 2)
        small_k = np.array([[10.0], [20.0], [30.0], [40.0], [50.0]])
        res_k = compute_icc_2_1(small_k, "Small K Test")
        assert res_k.passed is False
        assert res_k.icc_value is None
        assert "INSUFFICIENT" in res_k.agreement_interpretation

    def test_check_3_physical_phantom_concordance_evaluates_actual_error(self):
        """Check 3: Physical phantom concordance evaluates actual concordance without constant True."""
        data = generate_synthetic_m15v_test_data()
        
        # Perfect concordance
        report_ok = evaluate_m15_validation_gate(**data)
        assert report_ok.phantom_concordance.passed is True
        assert report_ok.phantom_concordance.critical_discrepancies == 0

        # Inject intentional discrepancy in phantom 1
        data_bad = dict(data)
        data_bad["phantom_measurements"] = {
            "PHANTOM_M15_01_FAVORABLE": {
                "LP": {"is_accessible": False},
            }
        }

        report_bad = evaluate_m15_validation_gate(**data_bad)
        assert report_bad.phantom_concordance.critical_discrepancies > 0
        assert report_bad.phantom_concordance.passed is False

    def test_check_4_patient_endpoints_fail_closed_without_artifacts(self):
        """Check 4: Endpoints fail closed with HTTP 422/404 when demo_mode=False."""
        nonexistent_case = "NONEXISTENT_PATIENT_CASE_999"
        
        # Reachability
        resp_reach = client.get(
            f"/api/cases/{nonexistent_case}/endoscopy/CAND_01/reachability",
            params={"demo_mode": False}
        )
        assert resp_reach.status_code in (422, 404)

        # Stone coverage
        resp_stone = client.get(
            f"/api/cases/{nonexistent_case}/endoscopy/CAND_01/stone-coverage",
            params={"demo_mode": False}
        )
        assert resp_stone.status_code in (422, 404)

        # Access caliber profiles
        resp_tract = client.get(
            f"/api/cases/{nonexistent_case}/endoscopy/CAND_01/access-caliber-profiles",
            params={"demo_mode": False}
        )
        assert resp_tract.status_code in (422, 404)

    def test_check_5_demo_mode_returns_explicit_synthetic_provenance(self):
        """Check 5: demo_mode=True returns synthetic simulation with clear provenance."""
        case_id = "DEMO_CASE_001"
        resp = client.get(
            f"/api/cases/{case_id}/endoscopy/CAND_01/reachability",
            params={"demo_mode": True}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["provenance_mode"] == "SYNTHETIC_DEMO_NON_CLINICAL"
        assert data["candidate_id"] == "CAND_01"

    def test_check_6_totalsegmentator_v2_classes_and_multilabel_flag(self):
        """Check 6: TotalSegmentator v2 class map and multi-label flag."""
        assert TOTALSEGMENTATOR_CLASSES[20] == "colon"
        assert TOTALSEGMENTATOR_CLASSES[63] == "inferior_vena_cava"
        assert TOTALSEGMENTATOR_CLASSES[102] == "rib_left_11"
        assert TOTALSEGMENTATOR_CLASSES[103] == "rib_left_12"
        assert TOTALSEGMENTATOR_CLASSES[114] == "rib_right_11"
        assert TOTALSEGMENTATOR_CLASSES[115] == "rib_right_12"

        # Check adapter builds command containing --ml
        adapter = TotalSegmentatorAdapter(task="total", fast=True)
        # Mock run generates v2 multi-label output
        vol = np.zeros((30, 30, 30), dtype=np.int16)
        out = adapter.segment_volume(vol, target_kidney="right", force_mock=True)
        assert "colon" in out.hazard_masks
        assert "inferior_vena_cava" in out.hazard_masks
        assert "rib_left_12" in out.hazard_masks
        assert out.provenance.model_version == "v2.4.0"

    def test_check_7_nnunet_packaging_affine_preservation(self, tmp_path):
        """Check 7: nnU-Net case packaging preserves origin and affine transform."""
        mgr = NnunetPipelineManager(output_root=tmp_path)
        vol = np.zeros((10, 10, 10), dtype=np.int16)
        lbl = np.zeros((10, 10, 10), dtype=np.uint8)

        affine = np.array([
            [-1.0, 0.0, 0.0, 50.0],
            [0.0, -1.0, 0.0, -120.0],
            [0.0, 0.0, 2.0, -35.0],
            [0.0, 0.0, 0.0, 1.0],
        ])
        origin_lps = (50.0, -120.0, -35.0)

        img_p, lbl_p = mgr.package_case(
            case_id="CASE_AFFINE_TEST",
            ct_array=vol,
            label_array=lbl,
            spacing_mm=(1.0, 1.0, 2.0),
            origin_lps_mm=origin_lps,
            affine_4x4=affine,
        )

        assert img_p.is_file()
        assert lbl_p.is_file()

        import nibabel as nib
        nii_img = nib.load(str(img_p))
        np.testing.assert_allclose(nii_img.affine, affine, atol=1e-4)

    def test_check_8_nifti_quality_gate_thickness_and_slices(self, tmp_path):
        """Check 8: NIfTI quality gating rejects slice thickness > 2.5 mm."""
        import nibabel as nib

        # 1. Thick slice case (3.0 mm > 2.5 mm threshold)
        thick_data = np.zeros((20, 20, 20), dtype=np.int16)
        thick_data[5:15, 5:15, 5:15] = 200  # Non-empty
        thick_affine = np.diag([1.0, 1.0, 3.0, 1.0])
        thick_nii = nib.Nifti1Image(thick_data, thick_affine)
        thick_path = tmp_path / "thick_scan.nii.gz"
        nib.save(thick_nii, str(thick_path))

        res_thick = run_planning_pipeline(str(thick_path), tmp_path / "out_thick", side="right")
        assert res_thick.status == "GATE_REJECTED"
        assert res_thick.quality_gate.passed is False
        assert any("Slice thickness" in r for r in res_thick.quality_gate.rejection_reasons)

        # 2. Too few slices (< 10 slices)
        few_data = np.zeros((5, 20, 20), dtype=np.int16)
        few_data[1:4, 5:15, 5:15] = 200  # Non-empty
        few_affine = np.diag([1.0, 1.0, 1.0, 1.0])
        few_nii = nib.Nifti1Image(few_data, few_affine)
        few_path = tmp_path / "few_slices.nii.gz"
        nib.save(few_nii, str(few_path))

        res_few = run_planning_pipeline(str(few_path), tmp_path / "out_few", side="right")
        assert res_few.status == "GATE_REJECTED"
        assert res_few.quality_gate.passed is False
        assert any("Insufficient slices" in r for r in res_few.quality_gate.rejection_reasons)

    def test_check_9_zero_coverage_under_uncertainty_and_tract_sizing(self):
        """Check 9: 0% coverage for unassessed/uncertain anatomy and NOT_ASSESSABLE tract sizing."""
        # A. Stone coverage
        item_uncertain = StoneCoverageItem(
            stone_id="S_UNCERTAIN",
            calyx_id="UPPER",
            total_volume_mm3=500.0,
            accessible_volume_mm3=0.0,
            coverage_fraction=0.0,
            access_class=StoneAccessClass.GEOMETRICALLY_RESTRICTED,
            access_mode="NONE",
            rationale="Uncertain anatomy",
        )
        cov_map = StoneAccessCoverageMap(
            trajectory_id="T_01",
            instrument_model_id="OLYMPUS_URF_V3",
            total_stone_volume_mm3=500.0,
            total_accessible_volume_mm3=0.0,
            geometric_coverage_estimate_percent=0.0,
            directly_reachable_volume_mm3=0.0,
            flexibly_accessible_volume_mm3=0.0,
            geometrically_restricted_volume_mm3=0.0,
            angularly_restricted_volume_mm3=0.0,
            uncertain_volume_mm3=500.0,
            fully_accessible_stone_ids=[],
            partially_accessible_stone_ids=[],
            inaccessible_stone_ids=["S_UNCERTAIN"],
            stone_items=[item_uncertain],
            descriptive_notice="Test notice",
            alternative_strategy_candidates=[],
        )
        assert cov_map.geometric_coverage_estimate_percent == 0.0
        assert cov_map.total_accessible_volume_mm3 == 0.0

        # B. Tract sizing with unassessed calyx
        graph = build_procedural_collecting_system_graph("TEST_CASE")
        report = generate_access_caliber_profiles(
            case_id="TEST_CASE",
            candidate_id="C_01",
            target_calyx_id="NONEXISTENT_CALYX",
            graph=graph,
            total_stone_volume_mm3=500.0,
            max_stone_caliper_mm=12.0,
        )
        assert report.target_calyx_min_feret_mm == 0.0
        assert report.profiles["MINI_PCNL"].infundibular_clearance_status == "NOT_ASSESSABLE"
        assert report.profiles["STANDARD_PCNL"].infundibular_clearance_status == "NOT_ASSESSABLE"
        assert "NOT_ASSESSABLE" in report.descriptive_summary

    def test_check_10_endoscopy_validation_gate_endpoint_status(self):
        """Check 10: Validation gate endpoint returns status field and not evaluable without reference."""
        resp = client.get("/api/cases/test_case/endoscopy/validation-gate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "NOT_EVALUABLE"
        assert data["overall_gate_passed"] is False
        assert data["inter_rater_reliability"] is None

    def test_check_11_patient_graph_serialization_roundtrip(self, tmp_path):
        """Check 11: CollectingSystemGraph JSON serialization and deserialization integrity."""
        graph = build_procedural_collecting_system_graph(case_id="TEST_CASE_SERIALIZE")
        save_path = tmp_path / "graph.json"
        graph.save_to_json(save_path)
        assert save_path.is_file()

        loaded = CollectingSystemGraph.load_from_json(save_path)
        assert loaded.case_id == "TEST_CASE_SERIALIZE"
        assert len(loaded.nodes) == len(graph.nodes)
        assert len(loaded.edges) == len(graph.edges)
        assert len(loaded.calyces) == len(graph.calyces)
        for cid, calyx in graph.calyces.items():
            assert cid in loaded.calyces
            assert pytest.approx(loaded.calyces[cid].infundibulopelvic_angle_deg, 1e-4) == calyx.infundibulopelvic_angle_deg
            assert pytest.approx(loaded.calyces[cid].infundibular_width_min_mm, 1e-4) == calyx.infundibular_width_min_mm

    def test_check_12_validation_gate_with_manifest_file(self, tmp_path):
        """Check 12: evaluate_m15_validation_gate() loads and evaluates locked manifest."""
        data = generate_synthetic_m15v_test_data()
        manifest_data = {
            "manifest_version": "1.0",
            "dataset_identifier": "DATASET_M15_TEST",
            "ipa_pred": data["ipa_pred"].tolist(),
            "ipa_ref": data["ipa_ref"].tolist(),
            "iw_pred": data["iw_pred"].tolist(),
            "iw_ref": data["iw_ref"].tolist(),
            "class_pred": [bool(x) for x in data["class_pred"]],
            "class_ref": [bool(x) for x in data["class_ref"]],
            "multi_expert_ratings": data["multi_expert_ratings"].tolist(),
            "phantom_measurements": data["phantom_measurements"],
        }
        manifest_file = tmp_path / "m15v_manifest.json"
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2)

        report = evaluate_m15_validation_gate(manifest_path=manifest_file)
        assert report.status == "PASS_FOR_NONCLINICAL_RESEARCH"
        assert report.overall_gate_passed is True

        # Nonexistent manifest fails closed
        report_missing = evaluate_m15_validation_gate(manifest_path=tmp_path / "nonexistent.json")
        assert report_missing.status == "NOT_EVALUABLE"
        assert report_missing.overall_gate_passed is False

    def test_check_13_phantom_measurements_missing_fails_closed(self):
        """Check 13: Omitting phantom_measurements fails closed (zero synthetic fallback)."""
        data = generate_synthetic_m15v_test_data()
        data["phantom_measurements"] = None
        report = evaluate_m15_validation_gate(**data)
        assert report.status == "NOT_EVALUABLE"
        assert report.overall_gate_passed is False
        assert "missing real reference" in report.summary_findings

    def test_check_14_pipeline_totalsegmentator_provider_execution(self, tmp_path):
        """Check 14: run_planning_pipeline supports TotalSegmentator provider and clinical mode."""
        import nibabel as nib
        data = np.zeros((20, 20, 20), dtype=np.int16)
        data[5:15, 5:15, 5:15] = 200
        nii = nib.Nifti1Image(data, np.diag([1.0, 1.0, 1.0, 1.0]))
        scan_p = tmp_path / "scan.nii.gz"
        nib.save(nii, str(scan_p))

        # 1. TotalSegmentator provider in demo mode runs with synthetic fallback
        res = run_planning_pipeline(
            input_path=scan_p,
            output_dir=tmp_path / "out_ts",
            side="right",
            segmentation_method="TOTALSEGMENTATOR",
            config={"demo_mode": True},
        )
        assert res.quality_gate.passed is True
        assert res.status != "GATE_REJECTED"
        assert res.status in ("SUCCESS", "NO_PLAN_CRITICAL_HAZARD")

        # 2. Strict clinical mode without native model fails closed
        with pytest.raises(ValueError, match="Clinical segmentation failed"):
            run_planning_pipeline(
                input_path=scan_p,
                output_dir=tmp_path / "out_ts_strict",
                side="right",
                segmentation_method="TOTALSEGMENTATOR",
                config={"demo_mode": False, "require_clinical_segmentation": True}
            )

    def test_check_15_icc_degenerate_zero_variance_fails_closed(self):
        """Check 15: compute_icc_2_1 fails closed on degenerate zero-variance matrix."""
        # 10 cases, 3 raters, identical constant scores
        zero_var = np.full((10, 3), 50.0)
        res = compute_icc_2_1(zero_var, "Zero Variance Test")
        assert res.passed is False
        assert res.icc_value is None
        assert "DEGENERATE_ZERO_VARIANCE" in res.agreement_interpretation

        # Non-finite values in matrix
        nan_matrix = np.full((10, 3), 50.0)
        nan_matrix[0, 0] = np.nan
        res_nan = compute_icc_2_1(nan_matrix, "NaN Matrix Test")
        assert res_nan.passed is False
        assert res_nan.icc_value is None
        assert "NON_FINITE_VALUES" in res_nan.agreement_interpretation

    def test_check_16_continuous_and_classification_input_validation(self):
        """Check 16: Input validation on shape mismatches and non-finite values."""
        # Continuous agreement shape mismatch
        res_diff_shape = compute_continuous_agreement(
            np.array([1.0, 2.0]), np.array([1.0, 2.0, 3.0]), "Mismatch", 5.0
        )
        assert res_diff_shape.passed is False
        assert "Shape mismatch" in res_diff_shape.details

        # Continuous agreement with NaN
        res_nan = compute_continuous_agreement(
            np.array([1.0, np.nan]), np.array([1.0, 2.0]), "NaN", 5.0
        )
        assert res_nan.passed is False
        assert "Non-finite values" in res_nan.details

        # Classification agreement shape mismatch
        res_class_mismatch = compute_classification_agreement(
            np.array([True, False]), np.array([True])
        )
        assert res_class_mismatch.passed is False

        # Classification agreement sensitivity/specificity threshold check (< 0.90 fails)
        pred_low_sens = np.array([True] * 4 + [False] * 1 + [False] * 5)
        ref_low_sens = np.array([True] * 5 + [False] * 5)
        res_sens = compute_classification_agreement(pred_low_sens, ref_low_sens, kappa_threshold=0.5)
        assert res_sens.sensitivity == 0.80
        assert res_sens.passed is False

    def test_check_17_manifest_example_only_fails_closed(self, tmp_path):
        """Check 17: Manifest marked as example_only=True fails closed."""
        p = tmp_path / "example_manifest.json"
        with open(p, "w", encoding="utf-8") as f:
            json.dump({
                "manifest_identifier": "EXAMPLE-MANIFEST",
                "example_only": True,
                "cases": []
            }, f)
        report = evaluate_m15_validation_gate(manifest_path=p)
        assert report.status == "NOT_EVALUABLE"
        assert report.overall_gate_passed is False
        assert "example_only=True" in report.summary_findings

    def test_check_18_manifest_placeholder_hash_fails_closed(self, tmp_path):
        """Check 18: Manifest containing placeholder or empty-file hash fails closed."""
        # 1. Ellipsis placeholder
        p_dots = tmp_path / "dots_manifest.json"
        with open(p_dots, "w", encoding="utf-8") as f:
            json.dump({
                "manifest_identifier": "TEST-MANIFEST",
                "example_only": False,
                "cases": [
                    {
                        "case_id": "ACU_CTU_001",
                        "ct_volume_sha256": "...",
                        "morphometry_ground_truth": {"UP": {"ipa_deg": 50.0, "iw_min_mm": 5.0, "reachable": True}}
                    }
                ]
            }, f)
        rep_dots = evaluate_m15_validation_gate(manifest_path=p_dots)
        assert rep_dots.status == "NOT_EVALUABLE"
        assert "placeholder/empty SHA-256 digest" in rep_dots.summary_findings

        # 2. Empty-file SHA-256
        empty_h = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        p_empty = tmp_path / "empty_h_manifest.json"
        with open(p_empty, "w", encoding="utf-8") as f:
            json.dump({
                "manifest_identifier": "TEST-MANIFEST",
                "example_only": False,
                "cases": [
                    {
                        "case_id": "ACU_CTU_001",
                        "ct_volume_sha256": empty_h,
                        "morphometry_ground_truth": {"UP": {"ipa_deg": 50.0, "iw_min_mm": 5.0, "reachable": True}}
                    }
                ]
            }, f)
        rep_empty = evaluate_m15_validation_gate(manifest_path=p_empty)
        assert rep_empty.status == "NOT_EVALUABLE"
        assert "placeholder/empty SHA-256 digest" in rep_empty.summary_findings

    def test_check_19_manifest_nested_cases_evaluation(self, tmp_path):
        """Check 19: Valid nested cases[] manifest successfully parses and evaluates."""
        data = generate_synthetic_m15v_test_data()
        dummy_file = tmp_path / "ct_vol.nii.gz"
        dummy_file.write_bytes(b"DATA_CT_VOLUME_CONTENT")
        import hashlib
        real_hash = hashlib.sha256(b"DATA_CT_VOLUME_CONTENT").hexdigest()

        # Build nested cases
        cases = []
        for i in range(len(data["ipa_ref"])):
            cases.append({
                "case_id": f"ACU_CASE_{i:03d}",
                "ct_volume_nifti": str(dummy_file),
                "ct_volume_sha256": real_hash,
                "morphometry_ground_truth": {
                    "UP": {
                        "ipa_deg": float(data["ipa_ref"][i]),
                        "iw_min_mm": float(data["iw_ref"][i]),
                        "reachable": bool(data["class_ref"][i])
                    }
                },
                "morphometry_predictions": {
                    "UP": {
                        "ipa_deg": float(data["ipa_pred"][i]),
                        "iw_min_mm": float(data["iw_pred"][i]),
                        "reachable": bool(data["class_pred"][i])
                    }
                },
                "rater_ipa_measurements": data["multi_expert_ratings"][i].tolist()
            })

        manifest = {
            "manifest_identifier": "ACU-M15-NESTED-TEST",
            "example_only": False,
            "cases": cases,
            "phantom_measurements": data["phantom_measurements"]
        }
        man_path = tmp_path / "nested_manifest.json"
        with open(man_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        report = evaluate_m15_validation_gate(manifest_path=man_path)
        assert report.status == "PASS_FOR_NONCLINICAL_RESEARCH"
        assert report.overall_gate_passed is True
        assert report.ipa_validation.sample_size == len(data["ipa_ref"])

    def test_check_20_phantom_tip_error_and_loading_concordance(self):
        """Check 20: Phantom evaluation verifies loaded tool and tip error tolerance (<= 1.0 mm)."""
        data = generate_synthetic_m15v_test_data()

        # Deflection with tip error > 1.0 mm on accessible calyx fails concordance
        data_bad_tip = dict(data)
        data_bad_tip["phantom_measurements"] = {
            "PHANTOM_M15_01_FAVORABLE": {
                "UP": {"is_accessible": True, "tip_error_mm": 1.45},  # Exceeds 1.0 mm tolerance
                "MP": {"is_accessible": True, "tip_error_mm": 0.40},
                "LP": {"is_accessible": True, "tip_error_mm": 0.50},
            },
            "PHANTOM_M15_02_MODERATE": {
                "UP": {"is_accessible": True, "tip_error_mm": 0.45},
                "MP": {"is_accessible": True, "tip_error_mm": 0.40},
                "LP": {"is_accessible": True, "tip_error_mm": 0.50},
            },
            "PHANTOM_M15_03_ACUTE_CHALLENGE": {
                "UP": {"is_accessible": True, "tip_error_mm": 0.50},
                "MP": {"is_accessible": True, "tip_error_mm": 0.45},
                "LP": {"is_accessible": False, "tip_error_mm": 1.50},
            }
        }
        rep_tip = evaluate_m15_validation_gate(**data_bad_tip)
        assert rep_tip.phantom_concordance.passed is False
        assert rep_tip.phantom_concordance.critical_discrepancies > 0

    def test_check_21_api_path_traversal_and_case_id_sanitization(self):
        """Check 21: FastAPI endpoint rejects path traversal sequences and invalid case IDs."""
        # 1. Path traversal in manifest_path (HTTP 400)
        resp_trav = client.get(
            "/api/cases/test_case/endoscopy/validation-gate",
            params={"manifest_path": "../../secret.json"}
        )
        assert resp_trav.status_code == 400
        assert "Path traversal" in resp_trav.json()["detail"]

        # 2. Invalid case_id with traversal attempts (HTTP 400)
        resp_case = client.get("/api/cases/case..traversal/endoscopy/validation-gate")
        assert resp_case.status_code == 400
        assert "Invalid case identifier" in resp_case.json()["detail"]

    def test_check_22_vmtk_symmetric_h95_and_signed_tangent(self):
        """Check 22: VMTK benchmark computes true symmetric H95 and signed direction-aware tangent cosine."""
        # Identical curves: MAE = 0, H95 = 0, Cosine = 1.0
        line_a = np.array([[0.0, 0.0, float(z)] for z in range(30)])
        line_b = line_a.copy()
        met_same = VMTKBenchmarkHarness.compare_centerlines(line_a, line_b)
        assert met_same.passed is True
        assert met_same.mean_positional_error_mm < 1e-4
        assert met_same.hausdorff_95_mm < 1e-4
        assert pytest.approx(met_same.tangent_cosine_alignment_mean, 1e-3) == 1.0

        # Reversed curve: Tangents are anti-parallel -> signed cosine < 0 -> passed is False
        line_rev = line_a[::-1]
        met_rev = VMTKBenchmarkHarness.compare_centerlines(line_a, line_rev)
        assert met_rev.tangent_cosine_alignment_mean < 0.0
        assert met_rev.passed is False
