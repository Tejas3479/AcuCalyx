# AcuCalyx™ Core Internal Premarket Submission Dossier Map
## Evidence Mapping & Cross-Reference Structure for FDA eSTAR Template (v7.1 / June 2026)

**Document Identifier:** MAP-ACU-ESTAR-2026A  
**Target Submission Format:** FDA CDRH non-IVD eSTAR (Current Baseline: Version 7.1, June 1, 2026)  
**Submission Pathway:** Decision Gate M6.5 Branch A (510(k) Premarket Notification) / Branch B (De Novo Request)  
**Software Documentation Tier:** Expected Level: Enhanced (per FDA Software Functions Guidance, June 2023)  

---

## 1. Executive Structure & eSTAR Dynamic PDF Architecture

### 1.1 The Nature of FDA eSTAR Submissions
In accordance with FDA CDRH policy, electronic submissions for 510(k) and De Novo classifications must utilize the official FDA eSTAR dynamic interactive PDF. The official template features automated JavaScript validation, conditional section rendering based on device technology, and built-in administrative cover sheets.

> [!NOTE]
> **Integrated Administrative Forms:**  
> When submitting via eSTAR, Form FDA 3514 (Premarket Review Submission Cover Sheet) and Form FDA 3881 (Indications for Use Page) are built directly into the dynamic PDF questionnaire. They do not exist as independent detached PDF exhibits; instead, the data fields are populated within the form itself.

### 1.2 Purpose of this Evidence Dossier Map
This document serves as the **Internal Master Evidence Index** used by regulatory affairs professionals to assemble, verify, and cross-reference all verified AcuCalyx design controls, risk files, cybersecurity audits, benchtop reports, and clinical feasibility records into the official FDA eSTAR template until the dynamic PDF displays `"eSTAR COMPLETE"`.

---

