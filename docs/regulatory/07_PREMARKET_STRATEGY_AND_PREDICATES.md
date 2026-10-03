# AcuCalyx™ Premarket Regulatory Strategy & Predicate Device Evaluation

**Document ID:** STRAT-ACU-001  
**Version:** 1.0 (Frozen)  
**Governing Regulation:** 21 CFR Part 807 Subpart E (Premarket Notification) / FD&C Act §513  
**Target Milestone:** Milestone M5 Dossier Compilation & Pre-Submission Strategy  
**Status:** APPROVED & FROZEN  

---

## 1. Executive Summary & Regulatory Pathway

This document establishes the formal premarket notification strategy for **AcuCalyx™ Core**, identifying the governing FDA classification regulation, primary predicate device, reference devices, substantial equivalence comparative analysis, and Q-Submission protocol.

### 1.1 Dual Regulatory Pathway Analysis

```
                                [AcuCalyx™ Core Strategy]
                                            │
                                            ▼
                           [CDRH Pre-Submission (Q-Sub)]
                                            │
                     ┌──────────────────────┴──────────────────────┐
                     │                                             │
                     ▼                                             ▼
        [Primary: 510(k) Pathway]                      [Contingency: De Novo Pathway]
        • 21 CFR 892.2050 (Class II, LLZ)              • FD&C Act §513(f)(2)
        • Primary Predicate: Mimics (K183105)          • Invoked if FDA determines
        • Reference: Brainlab (K191014)                • Multi-objective Pareto PCNL
        • Proven Substantial Equivalence               • access planning is novel
```

1. **Primary Strategy: 510(k) Premarket Notification (21 CFR 892.2050, Product Code LLZ)**
   - Medical image processing software systems intended for 3D reconstruction, anatomical measurement, and preoperative planning are routinely cleared under regulation 21 CFR 892.2050.
   - AcuCalyx performs diagnostic CT segmentation, calculates planned geometric corridors, and renders simulated projections without directly actuating or controlling physical surgical instruments.
2. **Contingency Strategy: De Novo Classification (FD&C Act §513(f)(2))**
   - If the Agency determines that automated multi-objective Pareto trajectory optimization and C-arm angle roadmapping for percutaneous renal access constitute a novel technological feature raising new questions of safety or effectiveness, AcuCalyx will submit a De Novo classification request.
   - The design controls, benchtop testing, and human factors validation developed under Milestone M5 are architected to satisfy either 510(k) or De Novo standards without structural alteration.

---

## 2. Audited Predicate & Reference Device Landscape

To resolve past inaccuracies in citation numbers, all candidate predicate and reference devices have been formally verified against FDA clearance records:

### 2.1 Primary Predicate Device: Materialise Mimics Medical (K183105)
- **510(k) Number:** K183105 (Cleared November 2018; Primary Predicate K073468)
- **Regulation:** 21 CFR 892.2050
- **Product Code:** `LLZ` (System, Image Processing, Radiological)
- **Classification:** Class II
- **Indications for Use:** Software intended for use as a software interface and image segmentation system for the transfer of DICOM imaging information. It assists in 3D visualization, anatomical measurement, and virtual surgical planning.
- **Substantial Equivalence Nexus:** Demonstrates that automated segmentation, 3D surface extraction, anatomical distance measurement, and virtual trajectory definition are established Class II LLZ indications.

### 2.2 Reference Device: Brainlab Elements (K191014 / K212420)
- **510(k) Numbers:** K191014 (Viewer/Planning), K212420 (Elements Suite), K243633
- **Regulation:** 21 CFR 892.2050
- **Product Code:** `LLZ`
- **Classification:** Class II
- **Substantial Equivalence Nexus:** Establishes the safety and effectiveness of software-guided surgical trajectory planning, anatomical hazard avoidance margins, and volumetric risk corridor visualization.

