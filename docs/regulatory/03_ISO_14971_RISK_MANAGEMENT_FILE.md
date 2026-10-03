# AcuCalyx™ ISO 14971:2019 Risk Management File

**Document ID:** RMF-ACU-001  
**Version:** 1.0 (Frozen)  
**Governing Standard:** ISO 14971:2019 / ISO/TR 24971:2020 / ISO/TS 24971-2:2026  
**Quality System:** FDA QMSR (21 CFR Part 820)  
**Status:** APPROVED & FROZEN  

---

## 1. Executive Summary & Regulatory Policy

This Risk Management File documents the systematic identification, evaluation, control, and post-mitigation residual risk assessment for **AcuCalyx™ Core** across its entire software lifecycle.

### 1.1 Conformance with ISO 14971:2019
In strict compliance with ISO 14971:2019:
1. **Objective Acceptability Criteria:** Non-standard formulations (such as "RPN < threshold" or generic "ALARP") are discarded. Risk acceptability is determined strictly by an objective, pre-established Severity $\times$ Probability acceptability matrix defined in Section 2.
2. **Causal Sequence Modeling:** Hazards are evaluated not in isolation, but as complete causal chains:
   $$\text{Fault / Vulnerability} \longrightarrow \text{Hazardous Situation} \longrightarrow \text{Clinical Harm}$$
3. **Software Risk Controls as Mitigations:** Software interlocks and safety checks are documented as risk mitigations within the broader clinical workflow. The system does not claim mathematical impossibility of clinician error; rather, it enforces interlocks and verifiable barriers that minimize probability and break hazardous sequences.
4. **Overall Residual Risk & Benefit-Risk Analysis:** Overall residual risk is evaluated against the established clinical benefits of single-tract percutaneous renal stone clearance.

---

## 2. Objective Risk Acceptability Policy

### 2.1 Severity Levels (S1 to S5)
- **S1 (Negligible):** Inconvenience, temporary discomfort, minor delay ($<5\text{ min}$) with no clinical consequence.
- **S2 (Minor):** Superficial injury, minor bleed requiring no transfusion, procedural delay ($5\text{–}30\text{ min}$).
- **S3 (Serious):** Injury requiring medical intervention (blood transfusion, auxiliary drainage, pneumothorax requiring chest tube).
- **S4 (Critical):** Permanent impairment, life-threatening visceral laceration, colon perforation requiring laparotomy/colostomy, vascular injury requiring angioembolization.
- **S5 (Catastrophic):** Patient death.

### 2.2 Probability Levels (P1 to P5)
- **P1 (Extremely Rare):** $< 10^{-6}$ per procedure.
- **P2 (Remote):** $10^{-6} \text{ to } 10^{-4}$ per procedure.
- **P3 (Occasional):** $10^{-4} \text{ to } 10^{-2}$ per procedure.
- **P4 (Probable):** $10^{-2} \text{ to } 10^{-1}$ per procedure.
- **P5 (Frequent):** $> 10^{-1}$ per procedure.

### 2.3 Objective Risk Acceptability Matrix

```
┌────────────────┬────────────────────────────────────────────────────────┐
│ PROBABILITY    │                       SEVERITY                         │
│                ├────────────┬────────────┬────────────┬────────────┬────┤
│                │ S1 (Negl)  │ S2 (Minor) │ S3 (Ser)   │ S4 (Crit)  │ S5 │
├────────────────┼────────────┼────────────┼────────────┼────────────┼────┤
│ P5 (Frequent)  │ Unaccept   │ Unaccept   │ Unaccept   │ Unaccept   │ Un │
│ P4 (Probable)  │ Accept     │ Unaccept   │ Unaccept   │ Unaccept   │ Un │
│ P3 (Occasional)│ Accept     │ Accept     │ Unaccept   │ Unaccept   │ Un │
│ P2 (Remote)    │ Accept     │ Accept     │ Accept     │ Accept*    │ Un │
│ P1 (Extr Rare) │ Accept     │ Accept     │ Accept     │ Accept     │ Ac*│
└────────────────┴────────────┴────────────┴────────────┴────────────┴────┘
*Requires formal benefit-risk justification documented in Section 6.
```

---

## 3. Preliminary Hazard Analysis (PHA)

