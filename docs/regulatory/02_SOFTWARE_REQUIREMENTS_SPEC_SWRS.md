# AcuCalyx™ Software Requirements Specification (SwRS)

**Document ID:** SWRS-ACU-001  
**Version:** 1.0 (Frozen)  
**Governing Standard:** IEC 62304:2006 + AMD 1:2015 Clause 5.2  
**Software Safety Level:** IEC 62304 Class C Architectural Rigour  
**Traceability Tier:** Level 6 (Software Requirements)  

---

## 1. Introduction & Software Identification

This Software Requirements Specification (SwRS) establishes the detailed functional, algorithmic, safety, cybersecurity, and performance requirements for **AcuCalyx™ Core**.

In accordance with IEC 62304 Clause 5.2, each software requirement defines:
- Detailed functional and algorithmic behavior
- Exact input data types, valid ranges, and validation constraints
- Deterministic processing rules and mathematical transformations
- Structured output types and state mutations
- Failure modes, error handling, and fail-closed conditions
- Software Safety Classification (Class C, Class B, or Class A)
- Traceability upstream to System Requirements (SRS) and Risk Controls (RC)

---

## 2. Software Safety Partitioning & Classification

Per IEC 62304 Clause 4.3 and the AcuCalyx Architectural Partitioning Plan:
- **Class C Software Requirements:** Software items whose unmitigated failure could directly contribute to death or serious injury (e.g. erroneous trajectory calculation leading to colonic, vascular, or pleural transfixion; coordinate axis inversion; silent tampering).
- **Class B Software Requirements:** Presentation of safety-critical clinical warnings, interlock status badges, and C-arm verbal scripts, where clinician intervention is possible.
- **Class A Software Requirements:** Non-safety UI presentation infrastructure (Three.js WebGL orbit/zoom controls, cosmetic color shading, responsive layout styling).

---

## 3. Granular Software Requirements Register

### 3.1 DICOM Ingestion & Ingestion Quality Gate (SwRS-001 to SwRS-004)

#### SwRS-001: DICOM Series Validation & Modality Check
- **Safety Class:** Class C
- **Upstream Link:** SRS-001, SRS-017 | **Hazard Link:** `HAZ-IMG-01`
- **Input:** Directory path or list of DICOM files.
- **Processing:**
  1. Inspect DICOM header tag `(0008,0060) Modality`. Must equal `"CT"`. Non-CT (e.g. MR, XA, SC) rejected immediately with `InvalidModalityError`.
  2. Inspect tag `(0008,0008) ImageType`. Localizer / scout images (`"LOCALIZER"` in ImageType) must be stripped.
  3. Verify homogeneous `(0020,0052) FrameOfReferenceUID` across all slices.
- **Output:** Validated list of CT slice datasets.
- **Failure Mode / Error Code:** `ERR_DICOM_INVALID_MODALITY`, `ERR_DICOM_INCONSISTENT_FOR_UID`.

#### SwRS-002: Spatial Geometry & Slice Thickness Verification
- **Safety Class:** Class C
- **Upstream Link:** SRS-001 | **Hazard Link:** `HAZ-IMG-01`
- **Input:** Ordered CT slices.
- **Processing:**
  1. Compute slice thickness $\Delta z = |z_{i+1} - z_i|$ from `(0020,0032) ImagePositionPatient`.
  2. Assert $\Delta z \le 3.0\text{ mm}$. If $\Delta z > 3.0\text{ mm}$, raise `QualityGateError`.
  3. Verify slice spacing uniformity: $\max |\Delta z_i - \Delta z_{i-1}| \le 0.05\text{ mm}$.
- **Output:** Validated slice spacing parameter $\Delta z$ and ordered volume array.
- **Failure Mode / Error Code:** `ERR_QGATE_EXCESSIVE_SLICE_THICKNESS`, `ERR_QGATE_NONUNIFORM_SPACING`.

#### SwRS-003: Gantry Tilt Zero-Tolerance Gate
- **Safety Class:** Class C
- **Upstream Link:** SRS-002 | **Hazard Link:** `HAZ-IMG-02`
- **Input:** DICOM tags `(0018,1120) GantryDetectorTilt` and directional cosines `(0020,0037) ImageOrientationPatient`.
- **Processing:**
  1. Inspect `GantryDetectorTilt`. Assert $|tilt| \le 0.05^\circ$.
  2. Compute normal vector $\vec{n} = \vec{r}_{row} \times \vec{r}_{col}$. Assert collinearity with slice normal $[0, 0, 1]^T$ within $0.01\text{ rad}$.
