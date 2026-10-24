/**
 * Candidate Comparison Matrix Modal Component
 * Renders side-by-side Pareto access candidates with continuous physical trade-offs.
 */

import { caseService } from '../../services/caseService.js';
import { Modal } from './Modal.js';

export class ComparisonMatrixModal {
  constructor() {
    this.modalId = 'modal-comparison-matrix';
    this.tableId = 'comparison-matrix-table';
    this.init();
  }

  init() {
    this.boundOpen = () => this.open();
    // Expose global window method for backward compatibility and test compliance
    window.openComparisonMatrix = this.boundOpen;
  }

  async open() {
    Modal.open(this.modalId);
    const caseId = caseService.currentCaseId || window.currentCaseId;
    const loading = document.getElementById('matrix-loading');
    const content = document.getElementById('matrix-content');
    if (loading) loading.style.display = 'block';
    if (content) content.style.display = 'none';

    if (!caseId) {
      if (loading) {
        loading.innerHTML = `
          <div style="color: var(--text-secondary); padding: 32px; text-align: center;">
            <div style="font-size: 14px; font-weight: 700; margin-bottom: 6px;">No Active Case Selected</div>
            <div style="font-size: 12px;">Please select or create an active patient case first to review candidate trajectories.</div>
          </div>
        `;
      }
      return;
    }

    try {
      const data = await caseService.getComparisonMatrix(caseId);
      if (typeof window.renderComparisonMatrix === 'function') {
        window.renderComparisonMatrix(data);
      } else {
        this.renderTable(data);
      }
      if (loading) loading.style.display = 'none';
      if (content) content.style.display = 'block';
    } catch (err) {
      if (loading) {
        const isNotFound = err.message && (err.message.includes('404') || err.message.includes('not found') || err.message.includes('Not Found'));
        if (isNotFound) {
          loading.innerHTML = `
            <div style="color: var(--text-secondary); padding: 32px; text-align: center;">
              <div style="font-size: 15px; font-weight: 700; margin-bottom: 6px; color: var(--text-primary);">No Planned Trajectories Yet</div>
              <div style="font-size: 12px; margin-bottom: 16px;">This patient case has not completed multi-objective access optimization.</div>
              <button class="btn btn-primary" onclick="if(window.runPlanning) window.runPlanning();">Run Preop Planning Pipeline</button>
            </div>
          `;
        } else {
          loading.innerHTML = `
            <div style="color: var(--accent-red); padding: 24px; text-align: center;">
              <div style="font-size: 15px; font-weight: 700; margin-bottom: 6px;">Unable to Load Matrix</div>
              <div style="font-size: 12px; color: var(--text-secondary);">${err.message}</div>
            </div>
          `;
        }
      }
    }
  }

  renderTable(matrix) {
    const candidates = matrix.candidates || (Array.isArray(matrix) ? matrix : []);
    const table = document.getElementById(this.tableId) || document.querySelector(`#${this.modalId} .comparison-matrix-table`);
    if (!table) return;

    if (candidates.length === 0) {
      table.innerHTML = `
        <tbody>
          <tr>
            <td colspan="8" style="text-align: center; color: var(--text-muted); padding: 24px;">
              No Pareto candidates computed yet. Run the planning pipeline to generate optimal trajectories.
            </td>
          </tr>
        </tbody>
      `;
      return;
    }

    table.innerHTML = `
      <thead>
        <tr>
          <th>Tract ID</th>
          <th>Target Calyx</th>
          <th>Tract Depth</th>
          <th>Min Hazard Clearance</th>
          <th>Stone Reach</th>
          <th>Scope Deflection</th>
          <th>Rib Access</th>
          <th>Action</th>
        </tr>
      </thead>
      <tbody>
        ${candidates.map(c => {
          const clrMm = c.min_effective_clearance_mm?.value ?? (typeof c.min_effective_clearance_mm === 'number' ? c.min_effective_clearance_mm : '--');
          const lenMm = c.tract_length_mm?.value ?? (typeof c.tract_length_mm === 'number' ? c.tract_length_mm.toFixed(1) : '--');
          const stoneFrac = c.reachable_stone_fraction?.value != null 
            ? `${(c.reachable_stone_fraction.value * 100).toFixed(0)}%` 
            : (typeof c.reachable_stone_fraction === 'number' ? `${(c.reachable_stone_fraction * 100).toFixed(0)}%` : '--');
          const deflDeg = c.required_scope_deflection_deg?.value != null
            ? `${c.required_scope_deflection_deg.value.toFixed(1)}°`
            : (typeof c.required_scope_deflection_deg === 'number' ? `${c.required_scope_deflection_deg.toFixed(1)}°` : '--');

          return `
            <tr>
              <td><strong style="color: var(--accent-cyan); font-family: var(--font-mono);">${c.candidate_id}</strong></td>
              <td>${c.target_calyx_name || c.target_calyx_id || c.target_calyx || 'Lower Pole'}</td>
              <td>${lenMm} mm</td>
              <td><strong style="color: var(--accent-teal);">${clrMm} mm</strong></td>
              <td>${stoneFrac}</td>
              <td>${deflDeg}</td>
              <td><span class="meta-tag">${c.access_rib_classification || 'SUBCOSTAL'}</span></td>
              <td>
                <button class="btn btn-xs btn-primary" onclick="window.selectTrajectory('${c.candidate_id}')">
                  Select Tract
                </button>
              </td>
            </tr>
          `;
        }).join('')}
      </tbody>
    `;
  }
}
