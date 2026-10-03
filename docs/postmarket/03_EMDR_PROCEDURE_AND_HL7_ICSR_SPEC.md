# AcuCalyx™ Core Electronic Medical Device Reporting (eMDR) SOP
## Standard Operating Procedure & HL7 ICSR Technical Specification per 21 CFR Part 803

**Document Identifier:** SOP-ACU-EMDR-2026A  
**Regulatory Baseline:** 21 CFR Part 803 (Medical Device Reporting) & CDRH eMDR Standards (HL7 ICSR XML)  
**Target Milestone:** Milestone M8 (Commercial Operations)  

---

## 1. Regulatory Framework & Governance

21 CFR Part 803 mandates that medical device manufacturers report device-related deaths, serious injuries, and reportable malfunctions to the FDA. 

> [!IMPORTANT]
> **Human RA/QA Authority Principle:**  
> AcuCalyx regulatory software provides **rule-based triage and decision-support**, NOT autonomous legal determinations. All clinical incident records, adverse event classifications, and reportability evaluations must be formally reviewed, justified, and authorized by a designated Regulatory Affairs / Medical Safety Officer before submission to the FDA Electronic Submissions Gateway (ESG).

---

## 2. Statutory Reportability Criteria & Timeframes

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                      21 CFR PART 803 REPORTABILITY TIMEFRAMES                          │
├────────────────────┬─────────────────────────────┬─────────────────────────────────────┤
│ Report Type        │ Statutory Trigger Condition │ Statutory Transmission Deadline     │
├────────────────────┼─────────────────────────────┼─────────────────────────────────────┤
│ **30-Day Report**  │ • Patient Death             │ Within **30 calendar days** of      │
│ (Form FDA 3500A)   │ • Serious Injury            │ becoming aware of the reportable    │
│                    │ • Reportable Malfunction    │ event.                              │
├────────────────────┼─────────────────────────────┼─────────────────────────────────────┤
│ **5-Day Emergency**│ • Event requires immediate  │ Within **5 work days** of becoming  │
│ (Form FDA 3500A)   │   remedial action to prevent│ aware, or upon formal written FDA   │
│                    │   unreasonable risk of harm │ request.                            │
└────────────────────┴─────────────────────────────┴─────────────────────────────────────┘
```

### 2.1 Definition of Serious Injury (21 CFR 803.3)
An event is classified as a Serious Injury if it:
1. Is life-threatening.
2. Results in permanent impairment of a body function or permanent damage to a body structure (e.g., permanent renal loss, colonic fistula).
3. Necessitates medical or surgical intervention to preclude permanent impairment/damage (e.g., emergent laparotomy for retrorenal bowel perforation, embolization for intercostal arterial laceration).

### 2.2 Reportable Malfunction
A failure of the device to meet its performance specifications or perform as intended. A malfunction is reportable if the device or a similar device marketed by the manufacturer would be likely to cause or contribute to a death or serious injury if the malfunction were to recur. (For example, an undetected coordinate inversion displaying left calyces as right calyces).

---

## 3. HL7 Individual Case Safety Report (ICSR) XML Architecture

In accordance with FDA eMDR requirements, all electronic MDR submissions are formatted as **HL7 ICSR XML** payloads conforming to the FDA Implementation Guide:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<MCCI_IN200100UV01 xmlns="urn:hl7-org:v3" ITSVersion="XML_1.0">
  <id root="2.16.840.1.113883.3.987" extension="MDR-2026-0001"/>
  <creationTime value="20261015120000"/>
  <interactionId root="2.16.840.1.113883.1.6" extension="MCCI_IN200100UV01"/>
  <!-- Processing code: P for Production, T for Training -->
  <processingCode code="P"/>
  <processingModeCode code="T"/>
  <acceptAckCode code="AL"/>
  
  <!-- PORX_IN040006UV: Device Adverse Event Report -->
  <PORX_IN040006UV>
    <subject>
      <!-- Section A: Patient Data (Pseudonymized) -->
      <!-- Section B: Adverse Event Description -->
      <!-- Section D: Suspect Medical Device -->
      <!-- Section G: Manufacturer Report Details -->
    </subject>
  </PORX_IN040006UV>
</MCCI_IN200100UV01>
```

### 3.1 Device Identification Mapping (Section D)
- **Brand Name:** AcuCalyx™ Core
- **Common Device Name:** Preoperative PCNL Planning & Virtual Fluoroscopy Software
- **Unique Device Identifier (UDI):** `(01)00860000000001` *(Placeholder pending formal issuing-agency assignment)*
- **Software Build ID:** `ACU-CORE-COMMERCIAL-20261015-BLD01`
- **Application Version:** `1.0.0`
- **Case Provenance Signature:** Embeds the case's immutable HMAC-SHA256 surgical plan fingerprint.
