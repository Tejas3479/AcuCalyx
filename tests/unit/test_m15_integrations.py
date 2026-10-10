"""
AcuCalyx Automated Test Suite: Milestone M15 External Resources & Tool Integrations
Governed by ACU-M15-EXEC-PLAN-2026-V2.

Tests:
1. SimpleITK Medical Imaging Bridge (Resampling, Distance Maps, Morphology)
2. TotalSegmentator v2 Adapter (Class Mappings, Provenance, Hazard Segmentation)
3. nnU-Net v2 Dataset Packaging & Quality Metrics (dataset.json, NIfTI, Dice, HD95)
4. 3D Slicer & MONAI Label Expert Annotation Bridge (Presets, Consensus, Inter-Rater)
5. VMTK Centerline Benchmarking Harness (SlicerVMTK script, Distance Ridge, Agreement)
6. Public Datasets & Licensing Audit Registry (KiTS23, TRUSTED, PCNL-Ref-30)
"""

import json
from pathlib import Path
import numpy as np
import pytest

from acucalyx.geometry.simpleitk_bridge import (
    HAS_SITK,
    numpy_to_sitk,
    sitk_to_numpy,
    resample_to_isotropic,
    compute_signed_maurer_distance_map,
    extract_largest_connected_component,
    binary_morphology,
)
from acucalyx.integrations.totalsegmentator_adapter import (
    TotalSegmentatorAdapter,
    TotalSegmentatorOutput,
    TOTALSEGMENTATOR_CLASSES,
    ACUCALYX_HAZARD_CATEGORY_MAP,
)
from acucalyx.integrations.nnunet_pipeline import (
    NnunetPipelineManager,
    NnunetDatasetConfig,
    NNUNET_PCNL_LABELS,
)
from acucalyx.integrations.slicer_monailabel_bridge import (
    SlicerMonaiBridge,
    SLICER_PCNL_SEGMENT_DEFINITIONS,
    InterRaterConsensusReport,
    MonaiLabelClient,
)
from acucalyx.endoscopy.vmtk_benchmark import (
    VMTKBenchmarkHarness,
    CenterlineBenchmarkMetrics,
)
from acucalyx.data.dataset_registry import (
    DatasetLicenseType,
    get_dataset_metadata,
    list_datasets,
)


# =============================================================================
# 1. SimpleITK Bridge Tests
# =============================================================================

class TestSimpleITKBridge:
    def test_sitk_availability(self):
        assert HAS_SITK is True

    def test_numpy_sitk_roundtrip(self):
        arr = np.zeros((20, 25, 30), dtype=np.int16)
        arr[5:15, 8:18, 10:20] = 500
        img = numpy_to_sitk(arr, spacing_mm=(1.5, 1.5, 2.0), origin_lps_mm=(10.0, 20.0, 30.0))
        assert img is not None

        out_arr, meta = sitk_to_numpy(img)
        assert out_arr.shape == (20, 25, 30)
        assert out_arr[10, 10, 15] == 500
        assert meta.spacing_mm == (1.5, 1.5, 2.0)
        assert meta.origin_lps_mm == (10.0, 20.0, 30.0)

    def test_resample_to_isotropic(self):
        arr = np.zeros((10, 20, 20), dtype=np.float32)
        arr[3:7, 5:15, 5:15] = 100.0
        # Z-spacing is 3.0 mm, X/Y is 1.0 mm -> isotropic 1.0 mm should expand Z to 30 slices
        iso_arr = resample_to_isotropic(arr, current_spacing_mm=(1.0, 1.0, 3.0), target_spacing_mm=1.0)
        assert iso_arr.shape[0] == 30
        assert iso_arr.shape[1] == 20
        assert iso_arr.shape[2] == 20

    def test_signed_maurer_distance_map(self):
        mask = np.zeros((30, 30, 30), dtype=np.uint8)
        # Sphere of radius 6 voxels at center (15, 15, 15)
        z, y, x = np.ogrid[:30, :30, :30]
        sphere = ((x - 15)**2 + (y - 15)**2 + (z - 15)**2) <= 36
        mask[sphere] = 1

        dist = compute_signed_maurer_distance_map(mask, spacing_mm=(1.0, 1.0, 1.0), inside_is_positive=True)
        # Center should be positive distance inside (approx 4.5 - 6 mm depending on discretization)
        assert dist[15, 15, 15] >= 4.0
        # Corner outside should be negative
        assert dist[0, 0, 0] < -10.0

    def test_extract_largest_connected_component(self):
        mask = np.zeros((20, 20, 20), dtype=np.uint8)
        mask[2:4, 2:4, 2:4] = 1    # Small island: 8 voxels
        mask[10:16, 10:16, 10:16] = 1  # Large component: 216 voxels

        largest = extract_largest_connected_component(mask)
        assert largest[3, 3, 3] == 0       # Small island removed
        assert largest[12, 12, 12] == 1    # Large component preserved


