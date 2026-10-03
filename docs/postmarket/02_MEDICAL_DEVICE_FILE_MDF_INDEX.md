# AcuCalyx™ Core Medical Device File (MDF) Index
## Master Technical & Manufacturing Record per ISO 13485:2016 Clause 4.2.3 & FDA QMSR (21 CFR Part 820)

**Document Identifier:** MDF-ACU-M8-2026A  
**Software Release Baseline:** AcuCalyx Core v1.0.0-COMMERCIAL (`ACU-CORE-COMMERCIAL-20261015-BLD01`)  
**Governing Standard:** ISO 13485:2016 Clause 4.2.3 (Medical Device File) & FDA QMSR (21 CFR Part 820)  
**Status:** SEALED COMMERCIAL MEDICAL DEVICE FILE  

---

## 1. Regulatory Context: Medical Device File under FDA QMSR

> [!NOTE]
> **QMSR Alignment & Elimination of Legacy DMR Terminology:**  
> In the final rule for the Quality Management System Regulation (QMSR, effective February 2, 2026), the FDA harmonized 21 CFR Part 820 with ISO 13485:2016 and explicitly eliminated legacy FDA-specific terms including "Device Master Record (DMR)", "Design History File (DHF)", and "Device History Record (DHR)".  
> 
> Under ISO 13485:2016 Clause 4.2.3, finished device manufacturers must establish and maintain a **Medical Device File (MDF)** for each medical device type or family, containing or referencing documents that define device specifications, manufacturing processes, labeling, installation, and servicing.

---

## 2. Comprehensive Medical Device File (MDF) Structure

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│               ACUCALYX™ CORE MEDICAL DEVICE FILE (ISO 13485 CLAUSE 4.2.3)              │
├──────┬────────────────────────────────┬────────────────────────────────────────────────┤
│ Sec  │ Technical Dimension            │ Controlled Reference Document / Specification  │
├──────┼────────────────────────────────┼────────────────────────────────────────────────┤
│ 1.0  │ General Device Description &   │ • System Architecture (SRS Section 4)          │
│      │ Intended Use                   │ • Indications for Use & Target Patient Pop.    │
│      │                                │ • Validated Input Operating Envelope           │
├──────┼────────────────────────────────┼────────────────────────────────────────────────┤
│ 2.0  │ Product Software & Algorithm   │ • Software Requirements Spec (SwRS v2.0)       │
│      │ Specifications                 │ • Continuous LPS Trajectory Math Specification │
│      │                                │ • TotalSegmentator v2 Model Card (SHA-256)     │
│      │                                │ • DICOM PS 3.2 Conformance Statement           │
├──────┼────────────────────────────────┼────────────────────────────────────────────────┤
│ 3.0  │ Manufacturing, Packaging &     │ • Golden Container Manifest (Docker/OCI)       │
│      │ Build Recipes                  │ • Host Environment Envelope (OS, GPU, CUDA)    │
│      │                                │ • Codebase Git Tag: `release/v1.0.0-commercial`│
│      │                                │ • SBOM Baseline (CycloneDX v1.5 JSON)          │
├──────┼────────────────────────────────┼────────────────────────────────────────────────┤
│ 4.0  │ Labeling, IFU & Packaging      │ • Clinician Cockpit Operator's Manual & IFU    │
│      │ Specifications                 │ • Statutory 21 CFR 801.109 Rx Only Notice      │
│      │                                │ • UDI Assignment: DI `(01)00860000000001`      │
│      │                                │   *(Placeholder pending issuing-agency grant)* │
├──────┼────────────────────────────────┼────────────────────────────────────────────────┤
│ 5.0  │ Installation, Deployment &     │ • Production Deployment Qualification Protocol │
│      │ Servicing Procedures           │ • Clean Install, Upgrade & Rollback Checklist  │
│      │                                │ • Host Platform TLS 1.3 Certificate Setup      │
│      │                                │ • C-Arm Dry-Run Phantom Calibration SOP        │
│      │                                │ • Patch Verification & Anti-Downgrade Protocol │
└──────┴────────────────────────────────┴────────────────────────────────────────────────┘
```

---

## 3. Commercial Software Deployment Envelope

The software is validated exclusively for deployment on hospital workstations meeting the following verified environment contract:

| Environment Attribute | Validated Commercial Specification |
|---|---|
| **Operating System** | Microsoft Windows 11 Enterprise (64-bit) OR Windows Server 2022 |
| **Processor Architecture** | x86_64 Intel Core i7 / Xeon (12th Gen or newer, $\ge 8$ physical cores) |
| **System Memory (RAM)** | $\ge 32\text{ GB}$ DDR4 / DDR5 ECC memory |
| **Graphics Processing Unit** | NVIDIA RTX 4080 / RTX A4000 (Ada Lovelace or Ampere, $\ge 16\text{ GB}$ VRAM) |
| **NVIDIA Driver Baseline** | Production Branch Driver $\ge 550.54$ (CUDA 12.4 runtime supported) |
| **Network Interface** | Dual 1000BASE-T Ethernet (Isolated PACS VLAN + Management VLAN) |
| **Network Security** | TLS 1.3 mandatory; X.509 v3 certificates with AES-256-GCM cipher suites |
| **Storage Subsystem** | $\ge 500\text{ GB}$ NVMe SSD dedicated storage with BitLocker encryption |

---

## 4. Software Installation, Upgrade & Rollback Verification

In accordance with ISO 13485 Clause 7.5.1 and Clause 7.5.6:
1. **Clean Installation:** Automated installer verifies host OS, GPU VRAM, CUDA runtime, and writes immutable audit logs.
2. **Upgrade Verification:** Preserves existing case databases, configuration baselines, and cryptographic audit records.
3. **Rollback Safety:** Automated installer rejects corrupted packages and prohibits downgrading software builds unless authorized under formal CAPA with database schema rollback verification.
