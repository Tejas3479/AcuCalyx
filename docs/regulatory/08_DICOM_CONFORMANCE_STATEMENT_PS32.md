# AcuCalyx™ Core DICOM PS 3.2 Conformance Statement
## Normative Conformance Statement for Preoperative Planning & Rehearsal Platform

**Document Identifier:** DCS-ACU-PS32-2026A  
**Software Release Baseline:** AcuCalyx Core v1.0.0-RC1 (Regulatory Submission Baseline 1.0)  
**Software Build Identifier:** ACU-CORE-20261001-BLD01  
**Governing Standard:** NEMA PS 3.1–3.22 (DICOM Standard 2026a Release)  
**Conformance Class:** DICOM PS 3.2 Normative Conformance  

---

## 1. Conformance Statement Overview

AcuCalyx™ Core is an uncertainty-aware surgical planning and virtual fluoroscopy rehearsal platform for percutaneous nephrolithotomy (PCNL). It implements a single Application Entity (`ACUCALYX_AE`) that interacts with hospital Picture Archiving and Communication Systems (PACS) and computed tomography (CT) scanners over TCP/IP local area networks and DICOMweb RESTful protocols.

### 1.1 Network Services Summary

| SOP Class Name | SOP Class UID | Role | Transfer Syntaxes Supported |
|---|---|---|---|
| **CT Image Storage** | `1.2.840.10008.5.1.4.1.1.2` | SCP | Explicit VR Little Endian, Implicit VR Little Endian, Deflated Explicit VR |
| **Enhanced CT Image Storage** | `1.2.840.10008.5.1.4.1.1.2.1` | SCP | Explicit VR Little Endian, Implicit VR Little Endian |
| **Secondary Capture Image Storage** | `1.2.840.10008.5.1.4.1.1.7` | SCU | Explicit VR Little Endian |
| **Multi-frame Secondary Capture Image Storage** | `1.2.840.10008.5.1.4.1.1.7.2` | SCU | Explicit VR Little Endian |
| **Study Root Q/R Information Model – FIND** | `1.2.840.10008.5.1.4.1.2.2.1` | SCU | Explicit VR Little Endian |
| **Study Root Q/R Information Model – MOVE** | `1.2.840.10008.5.1.4.1.2.2.2` | SCU | Explicit VR Little Endian |

### 1.2 Non-Ionizing Secondary Capture DRR Encoding Policy
> [!IMPORTANT]
> **Normative Semantic Invariant (DICOM Part 3 Section A.8):**  
> Digitally Reconstructed Radiographs (DRRs), bullseye views, and progression trajectory rehearsal views generated from volumetric CT are synthetic, non-modality-specific reconstructions. In accordance with DICOM PS 3.3 Annex A.8, all synthetic forward projections are strictly exported as **Secondary Capture Image Storage** (`1.2.840.10008.5.1.4.1.1.7`) with tag `ConversionType (0008,0064) = "SYN"` and `DerivationDescription (0008,2111)` containing the C-arm projection parameters. AcuCalyx Core expressly forbids encoding synthetic projections as X-Ray Angiographic (XA) or Fluoroscopic images to prevent PACS archives from misclassifying simulated images as real patient ionizing radiation exposures.

---

## 2. Implementation Model & Application Data Flow

### 2.1 Application Entity Functional Definitions
The `ACUCALYX_AE` Application Entity provides three primary functional boundaries:
1. **CT Ingestion Service (Storage SCP):** Listens on a configurable TCP port (default: `11112`) for incoming DICOM associations from PACS or acquisition modalities. Validates series completeness, patient orientation, gantry tilt, and slice spacing against the validated operating envelope before passing volumetric arrays to the anatomical segmentation pipeline.
2. **Query/Retrieve Client (Q/R SCU):** Initiates DICOM C-FIND queries against hospital PACS nodes by Patient ID, Accession Number, or Study Date, and issues C-MOVE requests to retrieve designated axial series.
3. **Planning & DRR Export Service (Storage SCU):** Initiates outbound DICOM associations to PACS nodes to archive calibrated 2D synthetic DRR projections and 1-page sterile operating room planning cards.

