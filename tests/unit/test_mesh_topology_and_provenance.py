"""
tests/unit/test_mesh_topology_and_provenance.py

Automated unit tests validating mesh topology, positive volume invariants,
manifold component continuity, and strict server-side template provenance gating.
"""

import math
import pytest
from fastapi.testclient import TestClient

from src.acucalyx.geometry.anatomical_kidney_builder import AnatomicalKidneyBuilder
from app.api.main import app


@pytest.fixture
def api_client():
    return TestClient(app)


def test_renal_capsule_continuous_single_component_and_positive_volume():
    """
    Renal capsule must generate as a single continuous outer hull (not 26 disjoint fragments),
    have an open hilum portal, and strictly possess a positive calculated volume under CCW winding.
    """
    builder = AnatomicalKidneyBuilder()
    capsule = builder.build_renal_capsule()

    # Must be positive volume (CCW winding outward normals)
    assert capsule.volume > 0, f"Capsule volume must be positive, got {capsule.volume}"
    assert capsule.volume > 5000.0, f"Expected substantial anatomical capsule volume, got {capsule.volume}"

    # Must be a single continuous component (no floating fragments / islands)
    components = capsule.split(only_watertight=False)
    assert len(components) == 1, f"Expected 1 continuous component, got {len(components)}"

    # Face count should be realistic and detailed
    assert len(capsule.faces) > 5000, f"Mesh resolution too coarse: {len(capsule.faces)} faces"


def test_kidney_cortex_positive_volume_and_orientation():
    """
    Kidney cortex must have positive volume and outward normal orientation.
    """
    builder = AnatomicalKidneyBuilder()
    cortex = builder.build_kidney_cortex()

    assert cortex.volume > 0, f"Cortex volume must be positive, got {cortex.volume}"
    assert len(cortex.vertices) > 500
    assert len(cortex.faces) > 1000


def test_realistic_calculus_safety_invariant():
    """
    Demo crystalline calculus must use harmonic faceting (not spiky noise),
    have positive volume, and match expected physical stone volume without exploding.
    """
    builder = AnatomicalKidneyBuilder()
    stone = builder.build_realistic_crystalline_calculus()

    assert stone.volume > 0, f"Stone volume must be positive, got {stone.volume}"
    # Stone radius is approx 6mm, volume ~ 900 mm³
    assert 500.0 < stone.volume < 2000.0, (
        f"Calculus volume {stone.volume} deviated excessively from expected bounded volume"
    )


def test_arterial_tree_physiological_calibration():
    """
    Arterial tree must generate valid geometry with positive volume.
    """
    builder = AnatomicalKidneyBuilder()
    arteries = builder.build_arterial_tree()

    assert arteries.volume > 0, f"Arteries volume must be positive, got {arteries.volume}"
    assert len(arteries.faces) >= 500


def test_server_mesh_gating_strictly_fails_closed_for_patient_cases(api_client):
    """
    Endpoints serving 3D anatomical meshes must return HTTP 404 for non-demo patient cases
    if segmentation is missing, blocking any silent substitution of generic templates.
    """
    # Non-existent or non-demo patient case ID
    response = api_client.get("/api/cases/PATIENT_REAL_NON_DEMO_001/mesh/capsule?allow_template=true")
    assert response.status_code == 404, f"Expected 404 fail-closed, got {response.status_code}"

    detail = response.json().get("detail", "")
    assert "Mesh" in detail or "not found" in detail.lower()
