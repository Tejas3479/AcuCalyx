"""
Global Pytest Fixtures and Test Lifecycle Hygiene Manager
Prevents test executions from polluting production data/cases with ephemeral phantom/demo cases.
"""

from pathlib import Path
import shutil
import pytest

from app.api.case_store import CASES_DIR, save_case_meta


@pytest.fixture(scope="session", autouse=True)
def setup_test_fixture_cases():
    """
    Initializes standard registered test case fixtures (e.g. 'test_case', 'demo_case', etc.)
    so that unit suites have explicit persisted demo cases on disk rather than relying on
    in-memory prefix bypasses.
    """
    CASES_DIR.mkdir(parents=True, exist_ok=True)
    fixture_ids = ["test_case", "demo_case", "demo_case_01", "DEMO_CASE_001"]
    created_dirs = []

    for fid in fixture_ids:
        fdir = CASES_DIR / fid
        fdir.mkdir(parents=True, exist_ok=True)
        save_case_meta(fid, {
            "case_id": fid,
            "is_demo": True,
            "state": "READY",
            "owner_doctor_id": "DOC_ELENA_CHEN",
            "target_side": "left"
        })
        created_dirs.append(fdir)

    yield

    for fdir in created_dirs:
        shutil.rmtree(fdir, ignore_errors=True)


@pytest.fixture(scope="session", autouse=True)
def clean_ephemeral_test_cases():
    """
    Records baseline cases before testing starts, and removes any
    ephemeral test artifacts (DEMO_PHANTOM_*, PATIENT_TEST_*, CASE_slip_*, CASE_malicious_*)
    created during the test run upon session completion.
    """
    baseline_folders = {p.name for p in CASES_DIR.iterdir() if p.is_dir()} if CASES_DIR.exists() else set()
    yield
    if CASES_DIR.exists():
        for p in CASES_DIR.iterdir():
            if p.is_dir() and p.name not in baseline_folders:
                if p.name.startswith(("DEMO_PHANTOM_", "PATIENT_TEST_", "CASE_slip_", "CASE_malicious_")):
                    shutil.rmtree(p, ignore_errors=True)
