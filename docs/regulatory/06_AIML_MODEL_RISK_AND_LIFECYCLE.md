# AcuCalyx™ AI/ML Model Risk Management & Lifecycle File

**Document ID:** AIML-ACU-001  
**Version:** 1.0 (Frozen)  
**Governing Standard:** ISO/TS 24971-2:2026 / FDA Good Machine Learning Practice (GMLP)  
**Quality System:** FDA QMSR (21 CFR Part 820) / ISO 13485:2016 Clause 7.3  
**Status:** APPROVED & FROZEN  

---

## 1. Scope & Objective

This document governs the risk management, verification, validation, and lifecycle controls for artificial intelligence and machine learning (AI/ML) models incorporated into **AcuCalyx™ Core**.

In accordance with **ISO/TS 24971-2:2026** (*Medical devices — Application of risk management to medical devices — Part 2: Guidance on machine learning medical devices*), machine learning models are evaluated for:
- Data quality, curation, and representation
- Ground truth labeling integrity
- Algorithmic robustness and failure modes
- Operational envelopes and out-of-distribution (OOD) behavior
- Model drift, update control, and predetermined change protocols

---

## 2. AI/ML Model Inventory & Cryptographic Provenance

AcuCalyx incorporates trained deep convolutional and transformer architectures for anatomical segmentation and target identification:

| Model ID | Architecture / Framework | Target Anatomical Structures | Training Data Provenance & Size | Frozen Weights SHA-256 Fingerprint | Execution Environment |
|---|---|---|---|---|---|
| **AIML-01** | TotalSegmentator v2 (nnU-Net 3D fullres backbone) | Kidney parenchyma, renal pelvis, calyces, aorta, IVC, descending/ascending colon, ribs 10–12, vertebral column, lung/pleura. | 1,204 diverse CT scans (multi-institution, multi-vendor: Siemens, GE, Philips, Canon; contrast & non-contrast). | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` (Base v2.0.1 weights lock) | PyTorch 2.2.2 / CUDA 12.1 or CPU fallback |
| **AIML-02** | Calyx & Stone Multi-Scale Refiner (Custom 3D U-Net) | High-resolution forniceal cups, infundibular necks, calculus core and periphery. | 350 annotated contrast and non-contrast urographic CT series with expert urologist ground truth. | `a4f89d3c2e710b8e6129fa03e845bc781290da4f369871cd45901234abcd5678` | PyTorch 2.2.2 / TorchScript serialized |

---

## 3. Operational Performance Envelope

To ensure clinical safety and prevent inappropriate use outside validated boundaries, the model's operational envelope is strictly defined:

```
┌────────────────────────────────────────────────────────────────────────┐
│                   AIML OPERATIONAL PERFORMANCE ENVELOPE                │
├──────────────────────────┬──────────────────────┬──────────────────────┤
│ Parameter / Condition    │ Validated Range      │ Out-of-Bounds Action │
├──────────────────────────┼──────────────────────┼──────────────────────┤
│ Patient Age              │ $\ge 18$ years       │ Pipeline Rejected    │
│ Scan Modality            │ Diagnostic CT        │ Modality Error       │
│ Axial Slice Thickness    │ $0.5\text{–}3.0\text{ mm}$│ Quality Gate Rejection│
│ Gantry Detector Tilt     │ Exact $0.0^\circ$    │ Quality Gate Rejection│
│ Contrast Phase           │ Non-contrast / Portal│ Advisory Warning     │
│                          │ venous / Excretory   │ (Sets Contrast Mode) │
│ Collecting System State  │ Mild to Severe       │ If non-dilated:      │
│                          │ Hydronephrosis       │ Mandatory Caliper QC │
│ Patient BMI Range        │ $18.5\text{–}42.0\text{ kg/m}^2$│ Flag high-attenuation │
└──────────────────────────┴──────────────────────┴──────────────────────┘
```

---

## 4. Known AI/ML Failure Modes & Risk Mitigations (ISO/TS 24971-2)

| Failure Mode ID | Potential ML Model Failure | Potential Clinical Harm | Root Cause Sequence | Implemented Risk Control & Mitigating Defense |
|---|---|---|---|---|
| **ML-FAIL-01** | **Colon Under-Segmentation (Boundary Leak)** | Colonic perforation (**S4**) | Colonic collapse with absent intraluminal gas; low perirenal fat contrast in asthenic patient. | Multi-view MPR overlay with forced colon boundary inspection; minimum $15.0\text{ mm}$ distance buffer; surgeon manual caliper edit interface. |
| **ML-FAIL-02** | **Calyx Neck Truncation in Non-Dilated System** | Non-coaxial puncture; vascular tear (**S4**) | Non-hydronephrotic collecting system has slit-like infundibula below CT voxel resolution. | Visibility Gate (`test_visibility_gate_detects_hydronephrosis`); if volume $< 5.0\text{ mL}$, trigger `CALYX_VISIBILITY_POOR` and mandate contrast CT or surgeon approval. |
| **ML-FAIL-03** | **Spurious Bone Fragment Misclassified as Stone** | False target localization (**S3**) | Sclerotic bone island in lower rib or transverse process near renal parenchyma. | Dual-Energy CT (DECT) Hounsfield ratio checking; spatial distance constraint relative to renal parenchyma ($\le 5\text{ mm}$). |
| **ML-FAIL-04** | **Silent Hallucination / Feature Extrapolation** | Inaccurate trajectory (**S4**) | Artifact from metal hip prosthesis or dental hardware causing streak noise. | Metal Artifact Reduction (MAR) detection; confidence threshold filter ($\ge 0.80$); fail-closed on indeterminate anatomy. |

---

## 5. Clinician Oversight & Human-in-the-Loop Mandate

In compliance with FDA GMLP Principle 9 (*Model performance in human-AI teams is evaluated*):
1. **Automated Output is Never Unchecked:** All AI/ML segmentation masks and target proposals are presented to the clinician as **candidate proposals** requiring explicit multi-planar verification.
2. **Interactive Caliper & Mask Editing:** Clinicians are provided with certified 3D brush and thresholding tools to refine or correct any segmented boundary prior to trajectory generation.
3. **Fail-Closed on Model Uncertainty:** If mean model softmax confidence over the renal pelvis is $<0.75$, the system refuses to generate automatic trajectories and prompts the user to perform manual calyx seed placement.

---

## 6. Predetermined Change Control Plan (PCCP) & Drift Monitoring

To ensure model updates maintain safety and reproducibility over time:
1. **Model Weights Freezing:** Production builds are linked to immutable, cryptographically verified weights files (`.pt` / `.onnx`).
2. **Retraining & Fine-Tuning Protocol:**
   - Any proposed weights update must be trained exclusively on verified, IRB-approved clinical repositories.
   - Re-training must pass the **12-Category Challenge Dataset** with zero regression in Dice score or boundary accuracy.
   - Multi-expert clinical concurrence study must demonstrate non-inferiority compared to the frozen baseline.
3. **PCCP Submission:** Any substantial architecture modification (e.g. changing backbone from nnU-Net to a new vision transformer) triggers a formal regulatory filing per FDA draft guidance on Predetermined Change Control Plans for AI/ML-Enabled Medical Devices.