- **Output:** Boolean certification `gantry_tilt_zero = True`.
- **Failure Mode / Error Code:** `ERR_QGATE_GANTRY_TILT_DETECTED`.

#### SwRS-004: Continuous LPS Coordinate Transformation
- **Safety Class:** Class C
- **Upstream Link:** SRS-017 | **Hazard Link:** `HAZ-ALG-01`
- **Input:** Voxel grid coordinates $(i, j, k) \in \mathbb{N}^3$, `ImagePositionPatient`, `ImageOrientationPatient`, `PixelSpacing`.
- **Processing:** Construct $4 \times 4$ rigid affine matrix $\mathbf{M}_{LPS \leftarrow Voxel}$:
  $$\begin{bmatrix} x \\ y \\ z \\ 1 \end{bmatrix}_{LPS} = \begin{bmatrix} X_x \cdot \Delta x & Y_x \cdot \Delta y & 0 & S_x \\ X_y \cdot \Delta x & Y_y \cdot \Delta y & 0 & S_y \\ X_z \cdot \Delta x & Y_z \cdot \Delta y & \Delta z & S_z \\ 0 & 0 & 0 & 1 \end{bmatrix} \begin{bmatrix} i \\ j \\ k \\ 1 \end{bmatrix}$$
- **Output:** Continuous 3D coordinates in LPS space (mm).
- **Failure Mode / Error Code:** `ERR_COORD_SINGULAR_AFFINE`.

---

### 3.2 Anatomical Segmentation & Hazard Modeling (SwRS-005 to SwRS-008)

#### SwRS-005: Multi-Organ Volumetric Mask Extraction
- **Safety Class:** Class C
- **Upstream Link:** SRS-003, SRS-004 | **Hazard Link:** `HAZ-SURG-01`, `HAZ-SURG-02`
- **Input:** 3D CT volume array in LPS coordinates.
- **Processing:** Multi-backend segmentation inference (TotalSegmentator v2 or nnU-Net). Generates binary masks for:
  - Kidney (ipsilateral and contralateral)
  - Renal pelvicalyceal system
  - Renal calculi / stones
  - Retrorenal colon (descending / ascending)
  - Pleural reflections and lungs
  - Skeletal structures (ribs 10, 11, 12, spine)
  - Major vasculature (aorta, inferior vena cava, renal vessels)
- **Output:** Multi-class label map dictionary $\mathbf{M}_{labels}$.
- **Failure Mode / Error Code:** `ERR_SEG_INFERENCE_FAILURE`, `ERR_SEG_DISCONNECTED_ORGAN`.

#### SwRS-006: Visceral Hazard Distance Fields & Clearance Verification
- **Safety Class:** Class C
- **Upstream Link:** SRS-003, SRS-004 | **Hazard Link:** `HAZ-SURG-01`, `HAZ-SURG-02`
- **Input:** Binary masks for colon, pleura, aorta, IVC.
- **Processing:**
  1. Compute Euclidean Distance Transform (EDT) field $\Phi_{hazard}(\mathbf{x})$ for each visceral organ.
  2. For candidate trajectory line segment $\mathbf{L}(t) = \mathbf{P}_{skin} + t (\mathbf{P}_{target} - \mathbf{P}_{skin})$, evaluate:
     $$d_{min}(hazard) = \min_{t \in [0, 1]} \Phi_{hazard}(\mathbf{L}(t))$$
  3. Enforce clearances: $d_{min}(colon) \ge 15.0\text{ mm}$, $d_{min}(pleura) \ge 10.0\text{ mm}$, $d_{min}(great\_vessels) \ge 20.0\text{ mm}$.
- **Output:** Clearance distances and boolean hazard containment flag.
- **Failure Mode / Error Code:** `ERR_HAZARD_COLON_VIOLATION`, `ERR_HAZARD_PLEURAL_VIOLATION`.

