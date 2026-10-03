# AcuCalyx™ Clinical Events Committee (CEC) & Safety Monitoring Charter

**Document ID:** CEC-CHARTER-001  
**Version:** 1.0 (Frozen)  
**Governing Standard:** ISO 14155:2026 Clause 8 / FDA Guidance on Clinical Trial Safety Monitoring  
**Target Milestone:** Milestones M6A (Feasibility Pilot) & M6B (Pivotal Study)  
**Status:** APPROVED & FROZEN  

---

## 1. Charter Purpose & Independent Authority

This Charter defines the responsibilities, membership, event classification criteria, adjudication processes, and study halting rules for the independent **Clinical Events Committee (CEC)** governing AcuCalyx clinical investigations.

The CEC operates as an autonomous multidisciplinary expert body whose primary mandate is to ensure objective, unblinded (or blinded where feasible) safety oversight, adverse event adjudication, and device-relatedness assessment independent of trial sponsors and clinical investigators.

---

## 2. Committee Composition & Independence

### 2.1 Membership
The CEC comprises three voting members:
1. **Chairperson:** Board-certified academic endourologist with $>10$ years PCNL experience.
2. **Clinical Member:** Board-certified urologist specializing in complex nephrolithiasis.
3. **Radiological Member:** Board-certified interventional radiologist specializing in percutaneous access.

### 2.2 Independence & Conflict of Interest
In accordance with ISO 14155:2026:
- No CEC member shall be an investigator, co-investigator, or site staff at an active AcuCalyx trial center.
- Members must have no financial or equity interest in the sponsor company.

---

## 3. Adverse Event Classification (Clavien-Dindo System Grades I–V)

All procedural and post-procedural adverse events through Day 30 post-op will be classified per the standardized Clavien-Dindo system:

| Grade | Clinical Definition per Clavien-Dindo System | Typical PCNL Manifestations |
|---|---|---|
| **Grade I** | Minor alteration from normal post-op course; no need for pharmacological treatment or surgical, endoscopic, or radiological interventions. | Transient post-op hematuria not requiring transfusion; mild flank pain managed with oral analgesics; minor antiemetics. |
| **Grade II** | Requiring pharmacological treatments with drugs other than such allowed for grade I complications. | Blood transfusion (1–2 units PRBC); therapeutic IV antibiotics for post-op urinary tract infection or fever. |
| **Grade IIIa** | Complications requiring surgical, endoscopic, or radiological intervention **not under general anesthesia**. | Percutaneous nephrostomy tube repositioning; double-J stent placement; percutaneous chest tube insertion for pneumothorax under local anesthesia; renal angioembolization under local anesthesia. |
| **Grade IIIb** | Complications requiring surgical, endoscopic, or radiological intervention **under general anesthesia**. | Laparoscopic or open surgical repair of colonic transfixion; emergency open surgical exploration for refractory hemorrhage; surgical repair of splenic/hepatic laceration. |
| **Grade IVa** | Life-threatening complication requiring ICU management: Single organ dysfunction. | Severe urosepsis with respiratory failure requiring mechanical ventilation; acute renal failure requiring temporary dialysis. |
| **Grade IVb** | Life-threatening complication requiring ICU management: Multi-organ dysfunction. | Septic shock with multi-organ failure and disseminated intravascular coagulation (DIC). |
| **Grade V** | Patient death. | Mortality occurring within 30 days of index procedure. |

---

## 4. Causality & Device Relatedness Attribution (ISO 14155:2026)

Every reported adverse event will be adjudicated into one of six standard causality categories:

```
┌────────────────────────────────────────────────────────────────────────┐
│               ISO 14155:2026 EVENT RELATEDNESS TAXONOMY                │
├────────────────────────┬───────────────────────────────────────────────┤
│ Attribution Category   │ Regulatory & Clinical Criteria                │
├────────────────────────┼───────────────────────────────────────────────┤
│ 1. Not Related         │ Event completely explained by patient's       │
│                        │ pre-existing disease or unrelated factors.    │
├────────────────────────┼───────────────────────────────────────────────┤
│ 2. Unlikely Related    │ Temporal relationship exists, but other       │
│                        │ clinical causes provide plausible explanation.│
├────────────────────────┼───────────────────────────────────────────────┤
│ 3. Possibly Related    │ Event occurred in temporal proximity; device  │
│                        │ contribution cannot be excluded.              │
├────────────────────────┼───────────────────────────────────────────────┤
│ 4. Probably Related    │ Event has strong temporal and anatomical      │
│                        │ relationship to device planning corridor.     │
├────────────────────────┼───────────────────────────────────────────────┤
│ 5. Definitively Device-│ Direct causal link established: Event caused  │
│    Related             │ by erroneous trajectory calculation, software │
│                        │ coordinate corruption, or gantry angle bug.   │
├────────────────────────┼───────────────────────────────────────────────┤
│ 6. Technique / Surgi-  │ Event related to manual needle advancement,   │
│    cal-Related         │ dilation sheath torque, or laser lithotripsy  │
│                        │ independent of computational planning.        │
└────────────────────────┴───────────────────────────────────────────────┘
```

---

## 5. Formal Trial Halting Rules

In conformance with ISO 14155:2026 Clause 8.2 and FDA Safety Monitoring Guidelines, patient enrollment will be **immediately suspended across all sites** upon the occurrence of any of the following triggers:

1. **Any Grade V Event (Death):** Occurrence of a single patient death within 30 days of PCNL in the AcuCalyx arm judged possibly, probably, or definitively related to the device or access procedure.
2. **Definitively Device-Attributable Major Visceral Harm:** A single confirmed case of colonic perforation, bowel peritonitis, or great vessel laceration directly caused by a software calculation fault or unmitigated coordinate discrepancy.
3. **Excessive Serious Complication Rate:** Occurrence of $\ge 3$ Clavien-Dindo Grade IIIb or Grade IV events in the AcuCalyx arm, or an overall Grade III–IV rate exceeding $15.0\%$ of enrolled subjects (historical baseline $\sim 5\text{–}8\%$).

### Post-Suspension Protocol:
Suspension triggers immediate notification to reviewing IRBs and FDA CDRH within 5 business days, followed by a formal Quality Management System investigation under ISO 13485:2016 Clause 8.5.2 and IEC 62304 Clause 9.