# =============================================================================
# 2. TotalSegmentator v2 Adapter Tests
# =============================================================================

class TestTotalSegmentatorAdapter:
    def test_classes_and_hazard_mapping(self):
        assert 1 in TOTALSEGMENTATOR_CLASSES and TOTALSEGMENTATOR_CLASSES[1] == "spleen"
        assert 2 in TOTALSEGMENTATOR_CLASSES and TOTALSEGMENTATOR_CLASSES[2] == "kidney_right"
        assert 17 in TOTALSEGMENTATOR_CLASSES and TOTALSEGMENTATOR_CLASSES[17] == "colon"

        assert ACUCALYX_HAZARD_CATEGORY_MAP["colon"] == "VISCERAL_CRITICAL"
        assert ACUCALYX_HAZARD_CATEGORY_MAP["aorta"] == "VASCULAR_MAJOR"
        assert ACUCALYX_HAZARD_CATEGORY_MAP["kidney_right"] == "TARGET_ORGAN"

    def test_synthetic_totalseg_execution(self):
        adapter = TotalSegmentatorAdapter(task="total", fast=True, model_version="v2.4.0")
        vol = np.zeros((40, 50, 60), dtype=np.int16)

        out = adapter.segment_volume(vol, target_kidney="right", force_mock=True)
        assert isinstance(out, TotalSegmentatorOutput)
        assert out.multilabel_volume.shape == (40, 50, 60)
        assert "spleen" in out.hazard_masks
        assert "liver" in out.hazard_masks
        assert "colon" in out.hazard_masks
        assert "kidney_right" in out.hazard_masks

        # Provenance verification
        assert out.provenance.task_name == "total"
        assert out.provenance.model_version == "v2.4.0"
        assert out.provenance.license_identifier == "Apache-2.0"
        assert len(out.provenance.input_volume_sha256) == 64


# =============================================================================
# 3. nnU-Net v2 Pipeline Manager Tests
# =============================================================================

class TestNnunetPipelineManager:
    def test_dataset_json_generation(self, tmp_path):
        mgr = NnunetPipelineManager(output_root=tmp_path)
        json_path = mgr.write_dataset_json()
        assert json_path.is_file()

        with open(json_path, "r") as f:
            meta = json.load(f)
        assert meta["dataset_name"] == "Dataset501_AcuCalyxPCNL"
        assert "renal_pelvis" in meta["labels"]
        assert meta["labels"]["calculus_burden"] == 5
        assert meta["channel_names"] == {"0": "CT"}

    def test_case_packaging_and_metrics(self, tmp_path):
        mgr = NnunetPipelineManager(output_root=tmp_path)
        ct_arr = np.zeros((15, 20, 25), dtype=np.int16)
        lbl_arr = np.zeros((15, 20, 25), dtype=np.uint8)
        lbl_arr[5:10, 8:14, 10:18] = 1

        img_p, lbl_p = mgr.package_case("CASE_001", ct_arr, lbl_arr)
        assert img_p.exists()
        assert lbl_p.exists()
        assert mgr.config.num_training_cases == 1

        # Test metrics
        pred_arr = lbl_arr.copy()
        pred_arr[9, 13, 17] = 0  # 1 voxel difference
        dice = NnunetPipelineManager.compute_segmentation_dice(pred_arr, lbl_arr)
        assert dice > 0.95

        hd95 = NnunetPipelineManager.compute_hd95(pred_arr, lbl_arr)
        assert hd95 <= 1.5


# =============================================================================
# 4. 3D Slicer & MONAI Label Bridge Tests
# =============================================================================

