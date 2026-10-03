"""
AcuCalyx Reports: Preoperative Planning Report PDF Generator

Implements Step 14 of AcuCalyx v2.1:
- Generates an auditable, de-identified 2-page clinical planning summary
- Strictly separates observed metrics from uncertainty envelopes
- Features the 'Why this candidate?' explainable Pareto trade-off matrix
- Labels estimated anatomy honestly ('Estimated Lower-Pole Posterior Calyx Region')
- Implements mandatory decision-support disclaimers and sign-off blocks
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
import numpy as np

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

from acucalyx.audit.provenance import CaseProvenanceRecord
from acucalyx.collecting_system.visibility_gate import PCSVisibilityResult, PCSVisibilityState
from acucalyx.ingestion.quality_gate import QualityGateResult
from acucalyx.planning.pareto_optimizer import CandidateTrajectory
from acucalyx.stones.attenuation import StoneAttenuationProfile
from acucalyx.stones.volumetry import StoneMorphometry


def generate_preoperative_planning_pdf(
    output_path: Path,
    provenance: CaseProvenanceRecord,
    quality_gate: QualityGateResult,
    pcs_visibility: PCSVisibilityResult,
    stones: List[StoneMorphometry],
    attenuations: List[StoneAttenuationProfile],
    candidates: List[CandidateTrajectory]
) -> Path:
    """
    Renders an auditable 2-page Preoperative Planning Report PDF.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=18,
        leading=22,
        textColor=colors.HexColor('#1E3A8A'),
        fontName='Helvetica-Bold'
    )
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#4B5563')
    )
    section_heading = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontSize=12,
        leading=16,
        textColor=colors.HexColor('#1E3A8A'),
        spaceBefore=8,
        spaceAfter=4,
        fontName='Helvetica-Bold'
    )
    body_style = ParagraphStyle(
        'DocBody',
        parent=styles['Normal'],
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#1F2937')
    )
    disclaimer_style = ParagraphStyle(
        'DisclaimerText',
        parent=styles['Normal'],
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor('#DC2626'),
        fontName='Helvetica-Oblique'
    )

    story = []

    # =========================================================================
    # PAGE 1: Case Provenance, Quality Gate, and Stone Characterization
    # =========================================================================
    story.append(Paragraph("AcuCalyx™ Preoperative Planning Report", title_style))
    story.append(Paragraph("Patient-Specific Computational Planning for Percutaneous Renal Access — Decision Support Only", subtitle_style))
    story.append(Spacer(1, 8))

    # Provenance Header Table
    prov_data = [
        [Paragraph(f"<b>Case UUID:</b> {provenance.case_id}", body_style),
         Paragraph(f"<b>Software Version:</b> {provenance.software_version}", body_style)],
        [Paragraph(f"<b>Analysis Timestamp:</b> {provenance.analysis_timestamp[:19]} UTC", body_style),
         Paragraph(f"<b>Input Hash:</b> {provenance.input_data_sha256[:16]}...", body_style)]
    ]
    prov_table = Table(prov_data, colWidths=[270, 270])
    prov_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F3F4F6')),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#D1D5DB')),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(prov_table)
    story.append(Spacer(1, 8))

    # Quality Gate & PCS Visibility Status
    story.append(Paragraph("1. Imaging Quality & Anatomical Visibility Assessment", section_heading))
    qg_tier_color = "#10B981" if quality_gate.overall_quality_tier == "HIGH" else "#F59E0B"
    pcs_tier_color = "#10B981" if pcs_visibility.state == PCSVisibilityState.DIRECTLY_OPACIFIED else (
        "#F59E0B" if pcs_visibility.state == PCSVisibilityState.HYDRONEPHROTIC_DISTENDED else "#EF4444"
    )

    qg_summary = [
        [Paragraph("<b>Metric</b>", body_style), Paragraph("<b>Value / State</b>", body_style), Paragraph("<b>Clinical Interpretation</b>", body_style)],
        [Paragraph("Geometric Quality Tier", body_style),
         Paragraph(f"<font color='{qg_tier_color}'><b>{quality_gate.overall_quality_tier}</b></font>", body_style),
         Paragraph(f"Inter-slice spacing: {quality_gate.slice_spacing_mm:.2f}mm, Thickness: {quality_gate.slice_thickness_mm:.2f}mm", body_style)],
        [Paragraph("Pelvicalyceal Visibility", body_style),
         Paragraph(f"<font color='{pcs_tier_color}'><b>{pcs_visibility.state.value}</b></font>", body_style),
         Paragraph(f"Confidence score: {pcs_visibility.confidence_score:.2f} | Direct puncture lock: {pcs_visibility.allows_direct_puncture_lock}", body_style)]
    ]
    qg_table = Table(qg_summary, colWidths=[150, 150, 240])
    qg_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#E5E7EB')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#D1D5DB')),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(qg_table)
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"<b>Clinical Notice:</b> {pcs_visibility.clinical_notice}", body_style))
    story.append(Spacer(1, 8))

    # Stone Characterization Table
    story.append(Paragraph("2. Volumetric Stone Burden & Attenuation Characterization", section_heading))
    stone_rows = [
        [Paragraph("<b>ID</b>", body_style),
         Paragraph("<b>Volume (mm³)</b>", body_style),
         Paragraph("<b>Max Feret (mm)</b>", body_style),
         Paragraph("<b>Mean HU</b>", body_style),
         Paragraph("<b>Peak HU</b>", body_style),
         Paragraph("<b>Density Profile (<500 / 500-1000 / >1000 HU)</b>", body_style)]
    ]

    for s, a in zip(stones, attenuations):
        dens_str = f"{a.fraction_low_under_500hu*100:.0f}% / {a.fraction_intermediate_500_1000hu*100:.0f}% / {a.fraction_high_over_1000hu*100:.0f}%"
        stone_rows.append([
            Paragraph(f"#{s.stone_id} ({s.tier})", body_style),
            Paragraph(f"{s.volume_mm3:.1f}", body_style),
            Paragraph(f"{s.max_feret_diameter_mm:.1f}", body_style),
            Paragraph(f"{a.mean_hu:.0f}", body_style),
            Paragraph(f"{a.peak_hu:.0f}", body_style),
            Paragraph(dens_str, body_style)
        ])

    stone_table = Table(stone_rows, colWidths=[90, 80, 80, 60, 60, 170])
    stone_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#E5E7EB')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#D1D5DB')),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(stone_table)
    story.append(Spacer(1, 4))
    story.append(Paragraph("<b>Notice:</b> CT attenuation reflects radiopacity and assists fragmentation estimation. Mineral composition inference is not validated. Mechanical hardness is not directly measured.", disclaimer_style))

    # Page Break to Page 2
    story.append(PageBreak())

    # =========================================================================
    # PAGE 2: Candidate Trajectory Comparison (Pareto Matrix) & Disclaimers
    # =========================================================================
    story.append(Paragraph("3. Multi-Objective Candidate Trajectory Comparison (Pareto Matrix)", section_heading))
    story.append(Paragraph("Quantitative trade-offs between needle tract length, critical hazard clearance, and reachable stone burden.", subtitle_style))
    story.append(Spacer(1, 6))

    cand_rows = [
        [Paragraph("<b>Candidate</b>", body_style),
         Paragraph("<b>Target Region</b>", body_style),
         Paragraph("<b>Tract Length</b>", body_style),
         Paragraph("<b>Colon Clearance (Obs / Eff)</b>", body_style),
         Paragraph("<b>Pleural Risk</b>", body_style),
         Paragraph("<b>Stone Reach</b>", body_style),
         Paragraph("<b>Approach</b>", body_style),
         Paragraph("<b>Pareto</b>", body_style)]
    ]

    for c in candidates:
        pareto_badge = "<font color='#10B981'><b>YES</b></font>" if c.is_pareto_optimal else "<font color='#6B7280'>NO</font>"
        pleural_badge = "<font color='#10B981'>Clear</font>" if c.access_rib_classification != "SUPRACOSTAL_11" else "<font color='#EF4444'>Risk</font>"
        
        # Format calyx target label honestly
        calyx_label = c.target_calyx_name
        if pcs_visibility.state == PCSVisibilityState.ANATOMICALLY_ESTIMATED:
            calyx_label = f"Est. {c.target_calyx_name}"

        cand_rows.append([
            Paragraph(f"<b>{c.candidate_id}</b>", body_style),
            Paragraph(calyx_label, body_style),
            Paragraph(f"{c.tract_length_mm:.1f} mm", body_style),
            Paragraph(f"{c.min_effective_clearance_mm:.1f} mm (eff)", body_style),
            Paragraph(pleural_badge, body_style),
            Paragraph(f"{c.reachable_stone_fraction*100:.0f}%", body_style),
            Paragraph(c.access_rib_classification, body_style),
            Paragraph(pareto_badge, body_style)
        ])

    cand_table = Table(cand_rows, colWidths=[65, 85, 60, 105, 55, 60, 75, 35])
    cand_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#E5E7EB')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#D1D5DB')),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(cand_table)
    story.append(Spacer(1, 8))

    # Explainable "Why this candidate?" Justification Box
    story.append(Paragraph("4. Pareto Decision Rationale & Trade-Offs", section_heading))
    justification_items = []
    for c in candidates:
        if c.is_pareto_optimal:
            just_text = (
                f"<b>{c.candidate_id}:</b> Pareto-optimal trade-off. "
                f"Tract length: {c.tract_length_mm:.1f}mm | Effective clearance: {c.min_effective_clearance_mm:.1f}mm | "
                f"Stone coverage: {c.reachable_stone_fraction*100:.0f}% ({c.access_rib_classification}). "
                f"Scope deflection required: {c.required_scope_deflection_deg:.1f}°."
            )
            justification_items.append([Paragraph(just_text, body_style)])

    if justification_items:
        just_table = Table(justification_items, colWidths=[540])
        just_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#EFF6FF')),
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#3B82F6')),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('LEFTPADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(just_table)
    story.append(Spacer(1, 10))

    # Mandatory Legal, CDS, and Surgeon Sign-Off Section
    story.append(Paragraph("5. Clinical Decision Support Disclosure & Surgical Sign-Off", section_heading))
    legal_text = (
        "<b>MANDATORY NOTICE:</b> AcuCalyx™ is a clinical decision support planning system intended for "
        "preoperative visualization, risk estimation, and mathematical trajectory comparison. It does not replace "
        "intraoperative real-time fluoroscopic or ultrasonographic guidance. The operating surgeon maintains full, "
        "independent responsibility for selecting the final puncture site, needle trajectory, and operative approach. "
        "3D surface meshes and STL exports are for visual rehearsal only and are non-sterile."
    )
    story.append(Paragraph(legal_text, disclaimer_style))
    story.append(Spacer(1, 12))

    signoff_data = [
        [Paragraph("<b>Operating Urologist:</b> ___________________________", body_style),
         Paragraph("<b>Date / Time:</b> _________________________", body_style)],
        [Paragraph("<b>Selected Trajectory Candidate:</b> [  ] A   [  ] B   [  ] C   [  ] Manual Override", body_style),
         Paragraph("<b>Signature:</b> ___________________________", body_style)]
    ]
    signoff_table = Table(signoff_data, colWidths=[300, 240])
    signoff_table.setStyle(TableStyle([
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(signoff_table)

    doc.build(story)
    return output_path
