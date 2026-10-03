# AcuCalyx™ Core Postmarket Surveillance, MDR & Lifecycle Management Plan
## Quality System Operational Readiness per 21 CFR Part 803, Part 806 & ISO 13485:2016 Clause 8

**Document Identifier:** PMS-ACU-PLAN-2026A  
**Target Operational Milestone:** Milestone M8 (Commercialization & Postmarket Operations)  
**Governing Regulatory Baselines:**  
- 21 CFR Part 803: *Medical Device Reporting (MDR)*  
- 21 CFR Part 806: *Medical Devices; Reports of Corrections and Removals*  
- ISO 13485:2016 Clause 8.2.1 (Feedback) & Clause 8.5 (Improvement)  
- FDA Postmarket Cybersecurity Guidance / FD&C Act §524B(b)(3)  

---

## 1. Postmarket Regulatory Readiness Scope

While Milestone M7 establishes design release authorization for premarket submission, the manufacturer must maintain complete organizational readiness to execute statutory postmarket responsibilities immediately upon commercial authorization in Milestone M8:

```
┌────────────────────────────────────────────────────────────────────────┐
│               ACUCALYX™ CORE POSTMARKET REGULATORY LIFECYCLE           │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│   COMMERCIAL DISTRIBUTION (M8)                                         │
│   ├── Clinical User Complaints & Inquiries                             │
│   ├── Electronic Medical Device Reporting (eMDR / 21 CFR Part 803)     │
│   ├── Health Hazard Evaluation & Recalls (21 CFR Part 806)             │
│   ├── Coordinated Vulnerability Disclosure (CVD / Security Reporting)  │
│   ├── Corrective & Preventive Action (CAPA / ISO 13485 Clause 8.5.2)   │
│   └── Software Maintenance & Secure Patch Distribution (§524B)         │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Medical Device Reporting Procedure (21 CFR Part 803)

### 2.1 Reportability Criteria
Any customer complaint or clinical event alleging that AcuCalyx Core may have caused or contributed to a death or serious injury, or has malfunctioned in a manner that would likely cause or contribute to a death or serious injury if the malfunction were to recur, must be evaluated for statutory reporting:
1. **Death or Serious Injury (30-Day Report):** Electronic Form FDA 3500A submitted via the CDRH eSubmitter / ESG portal within **30 calendar days** of becoming aware.
2. **5-Day Reportable Event:** Events requiring immediate remedial action to prevent an unreasonable risk of substantial harm to public health must be reported within **5 work days**.

### 2.2 Clinical Event Adjudication Flow
- **Intake:** Automated complaint intake logging via Quality Management System.
- **Triage:** Clinical Specialist and Safety Officer assess whether the event involved organ perforation (colon, spleen, vascular), pneumothorax, or severe bleeding.
- **Technical Investigation:** Engineering retrieves the cryptographic `ClinicalSourceRecord` and audits whether the plan was followed or if a software calculation error occurred.

---

## 3. Reports of Corrections & Removals (21 CFR Part 806)

### 3.1 Field Safety Corrective Actions (FSCA)
If a software anomaly is discovered post-release that creates a potential health hazard (e.g., coordinate transposition under rare DICOM orientation permutations):
1. **Health Hazard Evaluation (HHE):** Multi-disciplinary committee determines hazard severity (Class I, II, or III recall).
2. **FDA Notification:** Written report submitted to the FDA District Office within **10 working days** of initiating a correction or removal.
3. **Customer Safety Notice:** Urgent Medical Device Notification dispatched to all hospital risk managers and clinical users with clear containment instructions.

---

## 4. Postmarket Cybersecurity Lifecycle Management (§524B)

### 4.1 Coordinated Vulnerability Disclosure (CVD) Policy
- **Public Security Point of Contact:** `security@acucalyx.com`
- **PGP Encryption Key:** Published on the manufacturer's official trust center.
- **Response Timeline:** Receipt acknowledged within **48 hours**; initial risk assessment completed within **7 calendar days**; mitigation timeline provided within **30 days**.

### 4.2 Security Patching & Regular Software Updates
- **Critical / Actively Exploited CVEs:** Emergency security patch developed, validated, and deployed within **30 calendar days**.
- **Routine Maintenance:** Quarterly security patch releases incorporating updated SOUP libraries and updated CISA KEV scans.

---

## 5. Postmarket Surveillance & Real-World Performance Monitoring

The manufacturer will maintain an active Postmarket Clinical Follow-up (PMCF) registry across clinical deployment sites:
1. **Primary Endpoints Monitored:** Successful first-pass puncture rate, total access fluoroscopy time, and Clavien-Dindo complications.
2. **Feedback Loop:** Clinical performance signals are fed directly into the ISO 14971 Risk Management File during annual safety reviews.
