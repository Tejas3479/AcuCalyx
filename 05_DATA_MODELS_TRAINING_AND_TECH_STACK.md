# 05. Data, Models, Training Pipeline & Technical Stack

---

## 💡 1. The Core Engineering Reality: 80% Does NOT Require ML Training

A common misconception in medical AI is that every capability requires training a deep neural network from scratch. In KidneyStone 3D, **the majority of the pipeline uses either pre-trained foundation segmentation models or deterministic 3D computational geometry**:

```
┌──────────────────────────────────────────────┬──────────────────────────────┐
│ Component                                    │ Method / Framework           │
├──────────────────────────────────────────────┼──────────────────────────────┤
│ 1. Kidney boundary segmentation              │ Pre-trained TotalSegmentator │
│ 2. Rib & spine segmentation                  │ Pre-trained TotalSegmentator │
│ 3. Colon boundary segmentation               │ Pre-trained TotalSegmentator │
│ 4. Lung / pleural segmentation               │ Pre-trained TotalSegmentator │
│ 5. Stone detection & segmentation            │ Deterministic HU threshold   │
│ 6. True 3D stone volume calculation          │ Voxel summation (Math)       │
│ 7. Stone hardness (HU) profiling             │ Radiodensity histogram (Math)│
│ 8. 3D surface mesh generation                │ Marching Cubes (Math)        │
│ 9. Needle trajectory optimization            │ Constrained 3D Vector Math   │
│ 10. Hazard clearance distance calculation    │ Euclidean Distance Transform │
│ 11. C-Arm gantry angle prescription          │ IEC 61217 Coordinate Trans.  │
│ 12. Interactive 3D visualization             │ WebGL / Three.js             │
│ 13. Hydronephrotic calyx segmentation        │ Custom Fine-Tuned nnU-Net    │
└──────────────────────────────────────────────┴──────────────────────────────┘
```

**Only 1 single component (Hydronephrotic Calyx Segmentation) requires custom model training.**

---

## 📦 2. Open Datasets: Where to Get the Data

All data needed to build, validate, and test this system is publicly and freely available:

