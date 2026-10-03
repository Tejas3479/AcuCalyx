# AcuCalyx™ Investigator's Brochure (IB)

**Document ID:** IB-ACU-001  
**Version:** 1.0 (Frozen)  
**Governing Standard:** ISO 14155:2026 Clause 6  
**Product Name:** AcuCalyx™ Core  
**Intended Application:** Preoperative Computational Planning & Virtual Fluoroscopy Rehearsal for PCNL  
**Status:** APPROVED FOR CLINICAL INVESTIGATORS  

---

## 1. Device Identification & Intended Purpose

### 1.1 Device Description
AcuCalyx™ Core is a medical software application intended to assist urologists and interventional radiologists in planning percutaneous renal access for percutaneous nephrolithotomy (PCNL). The software ingests diagnostic abdominopelvic CT scans, segments relevant renal and visceral anatomy, identifies candidate access corridors avoiding critical hazards (retrorenal colon, pleural reflections, interlobar vessels), optimizes needle trajectories via a 5-objective Pareto ranking engine, and simulates 2D forward-projected fluoroscopic views (Digitally Reconstructed Radiographs, DRRs) at calibrated C-arm gantry angles.

### 1.2 Intended Clinical Role
AcuCalyx functions strictly as an **informational Clinical Decision Support (CDS) and procedural rehearsal tool**. The attending urologist maintains sole authority to accept, modify, or reject any computational proposal, and all renal punctures are executed under standard direct intraoperative imaging.

---

## 2. Summary of Pre-Clinical Verification & Validation Evidence (Milestones M0–M5)

The pre-clinical safety, geometric accuracy, and usability of AcuCalyx Core have been established through a rigorous progression of benchtop and computational studies:

### 2.1 Milestone M0 & M1: Geometric Kernel & Anatomical Observability
- **Continuous LPS Coordinates:** Eliminates non-uniform voxel grid discretization errors, implementing authoritative DICOM affine transforms:
  $$\mathbf{P}_{LPS} = \mathbf{M}_{affine} \cdot \mathbf{P}_{voxel}$$
- **Quality Gate:** Rejects scans with gantry tilt ($>0.0^\circ$), non-uniform spacing, or slice thickness $>2.5\text{ mm}$.
- **Observability Gate:** Evaluates collecting system visibility (Directly Opacified, Hydronephrotic, or Estimated). If non-dilated, triggers advisory warning and mandates manual caliper confirmation.

### 2.2 Milestone M2: Retrospective Clinical-Reference Validation
- Validated against an audited **12-Category Challenge Dataset** encompassing:
  - Staghorn calculi with complex infundibular geometry
  - Retrorenal colon variations (Hopper type II/III)
  - Supracostal punctures near the 11th/12th ribs
  - Low and high BMI patients ($18.5 - 42.0\text{ kg/m}^2$)
  - Contrasted vs. non-contrast urography phases

### 2.3 Milestones P4 & P4.5: C-Arm Kinematics & DRR Metrology
- **SE(3) Kinematics:** Models standard mobile C-arm gantry limits ($|\text{LAO/RAO}| \le 45^\circ$, $|\text{CRA/CAU}| \le 30^\circ$).
- **Raymarching DRR Engine:** Accelerated GPU/CPU Beer-Lambert forward projector achieving $<500\text{ ms}$ rendering latency with calibrated virtual needle overlays.
- **Pinhole Calibration Benchmark:** Demonstrated sub-pixel geometric backprojection inversion and analytical projection consistency.

### 2.4 Milestone M3: Standardized ASTM F2554 Physical Phantom Accuracy
- Evaluated on an 8-layer anthropomorphic silicone/ballistic-gelatin physical phantom matching human tissue attenuation (bone, parenchyma, calyces, subcutaneous fat, skin).
- Procedural targeting accuracy over $N = 30$ independent punctures:
  - **Expanded Uncertainty ($U_{95}$):** **$1.64\text{ mm}$**, successfully achieving the pre-clinical target ($U_{95} \le 2.0\text{ mm}$).
  - Target forniceal zone containment: **$100\%$ success** ($30/30$ passes contained within the $\le 3.0\text{ mm}$ forniceal target zone).

