# AcuCalyx™ Core FDA Pre-Submission (Q-Submission) Briefing Package
## Formal Request for Agency Written Feedback & Pre-Submission Meeting

**Document Identifier:** QSUB-ACU-2026-001  
**Submission Date:** October 2026  
**Sponsor / Applicant:** AcuCalyx Medical Systems, Inc.  
**Device Proprietary Name:** AcuCalyx™ Core  
**Common / Usual Name:** Radiological Image Processing & PCNL Planning System  
**Statutory Classification:** 21 CFR 892.2050 (Medical Image Processing and Communication System)  
**Product Codes:** `LLZ` (System, Image Processing, Radiological) & `QIH` (Automated Radiological Image Processing Software)  
**Device Class:** Class II (Special Controls)  
**CDRH Review Division:** Office of Health Technology 8 (OHT8: Radiological Health) / Division of Radiological Health  
**Governing Guidance:** FDA Guidance *The Q-Submission Program and Meetings with FDA Staff* (January 2026)  
**Quality System Baseline:** FDA QMSR (21 CFR Part 820) / ISO 13485:2016 / IEC 62304 Class C  

---

## 1. Executive Summary & Purpose of the Q-Submission

AcuCalyx Medical Systems, Inc. is submitting this formal Pre-Submission (Q-Sub) briefing package to obtain agency feedback from the Center for Devices and Radiological Health (CDRH) regarding the premarket regulatory strategy, substantial equivalence determination, non-clinical benchtop performance testing, human factors engineering validation, and clinical evaluation requirements for **AcuCalyx™ Core**.

AcuCalyx™ Core is a Software as a Medical Device (SaMD) preoperative planning and virtual fluoroscopic rehearsal workbench designed to assist urologists and interventional radiologists in planning percutaneous nephrolithotomy (PCNL) needle access trajectories for adult patients with renal calculi.

### 1.1 Key Objectives of this Pre-Submission
1. **Regulatory Classification Confirmation:** Confirm that AcuCalyx™ Core is appropriately classified under 21 CFR 892.2050 (Product Codes `LLZ` and `QIH`, Class II) eligible for review under the 510(k) premarket notification pathway.
2. **Predicate & Reference Device Alignment:** Validate the proposed primary predicate device (**Materialise Mimics Medical, K183105**) and reference devices (**Brainlab Elements, K191014**; **Cydar EV Maps, K160088 / K212442**).
3. **Benchtop & Metrological Sufficiency:** Confirm that the completed non-clinical benchtop verification—consisting of the Milestone M15-V CT Urography Multi-Reader Benchmark and ASTM F2554-18 physical anthropomorphic phantom metrology ($U_{95} = 1.64\text{ mm}$)—provides sufficient evidence of safety and effectiveness to support 510(k) clearance without requiring human clinical trial data.
4. **Investigational Risk Classification (21 CFR Part 812):** In the event that prospective human clinical data is recommended, obtain agency concurrence that an adjunct informational clinical feasibility study ($N=30$) qualifies as a **Non-Significant Risk (NSR)** investigation under 21 CFR 812.2(b).
5. **Human Factors & Cybersecurity Concurrence:** Align on the summative human factors validation protocol under IEC 62366-1:2015+AMD1:2020 and the cybersecurity architecture under FD&C Act §524B.

---

## 2. Device Description & SaMD Workbench Scope

