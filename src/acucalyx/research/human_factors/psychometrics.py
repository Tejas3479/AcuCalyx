"""
AcuCalyx Research: Psychometric Cognitive Workload & Usability Evaluation Engine

Governing Requirement: Frozen Plan v6.1 (Section 6 & Section 7)
Implements:
1. NASA Task Load Index Raw Score (RTLX) multidimensional cognitive workload assessment.
2. System Usability Scale (SUS) 10-item standardized usability instrument.
3. Within-subject paired cohort statistical analyzer (AcuCalyx vs. Conventional Baseline)
   calculating paired differences, 95% confidence intervals, Cohen's d effect sizes, and p-values.
"""

from dataclasses import dataclass, field
import math
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from scipy import stats


@dataclass(frozen=True)
class NasaTlxRtlxAssessment:
    """
    NASA Task Load Index Raw Score (RTLX) assessment for an individual trial.
    Scores for all 6 subscales must fall in the range [0.0, 100.0].
    """
    participant_id: str
    condition_id: str  # 'CONVENTIONAL_BASELINE' or 'ACUCALYX_COCKPIT'
    mental_demand: float
    physical_demand: float
    temporal_demand: float
    performance: float      # Scale: 0 (Good/Perfect) to 100 (Poor/Failure)
    effort: float
    frustration: float

    def __post_init__(self):
        for name in ["mental_demand", "physical_demand", "temporal_demand", "performance", "effort", "frustration"]:
            val = getattr(self, name)
            if val < 0.0 or val > 100.0:
                raise ValueError(f"NASA-TLX subscale '{name}' must be between 0.0 and 100.0 (got {val})")

    @property
    def raw_score(self) -> float:
        """Computes unweighted Raw TLX score (RTLX) as the mean of all 6 subscales."""
        subscales = [
            self.mental_demand,
            self.physical_demand,
            self.temporal_demand,
            self.performance,
            self.effort,
            self.frustration
        ]
        return float(np.mean(subscales))


@dataclass(frozen=True)
class SystemUsabilityScaleAssessment:
    """
    Standardized 10-item System Usability Scale (SUS) instrument (Brooke, 1996).
    Each response must be an integer Likert rating from 1 (Strongly Disagree) to 5 (Strongly Agree).
    """
    participant_id: str
    item_responses: List[int]  # 10 integer ratings (1 to 5)

    def __post_init__(self):
        if len(self.item_responses) != 10:
            raise ValueError(f"SUS requires exactly 10 responses (got {len(self.item_responses)})")
        for idx, r in enumerate(self.item_responses):
            if r < 1 or r > 5:
                raise ValueError(f"SUS item {idx+1} response must be 1 to 5 (got {r})")

    @property
    def sus_score(self) -> float:
        """
        Computes standardized SUS score (0 to 100).
        Odd items: contribution = response - 1
        Even items: contribution = 5 - response
        Score = 2.5 * sum(contributions)
        """
        score_sum = 0
        for i, resp in enumerate(self.item_responses):
            if (i % 2) == 0:  # Odd item (0-indexed 0, 2, 4, 6, 8 -> 1, 3, 5, 7, 9)
                score_sum += (resp - 1)
            else:  # Even item (0-indexed 1, 3, 5, 7, 9 -> 2, 4, 6, 8, 10)
                score_sum += (5 - resp)
        return float(score_sum * 2.5)

    @property
    def adjective_rating(self) -> str:
        """Standardized adjective interpretation of SUS score."""
        s = self.sus_score
        if s >= 85.0:
            return "EXCELLENT"
        elif s >= 80.0:
            return "HIGH_USABILITY"  # Meets exploratory benchmark
        elif s >= 68.0:
            return "ACCEPTABLE"
        elif s >= 51.0:
            return "MARGINAL"
        else:
            return "UNACCEPTABLE"


@dataclass
class PairedWorkloadComparisonResult:
    """Statistical summary of within-subject paired cognitive workload evaluation."""
    sample_size_n: int
    mean_baseline_rtlx: float
    sd_baseline_rtlx: float
    mean_acucalyx_rtlx: float
    sd_acucalyx_rtlx: float
    mean_paired_difference: float  # AcuCalyx - Baseline (negative indicates workload reduction)
    ci95_difference: Tuple[float, float]
    p_value_paired_t: float
    p_value_wilcoxon: float
    cohens_d_effect_size: float
    is_workload_reduction_significant: bool
    subscale_mean_differences: Dict[str, float]


@dataclass
class SUSCohortSummaryResult:
    """Statistical summary of SUS scores across a study cohort."""
    sample_size_n: int
    mean_sus: float
    sd_sus: float
    median_sus: float
    iqr_sus: float
    proportion_meeting_benchmark_80_pct: float
    adjective_distribution: Dict[str, int]


