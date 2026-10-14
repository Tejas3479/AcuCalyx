"""
AcuCalyx Research: Formative Usability Protocol & Clinician Discovery Harness
(IEC 62366-1:2015 / FDA Human Factors Guidance / Milestone M14.5)

Governing Standard:
- Implements formative usability evaluation protocol for the PCNL Access Planning Workbench.
- Standardizes 4 clinical benchmark scenarios for comparative study (AcuCalyx vs. Conventional 2D CT MPR).
- Captures granular trial telemetry: task completion time, tract candidate selection,
  clinician overrides, error mechanisms, NASA-TLX workload, and SUS instruments.
- Provides the structured Surgeon Discovery Interview Protocol for quantitative tradeoff weighting.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from scipy import stats

from acucalyx.research.human_factors.psychometrics import (
    NasaTlxRtlxAssessment,
    PsychometricCohortAnalyzer,
    SystemUsabilityScaleAssessment,
)
from acucalyx.research.human_factors.task_analysis import STANDARD_CRITICAL_TASKS

logger = logging.getLogger("acucalyx.usability_protocol")


class UsabilityCondition(str, Enum):
    """Evaluation condition in within-subject paired crossover design."""
    CONVENTIONAL_BASELINE = "CONVENTIONAL_BASELINE"
    ACUCALYX_WORKBENCH = "ACUCALYX_WORKBENCH"


class ClinicianRole(str, Enum):
    """Clinical participant background."""
    ATTENDING_ENDOUROLOGIST = "ATTENDING_ENDOUROLOGIST"
    ENDOUROLOGY_FELLOW = "ENDOUROLOGY_FELLOW"
    UROLOGY_RESIDENT = "UROLOGY_RESIDENT"


@dataclass(frozen=True)
class UsabilityScenario:
    """Standardized PCNL planning challenge scenario for formative evaluation."""
    scenario_id: str
    title: str
    clinical_summary: str
    challenge_category: str
    target_kidney_side: str
    stone_burden_description: str
    primary_tradeoffs: List[str]
    benchmark_reference_tract: str
    contraindicated_tracts: List[str]
    complexity_tier: str  # 'STANDARD', 'CHALLENGING', 'HIGH_COMPLEXITY'


STANDARD_USABILITY_SCENARIOS: Dict[str, UsabilityScenario] = {
    "SCENARIO_01_LOWER_POLE": UsabilityScenario(
        scenario_id="SCENARIO_01_LOWER_POLE",
        title="Uncomplicated Solitary Lower Pole Calculus",
        clinical_summary=(
            "54-year-old male with 18 mm radio-opaque solitary calculus in the left posterior "
            "inferior calyx. Clear subcostal acoustic/radiological window; normal retroperitoneal anatomy."
        ),
        challenge_category="STANDARD_SUBCOSTAL",
        target_kidney_side="left",
        stone_burden_description="Solitary 18 mm stone in posterior lower pole, volume ~1850 mm³.",
        primary_tradeoffs=[
            "Direct optical line-of-sight vs skin entry tract length",
            "Infundibular axis alignment vs skin-to-papilla distance"
        ],
        benchmark_reference_tract="POSTERIOR_LOWER",
        contraindicated_tracts=["ANTERIOR_UPPER"],
        complexity_tier="STANDARD"
    ),
    "SCENARIO_02_RETRORENAL_COLON": UsabilityScenario(
        scenario_id="SCENARIO_02_RETRORENAL_COLON",
        title="Posterior Calyx Calculus with Retrorenal Colon Hazard",
        clinical_summary=(
            "62-year-old female with 20 mm left lower pole calculus. CT reveals a posterolateral "
            "descending colon running within 8 mm of the lower pole renal margin."
        ),
        challenge_category="RETRORENAL_COLON_HAZARD",
        target_kidney_side="left",
        stone_burden_description="20 mm lower pole calculus abutting lower infundibulum.",
        primary_tradeoffs=[
            "Direct lower pole puncture with marginal colon clearance (<10 mm) vs "
            "Middle calyx access with >20 mm colon clearance but acute infundibular torque",
            "Fluoroscopic C-arm vertical needle corridor vs visceral displacement risk"
        ],
        benchmark_reference_tract="POSTERIOR_MIDDLE",
        contraindicated_tracts=["POSTERIOR_LOWER_LATERAL"],
        complexity_tier="CHALLENGING"
    ),
    "SCENARIO_03_STAGHORN_INFUNDIBULUM": UsabilityScenario(
        scenario_id="SCENARIO_03_STAGHORN_INFUNDIBULUM",
        title="Partial Staghorn with Narrow Lower Infundibulum",
        clinical_summary=(
            "48-year-old male with 32 mm partial staghorn stone filling renal pelvis and "
            "lower pole calyx. Lower pole infundibulum is narrow (3.2 mm) and acutely angled."
        ),
        challenge_category="STAGHORN_COMPLEX_INFUNDIBULUM",
        target_kidney_side="right",
        stone_burden_description="32 mm branched calculus spanning renal pelvis and lower pole.",
        primary_tradeoffs=[
            "Rigid accessible stone clearance % from single tract vs multi-tract necessity",
            "Pelvic access through lower pole with high infundibular torque vs "
            "Direct upper/middle calyx puncture targeting pelvic core first"
        ],
        benchmark_reference_tract="POSTERIOR_LOWER_INTERPOLAR",
        contraindicated_tracts=["DIRECT_PELVIS_BLIND"],
        complexity_tier="HIGH_COMPLEXITY"
    ),
    "SCENARIO_04_SUPRACOSTAL_HIGH_KIDNEY": UsabilityScenario(
        scenario_id="SCENARIO_04_SUPRACOSTAL_HIGH_KIDNEY",
        title="High-Riding Upper Pole Stone Requiring Rib Tradeoff",
        clinical_summary=(
            "41-year-old female with 16 mm upper pole calyx stone. Left kidney is positioned high, "
            "upper pole situated under the 10th and 11th ribs."
        ),
        challenge_category="SUPRACOSTAL_PLEURAL_HAZARD",
        target_kidney_side="left",
        stone_burden_description="16 mm upper pole calyx calculus.",
        primary_tradeoffs=[
            "Supracostal (11th-12th intercostal) direct straight access with pleural reflection risk (<8 mm) vs "
            "Subcostal access with extreme upward crane angle (>45°) and extensive torque"
        ],
        benchmark_reference_tract="SUBCOSTAL_STEEP_UPWARD",
        contraindicated_tracts=["SUPRA_10_HIGH_PLEURA"],
        complexity_tier="CHALLENGING"
    )
}


@dataclass
class UsabilityTrialRecord:
    """Individual planning trial record captured during a usability test session."""
    trial_id: str
    session_id: str
    participant_id: str
    participant_role: ClinicianRole
    experience_years: int
    scenario_id: str
    condition: UsabilityCondition
    task_start_time: str
    task_end_time: str
    task_duration_seconds: float
    selected_candidate_id: str
    selected_calyx_name: str
    accepted_automated_proposal: bool
    clinician_override_applied: bool
    override_type: Optional[str] = None
    override_rationale: Optional[str] = None
    critical_errors_observed: List[str] = field(default_factory=list)
    nasa_tlx: Optional[NasaTlxRtlxAssessment] = None
    sus: Optional[SystemUsabilityScaleAssessment] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["participant_role"] = self.participant_role.value
        d["condition"] = self.condition.value
        if self.nasa_tlx:
            d["nasa_tlx"] = {
                "mental_demand": self.nasa_tlx.mental_demand,
                "physical_demand": self.nasa_tlx.physical_demand,
                "temporal_demand": self.nasa_tlx.temporal_demand,
                "performance": self.nasa_tlx.performance,
                "effort": self.nasa_tlx.effort,
                "frustration": self.nasa_tlx.frustration,
                "raw_score": self.nasa_tlx.raw_score
            }
        if self.sus:
            d["sus"] = {
                "item_responses": self.sus.item_responses,
                "sus_score": self.sus.sus_score,
                "adjective_rating": self.sus.adjective_rating
            }
        return d


class UsabilityStudySession:
    """
    Manages an end-to-end usability evaluation session across participants and scenarios.
    Computes comparative workload, task efficiency, and safety error metrics.
    """

    def __init__(self, session_id: str, investigator_id: str):
        self.session_id = session_id
        self.investigator_id = investigator_id
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.trials: List[UsabilityTrialRecord] = []

    def record_trial(self, trial: UsabilityTrialRecord) -> None:
        """Appends a completed trial record to the study session."""
        self.trials.append(trial)
        logger.info(
            f"Recorded Usability Trial {trial.trial_id} | Participant {trial.participant_id} | "
            f"Scenario {trial.scenario_id} | Condition {trial.condition.value} | "
            f"Duration {trial.task_duration_seconds:.1f}s"
        )

    def get_trials_by_condition(self, condition: UsabilityCondition) -> List[UsabilityTrialRecord]:
        return [t for t in self.trials if t.condition == condition]

    def compute_summary_analytics(self) -> Dict[str, Any]:
        """
        Synthesizes comparative metrics:
        - Task completion duration reduction (%)
        - Cognitive workload comparison (NASA-TLX RTLX)
        - System Usability Scale (SUS) scores
        - Critical use error rates
        - Automated proposal acceptance rate
        """
        baseline_trials = self.get_trials_by_condition(UsabilityCondition.CONVENTIONAL_BASELINE)
        acucalyx_trials = self.get_trials_by_condition(UsabilityCondition.ACUCALYX_WORKBENCH)

        # 1. Task Durations
        base_durations = [t.task_duration_seconds for t in baseline_trials]
        acuc_durations = [t.task_duration_seconds for t in acucalyx_trials]

        mean_base_time = float(np.mean(base_durations)) if base_durations else 0.0
        mean_acuc_time = float(np.mean(acuc_durations)) if acuc_durations else 0.0
        time_reduction_pct = (
            float((mean_base_time - mean_acuc_time) / mean_base_time * 100.0)
            if mean_base_time > 0 else 0.0
        )

        # 2. Critical Errors (C1-C6)
        base_errors = sum(len(t.critical_errors_observed) for t in baseline_trials)
        acuc_errors = sum(len(t.critical_errors_observed) for t in acucalyx_trials)

        # 3. Workload (NASA-TLX)
        base_tlx = [t.nasa_tlx for t in baseline_trials if t.nasa_tlx is not None]
        acuc_tlx = [t.nasa_tlx for t in acucalyx_trials if t.nasa_tlx is not None]

        workload_analysis = None
        if len(base_tlx) >= 2 and len(acuc_tlx) >= 2 and len(base_tlx) == len(acuc_tlx):
            workload_res = PsychometricCohortAnalyzer.analyze_paired_workload(base_tlx, acuc_tlx)
            workload_analysis = {
                "sample_size_n": workload_res.sample_size_n,
                "mean_baseline_rtlx": workload_res.mean_baseline_rtlx,
                "mean_acucalyx_rtlx": workload_res.mean_acucalyx_rtlx,
                "mean_difference": workload_res.mean_paired_difference,
                "ci95_difference": list(workload_res.ci95_difference),
                "p_value": workload_res.p_value_paired_t,
                "cohens_d": workload_res.cohens_d_effect_size,
                "is_significant": workload_res.is_workload_reduction_significant
            }

        # 4. Usability (SUS) for AcuCalyx
        sus_list = [t.sus for t in acucalyx_trials if t.sus is not None]
        sus_analysis = None
        if sus_list:
            sus_res = PsychometricCohortAnalyzer.analyze_sus_cohort(sus_list)
            sus_analysis = {
                "sample_size_n": sus_res.sample_size_n,
                "mean_sus": sus_res.mean_sus,
                "sd_sus": sus_res.sd_sus,
                "median_sus": sus_res.median_sus,
                "proportion_meeting_80_benchmark": sus_res.proportion_meeting_benchmark_80_pct,
                "adjective_distribution": sus_res.adjective_distribution
            }

        # 5. Acceptance & Override Rate
        acuc_total = len(acucalyx_trials)
        accepted_count = sum(1 for t in acucalyx_trials if t.accepted_automated_proposal)
        override_count = sum(1 for t in acucalyx_trials if t.clinician_override_applied)
        acceptance_rate_pct = (accepted_count / acuc_total * 100.0) if acuc_total > 0 else 0.0
        override_rate_pct = (override_count / acuc_total * 100.0) if acuc_total > 0 else 0.0

        return {
            "session_id": self.session_id,
            "investigator_id": self.investigator_id,
            "total_trials": len(self.trials),
            "baseline_trial_count": len(baseline_trials),
            "acucalyx_trial_count": acuc_total,
            "task_duration_seconds": {
                "mean_baseline": round(mean_base_time, 1),
                "mean_acucalyx": round(mean_acuc_time, 1),
                "reduction_percent": round(time_reduction_pct, 1)
            },
            "critical_errors_observed": {
                "baseline_total": base_errors,
                "acucalyx_total": acuc_errors,
                "error_elimination_rate_pct": (
                    round((base_errors - acuc_errors) / base_errors * 100.0, 1)
                    if base_errors > 0 else 100.0
                )
            },
            "acceptance_metrics": {
                "accepted_count": accepted_count,
                "override_count": override_count,
                "acceptance_rate_pct": round(acceptance_rate_pct, 1),
                "override_rate_pct": round(override_rate_pct, 1)
            },
            "workload_analysis": workload_analysis,
            "sus_analysis": sus_analysis
        }


# =============================================================================
# Surgeon Discovery Interview Guide
# =============================================================================

class SurgeonDiscoveryGuide:
    """
    Standardized Discovery Interview Protocol for Endourologists (Milestone M14.5).
    Investigates decision weighting across anatomical tradeoffs, clearance boundaries,
    and workflow integration in clinical practice.
    """

    SECTIONS = [
        {
            "section_id": "SEC_1_BASELINE_WORKFLOW",
            "title": "1. Current PCNL Preoperative Planning Baseline",
            "questions": [
                {
                    "q_id": "Q1_1",
                    "text": "What imaging studies do you routinely review before performing PCNL puncture?",
                    "options": ["Non-contrast CT (NCCT)", "CT Urography (CTU / Contrast)", "Retrograde Pyelogram in OR", "IV Urogram (IVU)", "Renal Ultrasound"],
                    "allow_multiple": True
                },
                {
                    "q_id": "Q1_2",
                    "text": "Who performs the initial percutaneous renal puncture at your institution?",
                    "options": ["Urologist in the OR", "Interventional Radiologist (IR) preoperatively", "Hybrid (Urologist guided by IR)", "Varies by case complexity"],
                    "allow_multiple": False
                },
                {
                    "q_id": "Q1_3",
                    "text": "On average, how many minutes do you spend reviewing axial/coronal CT slices to determine the entry calyx?",
                    "options": ["< 5 minutes", "5 - 15 minutes", "15 - 30 minutes", "> 30 minutes"],
                    "allow_multiple": False
                }
            ]
        },
        {
            "section_id": "SEC_2_TRADEOFF_RANKING",
            "title": "2. Clinical Tradeoff Weighting & Priority Ranking",
            "description": "Rank the following five planning dimensions from 1 (Most Critical) to 5 (Least Critical).",
            "dimensions": [
                {
                    "key": "visceral_clearance",
                    "label": "Colon / Pleura Clearance",
                    "description": "Distance between candidate tract corridor and adjacent visceral hazards."
                },
                {
                    "key": "direct_papillary_puncture",
                    "label": "Direct Forniceal / Papillary Access",
                    "description": "Ensuring needle enters via the calyx fornix rather than the infundibular neck to avoid vascular injury."
                },
                {
                    "key": "stone_volume_reachability",
                    "label": "Primary Stone Volume Reachability",
                    "description": "Percentage of total stone burden reachable via rigid nephroscope without secondary tract."
                },
                {
                    "key": "infundibular_axis_alignment",
                    "label": "Infundibular Torque & Axis Angle",
                    "description": "Angle between puncture axis and infundibulum into the renal pelvis (scope torque resistance)."
                },
                {
                    "key": "rib_classification",
                    "label": "Subcostal vs. Supracostal Trajectory",
                    "description": "Avoiding intercostal puncture through 10th-11th or 11th-12th ribs."
                }
            ]
        },
        {
            "section_id": "SEC_3_THRESHOLD_BOUNDARIES",
            "title": "3. Quantitative Safety Boundaries & Clearance Sensitivities",
            "questions": [
                {
                    "q_id": "Q3_1",
                    "text": "What is the minimum margin of clearance from the colon before you consider an access tract unsafe?",
                    "options": ["< 5 mm", "5 - 10 mm", "10 - 15 mm", "> 15 mm", "Colon must be completely outside trajectory path with fascia buffer"],
                    "allow_multiple": False
                },
                {
                    "q_id": "Q3_2",
                    "text": "For supracostal access (above 12th rib), what is your threshold distance from the pleural reflection?",
                    "options": ["< 5 mm", "5 - 10 mm", "10 - 15 mm", "Avoid supracostal access unless lower tract completely fails"],
                    "allow_multiple": False
                },
                {
                    "q_id": "Q3_3",
                    "text": "How do you treat automated stone reachability estimates if flexible scope deflection is not physically simulated?",
                    "options": [
                        "Must be labeled 'NOT_EVALUABLE' or shown as rigid-only",
                        "Acceptable as rough guidance if clearly labeled as an estimate",
                        "Do not want flexible reachability displayed at all"
                    ],
                    "allow_multiple": False
                }
            ]
        },
        {
            "section_id": "SEC_4_SUMMARY_CARD_UTILITY",
            "title": "4. Preoperative Summary Card & Communication Utility",
            "questions": [
                {
                    "q_id": "Q4_1",
                    "text": "Would a 1-page standardized PCNL Preoperative Planning Card improve the OR surgical timeout / briefing?",
                    "options": ["Strongly Agree", "Agree", "Neutral", "Disagree", "Strongly Disagree"],
                    "allow_multiple": False
                },
                {
                    "q_id": "Q4_2",
                    "text": "How valuable is providing precomputed Bull's-Eye and Progression C-arm gantry angles with a verbal readback script to the radiologic technologist?",
                    "options": ["Essential (Eliminates repeated positioning trials)", "Very Useful", "Moderately Useful", "Not Useful"],
                    "allow_multiple": False
                }
            ]
        }
    ]

    @classmethod
    def get_protocol_schema(cls) -> Dict[str, Any]:
        """Returns the complete interview guide structure."""
        return {
            "protocol_name": "AcuCalyx Formative Surgeon Discovery Interview Protocol",
            "version": "1.0 (Milestone M14.5)",
            "governing_standard": "IEC 62366-1:2015 Clause 5.4",
            "sections": cls.SECTIONS
        }

    @classmethod
    def generate_markdown_interview_sheet(cls) -> str:
        """Generates a printable markdown sheet for clinician interviewers."""
        lines = [
            "# AcuCalyx: Clinician Discovery & Tradeoff Weighting Interview",
            "**Document ID:** ACU-M14.5-DISCOVERY-GUIDE-V1",
            "**Standard:** IEC 62366-1:2015 / FDA August 2026 Human Factors Guidance",
            "",
            "---",
            "**Participant ID:** ____________________  **Role:** [ ] Attending  [ ] Fellow  [ ] Resident",
            "**Institution:** ____________________     **Years Experience in PCNL:** ______",
            "**Date:** ________________________        **Interviewer:** ____________________",
            "---",
            ""
        ]
        for sec in cls.SECTIONS:
            lines.append(f"## {sec['title']}")
            if "description" in sec:
                lines.append(f"*{sec['description']}*\n")
            if "questions" in sec:
                for q in sec["questions"]:
                    lines.append(f"### {q['q_id']}: {q['text']}")
                    for opt in q["options"]:
                        lines.append(f"- [ ] {opt}")
                    lines.append("")
            if "dimensions" in sec:
                lines.append("| Rank (1-5) | Dimension | Description |")
                lines.append("| :---: | :--- | :--- |")
                for dim in sec["dimensions"]:
                    lines.append(f"| [   ] | **{dim['label']}** | {dim['description']} |")
                lines.append("")
        return "\n".join(lines)
