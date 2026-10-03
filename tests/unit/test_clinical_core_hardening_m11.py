"""
Unit Tests for Milestone M11: PCNL Clinical Core Hardening & Scope Freeze

Verifies:
1. Descriptive Guy's Stone Score (GSS Grades I-IV) per Thomas et al. (2011)
2. Descriptive S.T.O.N.E. Nephrolithometry score (5-13 points) per Okhunov et al. (2013)
3. FDA CDS Scope Boundary Invariants (no treatment recommendations or predictive claims)
4. Anatomical Structure Provenance and fail-closed clinical readiness gating
5. Physical LPS to 2D MPR slice coordinate translation integrity
"""

import pytest
import numpy as np

from acucalyx.stones.scoring import (
    GuysStoneGrade,
    compute_guys_stone_score,
    compute_stone_nephrolithometry
)
from acucalyx.anatomy.segmentation import (
    AnatomicalCorridorMasks,
    OrganLabel,
    StructureProvenance
)
from acucalyx.anatomy.backends import (
    HeuristicFallbackBackend,
    ManualReferenceMaskBackend,
    PcnlSpecializedModelBackend,
    get_segmentation_backend
)
from acucalyx.geometry.coordinates import SpatialOrientation


class TestGuysStoneScore:
    """Verifies Guy's Stone Score grading rules per Thomas et al. (2011)."""

    def test_grade_i_solitary_lower_pole_stone(self):
        result = compute_guys_stone_score(
            stone_count=1,
            stone_locations=["lower_pole"],
            is_staghorn=False,
            has_abnormal_anatomy=False
        )
        assert result.grade == GuysStoneGrade.GRADE_I
        assert "lower calyx" in result.description.lower()
        assert not result.is_staghorn

    def test_grade_ii_solitary_upper_pole_stone(self):
        result = compute_guys_stone_score(
            stone_count=1,
            stone_locations=["upper_pole"],
            is_staghorn=False,
            has_abnormal_anatomy=False
        )
        assert result.grade == GuysStoneGrade.GRADE_II
        assert "upper pole" in result.description.lower()

    def test_grade_ii_multiple_stones_normal_anatomy(self):
        result = compute_guys_stone_score(
            stone_count=3,
            stone_locations=["lower_pole", "middle_pole"],
            is_staghorn=False,
            has_abnormal_anatomy=False
        )
        assert result.grade == GuysStoneGrade.GRADE_II

    def test_grade_iii_partial_staghorn(self):
        result = compute_guys_stone_score(
            stone_count=1,
            stone_locations=["pelvis", "lower_pole"],
            is_staghorn=False,
            is_partial_staghorn=True,
            has_abnormal_anatomy=False
        )
        assert result.grade == GuysStoneGrade.GRADE_III
        assert "partial staghorn" in result.description.lower()

    def test_grade_iii_diverticulum_calculus(self):
        result = compute_guys_stone_score(
            stone_count=1,
            stone_locations=["calyceal_diverticulum"],
            in_calyceal_diverticulum=True
        )
        assert result.grade == GuysStoneGrade.GRADE_III

    def test_grade_iv_full_staghorn(self):
        result = compute_guys_stone_score(
            stone_count=1,
            stone_locations=["pelvis", "upper_pole", "middle_pole", "lower_pole"],
            is_staghorn=True
        )
        assert result.grade == GuysStoneGrade.GRADE_IV
        assert result.is_staghorn

    def test_grade_iv_spina_bifida(self):
        result = compute_guys_stone_score(
            stone_count=1,
            stone_locations=["lower_pole"],
            is_staghorn=False,
            has_spina_bifida_or_dysraphism=True
        )
        assert result.grade == GuysStoneGrade.GRADE_IV


