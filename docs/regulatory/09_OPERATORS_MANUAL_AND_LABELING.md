# AcuCalyx™ Core Clinician Cockpit Operator's Manual & Medical Device Labeling
## Instructions for Use (IFU), Operating Envelope, Warnings & Contraindications

**Document Identifier:** LBL-ACU-IFU-2026A  
**Regulatory Baseline:** 21 CFR Part 801 / 21 CFR 801.109 (Prescription Devices) & 21 CFR Part 830 (UDI)  
**Software Release Baseline:** AcuCalyx Core v1.0.0-RC1 (Regulatory Submission Baseline 1.0)  

---

## 1. Statutory Prescription Device Statement (21 CFR 801.109)

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                        │
│   CAUTION: Federal law (USA) restricts this device to sale by or on the order of a     │
│   licensed physician (Rx Only).                                                        │
│                                                                                        │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

The statutory prescription disclaimer is displayed on the physical software distribution packaging, the electronic installation media, the application launch splash screen, the system *About* dialog, and all exported 1-page sterile operating room planning summary documents.

---

## 2. Device Identification & Unique Device Identification (UDI)

- **Device Trade Name:** AcuCalyx™ Core
- **Device Common Name:** System, Image Processing, Radiological / Preoperative Surgical Planning Software
- **Software Build Identifier:** `ACU-CORE-20261001-BLD01`
- **Device Version:** `v1.0.0-RC1`
- **Unique Device Identifier (UDI):**
  - **Device Identifier (DI):** `(01)00860000000001` (Assigned via GS1 / FDA GUDID)
  - **Production Identifier (PI):** `(8012)ACU-CORE-20261001-BLD01(11)261001`
- **Manufacturer Establishment:** AcuCalyx Surgical Technologies Inc.

---

## 3. Indications for Use & Intended Clinical Audience

### 3.1 Indications for Use Statement
AcuCalyx™ Core is a medical device software application intended for use by qualified medical professionals (urologists and interventional radiologists) as an aid in preoperative planning and virtual fluoroscopy rehearsal for percutaneous nephrolithotomy (PCNL). 

The software imports volumetric axial computed tomography (CT) datasets of the abdomen and pelvis, segments renal parenchymal and surrounding at-risk anatomical structures, calculates and evaluates potential percutaneous needle access corridors targeting renal calyces, and simulates 2D radiographic projections (digitally reconstructed radiographs) aligned with clinician-specified C-arm fluoroscopy orientations.

### 3.2 Intended Clinical Users
The device is intended exclusively for use by:
1. Licensed urologists trained in percutaneous renal access.
2. Interventional radiologists performing percutaneous nephrostomy.
3. Clinical fellows and residents under direct attending physician supervision.

---

## 4. Validated Input Operating Envelope (Eligibility Criteria)

> [!IMPORTANT]
> **Input Eligibility vs. Clinical Contraindications:**  
> The following parameters represent the validated engineering operational envelope of the software. CT scans outside this envelope are rejected at ingestion to ensure anatomical observability and metrological validity.

| Parameter | Validated Operational Envelope | Software Behavior if Violating |
|---|---|---|
| **Patient Age** | Adult patients ($\ge 18$ years) | Ingestion warning; pediatric use contraindicated |
| **Scanner Geometry** | Helical axial CT acquisition with zero gantry tilt ($\text{tilt} = 0.0^\circ$) | **Fail-Closed Rejection** (`ERR_INPUT_REJECTED_GANTRY_TILT`) |
| **Slice Thickness** | $\le 2.5\text{ mm}$ (Recommended: $\le 1.5\text{ mm}$) | Slices $>2.5\text{ mm}$ rejected (`ERR_INPUT_REJECTED_SLICE_THICKNESS`) |
| **In-Plane Pixel Spacing** | $\le 1.0\text{ mm} \times 1.0\text{ mm}$ | Slices $>1.0\text{ mm}$ trigger low-resolution visual warning |
| **Field of View (FOV)** | Bilateral lower ribs (10th–12th), full renal parenchyma, calyces, and flank skin | Incomplete organ bounding box triggers abort (`ERR_FOV_INCOMPLETE`) |
| **Contrast Enhancement** | Non-contrast helical CT OR delayed excretory phase CT | Non-contrast with severe unenhanced calyces requires user-confirmed gating |
| **Artifact Level** | Absence of massive metal streak artifact from bilateral hip prostheses | Metal streak $>1500\text{ HU}$ crossing renal bed triggers manual review warning |

---

## 5. Clinical Contraindications

1. **Pediatric Patients:** AcuCalyx Core is contraindicated for patients under 18 years of age due to distinct pediatric renal calyceal compliance, respiratory excursion, and radiation risk profiles.
2. **Emergency PCNL / Acute Septic Shock:** Contraindicated in emergent, hemodynamically unstable cases requiring immediate bedside decompression without prior high-resolution CT imaging.
3. **Severe Uncorrected Coagulopathy:** Standard clinical surgical contraindication to percutaneous puncture.

---

## 6. Warnings, Precautions & Clinical Invariants

### 6.1 Attending Surgeon Clinical Authority Invariant
> [!WARNING]
> **AcuCalyx Core is a Clinical Decision Support (CDS) Tool:**  
> The software provides computer-assisted planning, multi-objective trajectory ranking, and virtual fluoroscopy simulation. It does **NOT** provide active intraoperative needle tracking, automated needle driving, or robotic guidance. The attending physician retains sole medical, surgical, and legal responsibility for verifying all anatomical boundaries, selecting the target calyx and puncture angle, and executing the puncture under continuous live real-time imaging (fluoroscopy or ultrasound).

### 6.2 Preoperative Virtual Rehearsal Warnings
- **Pneumothorax Risk:** Intercostal access trajectories above the 11th rib carry documented risk of pleural violation. The surgeon must verify diaphragm position on inspiratory/expiratory fluoroscopy.
- **Colon Perforation:** Trajectories with posterior retrorenal colon proximity $< 5.0\text{ mm}$ are flagged with critical red interlocks. The surgeon must verify absence of bowel along the proposed corridor.
- **Surgical Position Transform:** AcuCalyx supports prone and supine positions. Trajectory calculations derived from supine CT must be verified for renal displacement if the patient is positioned prone.

---

## 7. Runtime Safety Interlocks (U1–U6 Summary)

The clinician cockpit enforces six mandatory safety interlocks before releasing any plan:
- **Interlock U1 (Laterality Verification):** Mandatory explicit operator confirmation of left vs. right kidney.
- **Interlock U2 (Surgical Position Lock):** Prevents coordinate transposition between prone and supine poses.
- **Interlock U3 (Hydronephrosis Observability Gate):** Prevents target selection if calyceal dilation is undetectable.
- **Interlock U4 (Thoracic & Visceral Safety Corridor):** Imposes mandatory buffer zones ($>5\text{ mm}$ colon/spleen, $>10\text{ mm}$ liver).
- **Interlock U5 (Medial Counter-Puncture Guard):** Red warning alarm if trajectory passes medial to the renal hilum or great vessels.
- **Interlock U6 (Stale Plan Anti-Tamper Invalidation):** Automatically invalidates plan cryptographic signatures if underlying segmentation or CT coordinates mutate.
