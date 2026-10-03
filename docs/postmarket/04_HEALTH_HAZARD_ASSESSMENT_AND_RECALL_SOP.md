# AcuCalyx™ Core Health Hazard Assessment & Field Corrections SOP
## Procedure for Health Hazard Assessment (HHA) & Reports of Corrections and Removals (21 CFR Part 806)

**Document Identifier:** SOP-ACU-HHA-2026A  
**Regulatory Baseline:** 21 CFR Part 806 (Corrections & Removals) & 21 CFR Part 7 (Recall Policy)  
**Target Milestone:** Milestone M8 (Commercial Operations)  

---

## 1. Scope & Regulatory Authority

This procedure defines the internal protocol for conducting a **Health Hazard Assessment (HHA)** when a potential software anomaly, defect, or vulnerability is identified in commercial distribution, and for managing voluntary Field Safety Corrective Actions (FSCA).

> [!IMPORTANT]
> **FDA Recall Classification Authority:**  
> The internal Health Hazard Assessment tool assists the manufacturer's Quality Review Board in quantifying risk priority. The software **does NOT** legally classify a recall. The **FDA assigns the official statutory recall classification (Class I, Class II, or Class III)** after reviewing the firm's health hazard evaluation and corrective action plan.

---

## 2. Health Hazard Assessment (HHA) Evaluation Framework

When an anomaly is escalated from complaint handling or cybersecurity monitoring, the Health Hazard Evaluation Committee convenes to evaluate:
1. Whether any disease or injury has already occurred from device use.
2. Whether any existing conditions could contribute to a clinical hazard.
3. Assessment of hazard severity to affected patient populations.
4. Probability of occurrence of the hazard if unmitigated.
5. Immediate and long-term consequences of the hazard.

### 2.1 Internal Risk Priority Matrix

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                      INTERNAL HEALTH HAZARD RISK PRIORITY MATRIX                       │
├───────────────────────┬────────────────────────────────────────────────────────────────┤
│ Severity Level (S)    │ Clinical Definition                                            │
├───────────────────────┼────────────────────────────────────────────────────────────────┤
│ **Critical (S1)**     │ Potential patient death, bowel perforation, severe hemorrhage. │
│ **Major (S2)**        │ Reversible injury, pleural puncture, pneumothorax, pain.       │
│ **Minor (S3)**        │ Minor procedural delay, transient display glitch, re-aiming.   │
├───────────────────────┼────────────────────────────────────────────────────────────────┤
│ Probability Level (P) │ Frequency / Likelihood in Clinical Field                       │
├───────────────────────┼────────────────────────────────────────────────────────────────┤
│ **High (P1)**         │ Systematic error affecting common CT acquisition geometries.   │
│ **Medium (P2)**       │ Occurs under specific anatomical permutations (e.g., BMI > 35).│
│ **Low (P3)**          │ Rare edge case requiring multiple simultaneous operator errors.│
└───────────────────────┴────────────────────────────────────────────────────────────────┘
```

---

## 3. Reporting to FDA District Office (21 CFR Part 806)

### 3.1 Reportable Corrections and Removals
Under 21 CFR 806.10, any correction or removal initiated by a manufacturer to reduce a risk to health posed by the device must be reported in writing to the applicable FDA District Office within **10 working days** of initiating the action.

### 3.2 Contents of 10-Day Written Report
The written report submitted by the Director of Regulatory Affairs must contain:
1. Manufacturer establishment registration number and contact details.
2. Device brand name, model numbers, software build ID, and UDI.
3. Clear description of the defect, software anomaly, or vulnerability.
4. Total number of units distributed and geographic site locations.
5. The firm's internal Health Hazard Assessment.
6. Copy of the customer Field Safety Notice (FSN) dispatched to hospital risk managers.

---

## 4. Urgent Medical Device Field Safety Notice (FSN) Structure

Customer communications dispatched under this SOP must follow standard FDA FSN formatting:
- **Header:** `URGENT MEDICAL DEVICE SAFETY NOTICE: SOFTWARE PATCH REQUIRED`
- **Affected Product:** AcuCalyx™ Core, Version 1.0.0, Build `ACU-CORE-COMMERCIAL-20261015-BLD01`
- **Issue Description:** Specific explanation of software anomaly (e.g., calculation artifact).
- **Clinical Risk:** Impact on surgical planning and potential anatomical risk.
- **Immediate Required Actions for Users:** Manual clinical confirmation protocol under live fluoroscopy.
- **Remediation & Patch Deployment:** Deployment schedule for validated software update archive (`.acupkg`).
