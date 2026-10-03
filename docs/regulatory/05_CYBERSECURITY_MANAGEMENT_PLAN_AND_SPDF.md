# AcuCalyx™ Premarket Cybersecurity Management Plan & SPDF

**Document ID:** SEC-ACU-001  
**Version:** 1.0 (Frozen)  
**Governing Authority:** FDA Final Guidance (February 2026) / FD&C Act §524B / AAMI TIR57  
**Quality System:** FDA QMSR (21 CFR Part 820) / ISO 13485:2016  
**Status:** APPROVED & FROZEN  

---

## 1. Executive Summary & Statutory Applicability

This Cybersecurity Management Plan establishes the Secure Product Development Framework (SPDF) and premarket cybersecurity controls for **AcuCalyx™ Core**.

Under the **Federal Food, Drug, and Cosmetic Act (FD&C Act) §524B** (*Ensuring Cybersecurity of Devices*) and the **FDA Final Guidance (February 2026)** (*Cybersecurity in Medical Devices: Quality System Considerations and Content of Premarket Submissions*), AcuCalyx qualifies as a **"cyber device"** because it:
1. Includes software validated, installed, or authorized by the sponsor into a device or system.
2. Has the ability to connect to the internet or local hospital networks (e.g. PACS, DICOM nodes, RIS).
3. Contains technological characteristics and software dependencies vulnerable to cybersecurity threats.

---

## 2. Deployment Architecture & Trust Boundaries

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          HOSPITAL ENTERPRISE NETWORK                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌────────────────────┐                   ┌────────────────────────────┐   │
│   │ Hospital PACS /    │   TLS 1.3 / DIMSE │ Hospital Radiology / OR    │   │
│   │ Image Archive Node │ ◄───────────────► │ Workstation Display        │   │
│   └─────────┬──────────┘   DICOMweb HTTPS  └─────────────┬──────────────┘   │
│             │                                            │                  │
│   ══════════╪════════════════════════════════════════════╪═══════════════   │
│             │            TRUST BOUNDARY                  │                  │
│             ▼                                            ▼                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                       ACUCALYX™ CORE APPLIANCE                      │   │
│   │                                                                     │   │
│   │   ┌─────────────────────────┐         ┌─────────────────────────┐   │   │
│   │   │ DICOM Ingestion Guard   │         │ Secure REST API Gateway │   │   │
│   │   │ (PS 3.15 PHI Scrubber)  │         │ (JWT / mTLS / RBAC)     │   │   │
│   │   └───────────┬─────────────┘         └────────────┬────────────┘   │   │
│   │               │                                    │                │   │
│   │               ▼                                    ▼                │   │
│   │   ┌─────────────────────────────────────────────────────────────┐   │   │
│   │   │            ISOLATED SAFETY COMPUTATIONAL CORE               │   │   │
│   │   │                                                             │   │   │
│   │   │   • Verified Anatomical Segmentation                        │   │   │
│   │   │   • Pareto Trajectory Optimizer                             │   │   │
│   │   │   • Canonical SHA-256 Plan Fingerprint Engine               │   │   │
│   │   └─────────────────────────────────────────────────────────────┘   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Trust Boundary Isolation:
1. **Network Interface:** All incoming traffic from PACS or OR clients must terminate at the authenticated API Gateway over TLS 1.3.
2. **Data Ingestion:** DICOM files are ingested through the `PHIGuard` boundary, which validates syntax, strips active executable scripts, and scrubs PHI per PS 3.15 Annex E.
3. **Execution Domain:** The computational safety kernel runs in a restricted memory space with zero outbound direct internet access.

---

## 3. STRIDE Threat Model & Mitigations