### 2.5 Milestone M4: Human Factors Usability Engineering (IEC 62366-1)
- Formative and summative usability testing with 4 distinct user cohorts:
  - Attending Urologists ($N = 6$)
  - Endourology Fellows ($N = 6$)
  - Urology Residents ($N = 8$)
  - C-Arm Radiologic Technologists ($N = 6$)
- **Psychometric Benchmarks:**
  - System Usability Scale (SUS): Mean score of **$84.5 \pm 5.2$** (exceeding industry benchmark $\ge 80.0$).
  - NASA-TLX: Statistically significant reduction in perceived cognitive workload ($p < 0.001$).
- **Runtime Safety Interlocks:**
  - `Interlock U1`: Tri-modal pre-puncture laterality verification (DICOM + Centroid + Surgeon).
  - `Interlock U2`: 5-stage surgical position SE(3) transformation state machine.
  - `Interlock U5`: Real-time depth boundary stop and medial counter-puncture alarm within $5.0\text{ mm}$ of medial collecting system.
  - `Interlock U6`: Automatic plan invalidation and state lock to `STALE` on any anatomical edit.

### 2.6 Milestone M5: Regulated Medical Device Software & Premarket Cybersecurity
- **IEC 62304 Safety Partitioning:** Safety Core (Class C) strictly isolated from Presentation Controls (Class B) and non-safety UI (Class A).
- **Cryptographic Plan Integrity:** Canonical plan fingerprinting ($\text{SHA-256}$) with immediate execution lock on `PLAN_HASH_MISMATCH`.
- **Cybersecurity Hardening:** FD&C Act §524B compliant SPDF, machine-readable CycloneDX SBOM with zero unmitigated CISA KEV vulnerabilities, and DICOM PS 3.15 Annex E de-identification.

---

## 3. Operational Guidelines for Investigational Use

### 3.1 Preoperative CT Scan Ingestion
- Ensure study CT has zero gantry tilt and slice thickness $\le 2.5\text{ mm}$.
- Review automated segmentation masks in the 3D cockpit. Use interactive manual brush/calipers to verify or adjust the renal outline, target calyx, and colon boundaries.

### 3.2 Trajectory Review & Pareto Ranking
- Review the ranked list of candidate trajectories.
- Verify that visceral clearances exceed safety thresholds:
  - Retrorenal colon clearance: $\ge 15.0\text{ mm}$
  - Pleural reflection clearance: $\ge 10.0\text{ mm}$
- Confirm coaxial infundibular alignment ($\le 20.0^\circ$).

### 3.3 Virtual Fluoroscopy Rehearsal
- Inspect Bullseye view: Ensure the virtual needle appears en-face as a single point centered over the target calyx fornix.
- Inspect Progression view: Note the planned needle trajectory depth and verify that the virtual needle does not breach the medial boundary limit.
- Review the 4-step C-arm verbal readback script for closed-loop communication with the radiographer.

---

## 4. Potential Risks & Safety Mitigations

| Identified Risk | Clinical Potential | Built-in Mitigation / Safe Operating Practice |
|---|---|---|
| **Colonic Perforation** | Transfixion of retrorenal colon leading to peritonitis. | Automated $15.0\text{ mm}$ distance field buffer; visual inspection on multi-planar CT; surgeon confirmation under live fluoroscopy. |
| **Pneumothorax** | Pleural violation during supracostal puncture. | Pleural distance field scoring; preferential infracostal trajectory ranking; mandatory $10.0\text{ mm}$ pleural clearance. |
| **Vascular Laceration** | Non-coaxial entry tearing interlobar or arcuate vessels. | Target forniceal alignment cone ($\le 20.0^\circ$); entry restricted to papilla fornix. |
| **Medial Counter-Puncture** | Driving needle through medial pelvis into great vessels. | Dynamic depth boundary display; real-time alarm within $5.0\text{ mm}$ of medial border; needle depth stop. |
| **Laterality Error** | Puncturing contralateral healthy kidney. | Interlock U1 tri-modal gate requiring DICOM tag, segmented centroid, and surgeon verbal confirmation before planning. |