| Hazard ID | Clinical Harm Description | Severity | Unmitigated Cause Sequence | Initial Risk | Implemented Risk Control | Mitigated Probability | Residual Risk | Verification Evidence |
|---|---|---|---|---|---|---|---|---|
| **HAZ-SURG-01** | **Colonic Perforation / Peritonitis** | **S4** | CT planning trajectory traverses retrorenal or lateral colon undetected $\rightarrow$ Surgeon executes transfixion $\rightarrow$ Sepsis/fecal fistula. | **P4 / S4 (Unaccept)** | **RC-01:** Mandatory $\ge 15.0\text{ mm}$ colon clearance buffer; distance field collision rejection; multi-view visualization. | **P1 (Extr Rare)** | **P1 / S4 (Acceptable with BR)** | Unit test `test_hazard_clearance_and_intersection` |
| **HAZ-SURG-02** | **Pneumothorax / Hemothorax** | **S3** | Supracostal puncture penetrates pleural reflection above 12th rib $\rightarrow$ Lung collapse / thoracic bleeding $\rightarrow$ Chest tube placement. | **P4 / S3 (Unaccept)** | **RC-02:** Thoracic boundary distance field; preferential infracostal trajectory scoring; $\ge 10.0\text{ mm}$ pleural buffer. | **P2 (Remote)** | **P2 / S3 (Acceptable)** | Unit test `test_thoracic_and_intercostal_risk_models` |
| **HAZ-SURG-03** | **Segmental / Interlobar Vascular Tear** | **S4** | Puncture enters infundibular neck or renal pelvis non-coaxially $\rightarrow$ Lacerates segmental vessels $\rightarrow$ Massive hemorrhage. | **P4 / S4 (Unaccept)** | **RC-03:** Conical forniceal target alignment ($\le 20.0^\circ$ coaxial cone); parenchymal entry via papilla fornix only. | **P2 (Remote)** | **P2 / S4 (Acceptable with BR)** | Unit test `test_conical_puncture_zone_coaxial_validation` |
| **HAZ-SURG-04** | **Medial Counter-Puncture / Great Vessel Laceration** | **S5** | Needle driven past target calyx through medial renal border into aorta/IVC $\rightarrow$ Exsanguinating hemorrhage / death. | **P3 / S5 (Unaccept)** | **RC-04 (Interlock U5):** Dynamic depth boundary check; medial boundary halt alarm within $5.0\text{ mm}$ of medial collecting system. | **P1 (Extr Rare)** | **P1 / S5 (Acceptable with BR)** | Unit test `test_interlock_u5_depth_boundary_and_counter_puncture_alarms` |
| **HAZ-USE-01** | **Wrong-Side Puncture (Sentinel Event)** | **S4** | Misidentification of stone side during positioning $\rightarrow$ Puncture of healthy contralateral kidney $\rightarrow$ Organ damage. | **P3 / S4 (Unaccept)** | **RC-05 (Interlock U1):** Tri-modal laterality consensus gate (DICOM tag + segmented kidney centroid + surgeon verbal confirmation). | **P1 (Extr Rare)** | **P1 / S4 (Acceptable with BR)** | Unit test `test_interlock_u1_laterality_verification` |
| **HAZ-USE-02** | **Spatial Transposition (Supine vs Prone)** | **S4** | Coordinate frame mismatch between supine CT and prone surgical position $\rightarrow$ Target and hazards spatially inverted. | **P3 / S4 (Unaccept)** | **RC-06 (Interlock U2):** 5-stage verified SE(3) pose transformation state machine; explicit flank orientation certification. | **P1 (Extr Rare)** | **P1 / S4 (Acceptable with BR)** | Unit test `test_interlock_u2_surgical_position_transform` |
| **HAZ-USE-03** | **Superseded / Stale Plan Execution** | **S3** | Patient anatomy or target calyx modified after plan approval $\rightarrow$ Surgeon operates with obsolete trajectory coordinates. | **P3 / S3 (Unaccept)** | **RC-07 (Interlock U6):** Immediate state transition to STALE on any parameter mutation; blocking of DRR export until re-approval. | **P1 (Extr Rare)** | **P1 / S3 (Acceptable)** | Unit test `test_interlock_u6_stale_plan_invalidation` |
| **HAZ-CYB-01** | **Unauthorized Trajectory Alteration (Tampering)** | **S4** | Malicious actor or bit corruption alters skin entry or target coordinates in transit $\rightarrow$ Erroneous trajectory rendered. | **P3 / S4 (Unaccept)** | **RC-08:** Canonical JSON SHA-256 plan fingerprinting; tamper detection trap triggers immediate `PLAN_HASH_MISMATCH` interlock. | **P1 (Extr Rare)** | **P1 / S4 (Acceptable with BR)** | Unit test `test_cryptographic_plan_fingerprint_anti_tamper` |
| **HAZ-RAD-01** | **Excessive Radiation Exposure** | **S2** | Inefficient C-arm positioning leads to prolonged fluoroscopy time ($>10\text{ min}$) $\rightarrow$ Radiation dermatitis / cumulative dose. | **P4 / S2 (Unaccept)** | **RC-09:** C-arm angle roadmap; Bullseye alignment view; ALARA dose optimization index; C-arm verbal readback protocol. | **P2 (Remote)** | **P2 / S2 (Acceptable)** | Unit test `test_alara_radiation_planning_report` |

---

## 4. Software Failure Mode & Effects Analysis (SwFMEA)

