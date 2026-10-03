# AcuCalyx™ Clinical Investigation Plan (CIP): Feasibility Pilot

**Protocol Title:** Prospective Multi-Center Feasibility Study of AcuCalyx™ Computational Planning and Virtual Fluoroscopy Rehearsal in Percutaneous Nephrolithotomy  
**Protocol Identifier:** `ACU-PILOT-2026-01`  
**Document Version:** 1.0 (Frozen)  
**Governing Standard:** ISO 14155:2026 Clause 5 / GCP / 21 CFR Part 812  
**Target Sample Size:** $N = 30$ Patients (15 Intervention vs. 15 Control)  
**Investigational Centers:** 2 Academic Medical Centers (4 Credentialed Urologists)  

---

## 1. Study Synopsis & Scientific Rationale

### 1.1 Incremental Clinical Value & Hypothesis
Prior randomized clinical trials (e.g. 2023 3D reconstruction literature) have reported that virtual 3D models can improve access times and reduce radiation compared to unassisted fluoroscopy. However, generic 3D models do not solve the fundamental challenges of PCNL access: multi-objective trade-offs, visceral hazard clearance buffers, and C-arm projection geometry.

AcuCalyx™ Core evaluates an **advanced computational planning and rehearsal paradigm**:
1. **Multi-Objective Pareto Optimization:** Simultaneously evaluates parenchymal tract length, visceral hazard clearance, calyx infundibular coaxiality, rigid scope reach, and intercostal clearance.
2. **Visceral Hazard Distance Fields:** Guaranteed computational exclusion margins ($\ge 15.0\text{ mm}$ retrorenal colon buffer, $\ge 10.0\text{ mm}$ pleural reflection buffer).
3. **Forniceal Target Alignment:** Restricts needle puncture to a $\le 20.0^\circ$ coaxial cone through the papilla fornix, protecting interlobar vessels.
4. **Device-Calibrated Virtual Fluoroscopy (DRR):** Forward-projects synthetic C-arm fluoroscopy views at Bullseye and Progression angles, enabling pre-procedural visual rehearsal.
5. **Runtime Safety Interlocks:** Usability gates enforcing laterality consensus (U1), surgical position transformation (U2), and medial depth boundary alarms (U5).

**Primary Clinical Feasibility Hypothesis:**
Preoperative planning and virtual fluoroscopy rehearsal with AcuCalyx Core is feasible, integrates smoothly into the surgical workflow, achieves high surgeon plan adoption ($\ge 80\%$), reduces fluoroscopy access time, and maintains an uncompromised procedural safety profile without device-related serious adverse events.

---

## 2. Study Design & Randomization

### 2.1 Study Structure
- **Design:** Prospective, 2-center, randomized comparative feasibility pilot study.
- **Allocation Ratio:** 1:1 allocation (15 AcuCalyx-assisted access vs. 15 standard access control).
- **Stratification:** Stratified by stone complexity: Guy's Stone Score I/II (simple) vs. Guy's Stone Score III/IV (complex).
- **Intraoperative Access Guidance Standardization:**
  - **Both arms use the exact same intraoperative modality:** Standard biplanar fluoroscopy.
  - Ultrasound guidance is excluded from the initial access attempt in both arms, permitted only as a documented "rescue" modality if primary fluoroscopic access fails after $\ge 5$ attempts or 10 minutes. This isolates the computational planning intervention from imaging modality confounding.

### 2.2 Study Flow Chart