#### SwRS-007: Calyx Forniceal Target & Coaxial Zone Extraction
- **Safety Class:** Class C
- **Upstream Link:** SRS-005 | **Hazard Link:** `HAZ-SURG-03`
- **Input:** Pelvicalyceal mask and stone coordinates.
- **Processing:**
  1. Identify target calyx cup harboring or nearest to stone burden.
  2. Compute calyx centroid $\mathbf{C}_{calyx}$ and infundibular neck axis vector $\vec{v}_{inf}$.
  3. Define allowable puncture cone with apex at fornix and half-angle $\theta_{cone} \le 20.0^\circ$ aligned with $\vec{v}_{inf}$.
- **Output:** 3D forniceal target point $\mathbf{P}_{target}$ and unit vector $\vec{v}_{coaxial}$.
- **Failure Mode / Error Code:** `ERR_TARGET_INDETERMINATE_FORNIX`.

#### SwRS-008: Rigid Scope Reachability Computation
- **Safety Class:** Class C
- **Upstream Link:** SRS-006 | **Hazard Link:** `HAZ-PLAN-01`
- **Input:** Target calyx axis, secondary calyx positions, stone locations.
- **Processing:** Compute subtended infundibulo-pelvic angle $\alpha$ between candidate puncture axis and secondary calyces. If $\alpha < 90.0^\circ$, classify secondary calyx as reachable only via flexible nephroscope.
- **Output:** Reachability classification map (Rigid Reachable vs Flexible Required).
- **Failure Mode / Error Code:** `None` (Deterministic geometric classification).

---

### 3.3 Trajectory Optimization & Kinematics (SwRS-009 to SwRS-012)

#### SwRS-009: 5-Objective Pareto Trajectory Ranking
- **Safety Class:** Class C
- **Upstream Link:** SRS-018 | **Hazard Link:** `HAZ-PLAN-02`
- **Input:** Candidate skin entry points $\mathbf{P}_{skin} \in \mathcal{S}_{flank}$, target $\mathbf{P}_{target}$, hazard distance fields.
- **Processing:** Evaluate 5 objective fitness functions:
  1. $f_1$: Parenchymal tract length (minimize)
  2. $f_2$: Visceral hazard clearance margin (maximize)
  3. $f_3$: Infundibular coaxial alignment angle (minimize deviation)
  4. $f_4$: Caliceal stone reachability score (maximize)
  5. $f_5$: Thoracic / intercostal clearance margin (maximize)
  Extract non-dominated Pareto frontier using Kung's / NSGA-II algorithm.
- **Output:** Ranked list of Pareto-optimal trajectories $\mathcal{T}^*$.
- **Failure Mode / Error Code:** `ERR_PLAN_NO_FEASIBLE_TRAJECTORY` (Fail-Closed).

#### SwRS-010: C-Arm Gantry Angle Roadmapping
- **Safety Class:** Class C
- **Upstream Link:** SRS-008 | **Hazard Link:** `HAZ-DEV-01`
- **Input:** Trajectory vector $\vec{t} = \frac{\mathbf{P}_{target} - \mathbf{P}_{skin}}{\|\mathbf{P}_{target} - \mathbf{P}_{skin}\|}$.
- **Processing:**
  1. Compute Bullseye View (en-face projection): Source-detector axis collinear with $\vec{t}$.
     $$\text{LAO/RAO} = \arctan2(t_x, t_z), \quad \text{CRA/CAU} = \arcsin(-t_y)$$
  2. Compute Progression / Depth View: Rotate gantry $90.0^\circ$ perpendicular to $\vec{t}$.
  3. Enforce kinematic envelope: $|\text{LAO/RAO}| \le 45.0^\circ$, $|\text{CRA/CAU}| \le 30.0^\circ$.
- **Output:** C-arm primary and secondary angle pairs $(\alpha_{bullseye}, \beta_{bullseye})$ and $(\alpha_{prog}, \beta_{prog})$.
- **Failure Mode / Error Code:** `ERR_CARM_KINEMATIC_LIMIT_EXCEEDED`.