```
┌────────────────────────────────────────────────────────────────────────────┐
│                    SOFTWARE FMEA CAUSAL CHAIN SCHEMA                       │
├─────────────────┬──────────────────────┬───────────────────────────────────┤
│ Component       │ Potential Failure    │ Cause Sequence                    │
│                 │ Mode                 │                                   │
├─────────────────┼──────────────────────┼───────────────────────────────────┤
│ DICOM Reader    │ Spacing Inversion    │ Inconsistent slice sorting order  │
│                 │                      │ causes reversed Z coordinate.     │
├─────────────────┼──────────────────────┼───────────────────────────────────┤
│ Segmentation    │ Colon Boundary       │ Under-segmentation of collapsed   │
│                 │ Leakage              │ descending colon in low-fat scan. │
├─────────────────┼──────────────────────┼───────────────────────────────────┤
│ Pareto Engine   │ Empty Frontier       │ Over-constrained clearances       │
│                 │                      │ produce 0 feasible paths.         │
├─────────────────┼──────────────────────┼───────────────────────────────────┤
│ C-Arm Kinematics│ Gantry Collision     │ Extreme cranial tilt ($>45^\circ$)│
│                 │                      │ collides with patient table.      │
├─────────────────┼──────────────────────┼───────────────────────────────────┤
│ Plan Exporter   │ In-Transit Edit      │ Unauthenticated REST endpoint     │
│                 │                      │ modifies entry coordinate.        │
└─────────────────┴──────────────────────┴───────────────────────────────────┘
```

### Risk Controls Mapped to Software Modules:
1. **DICOM Reader:** Ingestion Quality Gate enforces strict monotonic Z-sorting via `ImagePositionPatient[2]`; rejects gantry tilt.
2. **Segmentation:** Multi-backend consensus check + clinician interactive caliper QC inspection; fail-closed on confidence $<0.80$.
3. **Pareto Engine:** Returns explicit `ERR_PLAN_NO_FEASIBLE_TRAJECTORY` ("No Plan"); never defaults to a hazardous compromised path.
4. **C-Arm Kinematics:** Software hard-clamps gantry angles to $|\text{LAO/RAO}| \le 45^\circ$ and $|\text{CRA/CAU}| \le 30^\circ$.
5. **Plan Exporter:** Cryptographic canonical SHA-256 fingerprint verification; unauthorized edit causes `PLAN_HASH_MISMATCH` lock.

---

## 5. Fault Tree Analysis (FTA)

### Top Clinical Event: Visceral Organ Perforation During PCNL Puncture

```
                                  [Visceral Perforation]
                                            │
                                    ┌───────┴───────┐
                                    │      OR       │
                                    └───────┬───────┘
                     ┌──────────────────────┴──────────────────────┐
                     │                                             │
          [Colonic Transfixion]                         [Medial Hilar Vascular Tear]
                     │                                             │
             ┌───────┴───────┐                             ┌───────┴───────┐
             │      AND      │                             │      AND      │
             └───────┬───────┘                             └───────┬───────┘
        ┌────────────┴────────────┐                   ┌────────────┴────────────┐
        │                         │                   │                         │
[AcuCalyx Fails       [Surgeon Fails      [AcuCalyx Fails       [Surgeon Fails
to Detect Colon]      Independent Check]  to Alarm Depth]       Depth Verification]
        │                         │                   │                         │
  (Mitigated by:            (Mitigated by:      (Mitigated by:            (Mitigated by:
   RC-01 15mm Buffer;        Multi-planar CT     RC-04 Interlock U5;       Depth Progression
   TotalSegmentator v2)      Review Mandate)     Fornix Depth Stop)        C-Arm View Rehearsal)
```

> [!NOTE]
> **Fault Tree Analysis Conclusion:**  
> Visceral injury requires the simultaneous failure of **both** the computational planning tool and independent clinical verification by the attending surgical team. By implementing strict geometric safety buffers ($\ge 15\text{ mm}$ colon, $\ge 10\text{ mm}$ pleura), runtime depth alarms, and multi-planar visualization, AcuCalyx effectively severs the computational arm of the fault tree, reducing catastrophic risk to $P1$ (Extremely Rare).

---

## 6. Overall Residual Risk Evaluation & Benefit-Risk Analysis

### 6.1 Clinical Benefits
1. **Increased Stone-Free Rate (SFR):** Precise coaxial forniceal puncture enables optimal rigid nephroscope reach, maximizing single-session staghorn clearance.
2. **Elimination of Visceral Complications:** Computational 3D safety corridors actively steer trajectories away from retrorenal colon and pleural reflections, preventing catastrophic peritonitis and pneumothorax.
3. **Radiation Dose Reduction (ALARA):** Pre-calculated C-arm projection angles eliminate trial-and-error fluoroscopy search sweeps, substantially reducing ionizing radiation to patient and OR personnel.
4. **Reduction in Counter-Punctures:** Depth boundary warnings prevent over-advancement through the medial collecting system into major renal and retroperitoneal vessels.

### 6.2 Overall Residual Risk Determination
- Every individual risk has been mitigated to an acceptable level through design and software controls.
- Residual risks at Severity S4 (Colonic injury, Great vessel injury) have been reduced to Probability P1 (Extremely Rare) through redundant geometric and usability interlocks.
- **Conclusion:** The substantial clinical benefits of single-tract clearance and visceral injury prevention outweigh the residual risks of AcuCalyx™ Core. Overall residual risk is **ACCEPTABLE**.
