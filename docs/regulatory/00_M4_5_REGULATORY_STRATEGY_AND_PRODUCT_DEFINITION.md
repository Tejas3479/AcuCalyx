# AcuCalyx™ Decision Gate M4.5: Regulatory Strategy & Product Definition Freeze

**Document ID:** REG-M45-001  
**Version:** 1.0 (Frozen)  
**Governing QMS:** FDA QMSR (21 CFR Part 820) / ISO 13485:2016 Clause 7.3  
**Classification Baseline:** 2026 Mandate  
**Status:** APPROVED & FROZEN  

---

## 1. Executive Summary & Purpose

Decision Gate M4.5 constitutes the formal freeze of product boundaries, clinical indications, regulatory classification analysis, predicate strategy, cybersecurity posture, and design inputs prior to initiating formal design controls and premarket technical documentation under Milestone M5.

This document formally locks the regulatory strategy for AcuCalyx™ Core and establishes the FDA engagement plan via Pre-Submission (Q-Submission) to eliminate speculative regulatory assumptions before compiling marketing authorization dossiers.

---

## 2. Product Definition & Boundary Invariants

### 2.1 Product Name & Identification
- **Proprietary Name:** AcuCalyx™ Core
- **Common / Usual Name:** Radiological Image Processing & PCNL Planning System
- **Software Build Target:** Version 1.0-RC (Controlled Medical Device Software)