class TestStoneNephrolithometryScore:
    """Verifies S.T.O.N.E. score (range: 5 to 13 points) per Okhunov et al. (2013)."""

    def test_minimum_possible_score(self):
        # Size < 400 (1), Tract <= 100 (1), No hydronephrosis (1), Calyces <= 1 (1), HU <= 950 (1) -> 5 points
        res = compute_stone_nephrolithometry(
            stone_surface_area_mm2=250.0,
            tract_length_mm=75.0,
            has_hydronephrosis_or_obstruction=False,
            involved_calyces_count=1,
            mean_hu=800.0
        )
        assert res.total_score == 5
        assert res.size_points == 1
        assert res.tract_length_points == 1
        assert res.obstruction_points == 1
        assert res.number_calyces_points == 1
        assert res.essence_points == 1
        assert res.complexity_tier == "LOW"

    def test_maximum_possible_score(self):
        # Size >= 1600 (4), Tract > 100 (2), Obstruction (2), Calyces > 3 (3), HU > 950 (2) -> 13 points
        res = compute_stone_nephrolithometry(
            stone_surface_area_mm2=1800.0,
            tract_length_mm=125.0,
            has_hydronephrosis_or_obstruction=True,
            involved_calyces_count=4,
            mean_hu=1150.0
        )
        assert res.total_score == 13
        assert res.size_points == 4
        assert res.tract_length_points == 2
        assert res.obstruction_points == 2
        assert res.number_calyces_points == 3
        assert res.essence_points == 2
        assert res.complexity_tier == "HIGH"

    def test_intermediate_score_calculation(self):
        res = compute_stone_nephrolithometry(
            stone_surface_area_mm2=600.0,   # 2 pts
            tract_length_mm=95.0,           # 1 pt
            has_hydronephrosis_or_obstruction=False, # 1 pt
            involved_calyces_count=2,       # 2 pts
            mean_hu=1050.0                  # 2 pts
        )
        assert res.total_score == 8
        assert res.complexity_tier == "MODERATE"

    def test_cds_boundary_guardrail_presence(self):
        res = compute_stone_nephrolithometry(
            stone_surface_area_mm2=500.0,
            tract_length_mm=80.0,
            has_hydronephrosis_or_obstruction=False,
            involved_calyces_count=1,
            mean_hu=900.0
        )
        # Invariant: Must include regulatory non-prescriptive disclaimer
        assert "descriptive nephrolithometry score only" in res.regulatory_disclaimer.lower()
        assert "does not constitute an autonomous treatment recommendation" in res.regulatory_disclaimer.lower()


class TestStructureProvenanceAndGating:
    """Verifies anatomical provenance tracking and clinical readiness gates."""

    def test_heuristic_fallback_flags_non_clinical(self):
        spatial = SpatialOrientation.from_dicom_parameters(
            image_orientation_patient=[1, 0, 0, 0, 1, 0],
            image_position_patient=[0, 0, 0],
            pixel_spacing=[1.0, 1.0],
            slice_spacing=1.0
        )
        backend = HeuristicFallbackBackend()
        dummy_vol = np.zeros((40, 40, 40), dtype=np.float32)
        corridor = backend.segment_volume(dummy_vol, spatial)

        # Invariant: Heuristic fallback MUST fail clinical readiness gate
        assert not corridor.is_clinical_ready
        for prov in corridor.provenance.values():
            assert prov.segmentation_status == "HEURISTIC_FALLBACK"
            assert prov.tier == "SYNTHETIC_FALLBACK"

    def test_manual_reference_passes_clinical_gate(self):
        spatial = SpatialOrientation.from_dicom_parameters(
            image_orientation_patient=[1, 0, 0, 0, 1, 0],
            image_position_patient=[0, 0, 0],
            pixel_spacing=[1.0, 1.0],
            slice_spacing=1.0
        )
        corridor = AnatomicalCorridorMasks(spatial_orientation=spatial)
        mask = np.ones((20, 20, 20), dtype=bool)

        prov = StructureProvenance(
            organ_label="kidney_left",
            tier="REFERENCE_MANUAL",
            source_backend="Manual_Consensus_Standard",
            model_version="1.0.0",
            model_hash_sha256="N/A_MANUAL",
            training_dataset_id="Expert_Consensus_Cohort",
            visibility_state="DIRECTLY_VISUALIZED",
            segmentation_status="CLINICIAN_EDITED",
            confidence_qc_score=1.0,
            clinician_review_status="ACCEPTED"
        )
        corridor.set_mask(OrganLabel.KIDNEY_LEFT, mask, provenance=prov)

        assert corridor.is_clinical_ready

    def test_pcnl_specialized_backend_factory(self):
        backend = get_segmentation_backend("pcnl_specialized", model_version="1.2.0")
        assert isinstance(backend, PcnlSpecializedModelBackend)
        assert backend.backend_name == "PCNL_Specialized_Renal_v1.2.0"


class Test3DTo2DCoordinateTranslation:
    """Verifies physical LPS coordinate to 2D slice index transformation."""

    def test_affine_coordinate_mapping(self):
        spatial = SpatialOrientation.from_dicom_parameters(
            image_orientation_patient=[1, 0, 0, 0, 1, 0],
            image_position_patient=[-100.0, -100.0, 50.0],
            pixel_spacing=[0.8, 0.8],
            slice_spacing=1.5
        )

        # Target point at physical LPS
        p_lps = np.array([-60.0, -40.0, 80.0])
        v_idx = spatial.physical_to_voxel(p_lps)

        # Reverse back to physical
        p_reconstructed = spatial.voxel_to_physical(v_idx)
        np.testing.assert_allclose(p_reconstructed, p_lps, atol=1e-5)
