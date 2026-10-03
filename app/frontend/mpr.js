/**
 * AcuCalyx 2D Multi-Planar Reconstruction (MPR) Engine
 * Synchronized Axial, Coronal, and Sagittal slice viewer
 */

class AcuCalyxMPRViewer {
  constructor(imgElementId, sliderElementId, labelElementId) {
    this.imgElement = document.getElementById(imgElementId);
    this.sliderElement = document.getElementById(sliderElementId);
    this.labelElement = document.getElementById(labelElementId);

    this.currentCaseId = null;
    this.currentOrientation = 'AXIAL';
    this.currentSliceIndex = 40;
    this.maxSlices = {
      AXIAL: 80,
      CORONAL: 96,
      SAGITTAL: 96
    };
    this.windowWidth = 400.0;
    this.windowLevel = 40.0;
    this.activeCandidate = null;

    this.init();
  }

  init() {
    if (this.sliderElement) {
      this.sliderElement.addEventListener('input', (e) => {
        this.setSliceIndex(parseInt(e.target.value, 10));
      });
    }

    if (this.imgElement) {
      // Mouse wheel scrub
      this.imgElement.addEventListener('wheel', (e) => {
        e.preventDefault();
        const delta = e.deltaY > 0 ? -1 : 1;
        this.setSliceIndex(this.currentSliceIndex + delta);
      });
    }

    // Window presets buttons
    document.querySelectorAll('[data-preset]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const preset = e.target.getAttribute('data-preset');
        this.applyWindowPreset(preset);
      });
    });

    // Orientation tab buttons
    document.querySelectorAll('.tab-btn[data-orient]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        document.querySelectorAll('.tab-btn[data-orient]').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        this.setOrientation(btn.getAttribute('data-orient'));
      });
    });
  }

  setCase(caseId, sliceCount = 80) {
    this.currentCaseId = caseId;
    this.maxSlices.AXIAL = sliceCount;
    this.currentSliceIndex = Math.floor(sliceCount / 2);
    this.updateSliderLimits();
    this.refreshSlice();
  }

  setOrientation(orientation) {
    this.currentOrientation = orientation.toUpperCase();
    this.updateSliderLimits();
    this.currentSliceIndex = Math.floor(this.sliderElement.max / 2);
    this.sliderElement.value = this.currentSliceIndex;
    this.refreshSlice();
  }

  updateSliderLimits() {
    if (!this.sliderElement) return;
    const maxVal = (this.maxSlices[this.currentOrientation] || 80) - 1;
    this.sliderElement.min = 0;
    this.sliderElement.max = maxVal;
    this.sliderElement.value = Math.min(this.currentSliceIndex, maxVal);
  }

  setSliceIndex(idx) {
    const maxVal = parseInt(this.sliderElement.max, 10);
    this.currentSliceIndex = Math.max(0, Math.min(idx, maxVal));
    if (this.sliderElement) {
      this.sliderElement.value = this.currentSliceIndex;
    }
    this.refreshSlice();
  }

  applyWindowPreset(preset) {
    switch (preset.toLowerCase()) {
      case 'soft':
        this.windowWidth = 400.0;
        this.windowLevel = 40.0;
        break;
      case 'bone':
        this.windowWidth = 2000.0;
        this.windowLevel = 500.0;
        break;
      case 'kidney':
        this.windowWidth = 300.0;
        this.windowLevel = 50.0;
        break;
    }
    this.refreshSlice();
  }

  setActiveCandidate(candidate) {
    this.activeCandidate = candidate;
    if (candidate && candidate.target_point_lps) {
      this.syncToLPS(
        candidate.target_point_lps[0],
        candidate.target_point_lps[1],
        candidate.target_point_lps[2]
      );
    } else {
      this.refreshSlice();
    }
  }

  async syncToLPS(x, y, z) {
    if (!this.currentCaseId) return;
    try {
      const res = await fetch(`/api/cases/${this.currentCaseId}/mpr/lps_to_slice?x=${x}&y=${y}&z=${z}`);
      if (!res.ok) return;
      const data = await res.json();
      const orientKey = this.currentOrientation.toLowerCase();
      const planeInfo = data[orientKey];
      if (planeInfo) {
        this.currentSliceIndex = planeInfo.slice_index;
        this.crosshairPixel = { px: planeInfo.pixel_x, py: planeInfo.pixel_y };
        if (this.sliderElement) {
          this.sliderElement.value = this.currentSliceIndex;
        }
        this.refreshSlice();
      }
    } catch (err) {
      console.warn('LPS to slice mapping error:', err);
    }
  }

  refreshSlice() {
    if (!this.currentCaseId) return;

    let url = `/api/cases/${this.currentCaseId}/mpr/slice?orientation=${this.currentOrientation}&slice_index=${this.currentSliceIndex}&window_width=${this.windowWidth}&window_level=${this.windowLevel}&t=${Date.now()}`;
    if (this.crosshairPixel) {
      url += `&crosshair_px=${this.crosshairPixel.px}&crosshair_py=${this.crosshairPixel.py}`;
    }

    if (this.imgElement) {
      this.imgElement.src = url;
    }

    if (this.labelElement) {
      const maxVal = this.sliderElement ? this.sliderElement.max : 0;
      this.labelElement.textContent = `${this.currentOrientation} Slice ${this.currentSliceIndex} / ${maxVal} (W:${Math.round(this.windowWidth)} L:${Math.round(this.windowLevel)})`;
    }
  }
}

window.AcuCalyxMPRViewer = AcuCalyxMPRViewer;