#### SwRS-011: Virtual Fluoroscopy (DRR) Forward Projection
- **Safety Class:** Class C
- **Upstream Link:** SRS-015 | **Hazard Link:** `HAZ-USE-04`
- **Input:** 3D CT volume, C-arm source position $\mathbf{S}$, detector plane coordinates $\mathcal{D}$, projection matrix $\mathbf{P}_{carm}$.
- **Processing:** Raymarch Beer-Lambert attenuation integral:
  $$I(u, v) = I_0 \exp\left(-\int_0^L \mu(\mathbf{r}(s)) ds\right)$$
  Synthesizes 2D projection with superimposed calibrated virtual needle marker.
- **Output:** 2D DRR intensity image array $(U \times V)$.
- **Failure Mode / Error Code:** `ERR_DRR_OUT_OF_BOUNDS_PROJECTION`.

#### SwRS-012: Radiation ALARA Dose Estimation
- **Safety Class:** Class B
- **Upstream Link:** SRS-016 | **Hazard Link:** `HAZ-RAD-01`
- **Input:** Planned C-arm angles, patient skin thickness, projection path length.
- **Processing:** Calculate relative dose area product (DAP) index and organ dose hazard weighting based on beam path traversal of radiation-sensitive tissues.
- **Output:** ALARA dose index report with recommended beam collimation.
- **Failure Mode / Error Code:** `None` (Advisory informational calculation).

---

### 3.4 Runtime Safety Interlocks & Usability Layer (SwRS-013 to SwRS-017)

#### SwRS-013: Interlock U1 — Pre-Puncture Laterality Gate
- **Safety Class:** Class C
- **Upstream Link:** SRS-010 | **Hazard Link:** `HAZ-USE-01`
- **Input:** DICOM tag `(0020,0020) PatientOrientation`, segmented kidney centroid $y_{LPS}$, surgeon confirmed laterality enum (`LEFT` | `RIGHT`).
- **Processing:** Assert all 3 laterality sources match identically. If any mismatch occurs, lock planning pipeline and display `ERR_LATERALITY_MISMATCH`.
- **Output:** Cryptographically certified laterality token.
- **Failure Mode / Error Code:** `ERR_LATERALITY_MISMATCH` (Full Execution Block).

#### SwRS-014: Interlock U2 — Surgical Position SE(3) Transform Verification
- **Safety Class:** Class C
- **Upstream Link:** SRS-011 | **Hazard Link:** `HAZ-USE-02`
- **Input:** CT acquisition pose (typically `SUPINE`), OR procedural pose (`PRONE` | `MODIFIED_VALDIVIA`).
- **Processing:** Apply verified SE(3) coordinate transformation $\mathbf{T}_{OR \leftarrow CT}$. Validate that transformed needle entry corresponds to dorsal/flank skin.
- **Output:** Transformed surgical trajectory and C-arm angles.
- **Failure Mode / Error Code:** `ERR_POSE_TRANSFORM_INVALID`.

#### SwRS-015: Interlock U5 — Depth Boundary & Medial Counter-Puncture Alarm
- **Safety Class:** Class C
- **Upstream Link:** SRS-009 | **Hazard Link:** `HAZ-SURG-04`
- **Input:** Planned needle progression depth $d_{current}$, maximum allowable depth $d_{target} + 10.0\text{ mm}$, medial calyx boundary.
- **Processing:** If needle advance exceeds target fornix by $>5.0\text{ mm}$ or approaches renal hilum/vessels within $15.0\text{ mm}$, trigger critical visual and auditory counter-puncture alert.
- **Output:** Alarm state flag: `ALARM_COUNTER_PUNCTURE_CRITICAL`.
- **Failure Mode / Error Code:** `ERR_DEPTH_EXCEEDS_SAFE_BOUNDARY`.

#### SwRS-016: Interlock U6 — Stale Plan Invalidation & State Machine
- **Safety Class:** Class C
- **Upstream Link:** SRS-012 | **Hazard Link:** `HAZ-USE-03`
- **Input:** Plan state (`DRAFT`, `APPROVED`, `STALE`), patient registration event, CT re-import event.
- **Processing:** If any input parameter (patient pose, slice data, target calyx) is altered after approval, plan state immediately transitions to `STALE`. Stale plans are blocked from export and C-arm display.
- **Output:** Certified plan state enum.
- **Failure Mode / Error Code:** `ERR_PLAN_SUPERSEDED_STALE`.

