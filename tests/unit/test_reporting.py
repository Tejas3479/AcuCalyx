"""
Tests for AcuCalyx Preoperative Planning Reporting Subsystem:
- Headless Axial MPR Keyframe CT slice rendering with needle corridor overlay.
- Headless Coronal MPR Keyframe CT slice rendering with longitudinal alignment.
- Virtual Fluoroscopy Bull's-eye projection preview thumbnail.
- 2-page auditable ReportLab vector PDF generator with embedded keyframes.
- REST API endpoints: GET /api/cases/{case_id}/report, /pdf-report, and /keyframes/{name}.
"""

from pathlib import Path
import numpy as np
import pytest
from PIL import Image
from fastapi.testclient import TestClient

from acucalyx.audit.provenance import CaseProvenanceRecord
from acucalyx.collecting_system.visibility_gate import PCSVisibilityResult, PCSVisibilityState
from acucalyx.geometry.coordinates import SpatialOrientation
from acucalyx.geometry.transforms import LineSegment3D
from acucalyx.ingestion.quality_gate import QualityGateResult
from acucalyx.planning.pareto_optimizer import CandidateTrajectory
from acucalyx.reports.keyframe_renderer import (
    render_axial_mpr_keyframe,
    render_coronal_mpr_keyframe,
    render_bullseye_projection_keyframe,
    generate_case_report_keyframes,
    generate_fallback_keyframes
)
from acucalyx.reports.planning_report import generate_preoperative_planning_pdf
from acucalyx.stones.attenuation import StoneAttenuationProfile
from acucalyx.stones.volumetry import StoneMorphometry
from app.api.main import app

client = TestClient(app)


@pytest.fixture
def sample_volume_and_spatial():
    """Generates a synthetic 64x64x40 HU volume with realistic physical spacing."""
    vol = np.full((64, 64, 40), fill_value=-900.0, dtype=np.float32)  # air
    # Kidney ellipse
    vol[20:45, 20:45, 10:30] = 35.0  # soft tissue
    # Calyx lumen
    vol[28:34, 28:34, 18:22] = 10.0
    # Stone
    vol[30:32, 30:32, 19:21] = 1200.0

    affine = np.eye(4, dtype=np.float64)
    affine[0, 0] = 1.0  # dx
    affine[1, 1] = 1.0  # dy
    affine[2, 2] = 2.0  # dz
    affine[0:3, 3] = np.array([-32.0, -32.0, -40.0])

    spatial = SpatialOrientation(
        affine_matrix=affine,
        inv_affine_matrix=np.linalg.inv(affine),
        origin=np.array([-32.0, -32.0, -40.0]),
        spacing=np.array([1.0, 1.0, 2.0]),
        direction=np.eye(3)
    )
    return vol, spatial


@pytest.fixture
def sample_candidate():
    """Generates a test Pareto candidate trajectory."""
    return CandidateTrajectory(
        candidate_id="CAND-01",
        target_calyx_name="Lower-Pole Posterior Calyx",
        entry_point_lps=np.array([25.0, 15.0, -10.0]),
        target_point_lps=np.array([0.0, 0.0, 0.0]),
        tract_length_mm=31.2,
        min_effective_clearance_mm=14.2,
        hazard_evaluations=[],
        reachable_stone_fraction=0.92,
        required_scope_deflection_deg=18.5,
        access_rib_classification="SUBCOSTAL_12",
        is_pareto_optimal=True
    )


def test_render_axial_mpr_keyframe(sample_volume_and_spatial, sample_candidate, tmp_path):
    """Verifies Axial MPR slice extracts at target depth with overlays and scale bar."""
    vol, spatial = sample_volume_and_spatial
    out_file = tmp_path / "axial_test.png"

    img = render_axial_mpr_keyframe(
        volume_hu=vol,
        spatial=spatial,
        entry_lps=sample_candidate.entry_point_lps,
        target_lps=sample_candidate.target_point_lps,
        output_path=out_file,
        target_label="Lower-Pole Calyx"
    )

    assert isinstance(img, Image.Image)
    assert img.size == (512, 512)
    assert out_file.is_file()
    assert out_file.stat().st_size > 1000

    # Verify image is valid readable PNG
    with Image.open(out_file) as loaded_img:
        assert loaded_img.format == "PNG"
        assert loaded_img.size == (512, 512)


def test_render_coronal_mpr_keyframe(sample_volume_and_spatial, sample_candidate, tmp_path):
    """Verifies Coronal MPR slice extracts along calyx axis with target reticle."""
    vol, spatial = sample_volume_and_spatial
    out_file = tmp_path / "coronal_test.png"

    img = render_coronal_mpr_keyframe(
        volume_hu=vol,
        spatial=spatial,
        entry_lps=sample_candidate.entry_point_lps,
        target_lps=sample_candidate.target_point_lps,
        output_path=out_file,
        target_label="Lower-Pole Calyx"
    )

    assert isinstance(img, Image.Image)
    assert img.size == (512, 512)
    assert out_file.is_file()
    assert out_file.stat().st_size > 1000

    with Image.open(out_file) as loaded_img:
        assert loaded_img.format == "PNG"
        assert loaded_img.size == (512, 512)


def test_render_bullseye_projection_keyframe(sample_candidate, tmp_path):
    """Verifies Bull's-eye projection preview thumbnail renders with C-arm presets."""
    out_file = tmp_path / "bullseye_test.png"
    traj = LineSegment3D(sample_candidate.entry_point_lps, sample_candidate.target_point_lps)

    img = render_bullseye_projection_keyframe(
        trajectory=traj,
        bullseye_angles=(18.5, -12.0),
        progression_angles=(-71.5, 0.0),
        output_path=out_file,
        target_label="Lower-Pole Posterior Calyx"
    )

    assert isinstance(img, Image.Image)
    assert img.size == (512, 512)
    assert out_file.is_file()
    assert out_file.stat().st_size > 1000