```
┌────────────────────────────────────────────────────────────────────────┐
│                      ACUCALYX_AE IMPLEMENTATION MODEL                  │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│   HOSPITAL PACS / MODALITY                      ACUCALYX CORE          │
│   ┌─────────────────────┐                   ┌──────────────────────┐   │
│   │                     │─── C-STORE (CT) ─>│ Storage SCP          │   │
│   │                     │                   │                      │   │
│   │   DICOM Archive     │<── C-FIND (Q/R) ──│ Query/Retrieve SCU   │   │
│   │   & Modality Node   │<── C-MOVE (Q/R) ──│                      │   │
│   │                     │                   │                      │   │
│   │                     │<── C-STORE (SC) ──│ Storage SCU (DRR)    │   │
│   └─────────────────────┘                   └──────────────────────┘   │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. AE Specifications (`ACUCALYX_AE`)

### 3.1 Association Policies
- **General:** Maximum PDU size offered: `65,536 bytes`.
- **Number of Associations:** Supports up to 4 concurrent incoming C-STORE associations and 2 concurrent outbound associations.
- **Asynchronous Nature:** Does not negotiate asynchronous operations window.
- **Implementation Identifying Information:**
  - Implementation Class UID: `1.3.6.1.4.1.99999.1.0.0`
  - Implementation Version Name: `ACUCALYX_V1_0_0`

### 3.2 Association Acceptance Policy (Storage SCP)

#### 3.2.1 Accepted Presentation Contexts

| Abstract Syntax Name | Abstract Syntax UID | Transfer Syntax Name | Transfer Syntax UID | Role | Ext. Neg. |
|---|---|---|---|---|---|
| CT Image Storage | `1.2.840.10008.5.1.4.1.1.2` | Explicit VR Little Endian | `1.2.840.10008.1.2.1` | SCP | None |
| CT Image Storage | `1.2.840.10008.5.1.4.1.1.2` | Implicit VR Little Endian | `1.2.840.10008.1.2` | SCP | None |
| CT Image Storage | `1.2.840.10008.5.1.4.1.1.2` | Deflated Explicit VR LE | `1.2.840.10008.1.2.1.99` | SCP | None |
| Enhanced CT Storage | `1.2.840.10008.5.1.4.1.1.2.1` | Explicit VR Little Endian | `1.2.840.10008.1.2.1` | SCP | None |
| Verification (Echo) | `1.2.840.10008.1.1` | Explicit VR Little Endian | `1.2.840.10008.1.2.1` | SCP | None |

#### 3.2.2 SOP-Specific Conformance for CT Image Storage (Input Eligibility & Operating Envelope)
Upon receiving each slice, `ACUCALYX_AE` verifies conformity with the validated operational envelope:
1. **Gantry Tilt Constraint:** `Gantry/Detector Tilt (0018,1120)` must equal $0.0^\circ$. Datasets with non-zero tilt are rejected with status `0xC001` (Cannot understand / Gantry tilt unsupported).
2. **Slice Spacing Consistency:** Verified across `Image Position (Patient) (0020,0032)`. Variations $>0.1\text{ mm}$ trigger series rejection.
3. **Slice Thickness Limit:** `Slice Thickness (0018,0050)` must be $\le 2.5\text{ mm}$. Slices $>2.5\text{ mm}$ trigger warning status `0xB000`.
4. **Photometric Interpretation:** Must be `MONOCHROME2`.

### 3.3 Association Initiation Policy (Storage SCU)

#### 3.3.1 Proposed Presentation Contexts for Secondary Capture DRR Export

| Abstract Syntax Name | Abstract Syntax UID | Transfer Syntax Name | Transfer Syntax UID | Role | Ext. Neg. |
|---|---|---|---|---|---|
| Secondary Capture Image Storage | `1.2.840.10008.5.1.4.1.1.7` | Explicit VR Little Endian | `1.2.840.10008.1.2.1` | SCU | None |
| Multi-frame Secondary Capture | `1.2.840.10008.5.1.4.1.1.7.2` | Explicit VR Little Endian | `1.2.840.10008.1.2.1` | SCU | None |

#### 3.3.2 Mandatory Tags for Derived Rehearsal DRR Export
- `SOPClassUID (0008,0016)`: `1.2.840.10008.5.1.4.1.1.7`
- `Modality (0008,0060)`: `"OT"` (Other)
- `ConversionType (0008,0064)`: `"SYN"` (Synthesized Image)
- `DerivationDescription (0008,2111)`: `"AcuCalyx Virtual Fluoroscopy Rehearsal: CRA/CAU=deg, LAO/RAO=deg, SID=mm"`
- `BurnedInAnnotation (0028,0301)`: `"NO"` (Unless sterile OR 1-page summary burn-in explicitly requested)

---

## 4. Communication Profiles & Network Security

### 4.1 Physical Media Support
Standard Ethernet (1000BASE-T / 10GBASE-T) running over TCP/IP stack.

### 4.2 Secure DICOM Communication (DICOM PS 3.15 Annex B.1)
- **Transport Layer Security (TLS 1.3):** Supported per BCP 195 profile.
- **Cipher Suites:** Mandatory support for `TLS_AES_256_GCM_SHA384` and `TLS_CHACHA20_POLY1305_SHA256`.
- **Mutual Node Authentication:** X.509 v3 digital certificates for both server and client verification.

### 4.3 DICOMweb RESTful Services (Part 18)
- **WADO-RS (`/studies/{StudyUID}/series/{SeriesUID}`):** Retrieval of volumetric CT instances over HTTPS.
- **STOW-RS (`/studies`):** Outbound storage of Secondary Capture DRR datasets.
- **QIDO-RS (`/studies?PatientID={ID}`):** Query studies via RESTful HTTP JSON payloads.

---

## 5. Transformation of DICOM Application Level Confidentiality (PS 3.15)

AcuCalyx provides two operational modes for DICOM data handling:
1. **Clinical Production Mode:** Retains complete patient identification tags (`PatientName (0010,0010)`, `PatientID (0010,0020)`, `AccessionNumber (0008,0050)`) to maintain surgical safety, prevent laterality transposition, and ensure institutional EHR audit trail compliance.
2. **Research / Pre-Sub De-Identification Mode:** Enforces the DICOM PS 3.15 Basic Application Level Confidentiality Profile:
   - Replaces `PatientID` with HMAC-SHA256 pseudonym.
   - Cleanses `PatientName`, `PatientBirthDate`, `InstitutionName`, `ReferringPhysicianName`.
   - Modifies `PatientAge` and removes all Private Tags (`Tag group odd numbers`).