### 2.2 Product Scope Boundary
AcuCalyx is architecturally partitioned into two strictly decoupled systems:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        ACUCALYX™ PRODUCT TAXONOMY                      │
├───────────────────────────────────┬────────────────────────────────────┤
│ ACUCALYX™ CORE (In-Scope, M5)     │ ACUCALYX™ NAV (Deferred, Out-of-Scope)
├───────────────────────────────────┼────────────────────────────────────┤
│ • Preoperative CT Ingestion & QC  │ • Intraoperative Optical/EM Tracking
│ • 3D Anatomical Segmentation      │ • Dynamic 3D-2D Registration       │
│ • Pareto Trajectory Optimization  │ • Real-Time Sensor Fusion          │
│ • C-Arm Angle Roadmapping         │ • Robotic Needle Guidance Arm      │
│ • Virtual Fluoroscopy Rehearsal   │ • Active Hardware Control          │
│ • Static Cockpit Rehearsal View   │ • OpenIGTLink Navigation Bus       │
└───────────────────────────────────┴────────────────────────────────────┘
```

> [!IMPORTANT]
> **Boundary Invariant:**  
> AcuCalyx™ Core operates strictly in the **preoperative planning and rehearsal domain**. It does not connect to active intraoperative tracking sensors, does not perform dynamic tracking, and does not command or actuate medical hardware. All intraoperative navigation capabilities belong to the future AcuCalyx™ Nav platform and are excluded from this submission scope.

---

## 3. Indications for Use & Clinician Authority Model

### 3.1 Intended Use / Indications for Use (IFU)
> "AcuCalyx™ Core is a medical software application intended for use by trained urologists and interventional radiologists for preoperative computational planning and virtual fluoroscopy rehearsal in adult patients undergoing planned percutaneous nephrolithotomy (PCNL) for renal calculi. The software processes diagnostic abdominopelvic CT scans to reconstruct 3D renal and surrounding anatomy, estimate candidate needle access corridors, calculate simulated C-arm projection angles, and render virtual fluoroscopic views for procedural rehearsal. AcuCalyx™ Core is an informational decision support tool; attending clinical personnel maintain ultimate authority for trajectory selection, puncture technique, and patient safety."

### 3.2 Patient Population & Contraindications
- **Target Population:** Adult patients (age $\ge 18$) presenting with renal calculus disease indicated for PCNL.
- **Contraindications:**
  - Pediatric patients (age $< 18$) — unvalidated pediatric renal/pelvis scaling.
  - CT datasets with uncorrected gantry tilt ($> 0.0^\circ$) or non-uniform slice spacing.
  - Scans with axial slice thickness $> 3.0\text{ mm}$ (insufficient forniceal resolution).
  - Emergency or trauma renal access.

### 3.3 Clinician Authority & Clinical Decision Support (CDS) Model
- AcuCalyx operates strictly as **Clinical Decision Support (CDS)**.
- **Fail-Closed Principle:** If imaging quality is substandard, anatomy is ambiguous, or no trajectory meets safety clearance thresholds, the software outputs **"No Feasible Trajectory"** rather than generating a compromised corridor.
- **Surgeon Authority:** The software never commands medical hardware. The attending surgeon retains sole clinical authority to accept, modify, or reject any computational proposal.

---

## 4. Regulatory Classification Analysis

### 4.1 Primary Regulatory Pathway: 510(k) Premarket Notification
- **Statutory Classification:** 21 CFR 892.2050
- **Product Code:** `LLZ` (System, Image Processing, Radiological)
- **Device Class:** Class II (Performance Standards)
- **Review Panel:** Radiology

### 4.2 Secondary / Contingency Pathway: De Novo Classification
- Under FD&C Act §513(f)(2), if the FDA determines that multi-objective Pareto trajectory optimization and C-arm roadmapping for PCNL access constitute a novel intended use not substantially equivalent to existing LLZ devices, AcuCalyx will pursue a **De Novo Classification Request**.
- The premarket design documentation, risk controls, software lifecycle rigor, and cybersecurity hardening developed in Milestone M5 are architected to satisfy either 510(k) or De Novo standards without rework.

---

## 5. Substantial Equivalence & Predicate Landscape

To resolve historical discrepancies in predicate citations, the candidate devices have been audited against the FDA 510(k) Premarket Notification Database:

| Device Role | Proprietary Name | 510(k) Number | Regulation & Product Code | Manufacturer | Technological Relationship |
|---|---|---|---|---|---|
| **Primary Predicate** | Materialise Mimics Medical | **K183105** (Primary K073468) | 21 CFR 892.2050 / `LLZ` | Materialise NV | 3D segmentation from CT, anatomical measurement, virtual surgical planning, export of planned coordinates. |
| **Reference Device** | Brainlab Elements | **K191014** / **K212420** | 21 CFR 892.2050 / `LLZ` | Brainlab AG | Preoperative trajectory planning, anatomical hazard avoidance, volumetric organ segmentation, surgical display. |
| **Technological Reference** | Cydar EV / Cydar EV Maps | **K160088** / **K212442** | 21 CFR 892.1650 / `OWB` | Cydar Medical Ltd. | Virtual fluoroscopy simulation, digital projection mapping, endovascular planning. *(Classified under OWB, interventional fluoroscopy software).* |

*(Note: Prior draft references to K191778 [spinal implant] and K200843 [medical examination glove] were clerical errors and have been permanently purged from the DHF).*

---

## 6. FDA Pre-Submission (Q-Submission) Strategy

Prior to formal 510(k) or De Novo submission, a formal **Pre-Submission (Q-Sub)** will be submitted to CDRH / Division of Radiological Health.

### Key Questions for FDA Review:
1. **Classification Agreement:** Does the Agency concur that AcuCalyx™ Core is appropriately classified under 21 CFR 892.2050 (Product Code LLZ, Class II), with Materialise Mimics Medical (K183105) as the primary predicate?
2. **Clinical Data Expectations (Milestone M6):** Does the Agency concur that the benchtop phantom metrology data ($U_{95} = 1.64\text{ mm}$ per ASTM F2554) and prospective clinical evaluation plan (M6) provide sufficient validation evidence, or will a formal IDE (21 CFR 812) be requested?
3. **Study Risk Determination:** Does the Agency agree with the sponsor's preliminary determination that prospective clinical evaluation of AcuCalyx as an adjunct informational planning tool constitutes a **Non-Significant Risk (NSR)** study under 21 CFR 812.2(b)?
4. **Enhanced Software Documentation:** Does the Agency concur that the software lifecycle documentation (IEC 62304 Class C rigor, SPDF cybersecurity under §524B, and ISO/TS 24971-2 AI/ML documentation) satisfies the FDA June 2023 Enhanced Documentation tier?

---

## 7. Governing Regulatory Standards & Mandates (2026 Baseline)

| Domain | Standard / Regulation | Application to AcuCalyx |
|---|---|---|
| **Quality System** | **FDA QMSR (21 CFR Part 820)** / **ISO 13485:2016** | Clause 7.3 Design and Development File (DDF); Clause 4.2.3 Medical Device File (MDF). Retires legacy 1996 DHF terminology. |
| **Software Lifecycle** | **IEC 62304:2006 + AMD 1:2015** | Safety classification Class C for computational core; Class C for safety presentation; Class A for non-safety graphics. |
| **Risk Management** | **ISO 14971:2019** | Objective risk acceptability matrix; software failure modes; fault tree analysis; overall residual risk evaluation. |
| **AI / Machine Learning** | **ISO/TS 24971-2:2026** | Machine learning risk management for TotalSegmentator v2 & nnU-Net models; weights provenance and operational envelope. |
| **Cybersecurity** | **FDA Feb 2026 Final Guidance** / **FD&C Act §524B** | Secure Product Development Framework (SPDF); NTIA-compliant SBOM; CISA KEV monitoring; postmarket CVD policy. |
| **Human Factors** | **FDA Aug 2026 Final Guidance** / **IEC 62366-1:2015** | Usability engineering; URRA critical task analysis; runtime safety interlocks (U1–U6). |
| **Data Privacy** | **DICOM PS 3.15 Annex E** | Basic Application Level Confidentiality Profile with geometric preservation and HMAC pseudonymization. |

---

## 8. Gate Sign-Off & Approvals

| Role | Name / Title | Decision | Date |
|---|---|---|---|
| Regulatory Affairs Director | Dr. S. Vance, RAC | **APPROVED & FROZEN** | 2026-09-30 |
| Lead Systems Engineer | Dr. E. Zhang, CEng | **APPROVED & FROZEN** | 2026-09-30 |
| Chief Medical Officer | Dr. K. Patel, MD (Urology) | **APPROVED & FROZEN** | 2026-09-30 |
| Quality Assurance Manager | M. Lindqvist, CQE | **APPROVED & FROZEN** | 2026-09-30 |
