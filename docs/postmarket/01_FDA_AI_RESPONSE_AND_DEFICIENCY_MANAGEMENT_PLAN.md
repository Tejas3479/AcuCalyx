# AcuCalyx™ Core FDA Additional Information (FDA-AI) Request & Deficiency Management SOP
## Standard Operating Procedure for Premarket Review Tracking, 180-Day Hold Management & eSTAR Version Lock

**Document Identifier:** SOP-ACU-FDA-AI-2026A  
**Lifecycle Stage:** Milestone M7.5 (FDA Review Monitoring & Deficiency Resolution)  
**Governing Regulatory Baselines:**  
- FDA Guidance: *FDA and Industry Actions on Premarket Notification (510(k)) Submissions: Effect on Review Timelines*  
- FDA Guidance: *The De Novo Classification Process (Evaluation of Automatic Class III Designation)*  
- FDA CDRH eSTAR Program Policy (2026 Baseline)  

---

## 1. Purpose & Scope

This Standard Operating Procedure (SOP) governs the active regulatory management of AcuCalyx™ Core during formal CDRH premarket review following submission through the Customer Collaboration Portal (CCP). It establishes protocols for monitoring MDUFA V review timelines across both 510(k) and De Novo pathways, managing statutory 180-calendar-day hold clocks upon receipt of formal Additional Information (FDA-AI) request letters, and maintaining the mandatory eSTAR version-lock baseline.

---

## 2. Review Pathways & MDUFA V Review Timelines

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        MDUFA V PREMARKET REVIEW TIMELINE TRACKS                        │
├───────────────────────────────────┬────────────────────────────────────────────────────┤
│ TRACK M7.5-A: 510(k) REVIEW       │ TRACK M7.5-B: DE NOVO REVIEW                       │
├───────────────────────────────────┼────────────────────────────────────────────────────┤
│ • Day 1–15: eSTAR Technical Screen│ • Day 1–15: Preliminary Acceptance & Screening     │
│ • Day 60: Substantive Interaction │ • Substantive Review (Target: 150 FDA Days)        │
│   (SI) Goal (Interactive / AI)    │ • Special Controls & Classification Negotiations   │
│ • Day 90: Final FDA Decision Goal │ • Formal FDA-AI Request Management (180-Day Clock) │
│ • 180-Day Statutory Hold Clock    │ • 180-Day Statutory Hold Clock                     │
└───────────────────────────────────┴────────────────────────────────────────────────────┘
```

---

## 3. FDA-AI Request Intake & Statutory 180-Day Hold Management

### 3.1 Statutory 180-Day Hold Clock Rules
1. **Clock Pause:** When CDRH issues a formal Additional Information (FDA-AI) request letter, the official FDA review clock stops immediately, and the submission enters `"HOLD"` status.
2. **Statutory Time Limit:** The applicant has a strict statutory maximum of **180 calendar days** from the date of the FDA-AI letter to submit a complete response.
3. **No Extension Policy:** By statutory law, FDA review divisions cannot grant extensions beyond 180 calendar days. Failure to submit a complete response on or before Day 180 results in automatic withdrawal of the submission (`WITHDRAWN`).
4. **Internal Milestone Escalation:**
   - **Day 30:** Deficiency Resolution Matrix (DRM) completed; engineering work orders assigned.
   - **Day 90:** All supplemental testing and artifact revisions complete.
   - **Day 120:** Regulatory Affairs and Legal review complete; draft response compiled.
   - **Day 150:** Executive Quality Board formal sign-off; response submitted via CDRH portal. (Leaves a 30-day contingency buffer).

---

## 4. eSTAR Response Version-Lock Protocol

> [!IMPORTANT]
> **Mandatory eSTAR Version-Lock Requirement:**  
> In accordance with FDA eSTAR program policy, once an initial premarket submission has been formally acknowledged by CDRH, the submission is grandfathered to that specific eSTAR version (AcuCalyx Core Baseline: non-IVD eSTAR v7.1).  
> 
> When preparing an FDA-AI response or resolving technical screening inquiries, **the submission team MUST NOT upgrade to a newer eSTAR version released after the original submission date.** All deficiency responses, amended exhibits, and supplemental verification files must be loaded directly into the original eSTAR file baseline archived in `original_submission_estar_baseline/`.

---

## 5. Deficiency Resolution Matrix (DRM) Architecture

All inquiries from CDRH are transcribed into the **Deficiency Resolution Matrix (DRM)** and categorized into four standardized response workflows:

| Category | Deficiency Focus | Responsible Function | Required Deliverable |
|---|---|---|---|
| **Category A** | Labeling, IFU, Contraindications, Operating Envelope | Regulatory Affairs & Medical Director | Redline revisions to `09_OPERATORS_MANUAL_AND_LABELING.md`; updated splash metadata. |
| **Category B** | Software V&V, Traceability, Cybersecurity | Software Architecture & Cybersecurity Lead | Supplemental unit/property tests, revised RTM, updated CycloneDX SBOM / KEV justification. |
| **Category C** | Benchtop Metrology, C-Arm Kinematics, DRR | Metrology & Algorithm Team | Extended ASTM F2554 phantom metrology cuts, C-arm perturbation sensitivity analysis. |
| **Category D** | Clinical Feasibility, Subgroup Analysis, Adverse Events | Clinical Affairs & Biostatistics | Stratified subgroup analysis of ACU-PILOT-01 ($N = 30$) by BMI, calyx location, stone burden. |

### 5.1 Formal Response Sign-Off Criteria
An FDA-AI response package may only be submitted when:
1. 100% of numbered FDA deficiency items have an unambiguous, evidence-backed response.
2. Every modified software requirement or code change links to an automated regression test with 100% pass status.
3. The lead Regulatory Affairs specialist and Chief Medical Officer execute the formal response certification.
