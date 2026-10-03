# AcuCalyx™ Decision Gate M5.5: Clinical Investigational Readiness & FDA Pre-Sub Plan

**Document ID:** CLIN-GATE-M55-001  
**Version:** 1.0 (Frozen)  
**Governing Regulations:** ISO 14155:2026 / 21 CFR Part 812 / FDA Q-Submission Guidance  
**Status:** APPROVED & FROZEN  

---

## 1. Executive Summary & Purpose

Decision Gate M5.5 establishes the formal freeze of clinical investigational readiness, the regulatory Pre-Submission (Q-Sub) protocol, the investigational risk determination (SR vs. NSR) under 21 CFR Part 812, and the site-specific calibration gating requirements before initiating the prospective clinical feasibility pilot (Milestone M6A).

This gate enforces two critical regulatory principles:
1. **No Speculative Clinical Trial Commitments:** A large multi-center pivotal trial is not initiated until formal FDA Q-Sub feedback confirms premarket clinical data requirements and pilot feasibility data defines true operational variance.
2. **Formal IRB Risk Adjudication:** Non-Significant Risk (NSR) status is not unilaterally declared by the sponsor; it is formally justified and submitted to reviewing Institutional Review Boards (IRBs) with a contingency plan for a formal Investigational Device Exemption (IDE) under 21 CFR Part 812.

---

## 2. FDA Pre-Submission (Q-Submission) Protocol

Prior to first human patient enrollment, AcuCalyx will submit a formal Pre-Submission (Q-Sub) dossier to CDRH / Office of Health Technology 8 (OHT8: Radiological Health).

### 2.1 Formal Q-Sub Questions for CDRH Review

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        ACUCALYX™ CDRH Q-SUBMISSION QUESTION MATRIX                     │
├────┬─────────────────────────────┬─────────────────────────────────────────────────────┤
│ #  │ Regulatory Dimension        │ Specific Question for the Agency                    │
├────┼─────────────────────────────┼─────────────────────────────────────────────────────┤
│ Q1 │ Classification & Regulation │ Does the Agency concur that AcuCalyx™ Core is       │
│    │                             │ appropriately classified under 21 CFR 892.2050      │
│    │                             │ (Product Code LLZ, Class II, 510(k))?               │
├────┼─────────────────────────────┼─────────────────────────────────────────────────────┤
│ Q2 │ Substantial Equivalence     │ Does the Agency agree that Materialise Mimics       │
│    │                             │ Medical (K183105) and Brainlab Elements (K191014)   │
│    │                             │ serve as valid predicate and reference devices?     │
├────┼─────────────────────────────┼─────────────────────────────────────────────────────┤
│ Q3 │ Clinical Data Requirement   │ In light of the comprehensive benchtop metrology    │
│    │                             │ (ASTM F2554 U95 = 1.64 mm) and IEC 62366-1 human    │
│    │                             │ factors validation, does the Agency require clinical│
│    │                             │ data in a 510(k) submission for this intended use?  │
├────┼─────────────────────────────┼─────────────────────────────────────────────────────┤
│ Q4 │ Study Risk Determination    │ Does the Agency concur with the sponsor’s initial   │
│    │                             │ determination that an adjunct informational PCNL    │
│    │                             │ planning study constitutes a Non-Significant Risk   │
│    │                             │ (NSR) investigation under 21 CFR 812.2(b)?          │
├────┼─────────────────────────────┼─────────────────────────────────────────────────────┤
│ Q5 │ Feasibility Study Scope     │ Does the Agency concur that a 30-patient prospective│
│    │                             │ comparative feasibility study provides adequate     │
│    │                             │ human operational data if clinical data is required?│
├────┼─────────────────────────────┼─────────────────────────────────────────────────────┤
│ Q6 │ Primary Endpoints           │ Are fluoroscopy access time and <=2-pass puncture   │
│    │                             │ success viewed as clinically meaningful performance  │
│    │                             │ endpoints for PCNL access planning?                 │
├────┼─────────────────────────────┼─────────────────────────────────────────────────────┤
│ Q7 │ Control Arm Design          │ Does the Agency concur with standardizing the       │
│    │                             │ control arm on biplanar fluoroscopic guidance?      │
├────┼─────────────────────────────┼─────────────────────────────────────────────────────┤
│ Q8 │ AI/ML Documentation         │ Does the ISO/TS 24971-2:2026 model risk management  │
│    │                             │ documentation satisfy FDA premarket expectations?   │
├────┼─────────────────────────────┼─────────────────────────────────────────────────────┤
│ Q9 │ Cybersecurity Architecture  │ Does the FD&C Act §524B SPDF, machine-readable SBOM │
│    │                             │ (CycloneDX), and canonical plan fingerprinting      │
│    │                             │ meet the February 2026 Premarket Cyber Guidance?    │
├────┼─────────────────────────────┼─────────────────────────────────────────────────────┤
│ Q10│ Software Submission Tier    │ Does the Agency concur that the software lifecycle  │
│    │                             │ documentation satisfies the Enhanced Documentation  │
│    │                             │ level per the June 2023 Software Guidance?          │
└────┴─────────────────────────────┴─────────────────────────────────────────────────────┘
```

---

## 3. Investigational Device Risk Determination (21 CFR Part 812)

### 3.1 Regulatory Analysis: Significant Risk (SR) vs. Non-Significant Risk (NSR)
Under 21 CFR 812.3(m), a **Significant Risk (SR) Device** is defined as an investigational device that:
1. Is intended as an implant and presents a potential for serious risk to the health, safety, or welfare of a subject;
2. Is purported or represented to be for a use in supporting or sustaining human life and presents a potential for serious risk;
3. Is for a use of substantial importance in diagnosing, curing, mitigating, or treating disease, or otherwise preventing impairment of human health and presents a potential for serious risk; or
4. Otherwise presents a potential for serious risk to the health, safety, or welfare of a subject.

### 3.2 Clinical Decision Support (CDS) Regulatory Context
Per the FDA Final Guidance (*Clinical Decision Support Software*, January 2026), software that analyzes medical images (CT scans) to generate patient-specific anatomical models and trajectories is **not** exempt from medical device regulation under FD&C Act §520(o)(1)(E). AcuCalyx is regulated medical device software.

However, in determining clinical investigational risk under 21 CFR Part 812:
- **Non-Invasive:** AcuCalyx software never contacts the patient, emits radiation, or delivers energy.
- **Informational CDS Boundary:** AcuCalyx outputs candidate trajectories and simulated C-arm angles prior to puncture.
- **Independent Live Confirmation:** Puncture is executed strictly under direct, continuous, live intraoperative fluoroscopy. The attending urologist must independently confirm the needle path and possesses absolute clinical authority to adjust or abandon the trajectory.
- **Fail-Closed Architecture:** If imaging is ambiguous, the system enforces "No Plan" rather than an unsafe suggestion.

### 3.3 IRB & FDA Determination Protocol

```
┌────────────────────────────────────────────────────────────────────────┐
│                   INVESTIGATIONAL RISK DECISION WORKFLOW               │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│   Step 1: Sponsor Risk Justification Report                            │
│           • Compiles pre-clinical benchtop accuracy (U95 = 1.64 mm).   │
│           • Documents procedural safety boundaries & live fluoroscopy. │
│           • Concludes initial NSR recommendation under 21 CFR 812.2(b).│
│                                                                        │
│   Step 2: Submission to Central & Institutional IRBs                   │
│           • IRB reviews CIP, IB, and NSR Justification.                │
│                                                                        │
│   Step 3: IRB Adjudication Gate                                        │
│           ├── If IRB Agrees (NSR):                                     │
│           │   • Study proceeds under Abbreviated IDE (21 CFR 812.2b).  │
│           │   • Mandatory IRB approval + Informed Consent (Part 50).   │
│           │   • No formal FDA IDE application required.                │
│           │                                                            │
│           └── If IRB Disagrees (SR):                                   │
│               • Sponsor notifies FDA CDRH within 5 business days.      │
│               • Formal IDE Application compiled per 21 CFR 812.20.     │
│               • 30-day statutory FDA review; clinical hold until       │
│                 formal FDA approval letter received.                   │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Site-Specific C-Arm Calibration & Initiation Gate

