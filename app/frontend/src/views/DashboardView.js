/**
 * Dashboard View Component
 * Surgical Control Center displaying upcoming procedures, active vault KPIs, and schedule queue.
 */

import { caseService } from '../services/caseService.js';
import { authService } from '../services/auth.js';

export class DashboardView {
  constructor() {
    this.container = document.getElementById('view-dashboard');
  }

  async mount() {
    if (!this.container) return;
    const doctor = authService.getCurrentDoctor();

    const welcomeEl = document.getElementById('dashboard-doc-welcome');
    if (welcomeEl && doctor) {
      welcomeEl.textContent = `Welcome back, ${doctor.full_name}`;
    }

    try {
      const cases = await caseService.listCases();
      this.renderKPIs(cases);
      this.renderSchedule(cases);
    } catch (err) {
      console.warn('Dashboard load error:', err);
    }
  }

  renderKPIs(cases = []) {
    const totalPatients = cases.length;
    const plannedCount = cases.filter(c => ['PLAN_GENERATED', 'CLINICIAN_REVIEW', 'FINALIZED'].includes(c.state)).length;
    const readyCount = cases.filter(c => c.state === 'READY').length;

    const elTotal = document.getElementById('kpi-total-patients');
    const elPlanned = document.getElementById('kpi-planned-cases');
    const elReady = document.getElementById('kpi-ready-cases');

    if (elTotal) elTotal.textContent = totalPatients;
    if (elPlanned) elPlanned.textContent = plannedCount;
    if (elReady) elReady.textContent = readyCount;
  }

  renderSchedule(cases = []) {
    const tbody = document.getElementById('dashboard-schedule-tbody');
    if (!tbody) return;

    if (cases.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="6" style="text-align: center; color: var(--text-muted); padding: 32px;">
            No patient cases in your private vault yet. Click <strong>"+ Synthetic Demo"</strong> to load an analytical phantom case.
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = cases.map((c, idx) => {
      const side = (c.target_side || 'left').toUpperCase();
      const ptId = c.patient_id || `PT-${7800 + idx}`;
      const stateClass = `state-${c.state.toLowerCase()}`;

      return `
        <tr>
          <td><strong style="color: var(--accent-cyan); font-family: var(--font-mono);">${ptId}</strong></td>
          <td>${c.clinical_indication || 'Lower pole nephrolithiasis (>20mm)'}</td>
          <td><span class="meta-tag laterality-${side.toLowerCase()}">${side}</span></td>
          <td><span class="state-badge ${stateClass}">${c.state}</span></td>
          <td>${c.owner_doctor_name ? c.owner_doctor_name.split(',')[0] : 'Dr. Elena Chen'}</td>
          <td>
            <button class="btn btn-xs btn-primary" onclick="window.portalSelectCaseAndRehearse('${c.case_id}')">
              🎯 Rehearse
            </button>
          </td>
        </tr>
      `;
    }).join('');
  }
}
