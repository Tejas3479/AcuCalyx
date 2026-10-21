"""
Global Pytest Fixtures and Test Lifecycle Hygiene Manager
Prevents test executions from polluting production data/cases with ephemeral phantom/demo cases.
"""

from pathlib import Path
import shutil
import pytest

from app.api.case_store import CASES_DIR


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
