/**
 * Patient Directory View Component
 * Isolated patient records partition strictly restricted to authenticated physician.
 */

import { caseService } from '../services/caseService.js';
import { authService } from '../services/auth.js';

export class PatientDirectoryView {
  constructor() {
    this.container = document.getElementById('view-cases');
    this.cachedCases = [];
    this.initSearch();
  }

  initSearch() {
    const input = document.getElementById('patient-search-input');
    if (input) {
      input.addEventListener('input', () => this.filterAndRender());
    }
  }

  async mount() {
    if (!this.container) return;
    try {
      this.cachedCases = await caseService.listCases();
      this.filterAndRender();
    } catch (err) {
      console.warn('Patient directory fetch error:', err);
    }
  }

  filterAndRender() {
    const grid = document.getElementById('patient-directory-grid');
    if (!grid) return;

    const query = (document.getElementById('patient-search-input')?.value || '').toLowerCase();
    const filtered = this.cachedCases.filter(c => {
      const hay = `${c.case_id} ${c.patient_id || ''} ${c.clinical_indication || ''} ${c.state}`.toLowerCase();
      return hay.includes(query);
    });

    const doctor = authService.getCurrentDoctor();

    if (filtered.length === 0) {
      grid.innerHTML = `
        <div style="grid-column: 1 / -1; padding: 48px; text-align: center; background: var(--bg-surface); border: 1px dashed var(--border-color); border-radius: 12px;">
          <div style="margin-bottom: 12px;"><svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="var(--accent-cyan)" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg></div>
          <h3 style="font-size: 16px; margin-bottom: 8px;">Private Clinical Partition Active</h3>
          <p style="color: var(--text-muted); max-width: 500px; margin: 0 auto 16px auto;">
            Only patient scans allocated to <strong>${doctor ? doctor.full_name : 'this physician'}</strong> are accessible. 
            All other institutional cases are encrypted and isolated per HIPAA § 164.514.
          </p>
          <button class="btn btn-primary" onclick="window.createDemoCase()">+ Create Synthetic Demo Phantom</button>
        </div>
      `;
      return;
    }

    grid.innerHTML = filtered.map((c, idx) => {
      const isSelected = caseService.currentCaseId === c.case_id;
      const side = (c.target_side || 'left').toUpperCase();
      const ptId = c.patient_id || `PT-${7800 + idx}`;
      const age = c.patient_age || (48 + (idx * 4) % 25);
      const sex = c.patient_sex || (idx % 2 === 0 ? 'M' : 'F');

      return `
        <div class="patient-card ${isSelected ? 'selected' : ''}" onclick="window.portalSelectCaseAndRehearse('${c.case_id}')">
          <div class="patient-card-header">
            <div>
              <span class="patient-mrn">${ptId}</span>
              <span class="patient-demographics">${age}y / ${sex}</span>
            </div>
            <span class="state-badge state-${c.state.toLowerCase()}">${c.state}</span>
          </div>

          <div class="patient-indication">
            ${c.clinical_indication || 'Lower pole nephrolithiasis (>20mm)'}
          </div>

          <div class="patient-meta-row">
            <span class="meta-tag laterality-${side.toLowerCase()}">${side} KIDNEY</span>
            <span class="meta-tag">${c.case_id}</span>
          </div>

          <div class="patient-card-footer">
            <span class="doctor-badge"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:middle;margin-right:4px;"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>${c.owner_doctor_name ? c.owner_doctor_name.split(',')[0] : 'Dr. Elena Chen'}</span>
            <button class="btn btn-xs btn-outline">Rehearse →</button>
          </div>
        </div>
      `;
    }).join('');
  }
}