class PsychometricCohortAnalyzer:
    """Analyzes experimental usability and workload cohorts under controlled crossover designs."""

    @staticmethod
    def analyze_paired_workload(
        baseline_assessments: List[NasaTlxRtlxAssessment],
        acucalyx_assessments: List[NasaTlxRtlxAssessment],
        alpha: float = 0.05
    ) -> PairedWorkloadComparisonResult:
        """
        Conducts within-subject paired analysis of NASA-TLX RTLX scores.
        Expects matched participant IDs in both lists.
        """
        if len(baseline_assessments) != len(acucalyx_assessments):
            raise ValueError("Baseline and AcuCalyx assessment counts must match for paired analysis")
        if len(baseline_assessments) < 2:
            raise ValueError("At least 2 paired assessments required for statistical analysis")

        # Map by participant ID to ensure paired alignment
        base_map = {a.participant_id: a for a in baseline_assessments}
        acuc_map = {a.participant_id: a for a in acucalyx_assessments}

        common_ids = sorted(list(set(base_map.keys()) & set(acuc_map.keys())))
        if len(common_ids) != len(baseline_assessments):
            raise ValueError("Mismatched participant IDs between baseline and AcuCalyx conditions")

        base_scores = np.array([base_map[pid].raw_score for pid in common_ids], dtype=np.float64)
        acuc_scores = np.array([acuc_map[pid].raw_score for pid in common_ids], dtype=np.float64)

        diffs = acuc_scores - base_scores
        n = len(diffs)

        mean_diff = float(np.mean(diffs))
        sd_diff = float(np.std(diffs, ddof=1)) if n > 1 else 0.0

        # Paired t-test
        t_stat, p_val_t = stats.ttest_rel(acuc_scores, base_scores)

        # Wilcoxon signed-rank test
        try:
            w_stat, p_val_w = stats.wilcoxon(acuc_scores, base_scores)
        except Exception:
            p_val_w = float(p_val_t)

        # 95% Confidence Interval for paired difference
        se_diff = sd_diff / math.sqrt(n) if n > 0 else 0.0
        t_crit = stats.t.ppf(1.0 - alpha / 2.0, df=n - 1) if n > 1 else 1.96
        ci_lower = mean_diff - t_crit * se_diff
        ci_upper = mean_diff + t_crit * se_diff

        # Cohen's d for paired samples (mean diff / sd diff)
        cohens_d = float(mean_diff / sd_diff) if sd_diff > 1e-6 else 0.0

        # Subscale breakdown
        subscales = ["mental_demand", "physical_demand", "temporal_demand", "performance", "effort", "frustration"]
        subscale_diffs = {}
        for s in subscales:
            b_vals = [getattr(base_map[pid], s) for pid in common_ids]
            a_vals = [getattr(acuc_map[pid], s) for pid in common_ids]
            subscale_diffs[s] = round(float(np.mean(a_vals) - np.mean(b_vals)), 2)

        is_sig_reduction = bool((mean_diff < 0.0) and (p_val_t < alpha))

        return PairedWorkloadComparisonResult(
            sample_size_n=n,
            mean_baseline_rtlx=round(float(np.mean(base_scores)), 2),
            sd_baseline_rtlx=round(float(np.std(base_scores, ddof=1)), 2),
            mean_acucalyx_rtlx=round(float(np.mean(acuc_scores)), 2),
            sd_acucalyx_rtlx=round(float(np.std(acuc_scores, ddof=1)), 2),
            mean_paired_difference=round(mean_diff, 2),
            ci95_difference=(round(ci_lower, 2), round(ci_upper, 2)),
            p_value_paired_t=round(float(p_val_t), 4),
            p_value_wilcoxon=round(float(p_val_w), 4),
            cohens_d_effect_size=round(cohens_d, 3),
            is_workload_reduction_significant=is_sig_reduction,
            subscale_mean_differences=subscale_diffs
        )

    @staticmethod
    def analyze_sus_cohort(assessments: List[SystemUsabilityScaleAssessment]) -> SUSCohortSummaryResult:
        """Evaluates SUS scores across a study cohort against the exploratory benchmark of 80.0."""
        if not assessments:
            raise ValueError("At least one SUS assessment required for analysis")

        scores = [a.sus_score for a in assessments]
        n = len(scores)

        mean_s = float(np.mean(scores))
        sd_s = float(np.std(scores, ddof=1)) if n > 1 else 0.0
        med_s = float(np.median(scores))
        iqr_s = float(stats.iqr(scores)) if n > 1 else 0.0

        met_benchmark_count = sum(1 for s in scores if s >= 80.0)
        prop_met = (met_benchmark_count / n) * 100.0

        adj_counts = {"EXCELLENT": 0, "HIGH_USABILITY": 0, "ACCEPTABLE": 0, "MARGINAL": 0, "UNACCEPTABLE": 0}
        for a in assessments:
            adj = a.adjective_rating
            adj_counts[adj] = adj_counts.get(adj, 0) + 1

        return SUSCohortSummaryResult(
            sample_size_n=n,
            mean_sus=round(mean_s, 2),
            sd_sus=round(sd_s, 2),
            median_sus=round(med_s, 2),
            iqr_sus=round(iqr_s, 2),
            proportion_meeting_benchmark_80_pct=round(prop_met, 1),
            adjective_distribution=adj_counts
        )