## 2. Internal Evidence Map to FDA eSTAR Dynamic Sections

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│             ACUCALYX™ INTERNAL EVIDENCE DOSSIER TO FDA eSTAR v7.1 MAPPING             │
├──────┬─────────────────────────────┬───────────────────────────────────────────────────┤
│ eSTAR│ eSTAR Topic / Dynamic       │ AcuCalyx Controlled Exhibit / Attachment          │
│ Sec  │ Subsection                  │                                                   │
├──────┼─────────────────────────────┼───────────────────────────────────────────────────┤
│ 1.0  │ General Information &       │ • Populated in eSTAR dynamic form fields          │
│      │ Administrative Details      │ • Exhibit E01: User Fee Cover Sheet & Establishment│
├──────┼─────────────────────────────┼───────────────────────────────────────────────────┤
│ 2.0  │ Device Description &        │ • Exhibit E02-A: SRS Section 4 (System Architecture)│
│      │ Principles of Operation     │ • Exhibit E02-B: 01_DESIGN_AND_DEVELOPMENT_SRS.md  │
│      │                             │ • Exhibit E02-C: Oper. Envelope & Workflow Guide  │
├──────┼─────────────────────────────┼───────────────────────────────────────────────────┤
│ 3.0  │ Indications for Use &       │ • Populated in eSTAR dynamic form fields          │
│      │ Clinical Audience           │ • Exhibit E03: Prescription Statement & Gating    │
├──────┼─────────────────────────────┼───────────────────────────────────────────────────┤
│ 4.0  │ Substantial Equivalence     │ • Exhibit E04-A: Candidate Predicate Landscape    │
│      │ (510k) / De Novo Summary    │   Matrix (Mimics K183105 & Brainlab K191014)      │
│      │                             │ • Exhibit E04-B: Technological Comparison Table   │
├──────┼─────────────────────────────┼───────────────────────────────────────────────────┤
│ 5.0  │ Device Labeling & Packaging │ • Exhibit E05-A: 09_OPERATORS_MANUAL_AND_LABELING │
│      │ (21 CFR Part 801 / 830)     │ • Exhibit E05-B: Software Splash & Sterile OR Card│
│      │                             │ • Exhibit E05-C: UDI DI/PI Assignment Sheet       │
├──────┼─────────────────────────────┼───────────────────────────────────────────────────┤
│ 6.0  │ Software Functions & V&V    │ • Exhibit E06-A: 02_SOFTWARE_REQUIREMENTS_SWRS.md │
│      │ (Enhanced Documentation     │ • Exhibit E06-B: Software Architecture Description │
│      │  Tier, June 2023 Guidance)  │ • Exhibit E06-C: 10-Tier RTM Traceability Closure │
│      │                             │ • Exhibit E06-D: V&V Protocols & Test Pass Reports│
│      │                             │ • Exhibit E06-E: IEC 62304 Anomaly Register       │
├──────┼─────────────────────────────┼───────────────────────────────────────────────────┤
│ 7.0  │ Cybersecurity Management    │ • Exhibit E07-A: 05_CYBERSECURITY_PLAN_AND_SPDF   │
│      │ (FD&C Act §524B, Feb 2026)  │ • Exhibit E07-B: Machine-Readable CycloneDX SBOM  │
│      │                             │ • Exhibit E07-C: STRIDE Threat Model Audit        │
│      │                             │ • Exhibit E07-D: CISA KEV Vulnerability Report    │
│      │                             │ • Exhibit E07-E: Coordinated Vulnerability Discl. │
├──────┼─────────────────────────────┼───────────────────────────────────────────────────┤
│ 8.0  │ AI/ML Risk & Lifecycle      │ • Exhibit E08-A: 12_AIML_SYSTEM_INVENTORY_CARD.md │
│      │ (Aug 2025 Final Guidance)   │ • Exhibit E08-B: Model Weights Hash & Provenance  │
│      │                             │ • Exhibit E08-C: Conditional PCCP (if applicable) │
├──────┼─────────────────────────────┼───────────────────────────────────────────────────┤
│ 9.0  │ Risk Management File        │ • Exhibit E09-A: 03_ISO_14971_RISK_MANAGEMENT_FILE│
│      │ (ISO 14971:2019 / 24971)    │ • Exhibit E09-B: Hazard Analysis & SwFMEA Matrix  │
│      │                             │ • Exhibit E09-C: Residual Risk & BRA Summary      │
├──────┼─────────────────────────────┼───────────────────────────────────────────────────┤
│ 10.0 │ Human Factors & Usability   │ • Exhibit E10-A: IEC 62366-1 Summative Usability  │
│      │ (August 2026 FDA Guidance)  │   Report (4 User Cohorts, Critical Tasks C1–C6)   │
│      │                             │ • Exhibit E10-B: Safety Interlocks U1–U6 Report   │
├──────┼─────────────────────────────┼───────────────────────────────────────────────────┤
│ 11.0 │ Non-Clinical Benchtop &     │ • Exhibit E11-A: ASTM F2554 Anthropomorphic       │
│      │ Metrology Verification      │   Phantom Metrology Report (Observed U95 = 1.64mm)│
│      │                             │ • Exhibit E11-B: C-Arm DRR Projection Metrology   │
├──────┼─────────────────────────────┼───────────────────────────────────────────────────┤
│ 12.0 │ Clinical Evidence & Feasibil│ • Exhibit E12-A: ISO 14155:2026 Clinical Investi- │
│      │ ity Study (ACU-PILOT-01)    │   gation Report (CIR, N = 30, Multi-Center)       │
│      │                             │ • Exhibit E12-B: Independent CEC Safety Report    │
├──────┼─────────────────────────────┼───────────────────────────────────────────────────┤
│ 13.0 │ Interoperability & Network  │ • Exhibit E13-A: 08_DICOM_CONFORMANCE_STATEMENT   │
│      │ Conformance (DICOM PS 3.2)  │ • Exhibit E13-B: Secondary Capture DRR Spec       │
│      │                             │ • Exhibit E13-C: DICOM PS 3.15 Profile Report     │
├──────┼─────────────────────────────┼───────────────────────────────────────────────────┤
│ 14.0 │ Postmarket QMS Readiness    │ • Exhibit E14-A: 14_POSTMARKET_SURVEILLANCE_PLAN  │
│      │ (QMSR / 21 CFR Part 820)    │ • Exhibit E14-B: MDR (Part 803) & Recalls (806)   │
└──────┴─────────────────────────────┴───────────────────────────────────────────────────┘
```

---

## 3. Candidate Predicate Landscape Analysis

AcuCalyx evaluates substantial equivalence against candidate predicates and candidate reference devices:

### 3.1 Primary Candidate Predicate: Materialise Mimics Medical (K183105)
- **Classification Regulation:** 21 CFR 892.2050 (System, Image Processing, Radiological - Product Code: LLZ)
- **Intended Use Comparison:** Both devices import medical imaging (CT), segment anatomical structures, and support pre-procedural planning.
- **Technological Differences:** AcuCalyx Core provides specialized renal calyceal targeting, multi-objective Pareto optimization, and simulated C-arm fluoroscopy DRR projection. The pre-submission Q-Sub dialogue confirms whether these features constitute technological differences that do not raise different questions of safety and effectiveness.

### 3.2 Candidate Reference Device: Brainlab Elements (K191014 / K212420)
- **Classification Regulation:** 21 CFR 892.2050 (Product Code: LLZ)
- **Utility:** Serves as a reference device demonstrating substantial equivalence for automated trajectory planning, critical organ hazard avoidance corridors, and multi-modal visualization.

### 3.3 De Novo Classification Contingency (Branch B)
If the FDA determines that multi-objective calyx optimization represents a novel intended use outside LLZ:
- AcuCalyx submits a De Novo Classification Request using the same eSTAR template.
- Proposes Special Controls including: ASTM F2554 phantom metrology standards, IEC 62366-1 critical task error thresholds, and fail-closed calyceal observability gating.