Before any investigational center enrolls a patient, it must satisfy the **Site Initiation Gate**:

1. **C-Arm Profiling:** The site's specific C-arm make, model, detector geometry (flat panel vs. image intensifier), and angular encoders are calibrated and registered in AcuCalyx.
2. **Anthropomorphic Phantom Dry-Run:**
   - Participating urologists must perform 3 simulated puncture passes on the validated M3 anthropomorphic phantom under the site's C-arm.
   - Puncture accuracy must achieve:
     $$\Delta \text{Angle} \le 2.0^\circ, \quad \Delta \text{Position} \le 2.0\text{ mm}$$
3. **Investigator Credentialing:**
   - Surgeons must be board-certified urologists with $\ge 50$ lifetime PCNL procedures.
   - Completion of formal training on AcuCalyx cockpit controls, Interlock U1 (Laterality), Interlock U2 (Surgical Position), Interlock U5 (Depth Alarm), and the 4-step C-arm verbal readback protocol.

---

## 5. Decision Gate M5.5 Sign-Off

| Reviewing Authority | Name & Title | Determination | Date |
|---|---|---|---|
| Regulatory Affairs Director | Dr. S. Vance, RAC | **APPROVED & LOCKED** | 2026-09-30 |
| Principal Clinical Investigator | Dr. K. Patel, MD (Urology) | **APPROVED & LOCKED** | 2026-09-30 |
| Lead Biostatistician | Dr. A. Moreau, PhD | **APPROVED & LOCKED** | 2026-09-30 |
| Quality Assurance Director | M. Lindqvist, CQE | **APPROVED & LOCKED** | 2026-09-30 |