```
                        [Screening & Informed Consent]
                        (Adults >= 18, Planned PCNL, CT <= 2.5mm)
                                      │
                                      ▼
                        [Pre-Procedural Documentation]
                        • Surgeon independently documents intended calyx in eCRF
                        • Stone volumetry & Guy's Stone Score recorded
                                      │
                                      ▼
                        [1:1 Stratified Randomization]
                                      │
                 ┌────────────────────┴────────────────────┐
                 ▼                                         ▼
    [Arm 1: AcuCalyx-Assisted]                [Arm 2: Standard Care Control]
    • CT loaded into AcuCalyx                 • CT reviewed on PACS
    • Pareto access plan selected             • Surgeon performs standard mental
    • Virtual fluoroscopy rehearsal             trajectory planning
    • Plan adoption recorded (Cat 1–4)        • No AcuCalyx display available
                 │                                         │
                 └────────────────────┬────────────────────┘
                                      │
                                      ▼
                         [Intraoperative PCNL Access]
                         • Biplanar fluoroscopy guidance
                         • Timer START: First fluoro exposure for access
                         • Authoritative C-arm telemetry recorded
                         • Timer STOP: Needle tip in calyx + aspiration confirmed
                         • Pass count and adjustments logged
                                      │
                                      ▼
                         [Post-Access Evaluation]
                         • Plan-execution fidelity (Arm 1 post-access fluoroscopy)
                         • Procedural metrics & NASA-TLX cognitive workload
                                      │
                                      ▼
                         [Day 30 Safety & Efficacy Follow-Up]
                         • Clavien-Dindo complications (Grades I–V)
                         • Non-contrast CT stone-free rate (SFR)
```

---

## 3. Patient Eligibility & Population

### 3.1 Inclusion Criteria
1. Adult male or female patients aged $\ge 18$ years.
2. Unilateral renal calculus disease indicated for PCNL per EAU/AUA Guidelines.
3. Preoperative diagnostic abdominopelvic CT scan meeting the validated AcuCalyx operating envelope:
   - Axial slice thickness $\le 2.5\text{ mm}$ (target $\le 1.5\text{ mm}$).
   - Exact $0.0^\circ$ gantry detector tilt ($\pm 0.05^\circ$).
   - Contrast or non-contrast phase with confirmed collecting system observability.
4. Scheduled for elective PCNL under general anesthesia in the prone or modified supine (Valdivia-Galdakao) position.
5. Signed written Institutional Review Board (IRB) approved Informed Consent Form.

### 3.2 Exclusion Criteria
1. Pediatric patients (age $< 18$ years).
2. Emergency or trauma renal access.
3. Severe uncorrected bleeding disorder (INR $> 1.5$, platelets $< 50,000/\mu\text{L}$).
4. Active, untreated urosepsis or positive preoperative urine culture without targeted antimicrobial coverage.
5. Severe complex congenital anomalies (horseshoe kidney, pelvic ectopia, retrorenal spleen/liver) outside model validation envelope.
6. Morbid obesity ($\text{BMI} > 45.0\text{ kg/m}^2$).
7. Inability or refusal to provide informed consent.

---

## 4. Operational Endpoint Definitions

### 4.1 Fluoroscopy Access Time (Seconds)
- **Clock START:** Initiated at the exact time of the first fluoroscopic exposure or pedal depression dedicated to locating the kidney or needle alignment for renal access.
- **Clock STOP:** Objective confirmation of successful entry into the collecting system, defined as:
  1. Free aspiration of clear urine or injected retrograde contrast/methylene blue through the 18G puncture needle, **AND**
  2. Fluoroscopic confirmation of the needle tip within the target calyx on two orthogonal angles (e.g. $0^\circ$ AP and $30^\circ$ oblique).
- **Intermittent Exposures:** All fluoroscopy time ($t_{fluoro}$, s) accumulated by the C-arm between START and STOP is recorded directly from the generator counter.

### 4.2 Needle Pass Count & Success Rate
- **Definition of "Pass":**
  - **New Pass:** Complete withdrawal of the needle tip through the skin followed by a new puncture, OR withdrawal back into subcutaneous fat followed by angular redirection $>30^\circ$.
  - **Adjustment:** Advancing or retracting along the established needle tract ($\le 10\text{ mm}$ without angular redirection) counts as an adjustment within the same pass.
- **$\le 2$-Pass Success:** Successful calyx entry and fluid aspiration confirmed on Pass 1 or Pass 2 without abandonment.
- **Target Calyx Documentation:** Prior to patient positioning, the operating surgeon independently selects and logs the intended target calyx in the eCRF (e.g. "Right Lower Pole Posterior"). Both arms are evaluated against their pre-documented target to eliminate intervention-defined bias.

