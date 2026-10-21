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
      if (this.viewer3d && typeof window.loadCaseArtifacts === 'function') {
        await window.loadCaseArtifacts(caseId);
      }
    };

    window.portalSelectCaseAndRehearse = async (caseId) => {
      await window.selectCase(caseId);
      this.router.navigate('cockpit');
    };

    window.selectTrajectory = async (candId) => {
      const caseId = caseService.currentCaseId;
      if (caseId && candId) {
        await caseService.selectTrajectory(caseId, candId);
        showToast(`Selected access tract: ${candId}`, 'info');
      }
    };

    window.createDemoCase = async () => {
      await this.topbar.populateCaseList();
    };

    // 7. Load Initial Case List and Start Routing
    await this.topbar.populateCaseList();
    this.router.start();

    // Re-render when doctor identity changes
    window.addEventListener('acucalyx:doctor-changed', async () => {
      await this.topbar.populateCaseList();
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
