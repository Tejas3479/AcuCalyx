# AcuCalyx™ Core Postmarket Surveillance & Real-World Performance Program
## Surveillance Program, Complaint Trending & Safety Review SOP per ISO 13485:2016 Clause 8.2

**Document Identifier:** SOP-ACU-PMS-2026A  
**Regulatory Baseline:** ISO 13485:2016 Clause 8.2.1 (Feedback) & FDA QMSR (21 CFR Part 820)  
**Target Milestone:** Milestone M8 (Commercial Operations)  

---

## 1. Scope & U.S.-First Regulatory Alignment

This procedure establishes the **Postmarket Surveillance (PMS) and Real-World Performance Program** for AcuCalyx™ Core.

> [!NOTE]
> **U.S.-First Roadmap vs. European Requirements:**  
> In accordance with U.S. FDA regulatory strategy, this program fulfills statutory postmarket monitoring obligations under FDA QMSR / ISO 13485:2016 Clause 8.2.1. FDA Section 522 postmarket surveillance studies apply only if specifically ordered by the Agency. European Medical Device Regulation (EU MDR 2017/745) requirements—such as annual Periodic Safety Update Reports (PSUR) and formal Post-Market Clinical Follow-up (PMCF) plans—are maintained as a separate international expansion branch.

---

## 2. Telemetry Scope & Clinical Sensor Boundaries (Core vs. Nav)

AcuCalyx Core is a preoperative planning and virtual fluoroscopy rehearsal software system. It does **NOT** contain intraoperative optical, electromagnetic, or robotic needle tracking hardware.

> [!IMPORTANT]
> **Core Telemetry Operating Boundary:**  
> Automated real-time measurement of "planned vs. executed needle trajectory deviation" is strictly **excluded** from Milestone M8 Core telemetry. Automated needle tracking discrepancy analysis is reserved for Milestone M9 (AcuCalyx Nav).  
> 
> Under Milestone M8, postmarket telemetry is strictly restricted to software operational metrics and manually entered clinical outcomes.

### 2.1 Permitted Core Postmarket Telemetry Elements
1. **Software Configuration Data:** Application version, build identifier, TotalSegmentator v2 model weights hash, C-arm profile ID.
2. **Case Pipeline Performance:** Pipeline execution success/failure, computation runtimes, segmentation QC observability passes/fails.
3. **Clinician Cockpit Interlocks:** Interlock activation counts (U1 laterality confirmations, U2 position transforms, U3 unenhanced calyx gates, U5 medial counter-puncture warnings).
4. **Voluntary Clinical Outcomes (Manually Entered):** Puncture success (Yes/No), number of attempts, total fluoroscopy time, postoperative complications.

---

## 3. Data Governance, Privacy & Pseudonymization Protocol

All postmarket data transmitted to the manufacturer's central analytics repository must satisfy HIPAA de-identification standards (45 CFR §164.514) and DICOM PS 3.15:
- **No Direct Identifiers:** Zero transmission of patient names, dates of birth, medical record numbers (MRNs), or hospital accession numbers.
- **Pseudonymous Case ID:** Generated via irreversible HMAC-SHA256 hashing using the hospital site's private salt (`CASE-PMS-xxxxxxxx`).
- **Data Minimization:** Only fields necessary for quality trending and safety monitoring are collected.
- **Encryption:** All telemetry in transit uses TLS 1.3; data at rest uses AES-256 encryption.

---

## 4. Complaint Trending & Periodic Internal Safety Reviews

### 4.1 Automated Signal Detection & Statistical Trending
The quality system runs monthly statistical process control (SPC) algorithms on incoming complaint data:
- Calculation of complaint rates per 1,000 processed cases.
- Automatic anomaly spike detection (Poisson probability $p < 0.01$).

### 4.2 Quarterly Executive Safety Review
The Chief Medical Officer and Quality Review Board convene quarterly to evaluate:
1. Complaint trending against pre-specified acceptance thresholds.
2. Review of any MDR-reportable incidents or field corrections.
3. Comparison of real-world complication rates against the ISO 14971 Benefit-Risk Analysis (BRA).
