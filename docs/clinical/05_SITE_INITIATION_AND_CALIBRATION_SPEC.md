# AcuCalyx™ Site Initiation & C-Arm Calibration Specification

**Document ID:** SIV-SPEC-ACU-001  
**Version:** 1.0 (Frozen)  
**Governing Standard:** ASTM F2554 / ISO 13485:2016 Clause 7.5.6 / ISO 14155:2026  
**Target Milestone:** Gate M5.5 Pre-Clinical Site Activation  
**Status:** APPROVED & FROZEN  

---

## 1. Scope & Objective

This specification governs the prerequisite technical qualification, hardware/network verification, C-arm geometric profiling, anthropomorphic phantom dry-run validation, and investigator credentialing required before an investigational center is certified for clinical patient enrollment in **AcuCalyx™ clinical studies (ACU-PILOT-01)**.

Under ISO 14155:2026 and ISO 13485 Clause 7.5.6, clinical trial validity requires that all medical device software and associated imaging equipment operate within verified, calibrated tolerances.

---

## 2. 4-Tier Site Initiation Gate

```
┌────────────────────────────────────────────────────────────────────────┐
│                        SITE ACTIVATION GATE WORKFLOW                   │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│   [TIER 1: IT & NETWORK APPLIANCE QUALIFICATION]                       │
│   • Hospital PACS connection verified over TLS 1.3                     │
│   • DICOM C-STORE / DIMSE / DICOMweb transfer syntax verified          │
│   • PHIGuard PS 3.15 de-identification audit passes 100%               │
│                        │                                               │
│                        ▼                                               │
│   [TIER 2: C-ARM DEVICE PROFILING & KINEMATICS REGISTRATION]           │
│   • C-Arm make, model, detector type (Flat Panel vs II) recorded       │
│   • Source-to-Detector Distance (SID), focal spot, and pitch verified  │
│   • Gantry angular limits hard-clamped (LAO/RAO +/-45, CRA/CAU +/-30)  │
│                        │                                               │
│                        ▼                                               │
│   [TIER 3: ANTHROPOMORPHIC PHANTOM METROLOGY BENCHMARK]                │
│   • M3 multi-layer physical phantom placed on surgical OR table        │
│   • 3 distinct target punctures executed under AcuCalyx C-arm guidance │
│   • Criterion: Angular error <= 2.0 deg, Spatial error <= 2.0 mm       │
│                        │                                               │
│                        ▼                                               │
│   [TIER 4: INVESTIGATOR CREDENTIALING & WORKFLOW CERTIFICATION]        │
│   • Urologists complete training on Interlocks U1, U2, U5, U6          │
│   • Closed-loop 4-step verbal C-arm readback protocol verified         │
│   • Transposition error detection test passed with 100% score          │
│                        │                                               │
│                        ▼                                               │
│   [SITE ACTIVATION CERTIFICATE ISSUED - READY FOR HUMAN ENROLLMENT]    │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Tier 2: C-Arm Kinematics & Projection Calibration

### 3.1 C-Arm Device Register Parameters
Every participating mobile fluoroscopy unit is profiled in the AcuCalyx configuration registry:
1. **Manufacturer & Model:** (e.g. Siemens Healthineers Cios Spin / Alpha; GE Healthcare OEC Elite / 9900; Philips Zenition 70).
2. **Detector Architecture:**
   - Amorphous Silicon Flat Panel Detector (FPD) or Cesium Iodide Image Intensifier (II).
   - Active matrix size (e.g. $1024 \times 1024$ or $1536 \times 1536$ pixels).
   - Pixel pitch (e.g. $0.194\text{ mm}$ or $0.205\text{ mm}$).
3. **Geometry & Kinematic Envelope:**
   - Source-to-Detector Distance ($\text{SID} = 1000\text{–}1050\text{ mm}$).
   - Source-to-Isocenter Distance ($\text{SOD} = 750\text{–}800\text{ mm}$).
   - Angular limits enforced: $|\text{LAO/RAO}| \le 45.0^\circ$, $|\text{CRA/CAU}| \le 30.0^\circ$.

---

## 4. Tier 3: Anthropomorphic Phantom Metrology Protocol (ASTM F2554)

### 4.1 Benchmark Procedure
1. Position the verified AcuCalyx M3 anthropomorphic phantom (silicone/gelatin, radiopaque calyces, rib cage) on the site's operating table in standard prone orientation.
2. Ingest the phantom CT scan into AcuCalyx Core; generate planned trajectories to the lower pole posterior calyx and interpolar calyx.
3. Align the site C-arm to the AcuCalyx calculated Bullseye and Progression angles.
4. Participating urologist executes 3 test needle punctures using standard 18G trocars.
5. Record final needle position via orthogonal high-resolution verification fluoroscopy.

### 4.2 Acceptance Tolerances
To achieve site certification, the mean targeting error across the 3 passes must satisfy:
$$\Delta \theta_{\text{mean}} \le 2.0^\circ \quad (\text{Angular Concordance})$$
$$\Delta d_{\text{mean}} \le 2.0\text{ mm} \quad (\text{Spatial Euclidean Concordance})$$

---

## 5. Site Activation Checklist & Certification

| Verification Item | Requirement Specification | Verification Evidence | Sign-Off |
|---|---|---|---|
| **PACS / Network Gateway** | DICOM C-STORE over TLS 1.3 verified; zero packet loss | IT Connectivity Audit Log | [ ] PASS |
| **DICOM PS 3.15 Guard** | 100% direct PHI scrubbed on sample series | `PHIGuard.verify_compliance` report | [ ] PASS |
| **C-Arm Profiling** | SID and FPD pixel pitch calibrated in registry | Site C-Arm Calibration File | [ ] PASS |
| **Phantom Metrology** | Angular error $\le 2.0^\circ$, spatial error $\le 2.0\text{ mm}$ | ASTM F2554 Metrology Report | [ ] PASS |
| **Investigator Training** | 4 surgeons trained on Interlocks U1–U6 & verbal scripts | Training Log & Certificate | [ ] PASS |
| **Source Data Exporter** | SHA-256 JSON export confirmed compatible with EDC | Sample Source Record Verification | [ ] PASS |

**Site Activation Decision:**  
When all items above are checked PASS, the Clinical Study Sponsor and Principal Investigator execute the **Certificate of Site Activation**, permitting patient screening to commence.