| Threat Category | Specific Threat Scenario | Potential Clinical / Security Harm | Implemented Cybersecurity Control | Verification Evidence |
|---|---|---|---|---|
| **Spoofing (S)** | Unauthorized workstation masquerades as surgeon terminal to approve a plan. | Plan approved without certified clinician oversight. | **SEC-01:** Mandatory cryptographic mutual TLS (mTLS) or signed JSON Web Tokens (JWT) with role-based claim `ATTENDING_SURGEON`. | Unit test `test_rbac_privilege_enforcement` |
| **Tampering (T)** | In-transit or memory manipulation alters needle skin entry or target coordinates. | Surgeon operates using altered, non-coaxial, or hazardous trajectory. | **SEC-02 (Anti-Tamper):** Canonical JSON serialization + SHA-256 plan fingerprinting. Any coordinate mutation invalidates the hash and locks execution. | Unit test `test_planned_trajectory_alteration_trap` |
| **Repudiation (R)** | User denies approving a hazardous or non-optimal trajectory corridor. | Absence of legal/clinical accountability for surgical decisions. | **SEC-03:** Append-only, cryptographically hashed audit log recording User ID, Timestamp, Plan Hash, and Action. | Automated audit log verification tests |
| **Information Disclosure (I)** | Unencrypted DICOM data or cached CT scans leak Protected Health Information (PHI). | HIPAA violation; patient privacy compromise. | **SEC-04:** DICOM PS 3.15 Annex E Basic Application Level Confidentiality Profile + deterministic HMAC pseudonymization. | Unit test `test_dicom_ps315_phi_deidentification` |
| **Denial of Service (D)** | Malformed DICOM injection (e.g. decompression bomb) crashes server during rehearsal. | Procedural delay in OR while patient is anesthetized. | **SEC-05:** Pre-ingestion memory limit checks ($\le 2\text{ GB}$), pixel uncompression bounds, and strict header validation. | Unit test `test_malformed_dicom_injection_rejection` |
| **Elevation of Privilege (E)** | Technician account attempts to modify safety clearance buffers or override alarms. | Removal of visceral organ safety buffers ($\ge 15\text{ mm}$ colon). | **SEC-06:** Role-Based Access Control (RBAC) enforced in safety core; clearance thresholds hardcoded as immutable constants. | Unit test `test_rbac_privilege_enforcement` |

---

## 4. Software Bill of Materials (SBOM) & CISA KEV Policy

In compliance with FD&C Act §524B(a)(1) and the NTIA Minimum Elements for Software Bill of Materials:

### 4.1 Required SBOM Baseline Elements
1. **Author / Supplier Name** (e.g. PyTorch Foundation, Insight Software Consortium)
2. **Component Name** (e.g. `torch`, `SimpleITK`, `pydicom`)
3. **Version String** (e.g. `2.2.2`, `2.3.1`)
4. **Unique Component Identifier** (Package URL / PURL)
5. **Cryptographic Hash** (SHA-256 of package distribution archive)
6. **Relationship Description** (Direct dependency vs Transitive dependency)
7. **License Identifier** (SPDX standardized license string, e.g. `BSD-3-Clause`)

### 4.2 Automated SBOM Generation Formats
AcuCalyx provides automated CLI and programmatic export of SBOM in two standard machine-readable formats:
- **CycloneDX JSON (v1.5 / v1.6)**
- **SPDX JSON (v2.3)**

### 4.3 Vulnerability Management & CISA KEV Monitoring
- **Automated Scanning:** Daily automated scan of SBOM components against:
  - **CISA Known Exploited Vulnerabilities (KEV) Catalog**
  - NIST National Vulnerability Database (NVD)
  - GitHub Advisory Database
- **Threshold Policy:**
  - Any CVE in the **CISA KEV Catalog** mandates emergency remediation within 14 business days.
  - Any CVE with CVSS base score $\ge 7.0$ (High / Critical) requires formal risk assessment under ISO 14971 within 30 business days.

---

## 5. Cryptographic Plan Integrity Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│               CANONICAL PLAN FINGERPRINTING & TAMPER TRAP              │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│   Plan Object Parameters                                               │
│   [Patient ID, Trajectory, Angles, Clearance, Depth]                   │
│                        │                                               │
│                        ▼                                               │
│   Canonical JSON Serialization                                         │
│   (Sorted keys, 4 decimal places for floats, ISO 8601 UTC)             │
│                        │                                               │
│                        ▼                                               │
│   SHA-256 Cryptographic Hash Engine                                    │
│   Fingerprint = SHA-256(Canonical_JSON_Bytes)                          │
│                        │                                               │
│                        ▼                                               │
│   [Runtime Integrity Check Gate]                                       │
│          ├── If Current_Hash == Expected_Hash ──► EXECUTION PERMITTED  │
│          └── If Current_Hash != Expected_Hash ──► PLAN_HASH_MISMATCH   │
│                                                   (EXECUTION LOCKED)   │
└────────────────────────────────────────────────────────────────────────┘
```

> [!CAUTION]
> **Zero-Tolerance Anti-Tamper Invariant:**  
> If an attacker or memory corruption alters any plan parameter (even by $0.01\text{ mm}$ or $0.1^\circ$), the calculated SHA-256 fingerprint will diverge completely. The system instantly halts display, sets plan status to `TAMPERED_LOCK`, logs a high-priority security event, and blocks virtual fluoroscopy generation.

---

## 6. Coordinated Vulnerability Disclosure (CVD) & Postmarket Plan

Under FD&C Act §524B(a)(2):
1. **Vulnerability Reporting Channel:** Dedicated security intake email (`security@acucalyx.health`) and published PGP key.
2. **Coordinated Response Timeline:** Acknowledgement within 48 hours; initial triage and risk assessment within 7 calendar days.
3. **Patch Distribution:** Cryptographically signed software update packages distributed to healthcare institutions with verifiable release notes and updated SBOM.