| Dataset | Sample Size | Contents & Annotations | Access URL |
| :--- | :--- | :--- | :--- |
| **KiTS23** (Kidney Tumor Segmentation) | 489 Cases | Thin-slice contrast abdominal CTs; dense kidney, cyst, and tumor masks; high incidence of hydronephrosis. | [github.com/neheller/kits23](https://github.com/neheller/kits23) |
| **Medical Segmentation Decathlon (MSD)** | 210 Cases | Task 00 (Kidney & Kidney Tumor); standardized NIfTI format. | [medicaldecathlon.com](http://medicaldecathlon.com/) |
| **CT-ORG** | 140 Cases | Multi-organ CT dataset with annotated kidneys, liver, bladder, bones. | [cancerimagingarchive.net](https://www.cancerimagingarchive.net/) |
| **TCIA** (The Cancer Imaging Archive) | 10,000+ Cases | Massive archive of abdominal CT scans across multiple vendors (GE, Siemens, Philips, Canon). | [cancerimagingarchive.net](https://www.cancerimagingarchive.net/) |
| **KiPA22** (Kidney Parsing Challenge) | 70 Cases | Detailed segmentation of renal parenchyma, renal artery, renal vein, and collecting system. | [kipa22.grand-challenge.org](https://kipa22.grand-challenge.org/) |

---

## 🧠 3. The One Custom Model: Training the Calyx Segmentation Network

### A. The Annotation Workflow (3D Slicer)
Because generic datasets label the whole kidney but not individual calyces, a focused training set of **100 CT scans showing visible hydronephrosis** is selected from KiTS23 and TCIA:
1. Open CT volume in **3D Slicer** (free, open-source medical imaging platform).
2. Use the **Segment Editor** module with the *Threshold* tool set to $0\text{ to }25\text{ HU}$ (fluid density).
3. Use the *Islands* tool to keep the connected collecting system cavity.
4. Separate into 4 classes: **Renal Pelvis**, **Upper Calyx Group**, **Middle Calyx Group**, and **Lower Calyx Group**.
5. Export annotations as binary multi-label NIfTI masks (`.nii.gz`).

### B. Training via nnU-Net v2
nnU-Net is the gold standard for self-configuring 3D medical segmentation.

```bash
# 1. Install nnU-Net v2
pip install nnunetv2

# 2. Directory structure
# nnUNet_raw/
#   Dataset101_KidneyCalyx/
#     imagesTr/        <-- CT volumes (.nii.gz)
#     labelsTr/        <-- 4-class calyx masks (.nii.gz)
#     dataset.json

# 3. Automatic planning and preprocessing
nnUNetv2_plan_and_preprocess -d 101 --verify_dataset_integrity

# 4. Train 3D Full-Resolution UNet (Fold 0)
nnUNetv2_train 101 3d_fullres 0 --npz

# 5. Run inference on new patient scan
nnUNetv2_predict -i /path/to/patient_ct/ -o /path/to/output_masks/ -d 101 -c 3d_fullres
```

---

## 💻 4. Python Implementation: Core Pipeline Modules

### Module 1: Ingestion Gate & Stone Extraction (Pure Math)
```python
import SimpleITK as sitk
import numpy as np
from scipy import ndimage

def extract_stones(ct_nii_path: str, kidney_mask_path: str):
    """
    Extracts dense stones from non-contrast CT within the kidney boundary.
    No machine learning required - pure physics-based thresholding.
    """
    ct_image = sitk.ReadImage(ct_nii_path)
    ct_array = sitk.GetArrayFromImage(ct_image)  # [Z, Y, X]
    spacing = ct_image.GetSpacing()              # [dx, dy, dz] in mm
    voxel_vol_mm3 = spacing[0] * spacing[1] * spacing[2]
    
    kidney_mask = sitk.GetArrayFromImage(sitk.ReadImage(kidney_mask_path)) > 0
    
    # Restrict CT to kidney volume
    kidney_ct = np.where(kidney_mask, ct_array, -1024)
    
    # Dual threshold: >400 HU for calcium stones, >200 HU for soft/uric acid
    dense_stone_mask = (kidney_ct > 400).astype(np.uint8)
    soft_stone_mask = (kidney_ct > 200).astype(np.uint8)
    
    # Label individual stone clusters
    labeled_stones, num_stones = ndimage.label(dense_stone_mask)
    
    stone_profiles = []
    for s_id in range(1, num_stones + 1):
        voxels = (labeled_stones == s_id)
        vol_mm3 = np.sum(voxels) * voxel_vol_mm3
        mean_hu = float(np.mean(ct_array[voxels]))
        max_hu = float(np.max(ct_array[voxels]))
        centroid_vox = ndimage.center_of_mass(voxels)
        
        # Convert centroid to physical coordinates (mm)
        centroid_phys = ct_image.TransformContinuousIndexToPhysicalPoint(
            [centroid_vox[2], centroid_vox[1], centroid_vox[0]]
        )
        
        stone_profiles.append({
            "id": s_id,
            "volume_mm3": round(vol_mm3, 1),
            "mean_hu": round(mean_hu, 0),
            "max_hu": round(max_hu, 0),
            "centroid_mm": centroid_phys
        })
        
    return stone_profiles, dense_stone_mask
```

### Module 2: 3D Surface Mesh Generation (Marching Cubes)
```python
from skimage.measure import marching_cubes
import trimesh

def generate_smooth_mesh(mask_array: np.ndarray, spacing: tuple, output_path: str):
    """
    Converts a 3D binary voxel mask into a smoothed 3D polygon mesh (.glb / .stl).
    """
    # Marching cubes algorithm
    verts, faces, normals, _ = marching_cubes(
        mask_array, 
        level=0.5, 
        spacing=(spacing[2], spacing[1], spacing[0])
    )
    
    # Create polygon surface
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, vertex_normals=normals)
    
    # Apply Laplacian smoothing to eliminate voxel stair-step artifacts
    trimesh.smoothing.filter_laplacian(mesh, lamb=0.5, iterations=10)
    
    # Export for WebGL Three.js viewer or 3D printer
    mesh.export(output_path)
    return output_path
```

### Module 3: Trajectory Calculation & C-Arm Gantry Angles
```python
def compute_c_arm_trajectory(target_calyx_mm: np.ndarray, skin_entry_mm: np.ndarray):
    """
    Computes insertion vector and converts to IEC 61217 C-arm fluoroscopy angles,
    incorporating the supine-to-prone 180-degree coordinate inversion.
    """
    # 1. Trajectory vector from skin to target
    vec_supine = target_calyx_mm - skin_entry_mm
    depth_mm = float(np.linalg.norm(vec_supine))
    vec_norm = vec_supine / depth_mm
    
    # 2. Supine-to-Prone Transformation Matrix (180-deg flip around longitudinal Z axis)
    R_prone = np.array([
        [-1,  0,  0],   # Invert Right-Left (X)
        [ 0, -1,  0],   # Invert Anterior-Posterior (Y)
        [ 0,  0,  1]    # Retain Superior-Inferior (Z)
    ])
    
    vec_prone = R_prone @ vec_norm
    
    # 3. Calculate IEC 61217 Gantry Angles
    # LAO (+) / RAO (-) angulation in the transverse plane
    lao_rao_rad = np.arctan2(vec_prone[0], -vec_prone[1])
    lao_rao_deg = float(np.degrees(lao_rao_rad))
    
    # Cranial (+) / Caudal (-) angulation along the longitudinal axis
    cran_caud_rad = np.arcsin(np.clip(vec_prone[2], -1.0, 1.0))
    cran_caud_deg = float(np.degrees(cran_caud_rad))
    
    return {
        "needle_depth_mm": round(depth_mm, 1),
        "c_arm_lao_rao_deg": round(lao_rao_deg, 1),
        "c_arm_cran_caud_deg": round(cran_caud_deg, 1),
        "entry_point_mm": skin_entry_mm.tolist(),
        "target_calyx_mm": target_calyx_mm.tolist()
    }
```

---

## 🛠️ 5. Production Technology Stack

```
┌────────────────────────┬────────────────────────────────────────────────────────┐
│ Layer                  │ Technology Choice & Justification                      │
├────────────────────────┼────────────────────────────────────────────────────────┤
│ Ingestion & DICOM      │ PyDICOM, SimpleITK, Highdicom (DICOM-SR export)        │
│ 3D Segmentation        │ TotalSegmentator (pre-trained), nnU-Net v2 (fine-tuned)│
│ Geometry & Meshing     │ SciPy, scikit-image (Marching Cubes), trimesh          │
│ Backend API            │ FastAPI (Python 3.11 asynchronous REST service)        │
│ Frontend 3D Viewer     │ Three.js (WebGL, hardware-accelerated, zero-install)   │
│ Surgical Blueprint PDF │ ReportLab / WeasyPrint (Single-page sterile OR sheet)  │
│ Containerization       │ Docker with NVIDIA Container Toolkit (CUDA 12.2)       │
└────────────────────────┴────────────────────────────────────────────────────────┘
```
