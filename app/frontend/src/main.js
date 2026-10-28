/**
 * AcuCalyx Surgical Planning Workstation — Main Application Entry Point
 * Orchestrates modular components, views, services, and 3D WebGL viewport.
 */

import { authService } from './services/auth.js';
import { caseService } from './services/caseService.js';
import { Sidebar } from './components/Sidebar.js';
import { Topbar } from './components/Topbar.js';
import { Modal } from './components/Modals/Modal.js';
import { ComparisonMatrixModal } from './components/Modals/ComparisonMatrixModal.js';
import { SummaryCardModal } from './components/Modals/SummaryCardModal.js';
import { DoctorLoginModal } from './components/Modals/DoctorLoginModal.js';
import { showToast } from './components/Toast.js';

import { DashboardView } from './views/DashboardView.js';
import { PatientDirectoryView } from './views/PatientDirectoryView.js';
import { CockpitView } from './views/CockpitView.js';
import { WorkbenchView } from './views/WorkbenchView.js';
import { LearningView } from './views/LearningView.js';
import { UsabilityView } from './views/UsabilityView.js';
import { ValidationView } from './views/ValidationView.js';
import { SettingsView } from './views/SettingsView.js';

import { Router } from './router/Router.js';
import { AcuCalyxViewer3D } from './viewport/Viewer3D.js';
import { AcuCalyxMPRViewer } from './viewport/MPRViewer.js';

class AcuCalyxApplication {
  constructor() {
    this.sidebar = null;
    this.topbar = null;
    this.router = null;
    this.viewer3d = null;
    this.mprViewer = null;
    this.comparisonModal = null;
    this.summaryModal = null;
    this.doctorModal = null;
  }

  async init() {
    console.info('Initializing AcuCalyx Clinical Workstation (v2.1.0 Modular Architecture)...');
    window.showToast = showToast;

    // 1. Initialize Modals
    Modal.initEscapeListener();
    this.comparisonModal = new ComparisonMatrixModal();
    this.summaryModal = new SummaryCardModal();
    this.doctorModal = new DoctorLoginModal();

    // 2. Initialize Topbar & Sidebar
    this.topbar = new Topbar();
    this.sidebar = new Sidebar();

    // 3. Initialize Views
    const views = {
      dashboard: new DashboardView(),
      cases: new PatientDirectoryView(),
      cockpit: new CockpitView(),
      workbench: new WorkbenchView(),
      learning: new LearningView(),
      usability: new UsabilityView(),
      validation: new ValidationView(),
      settings: new SettingsView()
    };
    this.views = views;

    // 4. Initialize Router
    this.router = new Router(views, this.topbar);

    // 5. Initialize 3D WebGL and 2D MPR Viewports if container exists
    const threeContainer = document.getElementById('three-container');
    if (threeContainer && typeof window.THREE !== 'undefined') {
      try {
        if (!window.viewer3d) {
          this.viewer3d = new AcuCalyxViewer3D('three-container');
          window.viewer3d = this.viewer3d;
        } else {
          this.viewer3d = window.viewer3d;
        }
      } catch (err) {
        console.warn('3D Viewport initialization deferred:', err);
      }
    }

    const mprImg = document.getElementById('mpr-slice-img');
    if (mprImg) {
      try {
        if (!window.mprViewer) {
          this.mprViewer = new AcuCalyxMPRViewer('mpr-slice-img', 'mpr-slider', 'mpr-slice-label');
          window.mprViewer = this.mprViewer;
        } else {
          this.mprViewer = window.mprViewer;
        }
      } catch (err) {
        console.warn('MPR Viewport initialization deferred:', err);
      }
    }

    // 6. Connect global bridge methods for 3D raycasting and selection
    window.selectCase = async (caseId) => {
      await caseService.getCaseStatus(caseId);
      if (typeof window.cockpitSelectCase === 'function') {
        await window.cockpitSelectCase(caseId);
      } else if (this.viewer3d && typeof window.loadCaseArtifacts === 'function') {
        await window.loadCaseArtifacts(caseId);
      }
    };

    window.portalSelectCaseAndRehearse = async (caseId) => {
      await window.selectCase(caseId);
      this.router.navigate('cockpit');
    };

    window.selectTrajectory = async (candId) => {
      const caseId = caseService.currentCaseId || window.currentCaseId;
      if (!candId) return;

      // 1. Synchronize 3D WebGL viewport active needle trajectory
      if (window.viewer3d && typeof window.viewer3d.setActiveTrajectory === 'function') {
        window.viewer3d.setActiveTrajectory(candId);
      }
      const candidatesList = caseService.currentCandidates || window.currentCandidates || [];
      const candObj = candidatesList.find(c => (c.candidate_id || c.id) === candId);
      if (candObj && window.mprViewer && typeof window.mprViewer.setActiveCandidate === 'function') {
        window.mprViewer.setActiveCandidate(candObj);
      }

      // 2. Update candidate cards highlight across views & refresh keyframe preview
      document.querySelectorAll('.candidate-card').forEach(c => c.classList.remove('active'));
      const card = document.getElementById(`card-${candId}`);
      if (card) card.classList.add('active');

      if (typeof window.updateKeyframePreview === 'function') {
        window.updateKeyframePreview();
      }

      // 3. Persist selection via backend service
      if (caseId) {
        try {
          await caseService.selectTrajectory(caseId, candId);
          showToast(`Selected access tract: ${candId}`, 'info');
        } catch (e) {
          console.warn('Backend tract selection sync failed:', e);
        }
      }
    };

    window.createDemoCase = async () => {
      try {
        const res = await caseService.createDemoCase();
        showToast(`Synthetic demo phantom created: ${res.case_id}`, 'success');
        await this.topbar.populateCaseList(res.case_id);
        if (typeof window.selectCase === 'function') {
          await window.selectCase(res.case_id);
        }
        if (this.views.dashboard) await this.views.dashboard.mount();
        if (this.views.cases) await this.views.cases.mount();
      } catch (err) {
        showToast(`Demo creation failed: ${err.message}`, 'error');
      }
    };

    // 7. Load Initial Case List, Auto-Select Active Case, and Start Routing
    await this.topbar.populateCaseList();
    const initialCase = document.getElementById('case-select')?.value;
    if (initialCase) {
      try {
        await window.selectCase(initialCase);
      } catch (e) {
        console.warn('Initial case selection deferred:', e);
      }
    }
    this.router.start();

    // Re-render when doctor identity changes
    window.addEventListener('acucalyx:doctor-changed', async () => {
      await this.topbar.populateCaseList();
      const firstCase = document.getElementById('case-select')?.value;
      if (firstCase) {
        await window.selectCase(firstCase);
      }
      this.router.handleHashChange();
    });

    console.info('AcuCalyx Clinical Workstation ready.');
  }
}

// Global bootstrap
document.addEventListener('DOMContentLoaded', () => {
  const app = new AcuCalyxApplication();
  window.__acucalyxApp = app;
  app.init().catch(err => console.error('App init error:', err));
});
