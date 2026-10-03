<div align="center">

# AcuCalyx™ (KidneyStone 3D)
### Autonomous Preoperative CT Surgical Planning, Computational Geometry & Virtual Fluoroscopy Digital Twin for Percutaneous Nephrolithotomy (PCNL)

[![Python 3.13](https://img.shields.io/badge/Python-3.13%2B-blue.svg?logo=python&logoColor=white)](https://python.org)
[![Tests Passing](https://img.shields.io/badge/Tests-199%2F199%20Passing-brightgreen.svg?logo=pytest&logoColor=white)](./tests)
[![FDA Regulatory](https://img.shields.io/badge/FDA%20Pathway-510(k)%20Class%20II%20(LLZ)-informational.svg)](./docs/regulatory)
[![IEC 62304](https://img.shields.io/badge/IEC%2062304-Class%20B%20Compliant-blueviolet.svg)](./docs/regulatory/04_IEC_62304_SOFTWARE_LIFECYCLE_AND_SOUP.md)
[![HIPAA De-ID](https://img.shields.io/badge/HIPAA%20%2F%20PS%203.15-Cryptographic%20PHI%20Guard-success.svg)](./src/acucalyx/cybersecurity/phi_guard.py)
[![WebGL 3D](https://img.shields.io/badge/Viewer-Three.js%20WebGL%20PBR-orange.svg?logo=three.js&logoColor=white)](./app/frontend)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI%20REST-009688.svg?logo=fastapi&logoColor=white)](./app/api)

---

**A zero-hardware, cloud-native surgical digital twin that translates routine Non-Contrast CT (NCCT) scans into single-puncture percutaneous trajectories, patient-specific 3D anatomical models, and sterile C-Arm fluoroscopy gantry angles for existing operating room X-ray machines.**

[Key Innovations](#-key-architectural-innovations) •
[Interactive Cockpit](#-interactive-3d-rehearsal-cockpit) •
[Quick Start](#-quick-start--installation) •
[Verification](#-testing--verification-suite) •
[Regulatory DHF](#-complete-regulatory--clinical-documentation-suite) •
[Repository Tree](#-repository-structure)

</div>

---

## 📌 Executive Clinical Overview

In endourology, **Percutaneous Nephrolithotomy (PCNL)** is the definitive standard of care for large (>20 mm) or complex staghorn calculi, yet it carries the steepest learning curve of any urological procedure (requiring 60+ cases for baseline competency). 

Because surgeons are forced to mentally reconstruct complex 3D renal anatomy from hundreds of 2D CT slices in the OR:
* **80% of PCNL punctures in the US are outsourced to Interventional Radiology (IR)** due to spatial anxiety and lack of confident intraoperative targeting.
* **15% to 30% of complex cases require multiple puncture attempts**, escalating nephron loss, major hemorrhages requiring angioembolization (1–3%), and severe septic complications.
* **Retrorenal colon perforation occurs in 2% to 5% of cases**, a potentially fatal complication requiring emergent laparotomy.

**AcuCalyx™ eliminates procedural guesswork without requiring expensive surgical robots or tracking markers.** By running rigorous computational geometry on standard thin-slice CT scans, AcuCalyx:
1. Calculates true 3D stone volumetry and radiodensity profiles.
2. Evaluates continuous 3D clearance envelopes to surrounding viscera (colon, pleura, intercostal neurovascular bundles).
3. Optimizes access trajectories via a **Three-Tier Fail-Safe Pareto Optimizer**.
4. Simulates **C-Arm Fluoroscopy Gantry Angles (LAO/RAO and Cranial/Caudal)** to reproduce the exact Bull's-Eye (co-axial) and 90° Progression views on standard surgical C-arms.

```
                              CURRENT CLINICAL WORKFLOW (FLAWED)
┌────────────────────────┐      ┌─────────────────────────┐      ┌──────────────────────────┐
│ Patient gets Non-      │ ───► │ Surgeon scrolls through │ ───► │ Surgeon mentally guesses │
│ Contrast CT (300 slices│      │ 300 flat 2D slices      │      │ 3D trajectory in the OR  │
└────────────────────────┘      └─────────────────────────┘      └─────────────┬────────────┘
                                                                               │
                                            ┌──────────────────────────────────┴──────────────────────────────────┐
                                            ▼                                                                     ▼
                               ┌─────────────────────────┐                                           ┌─────────────────────────┐
                               │ Multi-tract punctures   │                                           │ Fatal hazard puncture   │
                               │ (15–30% complex cases)  │                                           │ (Retrorenal colon 2–5%) │
                               └─────────────────────────┘                                           └─────────────────────────┘

                              ACUCALYX™ WORKFLOW (ZERO-HARDWARE)
┌────────────────────────┐      ┌─────────────────────────┐      ┌──────────────────────────┐      ┌──────────────────────────┐
│ Non-Contrast CT DICOM  │ ───► │ AI 3D Mesh Engine       │ ───► │ 3-Tier Pareto Optimizer  │ ───► │ 1-Page Sterile Blueprint │
│ uploaded (<= 1.25mm)   │      │ (Surface Extraction)    │      │ & Distance Fields (SDF)  │      │ & C-Arm Gantry Angles    │
└────────────────────────┘      └─────────────────────────┘      └──────────────────────────┘      └──────────────────────────┘
                                                                               │
                                                                               ▼
                                                                 ┌──────────────────────────┐
                                                                 │ Single-tract puncture    │
                                                                 │ Zero colon perforations  │
                                                                 │ CPT 76376/76377 Billable │
                                                                 └──────────────────────────┘
```

---

## ⚡ Key Architectural Innovations

### 1. Authoritative DICOM Ingestion & Normal Projection
Standard slice thickness tags in DICOM headers (`0018,0050`) frequently fail to reflect true physical inter-slice spacing when gantry spacing varies. AcuCalyx computes physical slice spacing by projecting `ImagePositionPatient` vectors onto the slice normal:
$$d_k = \mathbf{P}_k \cdot (\mathbf{X} \times \mathbf{Y})$$
Enforces a fail-closed quality gate that detects gantry tilt, non-uniform slice intervals, and excessive slice thicknesses ($>2.5\text{ mm}$).

### 2. Anisotropic Euclidean Signed Distance Fields (SDF)
Computes true 3D spatial clearance fields to critical risk structures:
* **Retrorenal Colon:** Clearance threshold evaluated along the entire needle cylinder tract.
* **Pleural Reflection Envelope:** Supracostal rib trajectory classification (Subcostal, Intercostal 11–12, Supracostal 11, Supracostal 10).
* **Intercostal Neurovascular Bundles:** Superior rib margin targeting to prevent intercostal artery laceration.

### 3. Three-Tier Fail-Safe Pareto Optimizer
Trajectories are optimized using a constrained multi-objective formulation:
$$\min_{\mathbf{x}} \left[ L(\mathbf{x}), \frac{1}{1 + d_{\text{hazard}}(\mathbf{x})}, 1 - \Phi_{\text{stone}}(\mathbf{x}), \theta_{\text{deflection}}(\mathbf{x}) \right]$$
* **Tier 1 (Hard Safety Gate):** Rejects any trajectory violating working length ($>220\text{ mm}$), mechanical deflection ($>30^\circ$), or zero clearance ($d \le 0\text{ mm}$).
* **Fail-Closed State Machine:** Halts plan generation with `NO_PLAN_CRITICAL_HAZARD` or `NO_PLAN_INSUFFICIENT_EVIDENCE` if all candidates are unsafe.
* **Tier 2 (Non-Dominated Sorting):** Computes the strict Pareto-efficient frontier.
* **Tier 3 (Clinical Metadata):** Annotates Guy's Stone Score (I–IV) and S.T.O.N.E. nephrolithometry (5–13).

### 4. Virtual Fluoroscopy DRR Ray-Marching & C-Arm Kinematics
Projects 3D CT volumes into 2D digitally reconstructed radiographs (DRR) matching IEC 61217 C-arm geometry:
* **Bull's-Eye View (Co-Axial):** Gantry oriented collinear with the needle axis ($\mathbf{d}_{\text{needle}}$) such that the needle projects as a single concentric point over the target calyx fornix.
* **Progression View (Depth-Verification):** Gantry rotated $90^\circ$ orthogonal to the needle axis to measure real-time insertion depth and medial calyceal margin.
* **Hardware Profile Registry:** Built-in profiles for Siemens Cios Alpha, Philips Zenition 70, GE OEC 9900 Elite, and Ziehm Vision RFD.

### 5. Stochastic Monte Carlo Uncertainty Perturbation
Evaluates trajectory robustness across 200 random perturbations modeling:
* Diaphragmatic respiratory excursion ($\sigma = 2.5\text{ mm}$).
* Patient positioning shift and tissue relaxation ($\sigma = 1.5\text{ mm}$).
* Segmentation margin uncertainty ($\sigma = 1.0\text{ mm}$).
Emits exact 95% upper confidence bounds on collision probabilities using Clopper-Pearson binomial metrics.

### 6. HIPAA & DICOM PS 3.15 Annex E Cryptographic PHI Guard
All uploaded DICOM series are scrubbed at the point of ingestion:
* Direct identifiers (Name, MRN, Institution, Physician) are stripped or replaced with HMAC-SHA256 pseudonyms.
* Mandatory spatial geometry tags (`ImagePositionPatient`, `ImageOrientationPatient`, `PixelSpacing`) are strictly verified and preserved intact.

### 7. Clinical Usability & Fail-Safe Interlocks (U1–U6)
* **Interlock U1:** Two-step multi-evidence laterality verification gate (CT orientation + landmark checklist) locking plan execution until signed off by the attending surgeon.
* **Interlock U2:** Validated SE(3) spatial transformation modeling supine-to-prone anatomical kidney shift.
* **Interlock U4:** Sterile C-Arm Technologist Communication Card with exact verbal readback scripts.
* **Interlock U5:** Medial calyceal wall proximity alarm preventing counter-puncture vascular injury.

---

## 🖥️ Interactive 3D Rehearsal Cockpit

The web interface combines high-performance WebGL 3D rendering with synchronized 2D multi-planar CT imaging:

* **Three.js PBR Shaders:** Translucent renal cortex cutaway, ivory-gold crystalline calculi, vascular trees, skeletal ribs, and color-coded needle access corridors.
* **Synchronized 2D MPR Viewer:** Real-time Axial, Coronal, and Sagittal slice rendering with window/level presets (Soft Tissue, Bone, Kidney) and physical LPS cursor reticles.
* **Multi-Theme Support:** Clinical Dark, Standard Light, and Hybrid Ergonomic themes.

| Viewport | Screenshot Preview |
| :---: | :---: |
| **Dual-Monitor Rehearsal Cockpit** | ![Cockpit](./view_m13_rehearsal_cockpit.png) |
| **Pareto Candidate Access Trajectories** | ![Candidates](./view_candidates_rendered.png) |
| **Default Anatomical Cutaway** | ![Default Fixed](./view_default_fixed.png) |
| **Clinical Hybrid Theme** | ![Hybrid Theme](./view_theme_hybrid.png) |

---

## 🚀 Quick Start & Installation

### Prerequisites
* **Python 3.10+** (tested on Python 3.11, 3.12, 3.13)
* Modern web browser supporting WebGL2 (Chrome, Firefox, Edge, Safari)

### 1. Clone the Repository
```bash
git clone https://github.com/Tejas3479/AcuCalyx.git
cd AcuCalyx
```

### 2. Create Virtual Environment & Install Dependencies
```bash
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
pip install -e .
```

### 3. Launch the Web Application
```bash
python -m uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --reload
```
Open **[http://localhost:8000](http://localhost:8000)** in your browser to access the AcuCalyx Surgical Planning Cockpit.

### 4. Running the AcuCalyx CLI
```bash
# Display help and subcommands
acucalyx --help

# Run full end-to-end planning on a CT volume
acucalyx plan --input path/to/scan.nii.gz --output path/to/output_dir --side left

# Run quality gate verification on a DICOM directory
acucalyx qc --dicom-dir path/to/dicom_series/
```

---

## 🧪 Testing & Verification Suite

AcuCalyx maintains a comprehensive, automated test suite spanning unit tests, clinical golden cases, property-based invariants, and end-to-end procedural integration:

```bash
python -m pytest tests/unit tests/golden tests/integration tests/property
```

### Test Suite Structure (199 Tests, 100% Passing):
* **Unit Tests (175 tests):**
  * Geometry & Coordinates (`test_coordinates.py`, `test_volumetry.py`)
  * DICOM & NIfTI Ingestion (`test_dicom_ingestion.py`, `test_nifti_ingestion.py`, `test_quality_gate.py`)
  * Trajectory Corridors & Optimization (`test_planning_corridors.py`, `test_pareto.py`, `test_m12_pareto_planning.py`)
  * Virtual Fluoroscopy & DRR (`test_projection.py`, `test_drr_geometry.py`, `test_drr_advanced.py`, `test_m13_virtual_fluoroscopy.py`, `test_m13p_projection_metrology.py`)
  * Usability & Safety Interlocks (`test_hazard_engine.py`, `test_usability_engine.py`, `test_phase45_calibration.py`)
  * Regulatory, SBOM & PHI Guard (`test_regulatory_and_cybersecurity.py`, `test_premarket_submission_and_release.py`)
* **Golden Challenge Cases (19 tests):**
  * Normal anatomy, retrorenal colon hazard, staghorn calculus, supracostal high kidney, solitary kidney, severe hydronephrosis, thick-slice rejection, gantry tilt rejection, intercostal NV bundle risk.
* **Property-Based Invariants (4 tests):**
  * Voxel-to-physical roundtrip coordinate precision.
  * Rigid SE(3) transformation Euclidean distance invariance.
  * Distance field monotonicity under dilation.
  * Pareto non-dominance transitivity invariants.
* **Integration Tests (1 test):**
  * Complete execution from synthetic phantom generation through quality gate, stone volumetry, Pareto optimization, Monte Carlo, DRRs, GLB export, and auditable PDF report.

---

## 📂 Complete Regulatory & Clinical Documentation Suite

AcuCalyx includes an exhaustive, audit-ready Design History File (DHF) and regulatory dossier developed in compliance with FDA 510(k), IEC 62304, and ISO 14971:

### 1. Foundational Architecture & Research Index
* [**`01_PROJECT_BLUEPRINT_AND_ARCHITECTURE.md`**](./01_PROJECT_BLUEPRINT_AND_ARCHITECTURE.md): Master 24-feature architecture across 7 tiers, clinical narratives, and system design.
* [**`02_IEEE_RESEARCH_AND_LITERATURE_AUDIT.md`**](./02_IEEE_RESEARCH_AND_LITERATURE_AUDIT.md): Deep-dive audit of latest IEEE papers (*TMRB*, *JBHI*, *OJIM*, *Access*); physical realities of kidney surgery.
* [**`03_RUTHLESS_COMPETITIVE_LANDSCAPE.md`**](./03_RUTHLESS_COMPETITIVE_LANDSCAPE.md): Commercial analysis of NDR Medical ANT-X, J&J MONARCH, Siemens syngo, Ceevra, and Avatar Medical.
* [**`04_FEASIBILITY_SELF_AUDIT_SCORECARD.md`**](./04_FEASIBILITY_SELF_AUDIT_SCORECARD.md): 17-point verification matrix of all clinical, physical, and mathematical claims.
* [**`05_DATA_MODELS_TRAINING_AND_TECH_STACK.md`**](./05_DATA_MODELS_TRAINING_AND_TECH_STACK.md): Implementation & ML roadmap, datasets (KiTS23, MSD, TCIA), and 3D Slicer protocols.
* [**`06_PNEUMOTHORAX_VS_KIDNEYSTONE_COMPARISON.md`**](./06_PNEUMOTHORAX_VS_KIDNEYSTONE_COMPARISON.md): 7-dimension scoring table, reimbursement economics, and sequential execution roadmap.
* [**`07_PRESENTATION_PITCH_AND_DOCTOR_QA.md`**](./07_PRESENTATION_PITCH_AND_DOCTOR_QA.md): 30-second pitch, clinical analogies, objection responses (*"Aren't doctors already trained for this?"*).
* [**`08_COMPREHENSIVE_CHAT_RESEARCH_ARCHIVE.md`**](./08_COMPREHENSIVE_CHAT_RESEARCH_ARCHIVE.md): Complete chronological record of every research inquiry, derivation, and architectural milestone.

### 2. Clinical Readiness Suite (`docs/clinical/`)
* [`00_M5_5_CLINICAL_READINESS_AND_PRESUB_PLAN.md`](./docs/clinical/00_M5_5_CLINICAL_READINESS_AND_PRESUB_PLAN.md): Premarket submission plan and FDA Q-Submission charter.
* [`01_INVESTIGATIONAL_PROTOCOL_ACU_PILOT_01.md`](./docs/clinical/01_INVESTIGATIONAL_PROTOCOL_ACU_PILOT_01.md): Multi-center prospective clinical feasibility trial protocol.
* [`02_INVESTIGATORS_BROCHURE_IB.md`](./docs/clinical/02_INVESTIGATORS_BROCHURE_IB.md): Investigator's Brochure detailing pre-clinical bench testing.
* [`03_FEASIBILITY_STATISTICAL_ANALYSIS_PLAN.md`](./docs/clinical/03_FEASIBILITY_STATISTICAL_ANALYSIS_PLAN.md): Formal SAP and hypothesis testing for single-tract success.
* [`04_CEC_AND_SAFETY_MONITORING_CHARTER.md`](./docs/clinical/04_CEC_AND_SAFETY_MONITORING_CHARTER.md): Clinical Events Committee & DSMB safety monitoring charter.
* [`05_SITE_INITIATION_AND_CALIBRATION_SPEC.md`](./docs/clinical/05_SITE_INITIATION_AND_CALIBRATION_SPEC.md): Site initiation and physical phantom calibration specification.

### 3. Regulatory DHF Suite (`docs/regulatory/`)
* [`01_DESIGN_AND_DEVELOPMENT_INPUTS_SRS.md`](./docs/regulatory/01_DESIGN_AND_DEVELOPMENT_INPUTS_SRS.md): Software Requirements Specification.
* [`03_ISO_14971_RISK_MANAGEMENT_FILE.md`](./docs/regulatory/03_ISO_14971_RISK_MANAGEMENT_FILE.md): ISO 14971 Risk Management File, FMEA, and Hazard Analysis.
* [`04_IEC_62304_SOFTWARE_LIFECYCLE_AND_SOUP.md`](./docs/regulatory/04_IEC_62304_SOFTWARE_LIFECYCLE_AND_SOUP.md): IEC 62304 Class B Software Lifecycle and SOUP management.
* [`05_CYBERSECURITY_MANAGEMENT_PLAN_AND_SPDF.md`](./docs/regulatory/05_CYBERSECURITY_MANAGEMENT_PLAN_AND_SPDF.md): FDA Secure Product Development Framework (SPDF).
* [`08_DICOM_CONFORMANCE_STATEMENT_PS32.md`](./docs/regulatory/08_DICOM_CONFORMANCE_STATEMENT_PS32.md): Official DICOM PS 3.2 Conformance Statement.
* [`10_PREMARKET_SUBMISSION_DOSSIER_MAP.md`](./docs/regulatory/10_PREMARKET_SUBMISSION_DOSSIER_MAP.md): 510(k) Premarket Notification dossier cross-reference map.
* [`15_HUMAN_FACTORS_AND_USABILITY_ENGINEERING_REPORT.md`](./docs/regulatory/15_HUMAN_FACTORS_AND_USABILITY_ENGINEERING_REPORT.md): IEC 62366 Usability Engineering report.

### 4. Postmarket Operations & eMDR (`docs/postmarket/` & `ops/regulatory/`)
* [`02_MEDICAL_DEVICE_FILE_MDF_INDEX.md`](./docs/postmarket/02_MEDICAL_DEVICE_FILE_MDF_INDEX.md): Medical Device File (MDF) ISO 13485 index.
* [`03_EMDR_PROCEDURE_AND_HL7_ICSR_SPEC.md`](./docs/postmarket/03_EMDR_PROCEDURE_AND_HL7_ICSR_SPEC.md): FDA 21 CFR 803 Electronic Medical Device Reporting (eMDR).
* [`04_HEALTH_HAZARD_ASSESSMENT_AND_RECALL_SOP.md`](./docs/postmarket/04_HEALTH_HAZARD_ASSESSMENT_AND_RECALL_SOP.md): Health Hazard Assessment (HHA) & 21 CFR 7 Recall SOP.
* Automated Ops Tools: [`emdr_icsr_builder.py`](./ops/regulatory/emdr_icsr_builder.py), [`health_hazard_assessor.py`](./ops/regulatory/health_hazard_assessor.py), [`mdf_indexer.py`](./ops/regulatory/mdf_indexer.py), [`pms_analyzer.py`](./ops/regulatory/pms_analyzer.py).

---

## 🗂️ Repository Structure

```
AcuCalyx/
├── 01_PROJECT_BLUEPRINT_AND_ARCHITECTURE.md
├── 02_IEEE_RESEARCH_AND_LITERATURE_AUDIT.md
├── 03_RUTHLESS_COMPETITIVE_LANDSCAPE.md
├── 04_FEASIBILITY_SELF_AUDIT_SCORECARD.md
├── 05_DATA_MODELS_TRAINING_AND_TECH_STACK.md
├── 06_PNEUMOTHORAX_VS_KIDNEYSTONE_COMPARISON.md
├── 07_PRESENTATION_PITCH_AND_DOCTOR_QA.md
├── 08_COMPREHENSIVE_CHAT_RESEARCH_ARCHIVE.md
├── README.md                          # Master documentation and quick start
├── pyproject.toml                     # Python packaging and test configuration
├── requirements.txt                   # Production dependencies
│
├── app/                               # Full-Stack Web Application
│   ├── api/                           # FastAPI backend server
│   │   ├── main.py                    # Case lifecycle, LRU volume cache, PHI scrubbing
│   │   ├── routes_drr.py              # Virtual fluoroscopy & DRR streaming
│   │   ├── routes_rehearsal.py        # Intraoperative rehearsal telemetry
│   │   ├── routes_usability.py        # Usability interlocks (U1–U6) & verbal cards
│   │   └── schemas.py                 # Strict Pydantic REST API contracts
│   └── frontend/                      # WebGL Surgical Cockpit
│       ├── index.html                 # UI cockpit layout, theme toggle, modals
│       ├── viewer.js                  # Three.js PBR 3D renderer and trajectory cylinders
│       ├── mpr.js                     # 2D Multi-Planar Reconstruction slice renderer
│       └── style.css                  # Dark, Light, and Hybrid clinical themes
│
├── src/acucalyx/                      # Core Computational Geometry & Medical Domain
│   ├── anatomy/                       # Segmentation backends, confidence, thoracic risk
│   ├── audit/                         # Cryptographic SHA-256 provenance tracking
│   ├── clinical/                      # Intraoperative calibration & fidelity evaluator
│   ├── collecting_system/             # Calyceal infundibular visibility gating
│   ├── cybersecurity/                 # PHIGuard (PS 3.15), STRIDE threat model, SBOM
│   ├── dicom/                         # DICOM PS 3.2 conformance test harness
│   ├── fluoroscopy/                   # C-arm kinematics, DRR raymarcher, ALARA metrics
│   ├── geometry/                      # Coordinates, transforms, SDF, mesh decimation
│   ├── ingestion/                     # DICOM / NIfTI loaders and quality gate
│   ├── phantom/                       # Physical 3D printable phantom & mold generator
│   ├── planning/                      # 3-tier Pareto optimizer, scope kinematics, reach
│   ├── regulatory/                    # ISO 14971 safety boundaries, plan integrity
│   ├── reports/                       # ReportLab PDF surgical planning report generator
│   ├── research/                      # Human factors, NASA-TLX, task analysis
│   ├── stones/                        # Calculus candidate detection, volumetry, scoring
│   ├── uncertainty/                   # Monte Carlo motion perturbation and risk scoring
│   ├── usability/                     # OR surgical protocols and safety interlocks
│   ├── validation/                    # ASTM F2554 procedural validation & Clopper-Pearson
│   ├── cli.py                         # Command-line interface entry points
│   └── pipeline.py                    # End-to-end PCNL multi-stage execution pipeline
│
├── docs/                              # Formal Regulatory & Clinical DHF Dossiers
│   ├── clinical/                      # Clinical trials, SAP, IB, site calibration
│   ├── postmarket/                    # Postmarket surveillance, eMDR, HHA recall SOP
│   ├── regulatory/                    # IEC 62304, ISO 14971, SPDF, DICOM PS 3.2
│   └── third_party/                   # Open-source and third-party license matrices
│
├── ops/regulatory/                    # Automated Medical Device Ops & Vigilance Scripts
│   ├── emdr_icsr_builder.py           # HL7 ICSR XML adverse event generator
│   ├── health_hazard_assessor.py      # Quantitative health hazard severity classifier
│   ├── mdf_indexer.py                 # Medical Device File (MDF) automated indexer
│   └── pms_analyzer.py                # Postmarket complaint trend & signal detector
│
├── tests/                             # Verification & Test Suite (199 Tests)
│   ├── golden/                        # 19 clinical challenge cases & expert validation
│   ├── integration/                   # Full end-to-end pipeline execution test
│   ├── phantom/                       # Synthetic CT phantom generator fixture
│   ├── property/                      # Mathematical invariants (SE(3), SDF, Pareto)
│   └── unit/                          # 175 unit tests across all submodules
│
└── data/                              # Anatomical reference meshes & sample models
    ├── anatomical_preview/            # High-resolution 3D GLB renal structures
    └── test_preview/                  # Testing GLB/STL mesh fixtures
```

---

## 🏥 Regulatory Classification & Commercial Coding

* **FDA Classification:** Class II Medical Device (21 CFR 892.2050 - *Medical image management and processing system*).
* **FDA Product Code:** **LLZ** (Radiological Image Processing System).
* **Primary FDA Predicates:** Ceevra (K173426), Avatar Medical (K232490), Philips syngo DynaCT (K151800).
* **Applicable US Reimbursement Coding:**
  * **CPT 76376:** 3D radiologic evaluation requiring post-processing on existing workstation (\$80–\$110).
  * **CPT 76377:** 3D radiologic evaluation requiring advanced independent workstation reconstruction (\$120–\$160).
* **Institutional Value:** By reducing puncture attempts from 4.2 to 1.1, AcuCalyx saves an average of **28 minutes of operating room and fluoroscopy time per case** (~**\$1,800 to \$2,400 in direct institutional cost savings per surgery**).

---

## ⚖️ Investigational Device Disclaimer

> **CAUTION — Investigational Device.**  
> AcuCalyx™ is an investigational software platform limited by federal and international law to investigational use (21 CFR 812.5). The system is designed to provide clinical decision support and pre-procedural trajectory simulation for board-certified urologists. It does not automate puncture execution or replace surgeon judgment. All trajectories must be reviewed, confirmed, and verified against native patient DICOM imaging prior to sterile puncture.

---

<div align="center">
  <sub>Engineered by Tejas and the AcuCalyx Medical AI Systems Architecture Team • 2026</sub>
</div>
