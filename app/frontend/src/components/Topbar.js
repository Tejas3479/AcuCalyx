/**
 * Clinical Topbar Component
 * Manages breadcrumbs, doctor privacy vault status, case selector, benchmark scenarios, and actions.
 */

import { authService } from '../services/auth.js';
import { caseService } from '../services/caseService.js';
import { showToast } from './Toast.js';

export class Topbar {
  constructor() {
    this.init();
  }

  init() {
    authService.subscribe((doctor) => this.renderDoctorBadge(doctor));

    // Guard: only attach topbar action listeners if clinical-cockpit has not attached them
    if (!window.__cockpitWorkflowAttached) {
      window.__cockpitWorkflowAttached = true;

      // Handle case dropdown changes
      const caseSelect = document.getElementById('case-select');
      if (caseSelect) {
        caseSelect.addEventListener('change', async (e) => {
          const caseId = e.target.value;
          if (caseId) {
            try {
              if (typeof window.selectCase === 'function') {
                await window.selectCase(caseId);
              } else {
                await caseService.getCaseStatus(caseId);
              }
              showToast(`Loaded active case: ${caseId}`, 'info');
            } catch (err) {
              showToast(`Failed to load case: ${err.message}`, 'error');
            }
          }
        });
      }

      // Handle new demo case button
      const btnDemo = document.getElementById('btn-new-demo');
      if (btnDemo) {
        btnDemo.addEventListener('click', async () => {
          btnDemo.textContent = '⏳ Creating...';
          btnDemo.disabled = true;
          try {
            const res = await caseService.createDemoCase();
            showToast(`Synthetic demo phantom created: ${res.case_id}`, 'success');
            await this.populateCaseList(res.case_id);
          } catch (err) {
            showToast(`Demo creation failed: ${err.message}`, 'error');
          } finally {
            btnDemo.textContent = '+ Demo';
            btnDemo.disabled = false;
          }
        });
      }

      // Handle file upload
      const fileInput = document.getElementById('file-upload');
      if (fileInput) {
        fileInput.addEventListener('change', async (e) => {
          const file = e.target.files?.[0];
          if (!file) return;
          try {
            showToast(`Uploading ${file.name}...`, 'info');
            const res = await caseService.uploadCase(file);
            showToast(`Ingested ${res.input_file_count} file(s). Case ${res.case_id} is READY.`, 'success');
            await this.populateCaseList(res.case_id);
          } catch (err) {
            showToast(`Upload failed: ${err.message}`, 'error');
          }
        });
      }

      // Handle run plan button
      const btnPlan = document.getElementById('btn-run-plan');
      if (btnPlan) {
        btnPlan.addEventListener('click', async () => {
          const caseId = caseService.currentCaseId;
          if (!caseId) {
            showToast('Please select a case first.', 'warning');
            return;
          }
          btnPlan.textContent = '⏳ Planning...';
          btnPlan.disabled = true;
          try {
            const res = await caseService.runPlanning(caseId);
            showToast(`Pareto access plan computed for ${caseId}!`, 'success');
            if (typeof window.selectCase === 'function') {
              await window.selectCase(caseId);
            } else {
              await caseService.getCaseStatus(caseId);
            }
          } catch (err) {
            showToast(`Planning failed: ${err.message}`, 'error');
          } finally {
            btnPlan.textContent = '⚡ Run Plan';
            btnPlan.disabled = false;
          }
        });
      }
    }
  }

  renderDoctorBadge(doctor) {
    const badge = document.getElementById('topbar-doctor-badge');
    if (badge && doctor) {
      badge.innerHTML = `
        <span class="vault-dot" style="background-color: ${doctor.avatar_color || '#00e5a3'}"></span>
        <span class="vault-text"><strong>Vault:</strong> ${doctor.full_name.split(',')[0]}</span>
      `;
    }
  }

  setBreadcrumb(label) {
    const breadcrumb = document.getElementById('topbar-breadcrumb');
    if (breadcrumb) breadcrumb.textContent = label;
  }

  async populateCaseList(selectedCaseId = null) {
    const sel = document.getElementById('case-select');
    if (!sel) return;

    try {
      const cases = await caseService.listCases();
      sel.innerHTML = '';

      if (cases.length === 0) {
        sel.innerHTML = '<option value="">No cases (Click +Demo)</option>';
        return;
      }

      cases.forEach((c) => {
        const opt = document.createElement('option');
        opt.value = c.case_id;
        const displayId = c.case_id.length > 18 ? `${c.case_id.substring(0, 14)}…` : c.case_id;
        opt.textContent = `${displayId} [${c.state}]`;
        opt.title = c.case_id;
        sel.appendChild(opt);
      });

      const targetId = selectedCaseId || cases[0].case_id;
      sel.value = targetId;
      await caseService.getCaseStatus(targetId);
    } catch (err) {
      console.warn('Failed to load case list:', err);
    }
  }
}
