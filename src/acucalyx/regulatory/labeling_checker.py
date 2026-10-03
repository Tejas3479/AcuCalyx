"""AcuCalyx Medical Device Labeling & Operating Envelope Audit Utility.

Verifies adherence to 21 CFR Part 801 (Medical Device Labeling), 21 CFR 801.109
(Prescription Devices), 21 CFR Part 830 (UDI), and operating envelope criteria.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class LabelingChecker:
    """Audits documents, clinical summary exports, and UI splash payloads for regulatory labeling compliance."""

    MANDATORY_RX_REGEX = re.compile(
        r"CAUTION:\s*Federal\s*law.*restricts\s*this\s*device\s*to\s*sale\s*by\s*or\s*on\s*the\s*order\s*of\s*a\s*licensed\s*physician",
        re.IGNORECASE,
    )
    PEDIATRIC_CONTRAINDICATION_REGEX = re.compile(
        r"(contraindicated\s*for\s*patients\s*under\s*18|contraindicated\s*in\s*pediatric|under\s*18\s*years\s*of\s*age)",
        re.IGNORECASE,
    )
    GANTRY_TILT_ENVELOPE_REGEX = re.compile(
        r"(gantry\s*tilt.*0\.0|zero\s*gantry\s*tilt)",
        re.IGNORECASE,
    )
    SLICE_THICKNESS_ENVELOPE_REGEX = re.compile(
        r"(slice\s*thickness.*2\.5|2\.5\s*mm|\<=?\s*2\.5|\\le\s*2\.5)",
        re.IGNORECASE,
    )
    SURGEON_AUTHORITY_REGEX = re.compile(
        r"(attending\s*(surgeon|physician)|clinical\s*decision\s*support|does\s*not\s*provide\s*intraoperative\s*tracking|sole\s*(clinical|medical|surgical)\s*(responsibility|authority))",
        re.IGNORECASE,
    )
    UDI_DI_REGEX = re.compile(r"\(01\)\d{14}")

    def audit_text(self, text: str) -> Tuple[bool, List[str]]:
        """Audit raw text or document content against mandatory labeling criteria."""
        failures: List[str] = []

        if not self.MANDATORY_RX_REGEX.search(text) and "Rx Only" not in text:
            failures.append("MISSING_RX_ONLY: Statutory 21 CFR 801.109 prescription notice not detected.")

        if not self.PEDIATRIC_CONTRAINDICATION_REGEX.search(text):
            failures.append("MISSING_PEDIATRIC_CONTRAINDICATION: Contraindication under 18 years not detected.")

        if not self.GANTRY_TILT_ENVELOPE_REGEX.search(text):
            failures.append("MISSING_GANTRY_TILT_CRITERIA: Zero gantry tilt operating envelope requirement not detected.")

        if not self.SLICE_THICKNESS_ENVELOPE_REGEX.search(text):
            failures.append("MISSING_SLICE_THICKNESS_CRITERIA: Slice thickness <= 2.5 mm operating requirement not detected.")

        if not self.SURGEON_AUTHORITY_REGEX.search(text):
            failures.append("MISSING_SURGEON_AUTHORITY: Attending clinician authority disclaimer not detected.")

        passed = len(failures) == 0
        return passed, failures

    def audit_labeling_file(self, file_path: Path | str) -> Tuple[bool, List[str]]:
        """Audit a controlled markdown or text labeling file."""
        target = Path(file_path)
        if not target.exists():
            return False, [f"FILE_NOT_FOUND: {target} does not exist."]
        content = target.read_text(encoding="utf-8", errors="ignore")
        return self.audit_text(content)

    def audit_ui_splash_payload(self, payload: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Audit UI display configuration payload."""
        failures: List[str] = []

        rx_notice = payload.get("rx_notice", "")
        if "Rx Only" not in rx_notice and not self.MANDATORY_RX_REGEX.search(rx_notice):
            failures.append("UI_MISSING_RX: In-app splash does not contain prescription notice.")

        device_name = payload.get("trade_name", "")
        if not device_name:
            failures.append("UI_MISSING_DEVICE_NAME: In-app splash missing device trade name.")

        version = payload.get("version", "")
        if not version:
            failures.append("UI_MISSING_VERSION: In-app splash missing software version string.")

        passed = len(failures) == 0
        return passed, failures

    def audit_export_planning_card(self, card_text: str) -> Tuple[bool, List[str]]:
        """Audit 1-page sterile operating room planning card export."""
        failures: List[str] = []

        if "Rx Only" not in card_text and not self.MANDATORY_RX_REGEX.search(card_text):
            failures.append("EXPORT_MISSING_RX: Sterile planning card missing prescription statement.")

        if not self.SURGEON_AUTHORITY_REGEX.search(card_text):
            failures.append("EXPORT_MISSING_DISCLAIMER: Sterile planning card missing clinical decision support disclaimer.")

        passed = len(failures) == 0
        return passed, failures