### 4.3 C-Arm Radiation Dosimetry
Authoritative values logged directly from the C-arm system console:
1. **Total Access Fluoroscopy Time ($t_{access}$, seconds).**
2. **Cumulative Procedure Fluoroscopy Time ($t_{total}$, seconds).**
3. **Kerma-Area Product (KAP / DAP, in $\text{Gy}\cdot\text{cm}^2$ or $\mu\text{Gy}\cdot\text{m}^2$).**
4. **Cumulative Air Kerma at Reference Point ($K_{a,r}$, in mGy).**
5. **Total Number of Fluoroscopic Exposures / Frames.**

### 4.4 Plan Adoption & Modification Rate (AcuCalyx Arm)
At the time of preoperative plan review, the surgeon's interaction is categorized:
- **Category 1 (Adopted Unchanged):** Surgeon accepts the #1 ranked Pareto candidate trajectory without alteration.
- **Category 2 (Alternative Selected):** Surgeon selects a lower-ranked but Pareto-optimal candidate from the suggested list.
- **Category 3 (Manually Modified):** Surgeon adjusts the skin entry point or calyx target point using manual cockpit calipers.
- **Category 4 (Rejected):** Surgeon rejects the AcuCalyx proposal entirely and plans access without the software (mandatory eCRF documentation of clinical rationale).

### 4.5 Plan-Execution Fidelity (Process Metric for AcuCalyx Arm)
Evaluated from post-access biplanar fluoroscopy before tract dilation:
1. **Target-Zone Containment:** Needle tip positioned within $\le 3.0\text{ mm}$ of the planned calyx fornix apex (Yes / No).
2. **Angular Deviation ($\Delta \theta$):** 3D angle between planned trajectory vector $\vec{t}_{plan}$ and actual needle vector $\vec{t}_{actual}$ (degrees).
3. **Depth Deviation ($\Delta d$):** Difference between planned skin-to-target depth and actual needle depth-stop (mm).

### 4.6 Safety & Complications (Clavien-Dindo Classification I–V)
All adverse events occurring from skin puncture through Day 30 post-op are recorded:
- **Grade I:** Minor deviations from normal post-op course (analgesics, antiemetics).
- **Grade II:** Complications requiring pharmacological treatment (blood transfusion, IV antibiotics).
- **Grade IIIa:** Surgical/radiological intervention without general anesthesia (percutaneous chest tube for pneumothorax, ureteral stent exchange, angioembolization under local anesthesia).
- **Grade IIIb:** Surgical intervention under general anesthesia (laparotomy/repair of colonic perforation, open surgical exploration).
- **Grade IVa/b:** Life-threatening complication requiring ICU admission (single or multi-organ failure).
- **Grade V:** Patient death.
- **Adjudication:** All events evaluated by an independent Clinical Events Committee (CEC) blinded to study arm where possible.

---

## 5. Investigational Centers & Quality Oversight

### 5.1 Center Selection
- **Site 1:** Academic Medical Center A (High-volume stone center; standard prone PCNL workflow).
- **Site 2:** Academic Medical Center B (Tertiary stone center; modified supine Valdivia PCNL workflow).
- **Surgeon Criteria:** 2 board-certified urologists per center with $\ge 50$ lifetime PCNL procedures who have passed the Site Initiation and Phantom Calibration Gate.

### 5.2 Decoupled Data Flow & Source Records
- AcuCalyx Core software exports a cryptographically bound `ClinicalSourceRecord` (JSON with SHA-256 fingerprint) capturing: Case ID, software build version, planned coordinates, C-arm angles, safety interlock states, and plan adoption category.
- Clinical research staff transcribe procedural metrics into an external, validated, 21 CFR Part 11 compliant Electronic Data Capture (EDC) system (e.g. REDCap).
- Independent biostatisticians conduct data analysis using validated R / SAS scripts.