#### SwRS-017: C-Arm 4-Step Closed-Loop Verbal Script Generator
- **Safety Class:** Class B
- **Upstream Link:** SRS-019 | **Hazard Link:** `HAZ-USE-05`
- **Input:** Approved plan C-arm parameters.
- **Processing:** Format structured verbal readback script:
  - Step 1: Calyx ID ("Lower Pole Posterior")
  - Step 2: Projection Mode ("Bullseye En-Face")
  - Step 3: Gantry Angles ("LAO 25 degrees, Caudal 10 degrees")
  - Step 4: Verification ("Confirm Laser Centered on Flank Mark")
- **Output:** Formatted readback card string and transposition error detector.
- **Failure Mode / Error Code:** `None`.

---

### 3.5 Cybersecurity & Data Integrity (SwRS-018 to SwRS-022)

#### SwRS-018: Cryptographic Plan Canonical Fingerprint
- **Safety Class:** Class C
- **Upstream Link:** SRS-013 | **Hazard Link:** `HAZ-CYB-01`
- **Input:** Surgical plan data object.
- **Processing:**
  1. Serialize plan parameters into deterministic canonical JSON (sorted keys, 4 decimal places for floats, ISO 8601 UTC timestamps).
  2. Compute $\text{Fingerprint} = \text{SHA-256}(\text{CanonicalPlanJSON})$.
  3. Attach fingerprint to plan header. Verify on every reload, transfer, or display.
- **Output:** SHA-256 hex string (64 characters).
- **Failure Mode / Error Code:** `ERR_PLAN_TAMPER_DETECTED` (`PLAN_HASH_MISMATCH`).

#### SwRS-019: DICOM PS 3.15 Annex E Basic Profile De-Identification
- **Safety Class:** Class B
- **Upstream Link:** SRS-014 | **Hazard Link:** `HAZ-CYB-02`
- **Input:** Raw DICOM dataset.
- **Processing:** Apply attribute action table per PS 3.15 Annex E:
  - Strip direct patient identifiers (`PatientName`, `PatientID`, `PatientBirthDate`, etc.).
  - Retain mandatory geometric and spatial tags (`PixelSpacing`, `ImagePositionPatient`, `ImageOrientationPatient`, `SliceThickness`, `Rows`, `Columns`).
  - Compute keyed HMAC-SHA256 pseudonymized identifiers for longitudinal research linkage.
- **Output:** De-identified DICOM dataset.
- **Failure Mode / Error Code:** `ERR_DEIDENTIFICATION_FAILED`.

#### SwRS-020: Machine-Readable SBOM Generation
- **Safety Class:** Class A (Engineering tool)
- **Upstream Link:** FD&C Act §524B | **Hazard Link:** `HAZ-CYB-03`
- **Input:** Python runtime environment and package lockfile.
- **Processing:** Generate NTIA-compliant SBOM in CycloneDX and SPDX JSON formats, capturing: Supplier, Component, Version, SHA-256, License, and Dependency Depth.
- **Output:** CycloneDX / SPDX JSON document.
- **Failure Mode / Error Code:** `ERR_SBOM_GENERATION_FAILED`.

#### SwRS-021: Known Exploited Vulnerability (CISA KEV) Auditing
- **Safety Class:** Class A (Engineering tool)
- **Upstream Link:** FD&C Act §524B | **Hazard Link:** `HAZ-CYB-03`
- **Input:** SBOM component register, CISA KEV catalog feed.
- **Processing:** Cross-reference all direct and transitive dependencies against CISA KEV and CVE databases. Flag any component with CVSS score $\ge 7.0$ or listed on KEV.
- **Output:** Vulnerability audit report.
- **Failure Mode / Error Code:** `ERR_CRITICAL_CVE_DETECTED`.

#### SwRS-022: Role-Based Access Control (RBAC) Enforcement
- **Safety Class:** Class B
- **Upstream Link:** FD&C Act §524B | **Hazard Link:** `HAZ-CYB-04`
- **Input:** User identity token, requested action (`PLAN_APPROVE`, `CALIBRATE`, `AUDIT_LOG_READ`).
- **Processing:** Assert that only authenticated users with role `ATTENDING_SURGEON` can execute `PLAN_APPROVE`. Deny privilege escalation attempts.
- **Output:** Boolean authorization decision.
- **Failure Mode / Error Code:** `ERR_UNAUTHORIZED_ROLE_ACCESS`.
