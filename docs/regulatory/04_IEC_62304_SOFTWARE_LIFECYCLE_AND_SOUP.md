# AcuCalyx™ IEC 62304 Software Lifecycle & SOUP Management Plan

**Document ID:** SWLP-ACU-001  
**Version:** 1.0 (Frozen)  
**Governing Standard:** IEC 62304:2006 + AMD 1:2015  
**Quality System:** FDA QMSR (21 CFR Part 820) / ISO 13485:2016 Clause 7.3  
**Status:** APPROVED & FROZEN  

---

## 1. Software Development Lifecycle Overview

This document defines the software development and maintenance processes for **AcuCalyx™ Core** in strict adherence to **IEC 62304:2006 + AMD 1:2015**.

The lifecycle comprises:
1. Software Development Planning (Clause 5.1)
2. Software Requirements Analysis (Clause 5.2)
3. Architectural Design & Safety Partitioning (Clause 5.3)
4. Software Detailed Design (Clause 5.4)
5. Software Unit Implementation & Verification (Clause 5.5)
6. Software Integration & System Testing (Clauses 5.6 & 5.7)
7. Software Release (Clause 5.8)
8. Software Maintenance (Clause 6)
9. Software Risk Management (Clause 7)
10. Software Configuration Management (Clause 8)
11. Software Problem Resolution / Anomaly Management (Clause 9)

---

## 2. Software Safety Classification (IEC 62304 Clause 4.3)

### 2.1 Hazard Analysis & Classification Justification
- **Unmitigated Risk Evaluation:** An undetected software fault in trajectory calculation or visceral hazard clearance could result in colonic transfixion (peritonitis / septic shock) or medial great vessel laceration (exsanguinating hemorrhage), both carrying a potential outcome of death or catastrophic injury (**Severity S4 / S5**).
- **Classification Determination:** In accordance with IEC 62304 Clause 4.3(a), the software system is assigned **Software Safety Class C** at the system level.

### 2.2 Safety Partitioning (Clause 5.3.5)
To prevent non-safety presentation code from compromising safety functions, AcuCalyx implements strict architectural partitioning:

| Architectural Tier | Safety Class | Included Components | Isolation & Verification Mechanism |
|---|---|---|---|
| **Safety-Relevant Computational Core** | **Class C** | DICOM Ingestion Quality Gate, Coordinate Engine, Segmentation Backends, Hazard Distance Fields, Calyx Target Engine, Pareto Optimizer, C-Arm Kinematics, DRR Raymarcher, Plan Integrity Engine. | Isolated memory domain; deterministic execution; automated unit tests with 100% statement and branch coverage; formal verification. |
| **Safety-Related Presentation & Interlocks** | **Class C / B** | Interlocks U1–U6, C-Arm Closed-Loop Verbal Script Generator, Depth Boundary Visual/Auditory Alarms, Multimodal Laterality Badges. | Enforces fail-closed locks on safety core; strict data contract prevents unapproved display. |
| **Non-Safety Presentation Infrastructure** | **Class A** | Three.js WebGL OrbitControls, cosmetic shading and lighting, 2D MPR window/level slider interpolation, UI sidebar layout and responsive DOM elements. | Strictly downstream of safety boundary; zero write-access to planning state; failure of Class A component cannot corrupt or alter calculated coordinates. |

---

## 3. SOUP (Software of Unknown Provenance) Management (Clause 5.3.3 & Clause 8.1.2)

AcuCalyx incorporates third-party and open-source software libraries. Each item of SOUP is formally registered, assessed for functional requirements and cybersecurity vulnerabilities, and monitored under our configuration management procedure.

### 3.1 Audited SOUP Register

