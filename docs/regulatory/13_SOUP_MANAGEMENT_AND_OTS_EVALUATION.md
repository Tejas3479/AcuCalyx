# AcuCalyx™ Core SOUP Management & Off-The-Shelf (OTS) Software Evaluation
## Life-Cycle Management, Risk Evaluation & Safety Wrapping per IEC 62304 Clause 5.3.3 & Clause 8.1.2

**Document Identifier:** SOUP-ACU-REG-2026A  
**Software Release Baseline:** AcuCalyx Core v1.0.0-RC1  
**Governing Regulatory Baselines:**  
- IEC 62304:2006 + AMD1:2015 Clause 5.3.3 (SOUP Requirements) & Clause 8.1.2 (SOUP Configuration Management)  
- FDA Guidance: *Off-the-Shelf Software Use in Medical Devices*  
- FDA Premarket Cybersecurity Guidance (February 2026) / FD&C Act §524B  

---

## 1. SOUP Governance Policy & Risk Control Architecture

In medical device software engineering, Software of Unknown Provenance (SOUP) and Off-The-Shelf (OTS) components must be systematically identified, verified, and risk-managed to prevent unexpected failures in clinical operation.

AcuCalyx Core enforces a three-tier safety boundary around all SOUP dependencies:
1. **Safety Partitioning (IEC 62304 Clause 4.3):** Critical surgical math (continuous LPS trajectory calculations, hazard proximity scoring) is segregated from general-purpose UI rendering and web frameworks.
2. **Defensive Input/Output Sanitization:** All data entering and exiting SOUP libraries (such as pydicom or PyTorch) pass through strict type-enforced, range-bounded contracts (`SafetyBoundaryController`).
3. **Fail-Closed Anomaly Wrapping:** Any uncaught runtime exception thrown by a SOUP component results in a safe abort (`STATUS_ABORT_SOUP_EXCEPTION`), ensuring the device never presents unvalidated trajectory calculations to surgical personnel.

---

## 2. Comprehensive SOUP Inventory & Risk Evaluation Register

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                ACUCALYX™ CORE SOUP EVALUATION REGISTER                                 │
├──────────────┬─────────┬──────────────┬────────────┬─────────────┬───────────┬─────────────────────────┤
│ Component    │ Version │ Supplier /   │ License    │ Safety      │ Critical  │ Safety Mitigation /     │
│ Name         │ Baseline│ Maintainer   │ Type       │ Class       │ Function  │ Defensive Wrapping      │
├──────────────┼─────────┼──────────────┼────────────┼─────────────┼───────────┼─────────────────────────┤
│ Python       │ 3.13.7  │ Python S/W   │ PSF        │ Class B     │ Execution │ Standardized runtime    │
│ Runtime      │         │ Foundation   │ License    │             │ Platform  │ container, pinned build │
├──────────────┼─────────┼──────────────┼────────────┼─────────────┼───────────┼─────────────────────────┤
│ NumPy        │ 2.1.2   │ NumPy Core   │ BSD 3-Cl.  │ Class C     │ Coordinate│ Vector dimension checks,│
│              │         │ Developers   │            │             │ Math & SE3│ NaN/Inf traps on inputs │
├──────────────┼─────────┼──────────────┼────────────┼─────────────┼───────────┼─────────────────────────┤
│ PyTorch      │ 2.5.1   │ Linux Fdn /  │ Modified   │ Class B     │ AI Neural │ Deterministic inference,│
│              │         │ PyTorch Team │ BSD        │             │ Ingestion │ weights SHA-256 verify  │
├──────────────┼─────────┼──────────────┼────────────┼─────────────┼───────────┼─────────────────────────┤
│ SimpleITK    │ 2.4.0   │ ITK Consort. │ Apache 2.0 │ Class B     │ Volume Res│ Resampling orientation  │
│              │         │              │            │             │ ampling   │ check, gantry zero-tilt │
├──────────────┼─────────┼──────────────┼────────────┼─────────────┼───────────┼─────────────────────────┤
│ pydicom      │ 3.0.1   │ pydicom team │ MIT        │ Class B     │ DICOM I/O │ VR length guard, tag    │
│              │         │              │            │             │ Parser    │ injection sanitization  │
├──────────────┼─────────┼──────────────┼────────────┼─────────────┼───────────┼─────────────────────────┤
│ FastAPI      │ 0.115.0 │ Tiangolo /   │ MIT        │ Class A     │ REST API  │ Strict Pydantic models, │
│              │         │ Community    │            │             │ Transport │ TLS 1.3, RBAC auth token│
├──────────────┼─────────┼──────────────┼────────────┼─────────────┼───────────┼─────────────────────────┤
│ TotalSeg-    │ 2.2.0   │ Univ Hospital│ Apache 2.0 │ Class B     │ Organ     │ Volume plausibility &   │
│ mentator     │         │ Basel        │            │             │ Masking   │ topology runtime guards │
├──────────────┼─────────┼──────────────┼────────────┼─────────────┼───────────┼─────────────────────────┤
│ ReportLab    │ 4.2.5   │ ReportLab    │ BSD        │ Class A     │ PDF Gen-  │ Read-only sterile card, │
│              │         │ Inc.         │            │             │ erator    │ SHA-256 fingerprinting  │
└──────────────┴─────────┴──────────────┴────────────┴─────────────┴───────────┴─────────────────────────┘
```

---

## 3. Vulnerability Monitoring & Lifecycle Change Control

### 3.1 Automated SBOM Tracking (CycloneDX v1.5)
The complete dependency graph of all SOUP libraries is exported as a machine-readable CycloneDX v1.5 Software Bill of Materials (`sbom.json`). Every package name, purl identifier, exact version hash, and license string is compiled into the SBOM.

### 3.2 Continuous Vulnerability Auditing (CISA KEV & NVD)
The automated cybersecurity audit engine (`cisa_kev_vulnerability_auditor`) monitors the SOUP baseline against:
1. **CISA Known Exploited Vulnerabilities (KEV) Catalog:** Mandatory zero-tolerance policy for unmitigated KEV CVEs.
2. **National Vulnerability Database (NVD):** Any CVE with CVSS v3.1 score $\ge 7.0$ (High/Critical) triggers a formal Security Risk Assessment under ISO 14971.

### 3.3 SOUP Upgrade & Regression Testing Policy
No SOUP dependency may be updated in the production baseline without:
1. Documented engineering rationale and release note review.
2. Full automated regression test execution across the entire test baseline.
3. Verification that cryptographic hashes of mathematical outputs remain identical.
