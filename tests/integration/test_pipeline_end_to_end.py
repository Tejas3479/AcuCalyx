"""
End-to-end integration test for the AcuCalyx Planning Pipeline.

Verifies complete execution from synthetic CT phantom through to:
- Quality gate validation
- Calculus detection & volumetry
- PCS visibility gate
- Flank sampling & conical target zones
- Pareto trajectory extraction
- Empirical Monte Carlo perturbation
- Virtual fluoroscopy simulation
- GLB/STL mesh export
- Auditable Preoperative Planning PDF Report
- Cryptographic provenance tracking
"""

from pathlib import Path
import tempfile
import numpy as np
import pytest

from tests.phantom.phantom_generator import generate_synthetic_pcnl_phantom, save_phantom_to_nifti
from acucalyx.pipeline import run_planning_pipeline, PlanningPipelineResult


def test_end_to_end_pipeline_execution():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        input_nii = tmp_path / "phantom_input.nii.gz"
        output_dir = tmp_path / "case_output"

        # 1. Generate synthetic phantom CT
        vol, spatial, gt = generate_synthetic_pcnl_phantom(
            grid_shape=(96, 96, 80),
            spacing_mm=(1.0, 1.0, 1.0),
            stone_radius_mm=5.0,
            noise_sigma_hu=2.0
        )
        save_phantom_to_nifti(vol, spatial, input_nii)

        # 2. Execute planning pipeline
        cfg = {
            "coarse_step_mm": 15.0,
            "monte_carlo_samples": 50,
            "min_stone_voxels": 4
        }
        res: PlanningPipelineResult = run_planning_pipeline(
            input_path=input_nii,
            output_dir=output_dir,
            side="left",
            config=cfg
        )

        # 3. Assertions
        assert res.status == "SUCCESS"
        assert res.quality_gate.passed is True

        # Stones detection
        assert len(res.stones) >= 1
        stone = res.stones[0]
        # Distance between detected centroid and ground truth stone center < 3mm
        dist_to_gt = np.linalg.norm(stone.centroid_lps_mm - gt.stone_center_mm)
        assert dist_to_gt < 3.0

        # Candidates & Pareto optimization
        assert len(res.candidates) >= 1
        top_cand = res.candidates[0]
        assert top_cand.tract_length_mm > 0.0

        # Monte Carlo
        assert top_cand.candidate_id in res.monte_carlo_assessments
        mc_list = res.monte_carlo_assessments[top_cand.candidate_id]
        assert len(mc_list) >= 1
        for mc in mc_list:
            assert 0.0 <= mc.collision_probability <= 1.0

        # Fluoroscopy
        assert top_cand.candidate_id in res.fluoroscopy_views
        views = res.fluoroscopy_views[top_cand.candidate_id]
        assert "BULLS_EYE" in views
        assert "PROGRESSION" in views
        assert views["BULLS_EYE"].projected_needle_length_2d_mm < views["PROGRESSION"].projected_needle_length_2d_mm

        # 3D Meshes
        assert (output_dir / "meshes" / "kidney.glb").is_file()
        assert (output_dir / "meshes" / "stones.glb").is_file()
        assert (output_dir / "meshes" / f"needle_{top_cand.candidate_id}.glb").is_file()

        # PDF Report
        pdf_file = output_dir / "report.pdf"
        assert pdf_file.is_file()
        assert pdf_file.stat().st_size > 1000  # ReportLab PDF must have content
        with open(pdf_file, "rb") as f:
            header = f.read(5)
            assert header == b"%PDF-"

        # JSON Artifacts
        assert (output_dir / "quality.json").is_file()
        assert (output_dir / "stones.json").is_file()
        assert (output_dir / "candidates.json").is_file()
        assert (output_dir / "uncertainty.json").is_file()
        assert (output_dir / "provenance.json").is_file()