| SOUP Identifier | Package Name & Exact Version | Source / Vendor | License | Functional Role in AcuCalyx | Safety Criticality | Known CVEs (as of Sept 2026) | Verification & Monitoring Policy |
|---|---|---|---|---|---|---|---|
| **SOUP-01** | `torch == 2.2.2` | PyTorch Foundation | BSD-3-Clause | Deep learning tensor operations; model inference for TotalSegmentator v2. | **Class C** (Segmentation) | None unmitigated; monitored on NVD / CISA KEV. | Golden dataset regression testing; deterministic CPU/CUDA inference verification. |
| **SOUP-02** | `SimpleITK == 2.3.1` | Insight Software Consortium | Apache-2.0 | DICOM image IO, Euclidean Distance Transform (EDT), reslicing, spacing extraction. | **Class C** (Distance fields) | None reported. | Analytical geometric ground-truth tests; spatial transform verification. |
| **SOUP-03** | `numpy == 1.26.4` | NumPy Developers | BSD-3-Clause | 3D array algebra, coordinate transformations, vector math, affine matrices. | **Class C** (Coordinates) | None reported. | Multi-tier unit test suite covering affine inversions and singular matrices. |
| **SOUP-04** | `pydicom == 2.4.4` | PyDicom Team | MIT | DICOM metadata parsing, tag extraction, PS 3.15 de-identification. | **Class C** (Ingestion & Privacy) | None unmitigated; deprecation warnings reviewed. | Synthetic and clinical DICOM ingestion tests; PS 3.15 attribute audit. |
| **SOUP-05** | `scipy == 1.12.0` | SciPy Developers | BSD-3-Clause | Multi-objective optimization helpers, spatial KD-Tree distance lookups. | **Class C** (Optimization) | None reported. | Pareto frontier mathematical verification; analytical benchmark suites. |
| **SOUP-06** | `fastapi == 0.110.0` | Tiangolo / FastAPI | MIT | REST API gateway, OpenAPI schema generation, clinician cockpit backend. | **Class B** (Interface) | None reported. | Input validation via Pydantic; authenticated endpoint access control. |
| **SOUP-07** | `pydantic == 2.6.4` | Pydantic / Colvin | MIT | Runtime data contract enforcement, input validation, canonical schema typing. | **Class B** (Data contracts) | None reported. | Boundary validation tests; malformed JSON schema rejection tests. |

### 3.2 SOUP Update & Maintenance Protocol
1. **Lockfile Enforcement:** Dependency versions are strictly pinned via `poetry.lock` / `requirements.txt` with SHA-256 package hashes. Silent or automatic updates are prohibited.
2. **Pre-Upgrade Qualification:** Any proposed SOUP version update requires:
   - CVE vulnerability scan against NVD and CISA KEV Catalog.
   - 100% pass rate on full regression test suite (100+ automated tests).
   - Equivalence verification against analytical golden datasets.

---

## 4. Software Problem Resolution / Anomaly Management (Clause 9)

In accordance with IEC 62304 Clause 9, AcuCalyx maintains a formal problem resolution procedure:

```
┌────────────────────────────────────────────────────────────────────────┐
│                   SOFTWARE ANOMALY LIFECYCLE (Clause 9)                │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│   [1. REPORTED] ──► [2. CONFIRMED] ──► [3. IN_ANALYSIS]                │
│                                              │                         │
│                                              ▼                         │
│   [6. CLOSED] ◄─── [5. VERIFIED] ◄─── [4. RESOLVED]                    │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

### 4.1 Anomaly Severity Classifications
- **Severity 1 (Critical / Fatal):** Failure causing potential death, critical visceral harm, or unhandled crash during procedural rehearsal with no workaround.
- **Severity 2 (Major):** Failure impairing a safety-relevant computational or interlock function where a safe manual workaround exists.
- **Severity 3 (Moderate):** Non-safety calculation or visualization defect (e.g. minor DRR contrast clipping, non-critical telemetry display glitch).
- **Severity 4 (Minor):** Usability nuisance or cosmetic rendering irregularity in Class A presentation infrastructure.
- **Severity 5 (Cosmetic):** Minor UI styling, typography, or documentation defect.

### 4.2 Release Gate Mandate
- **Zero Open Severity 1 or 2 Anomalies:** No medical device software release shall be authorized if any unresolved Severity 1 or Severity 2 anomaly remains open.
- **Regression Verification:** Every resolved anomaly must include an associated automated unit test that replicates the defect, proves its resolution, and prevents future regression.