class TestSlicerMonaiBridge:
    def test_slicer_schema_export(self, tmp_path):
        schema_path = tmp_path / "Segment_Definitions.json"
        out_p = SlicerMonaiBridge.export_slicer_segment_schema(schema_path)
        assert out_p.is_file()

        with open(out_p, "r") as f:
            data = json.load(f)
        assert "segmentDefinitions" in data
        names = [s["name"] for s in data["segmentDefinitions"]]
        assert "Renal Pelvis" in names
        assert "Calculus Burden" in names

    def test_majority_voting_consensus(self):
        m1 = np.array([1, 1, 0, 2], dtype=np.uint8)
        m2 = np.array([1, 0, 0, 2], dtype=np.uint8)
        m3 = np.array([1, 1, 0, 1], dtype=np.uint8)

        cons = SlicerMonaiBridge.compute_majority_voting_consensus([m1, m2, m3])
        # Voxel 0: 1,1,1 -> 1
        # Voxel 1: 1,0,1 -> 1
        # Voxel 2: 0,0,0 -> 0
        # Voxel 3: 2,2,1 -> 2
        assert list(cons) == [1, 1, 0, 2]

    def test_inter_rater_concordance(self):
        m1 = np.zeros((10, 10, 10), dtype=np.uint8)
        m2 = np.zeros((10, 10, 10), dtype=np.uint8)
        m1[2:8, 2:8, 2:8] = 1
        m2[2:8, 2:8, 2:8] = 1
        m2[7, 7, 7] = 0  # minor variation

        rep = SlicerMonaiBridge.evaluate_inter_rater_concordance([m1, m2])
        assert rep.num_raters == 2
        assert rep.pairwise_dice_mean > 0.95
        assert rep.inter_observer_volume_cv_percent < 5.0

    def test_monailabel_client_offline(self):
        client = MonaiLabelClient(server_url="http://127.0.0.1:9999")
        info = client.get_server_info()
        assert info["status"] == "OFFLINE"


# =============================================================================
# 5. VMTK Centerline Benchmarking Tests
# =============================================================================

class TestVMTKBenchmarkHarness:
    def test_slicer_vmtk_script_generation(self):
        script = VMTKBenchmarkHarness.generate_slicer_vmtk_script(
            surface_stl_path=Path("mesh.stl"),
            source_seed_lps=np.array([45.0, -10.0, -32.0]),
            target_seed_lps=np.array([25.0, 15.0, 0.0]),
            output_centerline_vtk=Path("centerline.vtk"),
        )
        assert "vmtkscripts.vmtkCenterlines" in script
        assert "45.0" in script
        assert "centerline.vtk" in script

    def test_distance_ridge_centerline_and_comparison(self):
        # Cylindrical synthetic lumen along X axis
        mask = np.zeros((20, 20, 40), dtype=np.uint8)
        mask[8:13, 8:13, 5:35] = 1  # 5x5 tube along Z

        start = np.array([10.0, 10.0, 5.0])
        end = np.array([10.0, 10.0, 35.0])

        ref_pts = VMTKBenchmarkHarness.compute_distance_ridge_centerline(
            binary_lumen_mask=mask,
            start_point_lps=start,
            end_point_lps=end,
        )
        assert len(ref_pts) == 30

        # Compare AcuCalyx straight line vs distance ridge
        acu_pts = np.linspace(start, end, 30)
        metrics = VMTKBenchmarkHarness.compare_centerlines(acu_pts, ref_pts, "DistanceRidgeRef")

        assert metrics.mean_positional_error_mm < 1.0
        assert metrics.tangent_cosine_alignment_mean > 0.95
        assert metrics.passed is True


# =============================================================================
# 6. Public Datasets & Licensing Audit Tests
# =============================================================================

class TestDatasetRegistry:
    def test_kits23_license_audit(self):
        meta = get_dataset_metadata("KITS23")
        assert meta.license_type == DatasetLicenseType.NON_COMMERCIAL_RESEARCH_ONLY
        assert meta.license_identifier == "CC BY-NC-SA 4.0"
        assert meta.commercial_eligibility is False
        assert meta.collecting_system_annotated is False
        assert "minor calyx" in meta.clinical_limitations.lower()

    def test_trusted_dataset_audit(self):
        meta = get_dataset_metadata("TRUSTED")
        assert meta.license_type == DatasetLicenseType.OPEN_COMMERCIAL_PERMITTED
        assert meta.license_identifier == "CC BY 4.0"
        assert meta.commercial_eligibility is True
        assert "M14" in meta.intended_milestone_phase

    def test_acucalyx_reference_cohort_audit(self):
        meta = get_dataset_metadata("ACUCALYX_PCNL_REF_30")
        assert meta.license_type == DatasetLicenseType.PROPRIETARY_CLINICAL_BENCHMARK
        assert meta.case_count == 30
        assert meta.collecting_system_annotated is True
        assert meta.calculi_annotated is True
        assert meta.commercial_eligibility is True

    def test_list_datasets_filter(self):
        all_ds = list_datasets()
        assert len(all_ds) >= 4
        cs_only = list_datasets(collecting_system_only=True)
        assert len(cs_only) == 1
        assert cs_only[0].dataset_id == "ACUCALYX_PCNL_REF_30"