### 2.3 Technological Reference Device: Cydar EV / Cydar EV Maps (K160088 / K212442)
- **510(k) Numbers:** K160088 (Original clearance), K212442 (Cydar EV Maps)
- **Regulation:** 21 CFR 892.1650
- **Product Code:** `OWB` (Interventional Fluoroscopic X-Ray System Software)
- **Classification:** Class II
- **Substantial Equivalence Nexus:** Serves as a technological reference device for virtual fluoroscopy simulation, digital projection mapping, and intraoperative C-arm roadmapping. *(Note: Classified under OWB rather than LLZ, reflecting its interventional imaging workflow).*

---

## 3. Substantial Equivalence Comparison Matrix

| Technological / Clinical Feature | Subject Device: AcuCalyx™ Core | Primary Predicate: Mimics Medical (K183105) | Reference Device: Brainlab Elements (K191014) | Substantial Equivalence Analysis |
|---|---|---|---|---|
| **Device Classification** | Class II, 21 CFR 892.2050 | Class II, 21 CFR 892.2050 | Class II, 21 CFR 892.2050 | **Identical** |
| **Product Code** | `LLZ` | `LLZ` | `LLZ` | **Identical** |
| **Clinical Indication** | Preoperative planning & virtual rehearsal for PCNL | Preoperative surgical planning & anatomical modeling | Preoperative surgical trajectory planning & anatomical modeling | **Substantially Equivalent:** Both provide preoperative procedural planning based on CT. |
| **Input Data Modality** | Standard DICOM Axial CT | Standard DICOM Axial CT / MR | Standard DICOM Axial CT / MR | **Substantially Equivalent:** CT DICOM format compliant. |
| **3D Anatomical Segmentation** | Deep learning (nnU-Net) & thresholding | Thresholding, region growing, deep learning | Atlas-based & deep learning | **Equivalent:** Both produce 3D anatomical organ models. |
| **Trajectory Corridor Calculation** | Multi-objective Pareto optimization | User-defined points & vectors | User-guided planning corridors | **Equivalent:** Both compute 3D entry-to-target vectors; AcuCalyx provides computational ranking. |
| **Hazard Avoidance** | Automatic distance field buffers ($\ge 15\text{ mm}$ colon) | User visual inspection & distance caliper | Pre-segmented risk structure exclusion zones | **Substantially Equivalent:** Both avoid critical anatomical structures. |
| **Fluoroscopic Rehearsal** | Simulated forward projection DRR & C-arm angles | None (Export to CAD/RP) | Simulated projection views (X-Ray/DRR) | **Equivalent:** Comparable to Brainlab and Cydar EV projection capabilities. |
| **Clinician Control** | Informational decision support; surgeon retains authority | Informational planning tool; surgeon retains authority | Informational planning tool; surgeon retains authority | **Identical:** Neither commands active medical hardware. |
| **Cybersecurity Controls** | FD&C Act §524B compliant; SHA-256 plan fingerprinting | Standard OS security | Enterprise hospital security | **Superior / Compliant:** AcuCalyx meets 2026 premarket cybersecurity standards. |

---

## 4. FDA Q-Submission (Pre-Submission) Action Plan

To establish binding alignment with CDRH before submitting the formal premarket filing:

1. **Q-Submission Dossier Content:**
   - Detailed Description of AcuCalyx™ Core Software Architecture
   - Indications for Use Statement and Clinician Decision Support Model
   - Substantial Equivalence Comparison with Mimics Medical (K183105) and Brainlab Elements (K191014)
   - ASTM F2554 Benchtop Physical Phantom Metrology Results ($U_{95} = 1.64\text{ mm}$)
   - IEC 62366-1 Human Factors Formative & Summative Protocols
   - Cybersecurity Management Plan and Software Bill of Materials (SBOM)
   - Prospective Clinical Evaluation Protocol (Milestone M6)
2. **Key Agency Alignment Objectives:**
   - Obtain formal consensus on 510(k) eligibility under 21 CFR 892.2050 / `LLZ`.
   - Confirm that the proposed Milestone M6 clinical study qualifies as a Non-Significant Risk (NSR) investigation under 21 CFR 812.2(b).
   - Verify that the cybersecurity and AI/ML risk documentation fulfill the February 2026 Premarket Guidance expectations.
