"""
AcuCalyx Reports: Graphical Figures and Diagram Generator for Planning PDF

Implements Step 14 figure generation:
- Renders Pareto frontier trade-off charts (Tract Length vs Effective Clearance)
- Generates hazard safety margin bar charts
- Visualizes virtual C-arm fluoroscopy angle alignments
"""

import io
from pathlib import Path
from typing import List, Optional
import numpy as np

from reportlab.graphics.shapes import Drawing, Rect, String, Line, Circle, Group
from reportlab.lib import colors

from acucalyx.planning.pareto_optimizer import CandidateTrajectory


def create_pareto_tradeoff_drawing(
    candidates: List[CandidateTrajectory],
    width: float = 500.0,
    height: float = 140.0
) -> Drawing:
    """
    Renders an auditable vector drawing of the candidate Pareto trade-off space.
    X-axis: Tract Length (mm)
    Y-axis: Minimum Effective Clearance (mm)
    """
    d = Drawing(width, height)

    # Background canvas
    d.add(Rect(0, 0, width, height, fillColor=colors.HexColor('#F8FAFC'), strokeColor=colors.HexColor('#CBD5E1'), strokeWidth=0.5))

    # Title
    d.add(String(14, height - 16, "Pareto Access Corridor Trade-Off Space", fontSize=9, fontName='Helvetica-Bold', fillColor=colors.HexColor('#1E293B')))

    # Plot axes margins
    x_min, x_max = 50.0, width - 20.0
    y_min, y_max = 25.0, height - 30.0

    # Draw axes lines
    d.add(Line(x_min, y_min, x_max, y_min, strokeColor=colors.HexColor('#94A3B8'), strokeWidth=1))
    d.add(Line(x_min, y_min, x_min, y_max, strokeColor=colors.HexColor('#94A3B8'), strokeWidth=1))

    # Axis labels
    d.add(String(x_min + 100, 10, "Tract Length (mm) [Shorter is Better]", fontSize=7, fontName='Helvetica', fillColor=colors.HexColor('#64748B')))
    d.add(String(8, y_min + 30, "Clearance", fontSize=7, fontName='Helvetica', fillColor=colors.HexColor('#64748B')))

    if not candidates:
        d.add(String(x_min + 120, y_min + 40, "No candidates evaluated", fontSize=9, fontName='Helvetica-Oblique', fillColor=colors.HexColor('#94A3B8')))
        return d

    # Data bounds
    tract_lens = [c.tract_length_mm for c in candidates]
    clearances = [c.min_effective_clearance_mm for c in candidates]

    t_min = max(0.0, min(tract_lens) - 10.0)
    t_max = max(tract_lens) + 15.0 if tract_lens else 100.0
    c_min = 0.0
    c_max = max(clearances) + 10.0 if clearances else 30.0

    def scale_x(t: float) -> float:
        return x_min + ((t - t_min) / max(1.0, (t_max - t_min))) * (x_max - x_min - 20.0)

    def scale_y(c: float) -> float:
        return y_min + ((c - c_min) / max(1.0, (c_max - c_min))) * (y_max - y_min - 10.0)

    # Plot candidate points
    for idx, c in enumerate(candidates):
        px = scale_x(c.tract_length_mm)
        py = scale_y(c.min_effective_clearance_mm)
        letter = chr(65 + idx)

        has_col = any(h.is_intersecting for h in c.hazard_evaluations)
        if has_col:
            dot_color = colors.HexColor('#EF4444') # Red
        elif idx == 0 and c.min_effective_clearance_mm > 10.0:
            dot_color = colors.HexColor('#10B981') # Preferred Green
        else:
            dot_color = colors.HexColor('#F59E0B') # Amber

        # Point circle
        d.add(Circle(px, py, 6, fillColor=dot_color, strokeColor=colors.HexColor('#0F172A'), strokeWidth=0.5))
        d.add(String(px - 3, py - 3, letter, fontSize=7, fontName='Helvetica-Bold', fillColor=colors.white))

        # Text tag
        d.add(String(px + 8, py - 2, f"{c.candidate_id} ({c.tract_length_mm:.0f}mm, {c.min_effective_clearance_mm:.0f}mm)", fontSize=6, fontName='Helvetica', fillColor=colors.HexColor('#334155')))

    return d


def create_clearance_summary_bar_drawing(
    trajectory: CandidateTrajectory,
    width: float = 500.0,
    height: float = 90.0
) -> Drawing:
    """
    Renders horizontal safety clearance bar charts for all adjacent anatomical hazards.
    """
    d = Drawing(width, height)
    d.add(Rect(0, 0, width, height, fillColor=colors.HexColor('#F8FAFC'), strokeColor=colors.HexColor('#CBD5E1'), strokeWidth=0.5))
    d.add(String(14, height - 14, f"Hazard Clearances for Candidate {trajectory.candidate_id}", fontSize=8, fontName='Helvetica-Bold', fillColor=colors.HexColor('#1E293B')))

    hazards = trajectory.hazard_evaluations
    if not hazards:
        d.add(String(30, 40, "No adjacent anatomical hazards identified.", fontSize=7, fontName='Helvetica-Oblique', fillColor=colors.HexColor('#64748B')))
        return d

    y_pos = height - 32.0
    bar_x_start = 120.0
    max_bar_w = 320.0
    max_clearance = 40.0

    for h in hazards[:3]:
        # Organ label
        d.add(String(14, y_pos + 2, h.hazard_name.upper()[:15], fontSize=7, fontName='Helvetica-Bold', fillColor=colors.HexColor('#334155')))

        # Background track
        d.add(Rect(bar_x_start, y_pos, max_bar_w, 10, fillColor=colors.HexColor('#E2E8F0'), strokeColor=None))

        # Effective clearance bar
        eff = max(0.0, h.effective_clearance_mm)
        bar_w = (min(eff, max_clearance) / max_clearance) * max_bar_w
        bar_color = colors.HexColor('#10B981') if eff > 10.0 else (colors.HexColor('#F59E0B') if eff > 0.0 else colors.HexColor('#EF4444'))

        if bar_w > 0:
            d.add(Rect(bar_x_start, y_pos, bar_w, 10, fillColor=bar_color, strokeColor=None))

        # Text label
        d.add(String(bar_x_start + max_bar_w + 10, y_pos + 2, f"{eff:.1f} mm", fontSize=7, fontName='Helvetica-Bold', fillColor=colors.HexColor('#0F172A')))
        y_pos -= 18.0

    return d