### 2.1 Product Description
AcuCalyx™ Core is a medical software application deployed as a secure local clinical workbench (FastAPI backend with WebGL/Three.js interactive visualization frontend). The software imports standard diagnostic abdominopelvic CT DICOM datasets, reconstructs 3D patient-specific renal and surrounding anatomical structures, optimizes needle puncture corridors using a 5-objective Pareto ranking algorithm, simulates C-arm gantry projection angles (Bull's-Eye and Progression views), and renders digitally reconstructed radiographs (DRRs) for procedural rehearsal.

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│                    ACUCALYX™ CORE ARCHITECTURAL BOUNDARY                         │
├─────────────────────────────────────────────────┬─────────────────────────────────┤
│ IN-SCOPE: PREOPERATIVE WORKBENCH (AcuCalyx Core)│ OUT-OF-SCOPE: (AcuCalyx Nav)    │
├─────────────────────────────────────────────────┼─────────────────────────────────┤
│ • Diagnostic Axial CT Ingestion & Quality Gates │ • Optical/EM Needle Tracking    │
│ • Pelvicalyceal & Visceral 3D Segmentation      │ • Real-Time Sensor Fusion       │
│ • 5-Objective Pareto Trajectory Optimization    │ • Dynamic 3D-2D Registration    │
│ • C-Arm Angle Roadmapping (Bullseye/Progression)│ • Robotic Needle Arm Control    │
│ • Virtual Fluoroscopy Rehearsal (2D DRR)        │ • Active Surgical Actuation     │
│ • Multi-Evidence Laterality Gate (Interlock U1) │ • Intraoperative Guidance Bus   │
│ • Surgical Position SE(3) Lock (Interlock U2)   │ • OpenIGTLink Integration       │
│ • Auditable PDF & Planning Card Export (SHA-256)│                                 │
└─────────────────────────────────────────────────┴─────────────────────────────────┘
```

### 2.2 Clinician Decision Support (CDS) & Clinician Authority Model
- **Non-Actuating SaMD:** The software operates strictly in the preoperative domain. It does not interface with, actuate, or command physical surgical needles, robots, or electromechanical devices.
- **Clinician Sole Clinical Authority:** AcuCalyx™ Core is an informational decision support tool. Attending urologists and interventional radiologists retain 100% clinical and legal responsibility for target selection, corridor verification, patient positioning, and needle insertion.
- **Fail-Closed Principle:** If anatomical structures are ambiguous, opacification is absent, or no candidate trajectory satisfies safety buffers ($\ge 15\text{ mm}$ colon, $\ge 10\text{ mm}$ pleura), the software terminates in an explicit blocked state (`ERR_PLAN_NO_FEASIBLE_TRAJECTORY` / `REJECTED_NON_OPACIFIED`) rather than displaying a compromised or hazardous path.

---

## 3. Indications for Use & Target Patient Population

### 3.1 Proposed Indications for Use (IFU) Statement
> "AcuCalyx™ Core is a medical software application intended for use by trained urologists and interventional radiologists for preoperative computational planning and virtual fluoroscopic rehearsal in adult patients undergoing planned percutaneous nephrolithotomy (PCNL) for renal calculi.
> 
> The software processes standard diagnostic abdominopelvic CT scans to reconstruct 3D models of the kidney, collecting system, calculi, and adjacent anatomical risk structures; computes candidate needle puncture corridors based on parenchymal conservation and hazard clearance; calculates simulated C-arm gantry projection angles; and renders virtual fluoroscopic views for procedural rehearsal.
> 
> AcuCalyx™ Core is an adjunct informational planning tool; the attending physician maintains sole clinical authority for trajectory selection, procedural execution, and patient safety."

### 3.2 Target Population & Contraindications
- **Target Population:** Adult patients (age $\ge 18$) indicated for percutaneous renal access for nephrolithiasis.
- **Contraindications:**
  - Pediatric patients ($< 18$ years of age) — unvalidated anatomical scaling.
  - CT datasets with uncorrected gantry tilt ($> 0.0^\circ$) or non-uniform slice spacing.
  - CT scans with axial slice thickness $> 3.0\text{ mm}$ (insufficient forniceal resolution).
  - Emergency, acute trauma, or hemodynamically unstable patients.

---

## 4. Regulatory Strategy & Substantial Equivalence Analysis

### 4.1 Primary Regulatory Pathway: 510(k) Premarket Notification
The sponsor has evaluated the statutory classification under 21 CFR Part 860 and established that AcuCalyx™ Core falls under:
- **Regulation:** 21 CFR 892.2050 (Medical Image Processing and Communication System)
- **Product Codes:** `LLZ` (System, Image Processing, Radiological) & `QIH` (Automated Radiological Image Processing Software)
- **Device Class:** Class II

### 4.2 Predicate & Reference Device Landscape
All candidate devices have been audited against the FDA 510(k) database:

| Feature / Attribute | Subject Device: AcuCalyx™ Core | Primary Predicate: Materialise Mimics Medical (K183105) | Reference Device: Brainlab Elements (K191014) | Technological Reference: Cydar EV Maps (K160088 / K212442) |
| :--- | :--- | :--- | :--- | :--- |
| **Regulation & Product Code** | 21 CFR 892.2050 / `LLZ`, `QIH` | 21 CFR 892.2050 / `LLZ` | 21 CFR 892.2050 / `LLZ` | 21 CFR 892.1650 / `OWB` |
| **Intended Use** | Preoperative PCNL trajectory planning & virtual fluoroscopy rehearsal | Preoperative surgical planning, 3D segmentation & measurement | Preoperative surgical trajectory planning & hazard avoidance | Virtual fluoroscopy simulation & projection planning |
| **Input Modality** | Standard DICOM Axial CT | Standard DICOM CT / MR | Standard DICOM CT / MR | Standard DICOM CT / Angiography |
| **3D Anatomical Modeling** | Multi-organ deep learning (nnU-Net) & thresholding | Manual, semi-automated & deep learning segmentation | Automated atlas & deep learning segmentation | Automated vascular & skeletal segmentation |
| **Trajectory Calculation** | Multi-objective Pareto optimization ranking | User-defined points and distance calipers | Automated and user-guided risk corridor planning | Simulated projection path calculation |
| **Hazard Avoidance** | Automatic distance field buffers ($\ge 15\text{ mm}$ colon, $\ge 10\text{ mm}$ pleura) | Clinician visual inspection & caliper measurement | Pre-segmented risk organ exclusion zones | Anatomic overlay on fluoroscopic roadmap |
| **Projection Simulation** | Forward raymarched 2D DRR with C-arm angle calculation | Surface CAD export | Simulated DRR / X-ray views | Dynamic virtual fluoroscopy simulation |
| **Hardware Actuation** | None (Informational CDS Workbench) | None (Informational Software) | None (Informational Software) | None (Informational Software) |
| **Substantial Equivalence Nexus** | **Subject Device** | **Substantially Equivalent** | **Substantially Equivalent** | **Substantially Equivalent** |

---

## 5. Non-Clinical Benchtop & Analytical Performance Evidence

AcuCalyx™ Core has undergone extensive non-clinical analytical verification and benchtop metrological validation.

### 5.1 Milestone M15-V CT Urography Multi-Reader Benchmark (M15.1)
To establish ground truth anatomical accuracy without synthetic bias, a controlled feasibility cohort of real de-identified excretory-phase CT Urography (CTU) series was evaluated across 3 independent expert clinical readers (2 Attending Endourologists, 1 Interventional Radiologist):

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│             M15-V CT UROGRAPHY BENCHMARK RESULTS (VMTK DIJKSTRA REFERENCE)       │
├──────────────────────────────────┬─────────────────┬──────────────┬──────────────┤
│ Metrological Metric              │ Acceptance Gate │ Cohort Value │ Status       │
├──────────────────────────────────┼─────────────────┼──────────────┼──────────────┤
│ Calyx Detection Sensitivity      │ ≥ 85.0%         │ 95.8%        │ PASSED       │
│ Centerline Mean Absolute Error   │ ≤ 1.0 mm        │ 0.12 mm      │ PASSED       │
│ Symmetric Hausdorff (H95)        │ ≤ 2.0 mm        │ 0.88 mm      │ PASSED       │
│ Infundibular Caliper Error       │ ≤ 1.5 mm        │ 0.38 mm      │ PASSED       │
│ Opacification Fail-Closed Gating │ 100% Rejected   │ 100% (1/1)   │ PASSED       │
├──────────────────────────────────┴─────────────────┴──────────────┴──────────────┤
│ Overall Executive Gate Decision: GO_FEASIBILITY_PASSED (ISO 14971 / IEC 62304)   │
└──────────────────────────────────────────────────────────────────────────────────┘
```

**Key Findings:**
1. **Preserved Inter-Reader Disagreement:** Spatial ambiguity was not flattened by unweighted averaging. Areas of reader divergence ($0 < p < 1$) are preserved and disclosed to clinicians as spatial uncertainty volumes ($31.6\text{–}48.2\text{ mm}^3$), preventing false overconfidence.
2. **Deterministic Fail-Closed Opacification Check:** Non-opacified scans are automatically rejected with diagnostic errors before centerline extraction, eliminating blind puncture risks.

### 5.2 ASTM F2554-18 Physical Anthropomorphic Phantom Metrology (Milestone M3)
- **Standard:** ASTM F2554-18 *Standard Practice for Measurement of Positional Accuracy of Computer-Assisted Surgical Systems*.
- **Target Anatomy:** Radiopaque anthropomorphic renal silicone phantoms with target forniceal cups (2.5–3.5 mm diameter).
- **Expanded Uncertainty ($U_{95}$):** $U_{95} = 1.64\text{ mm}$ (Pre-specified acceptance budget $\le 2.0\text{ mm}$).
- **Conclusion:** Combined needle diameter (18G, 1.27 mm OD) plus system targeting error ($1.64\text{ mm}$) guarantees reliable entry into target forniceal cups.

---

## 6. Human Factors & Usability Engineering (IEC 62366-1)

AcuCalyx™ Core was developed in strict accordance with IEC 62366-1:2015+AMD1:2020 and the FDA Final Guidance *Applying Human Factors and Usability Engineering to Medical Devices* (August 3, 2026).

### 6.1 Critical Tasks & Runtime Safety Interlocks
The Use-Related Risk Analysis (URRA) identified six safety-critical tasks linked directly to software interlocks:
- **Interlock U1 (Laterality Consensus Gate):** Enforces 3-source agreement (DICOM metadata, 3D anatomical centroid, attending surgeon active verbal confirmation) before trajectory optimization unlocks (`HAZ-USE-01`).
- **Interlock U2 (Surgical Pose SE(3) Lock):** Verified coordinate transformation state machine tracking CT acquisition pose to operative table position (`PRONE` vs `SUPINE`), eliminating $180^\circ$ spatial transposition (`HAZ-USE-02`).
- **Interlock U3 (Visibility & Ambiguity Disclosure Gate):** Flags unenhanced or non-opacified calyces as `ESTIMATED_PRIOR` with spatial uncertainty cones and multi-reader ambiguity volumes ($0 < p < 1$), failing closed on non-opacified CTU scans (`HAZ-USE-04`).
- **Interlock U4 (Technician Transfer Card & Closed-Loop Readback):** Technician graphic gantry card combined with mandatory 4-step structured verbal readback protocol (`Target Calyx`, `Projection Mode`, `Gantry Angles`, `Confirmation`), preventing radiographer sign transposition errors (`HAZ-USE-05`).
- **Interlock U5 (Medial Boundary & Counter-Puncture Stop):** Case-derived needle advance stop alarm triggering within $5.0\text{ mm}$ of medial collecting system, mitigating hilar vascular and great vessel laceration (`HAZ-SURG-04`).
- **Interlock U6 (Stale Plan State Machine Lock):** Invalidates downstream trajectories and locks ReportLab PDF export upon any modification to patient pose, target calyx, or CT series until re-computed and re-approved (`HAZ-USE-03`).

### 6.2 Formative Usability Pilot Results ($N = 24$ Clinicians)
- **User Cohorts:** 6 Attending Endourologists, 6 Interventional Radiologists, 6 Endourology Fellows, 6 Urology Residents.
- **System Usability Scale (SUS):** $84.5 \pm 5.2$ (Grade A / Excellent).
- **Post-Study Cognitive Workload (Raw NASA-TLX):** $28.4 \pm 6.1$ / 100 (Low operator burden).
- **Critical Task Success Rate:** $98.6\%$.
- **Laterality Inversion Errors:** $0\%$ (100% prevented by Interlock U1).
- **Medial Counter-Puncture Errors:** $0\%$ (100% prevented by Interlock U5).

---

## 7. Premarket Cybersecurity & Data Integrity Posture (FD&C Act §524B)

In compliance with FD&C Act §524B and the FDA Final Guidance *Cybersecurity in Medical Devices: Quality System Considerations and Content of Premarket Submissions* (February 2026):
1. **Secure Product Development Framework (SPDF):** Architecture hardened against STRIDE threat taxonomy.
2. **Cryptographic Canonical Plan Fingerprint:** Every planning JSON payload is normalized and signed via canonical SHA-256 hash. Any byte-level modification in transit triggers `PLAN_HASH_MISMATCH` and halts execution.
3. **Machine-Readable SBOM (CycloneDX / SPDX):** Complete automated dependency inventory tracking all direct and transitive third-party packages. Zero unmitigated Known Exploited Vulnerabilities (KEVs) or Critical CVEs (CVSS $\ge 7.0$).
4. **DICOM PS 3.15 Annex E De-Identification:** Automated de-identification pipeline stripping direct PHI while preserving mandatory continuous LPS spatial coordinates.

---

## 8. Specific Questions for Agency Feedback (CDRH Review)

The sponsor respectfully requests written feedback and discussion during the Pre-Submission meeting on the following specific regulatory, clinical, and technological questions:

### Question 1: Regulatory Classification & 510(k) Eligibility
> **Question 1:** Does the Agency concur that AcuCalyx™ Core is appropriately classified under **21 CFR 892.2050 (Medical Image Processing and Communication System, Product Codes `LLZ` and `QIH`, Class II)** and eligible for review under the 510(k) premarket notification pathway?

*Sponsor Position:* AcuCalyx™ Core performs 3D anatomical reconstruction, computer-assisted trajectory ranking, and virtual fluoroscopic projection simulation from standard diagnostic CT scans. The software operates as an informational decision support tool in the preoperative domain and does not actuate or control medical hardware. This functionality is substantially equivalent to cleared Class II LLZ devices.

---

### Question 2: Predicate & Reference Device Landscape
> **Question 2:** Does the Agency agree that **Materialise Mimics Medical (K183105)** is an appropriate primary predicate device, and that **Brainlab Elements (K191014)** and **Cydar EV Maps (K160088 / K212442)** serve as valid reference devices demonstrating substantial equivalence?

*Sponsor Position:* Mimics Medical (K183105) establishes the foundational Class II indication for 3D segmentation, anatomical measurement, and virtual trajectory definition. Brainlab Elements (K191014) demonstrates anatomical hazard avoidance and volumetric corridor visualization. Cydar EV Maps (K160088) demonstrates virtual fluoroscopy simulation. Together, they establish substantial equivalence for all core technological characteristics.

---

### Question 3: Non-Clinical Benchtop Testing Sufficiency vs. Clinical Data Requirement
> **Question 3:** Considering the comprehensive non-clinical benchtop verification—specifically the **Milestone M15-V CT Urography Multi-Reader Benchmark** (sensitivity 95.8%, centerline MAE 0.12 mm, $H_{95} = 0.88\text{ mm}$) and the **ASTM F2554-18 physical anthropomorphic phantom metrology** ($U_{95} = 1.64\text{ mm}$)—does the Agency concur that non-clinical benchtop and human factors testing are sufficient to support 510(k) clearance without requiring human clinical trial data?

*Sponsor Position:* Per FDA guidance on Software as a Medical Device (SaMD) and radiological image processing tools, analytical verification against multi-reader ground truth combined with physical phantom metrology rigorously validates algorithmic accuracy and geometric reproducibility. Because AcuCalyx™ Core does not physically contact the patient or directly guide needles, benchtop and human factors validation provide robust assurance of safety and performance.

---

### Question 4: Investigational Device Risk Classification (21 CFR Part 812)
> **Question 4:** In the event that prospective clinical data is required by the Agency, does the Agency concur with the sponsor’s initial determination that a prospective comparative feasibility pilot (**Protocol ACU-PILOT-01, $N=30$**) constitutes a **Non-Significant Risk (NSR)** device investigation under 21 CFR 812.2(b)?

*Sponsor Position:* Under 21 CFR 812.3(m), AcuCalyx™ Core is not an implant, does not support or sustain human life, and does not present potential for serious risk because:
1. The software is completely non-invasive.
2. The software provides informational decision support prior to puncture.
3. Needle access is executed strictly under direct, continuous, real-time live fluoroscopic visualization according to standard-of-care clinical technique.
4. The attending physician retains absolute clinical authority to modify or abort the planned trajectory at any time.
Therefore, the study meets NSR criteria and may proceed under Institutional Review Board (IRB) approval in accordance with 21 CFR Part 50, Part 56, and abbreviated IDE requirements under 21 CFR 812.2(b).

---

### Question 5: Multi-Reader Consensus & Spatial Ambiguity Ground Truth Methodology
> **Question 5:** Does the Agency concur with the sponsor's multi-reader ground truth consensus methodology (STAPLE, spatial dispersion radii, and explicit preservation/disclosure of ambiguity volumes $0 < p < 1$) as an acceptable analytical validation framework for collecting-system segmentation and centerline extraction?

*Sponsor Position:* Inter-reader variability is inherent in radiological interpretation of the pelvicalyceal system. Rather than forcing artificial unweighted consensus, preserving and quantifying spatial ambiguity volumes directly informs clinical risk and aligns with FDA principles for AI/ML validation against multi-reader reference standards.

---

### Question 6: Human Factors Validation Protocol (IEC 62366-1)
> **Question 6:** Does the Agency concur that the proposed summative human factors validation protocol—evaluating 24 clinical participants across 4 user groups performing the 6 critical tasks under simulated simulated operating conditions with safety interlocks U1–U6—satisfies premarket human factors expectations under IEC 62366-1:2015+AMD1:2020?

*Sponsor Position:* The 24-participant evaluation exceeds the FDA-recommended minimum of 15 users per distinct user group for high-severity tasks, and tests all foreseeable use error mechanisms identified in the URRA.

---

### Question 7: Premarket Cybersecurity & Predetermined Change Control Plan (PCCP)
> **Question 7:** Does the Agency concur that the cybersecurity architecture (FD&C Act §524B, CycloneDX SBOM, SHA-256 canonical plan fingerprinting) and the scope of the Predetermined Change Control Plan (PCCP) covering retraining of the TotalSegmentator v2 model on expanded multi-center CTU cohorts meet current FDA premarket expectations?

*Sponsor Position:* The cybersecurity controls provide end-to-end data integrity and vulnerability monitoring. The PCCP establishes clear quantitative performance bounds (Dice $\ge 0.85$, Hausdorff $H_{95} \le 2.0\text{ mm}$) within which future model weight updates may be deployed postmarket without requiring supplemental 510(k) notifications.

---

## 9. Conclusion & Pre-Submission Meeting Request

AcuCalyx Medical Systems respectfully requests:
1. Formal written responses to Questions 1 through 7 within 70 to 75 calendar days of receipt.
2. A 1-hour teleconference Pre-Submission meeting with CDRH OHT8 review staff to discuss any outstanding feedback.
