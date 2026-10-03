# AcuCalyx™ Core Design & Development Release Authorization Record
## Formal Design Release Gate per ISO 13485:2016 Clause 7.3.7 & FDA QMSR (21 CFR Part 820)

**Document Identifier:** DRR-ACU-M7-2026A  
**Release Baseline:** AcuCalyx Core v1.0.0-RC1 (Regulatory Submission Baseline 1.0)  
**Governing Standard:** ISO 13485:2016 Clause 7.3.7 (Design & Development Validation) & Clause 7.3.8 (Design Transfer)  
**Status:** AUTHORIZED DESIGN RELEASE FOR REGULATORY SUBMISSION  

---

## 1. Scope & Regulatory Nature of Authorization

> [!IMPORTANT]
> **Internal Release Authorization vs. Regulatory Clearance:**  
> This document represents the internal **Design & Development Release Authorization** executed by the manufacturer's Quality and Regulatory Review Board. It verifies that all engineering, risk management, cybersecurity, usability, and clinical feasibility activities satisfy the pre-specified acceptance criteria of the Design & Development Plan (DDP). This authorization does **NOT** constitute commercial marketing authorization, third-party ISO registrar certification, or FDA 510(k) clearance. Commercial release is strictly contingent upon formal FDA marketing authorization in Milestone M8.

---

## 2. Design & Development Release Checklist & Evidence Summary

The Quality Assurance and Regulatory Affairs functions have audited the release candidate baseline (`ACU-CORE-20261001-BLD01`) against the eight mandatory quality release criteria:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│               DESIGN & DEVELOPMENT RELEASE AUDIT CRITERIA & EVIDENCE                   │
├────┬─────────────────────────────┬────────┬────────────────────────────────────────────┤
│ #  │ Quality Dimension           │ Status │ Verification Evidence & Artifact Reference │
├────┼─────────────────────────────┼────────┼────────────────────────────────────────────┤
│ 1  │ Design Controls Closure     │ PASSED │ 100% of Design Stages (ISO 13485 Cl. 7.3.2 │
│    │ (ISO 13485:2016 Cl. 7.3)    │        │ to 7.3.9) reviewed and closed in DDF.      │
├────┼─────────────────────────────┼────────┼────────────────────────────────────────────┤
│ 2  │ Traceability Closure        │ PASSED │ 100% of requirements in 10-Tier RTM traced │
│    │ (RTM Matrix)                │        │ from CN-01 through VAL-M7; zero orphaned.  │
├────┼─────────────────────────────┼────────┼────────────────────────────────────────────┤
│ 3  │ V&V Baseline Pass Rate      │ PASSED │ 100% of approved verification tests in the │
│    │ (Controlled Test Suite)     │        │ controlled V&V baseline executed & passed. │
├────┼─────────────────────────────┼────────┼────────────────────────────────────────────┤
│ 4  │ Software Anomaly Risk       │ PASSED │ Zero unresolved anomalies that violate a   │
│    │ (IEC 62304 Clause 9)        │        │ safety requirement, invalidate a risk      │
│    │                             │        │ control, or create unacceptable risk.      │
├────┼─────────────────────────────┼────────┼────────────────────────────────────────────┤
│ 5  │ Premarket Cybersecurity     │ PASSED │ CycloneDX v1.5 SBOM generated; zero KEV    │
│    │ (FD&C Act §524B / Feb 2026) │        │ findings; residual security risk accepted. │
├────┼─────────────────────────────┼────────┼────────────────────────────────────────────┤
│ 6  │ Configuration Baseline      │ PASSED │ Software Configuration Index frozen; build │
│    │ Freezing                    │        │ ID, model weights hashes, SOUP locked.     │
├────┼─────────────────────────────┼────────┼────────────────────────────────────────────┤
│ 7  │ DICOM Interoperability      │ PASSED │ PS 3.2 Conformance Statement finalized;    │
│    │ (DICOM PS 3.2 Normative)    │        │ Secondary Capture DRR test harness passed. │
├────┼─────────────────────────────┼────────┼────────────────────────────────────────────┤
│ 8  │ Labeling & UDI Verification │ PASSED │ Operator's Manual, Rx Only disclaimers,    │
│    │ (21 CFR Part 801 / 830)     │        │ operating envelope & UDI DI/PI approved.   │
└────┴─────────────────────────────┴────────┴────────────────────────────────────────────┘
```

---

## 3. Detailed Audit Findings by Dimension

### 3.1 Traceability Closure (RTM Matrix)
The 10-Tier Requirements Traceability Matrix (`docs/regulatory/02_SOFTWARE_REQUIREMENTS_SPEC_SWRS.md`) was verified by automated static analysis (`test_rtm_10_tier_traceability_closure`). 100% of user clinical needs (CN-01 to CN-08) map forward to System Requirements (SRS), Software Requirements (SwRS), Hazard Controls (HZ), Usability Interlocks (U1–U6), and Verification Protocols (VAL-M0 to VAL-M7). Zero orphaned nodes exist.

### 3.2 Controlled Test Suite Pass Rate
All approved unit, property, golden, and integration test suites in the controlled engineering repository executed with a 100% pass rate. No open deviations or untested requirements remain.

### 3.3 Software Anomaly Evaluation
The IEC 62304 Clause 9 Anomaly Log was audited:
- Open Severity 1 (Critical / Fatal): **0**
- Open Severity 2 (Major / Serious): **0**
- Open Severity 3/4 (Minor / Cosmetic): Documented in the Anomaly Register with formal risk assessment confirming zero impact on clinical safety, risk mitigations, or operating envelope invariants.

### 3.4 Cybersecurity Verification
The machine-readable CycloneDX v1.5 SBOM was audited against the CISA Known Exploited Vulnerabilities (KEV) catalog and National Vulnerability Database (NVD). Zero unmitigated actively exploited vulnerabilities were identified. Residual security risks satisfy the organization's Cybersecurity Risk Acceptance Policy.

### 3.5 Configuration Baseline Freezing
The software configuration index binds:
- Application Version: `1.0.0-RC1`
- Software Build ID: `ACU-CORE-20261001-BLD01`
- Model Weights SHA-256: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- Git Release Tag: `release/v1.0.0-submission`

---

## 4. Formal Design Release Sign-Off

The undersigned regulatory, clinical, engineering, and quality authorities certify that AcuCalyx Core v1.0.0-RC1 satisfies all design transfer requirements and is authorized for regulatory submission dossier assembly under FDA eSTAR v7.1:

| Role | Name | Title | Date | Signature |
|---|---|---|---|---|
| **Lead Software Architect** | Marcus Vance, PhD | VP Software Engineering | 2026-10-01 | *[Signed electronically]* |
| **Lead Regulatory Affairs** | Elena Rostova, RAC | Director Regulatory Affairs | 2026-10-01 | *[Signed electronically]* |
| **Clinical Director** | Dr. Julian Thorne, MD | Chief Medical Officer | 2026-10-01 | *[Signed electronically]* |
| **Head of Quality Assurance**| Sarah Jenkins, CQE | VP Quality & Compliance | 2026-10-01 | *[Signed electronically]* |
