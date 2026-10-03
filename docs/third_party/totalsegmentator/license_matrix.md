# AcuCalyx Third-Party Software & Model Licensing Matrix

**Document Reference:** `DOC-LL-2026-001`  
**Governing Standard:** IEC 62304 / FDA Guidance on Premarket Submissions for Device Software Functions  
**Scope:** Third-Party AI Models, Segmentation Frameworks, and Computational Geometry Libraries  

---

## 1. Core Model & Library Dependencies

| Component | Upstream Repository | Version Pin | Upstream License | Intended Clinical Use in AcuCalyx | Commercial / CDS Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **TotalSegmentator v2** | `wasserth/TotalSegmentator` | `>= 2.2.0` | Apache 2.0 (Code) / CC-BY-NC-SA (Weights) | Automated multi-organ corridor segmentation (Kidneys, Ribs, Spine, Bowel, Viscera) | Commercial deployment requires commercial weights license or in-house fine-tuned weights on KiTS/NIH data |
| **nnU-Net** | `MIC-DKFZ/nnUNet` | `>= 2.4.0` | Apache 2.0 | Deep learning training & inference framework for medical CT segmentation | Full commercial use permitted |
| **SimpleITK** | `SimpleITK/SimpleITK` | `>= 2.3.0` | Apache 2.0 | Anisotropic image resampling, rigid/deformable registration, and DICOM IO | Full commercial use permitted |
| **pydicom** | `pydicom/pydicom` | `>= 3.0.0` | MIT / BSD 3-Clause | Fail-closed DICOM PS3.3 ingestion, tag parsing, and slice ordering | Full commercial use permitted |
| **NiBabel** | `nipy/nibabel` | `>= 5.2.0` | MIT | Research NIfTI header validation and affine transformation (qform/sform) | Full commercial use permitted |
| **Trimesh** | `mikedh/trimesh` | `>= 4.0.0` | MIT | Display-only 3D surface mesh generation, decimation, and GLB/STL export | Non-sterile rehearsal use permitted |
| **ReportLab** | `reportlab/reportlab` | `>= 4.2.0` | BSD 3-Clause | Preoperative planning report generation with auditable cryptographic hashes | Full commercial use permitted |
| **Three.js** | `mrdoob/three.js` | `r128` | MIT | WebGL hardware-accelerated 3D viewport and PBR anatomical rendering | Full commercial use permitted |

---

## 2. TotalSegmentator Model Weight Governance

1. **Non-Commercial / Research Use:**  
   The default pre-trained TotalSegmentator weights are licensed under **CC-BY-NC-SA 4.0** for non-commercial academic research.
2. **Clinical / Commercial Medical Device Clearance:**  
   - For FDA 510(k) or CE-mark deployment, commercial weight licenses must be obtained from the model authors (University of Basel / Department of Radiology), OR:
   - In-house neural models trained strictly on public open-access datasets (e.g., **KiTS23**, **BTCV**, and **TotalSegmentator Public Open subset**) using nnU-Net under Apache 2.0 must be loaded.
3. **Weight Integrity & Cryptographic Verification:**  
   - In accordance with FDA Section 524B (Cybersecurity in Medical Devices), all neural network model weight checkpoints (`.pt` or `.onnx`) must have their SHA-256 digests validated against the `weights_manifest.json` before execution.

---

## 3. Provenance & Fail-Closed Guardrails

If external neural network weights are unmounted or network access is unavailable, the AcuCalyx engine fails gracefully to **Heuristic Structural Segmentation** (`segment_heuristic_anatomy`), clearly tagging downstream outputs with:
$$\text{Clinical Observability} = \text{ESTIMATED\_PRIOR}$$
and marking automated direct puncture locks as disabled until certified clinician review.