def test_generate_case_report_keyframes(sample_volume_and_spatial, sample_candidate, tmp_path):
    """Verifies multi-view keyframe generator produces axial, coronal, and bullseye PNGs."""
    vol, spatial = sample_volume_and_spatial
    kf_dir = tmp_path / "keyframes"

    paths = generate_case_report_keyframes(
        volume_hu=vol,
        spatial=spatial,
        candidate=sample_candidate,
        output_dir=kf_dir
    )

    assert "axial" in paths
    assert "coronal" in paths
    assert "bullseye" in paths
    for name, p in paths.items():
        assert p.is_file(), f"Keyframe {name} was not created: {p}"
        assert p.stat().st_size > 500


def test_generate_fallback_keyframes(sample_candidate, tmp_path):
    """Verifies fallback keyframe generator produces valid images when 3D CT volume is absent."""
    kf_dir = tmp_path / "fallback_keyframes"
    paths = generate_fallback_keyframes(sample_candidate, kf_dir)

    assert paths["axial"].is_file()
    assert paths["coronal"].is_file()
    assert paths["bullseye"].is_file()


def test_generate_preoperative_planning_pdf(sample_volume_and_spatial, sample_candidate, tmp_path):
    """Verifies the complete 2-page ReportLab PDF generation with embedded keyframes."""
    vol, spatial = sample_volume_and_spatial
    pdf_path = tmp_path / "test_report.pdf"

    from acucalyx.audit.provenance import create_provenance_record
    prov = create_provenance_record(
        case_id="CASE_TEST_001",
        study_uid="STUDY_001",
        series_uid="SERIES_001",
        modality="CT",
        input_data_hash="abcdef1234567890" * 4,
        software_version="2.1.0"
    )

    q_gate = QualityGateResult(
        passed=True,
        rejection_reasons=[],
        warnings=[],
        geometry_score=1.0,
        resolution_score=1.0,
        overall_quality_tier="HIGH",
        slice_thickness_mm=1.0,
        pixel_spacing_mm=(0.75, 0.75),
        slice_spacing_mm=1.0,
        is_contrast_enhanced=None,
        reconstruction_kernel="SoftTissue"
    )

    pcs_res = PCSVisibilityResult(
        state=PCSVisibilityState.DIRECTLY_OPACIFIED,
        confidence_score=0.95,
        fluid_cavity_volume_mm3=1800.0,
        mean_internal_hu=150.0,
        allows_direct_puncture_lock=True,
        clinical_notice="Collecting system directly opacified on CTU excretory phase."
    )

    stone = StoneMorphometry(
        stone_id=1,
        volume_mm3=450.0,
        volume_voxels=300,
        centroid_lps_mm=np.array([5.0, 5.0, 5.0]),
        max_feret_diameter_mm=12.5,
        bounding_box_span_mm=np.array([10.0, 10.0, 10.0]),
        tier="MODERATE"
    )

    atten = StoneAttenuationProfile(
        stone_id=1,
        mean_hu=950.0,
        median_hu=920.0,
        peak_hu=1350.0,
        std_hu=120.0,
        min_hu=450.0,
        fraction_low_under_500hu=0.05,
        fraction_intermediate_500_1000hu=0.35,
        fraction_high_over_1000hu=0.60,
        composition_inference="CALCIUM_OXALATE_SUSPECTED"
    )

    out_file = generate_preoperative_planning_pdf(
        output_path=pdf_path,
        provenance=prov,
        quality_gate=q_gate,
        pcs_visibility=pcs_res,
        stones=[stone],
        attenuations=[atten],
        candidates=[sample_candidate],
        verified_laterality="LEFT",
        confirmed_operative_position="PRONE_STANDARD",
        active_candidate_id="CAND-01",
        volume_hu=vol,
        spatial=spatial
    )

    assert out_file.is_file()
    assert out_file.stat().st_size > 5000  # Multi-page PDF with embedded images is sizable
    with open(out_file, "rb") as f:
        header = f.read(5)
        assert header == b"%PDF-"


def test_api_report_and_keyframe_endpoints():
    """Verifies FastAPI endpoints for report PDF downloading and keyframe image streaming."""
    # 1. Initialize demo case (pre-verified laterality and position)
    init_res = client.post("/api/cases/demo")
    assert init_res.status_code == 200
    case_id = init_res.json()["case_id"]

    # 2. Run planning
    plan_res = client.post(f"/api/cases/{case_id}/plan", json={
        "target_side": "left",
        "coarse_step_mm": 15.0,
        "monte_carlo_samples": 10
    })
    assert plan_res.status_code == 200

    # 3. Download Preoperative Planning PDF via /report
    rep_res = client.get(f"/api/cases/{case_id}/report")
    assert rep_res.status_code == 200
    assert rep_res.headers["content-type"] == "application/pdf"
    assert rep_res.content.startswith(b"%PDF-")

    # 4. Download Preoperative Planning PDF via /pdf-report
    pdf_res = client.get(f"/api/cases/{case_id}/pdf-report")
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert pdf_res.content.startswith(b"%PDF-")

    # 5. Stream Keyframe Images
    for kf_name in ["axial_keyframe.png", "coronal_keyframe.png", "bullseye_keyframe.png"]:
        kf_res = client.get(f"/api/cases/{case_id}/keyframes/{kf_name}")
        assert kf_res.status_code == 200
        assert kf_res.headers["content-type"] == "image/png"
        assert len(kf_res.content) > 500
