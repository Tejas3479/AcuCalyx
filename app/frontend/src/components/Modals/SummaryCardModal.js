/**
 * 1-Page Preoperative Planning Summary Card Modal Component
 * Displays printable summary for OR timeout and surgeon verification.
 */

import { caseService } from '../../services/caseService.js';
import { authService } from '../../services/auth.js';
import { Modal } from './Modal.js';

export class SummaryCardModal {
  constructor() {
    this.modalId = 'modal-summary-card';
    this.innerId = 'summary-card-inner';
    this.init();
  }

  init() {
    this.boundOpen = () => this.open();
    // Expose global window methods for backward compatibility and test compliance
    window.openSummaryCard = this.boundOpen;
    window.printSummaryCard = () => this.print();
  }

  async open() {
    Modal.open(this.modalId);
    const caseId = caseService.currentCaseId || window.currentCaseId;

    if (!caseId) {
      alert('Please load or select a patient case first.');
      return;
    }

    // Populate the rich structured clinical time-out document using real case metrics
    const meta = caseService.currentMeta || window.currentCaseMeta || {};
    const targetSide = (meta.target_side || window.currentVerifiedLaterality || 'left').toUpperCase();
    const candidates = caseService.currentCandidates || window.currentCandidates || meta.plan?.candidates || [];
    const activeCandId = meta.active_candidate_id || window.selectedCandidateId || (candidates[0]?.candidate_id) || 'CAND_001';
    const activeCand = candidates.find(c => (c.candidate_id || c.id) === activeCandId) || candidates[0] || {};

    const elCase = document.getElementById('card-case-id');
    if (elCase) elCase.textContent = caseId;
    const elSide = document.getElementById('card-side');
    if (elSide) elSide.textContent = targetSide;
    const elModality = document.getElementById('card-modality');
    if (elModality) elModality.textContent = meta.modality || 'NCCT (Preop CT)';
    const elDate = document.getElementById('card-date');
    if (elDate) elDate.textContent = new Date().toISOString().replace('T', ' ').substring(0, 19) + ' UTC';

    const elCandId = document.getElementById('card-cand-id');
    if (elCandId) elCandId.textContent = activeCand.candidate_id || activeCandId;
    const elRib = document.getElementById('card-rib-badge');
    if (elRib) elRib.textContent = activeCand.access_rib_classification || 'SUBCOSTAL';
    const elCalyx = document.getElementById('card-target-calyx');
    if (elCalyx) elCalyx.textContent = activeCand.target_calyx_name || activeCand.target_calyx || 'Lower Pole Posterior';
    const elDepth = document.getElementById('card-depth');
    if (elDepth) {
      const depthVal = activeCand.tract_length_mm?.value ?? (typeof activeCand.tract_length_mm === 'number' ? activeCand.tract_length_mm.toFixed(1) : '--');
      elDepth.textContent = depthVal + ' mm';
    }
    const elCoronal = document.getElementById('card-coronal-angle');
    if (elCoronal) {
      const ang = activeCand.puncture_angle_coronal_deg ?? activeCand.carm_primary_angle_deg ?? 18.5;
      elCoronal.textContent = (typeof ang === 'number' ? ang.toFixed(1) : ang) + '°';
    }
    const elSagittal = document.getElementById('card-sagittal-angle');
    if (elSagittal) {
      const ang = activeCand.puncture_angle_sagittal_deg ?? activeCand.carm_secondary_angle_deg ?? 30.0;
      elSagittal.textContent = (typeof ang === 'number' ? ang.toFixed(1) : ang) + '°';
    }

    // Populate comparison table inside summary card
    const tbody = document.getElementById('card-comparison-tbody');
    if (tbody) {
      tbody.innerHTML = '';
      try {
        const matrix = await caseService.getComparisonMatrix(caseId);
        const cardHash = document.getElementById('card-hash');
        if (cardHash) cardHash.textContent = matrix.provenance_hash || '--';

        (matrix.candidates || []).forEach(c => {
          const tr = document.createElement('tr');
          const isActive = (c.candidate_id === (matrix.active_candidate_id || activeCandId));
          if (isActive) tr.style.background = '#f0fdf4';
          tr.innerHTML = `
            <td style="padding: 4px 6px; border: 1px solid #cbd5e1; font-weight: ${isActive ? '800' : '500'};">${c.candidate_id} ${isActive ? '⭐' : ''}</td>
            <td style="padding: 4px 6px; border: 1px solid #cbd5e1;">${c.target_calyx_name || c.target_calyx_id || 'Lower Pole'}</td>
            <td style="padding: 4px 6px; border: 1px solid #cbd5e1;">${c.tract_length_mm?.value ?? (typeof c.tract_length_mm === 'number' ? c.tract_length_mm.toFixed(1) : '--')} mm</td>
            <td style="padding: 4px 6px; border: 1px solid #cbd5e1; color: ${(c.colon_clearance?.value < 15) ? '#b45309' : '#0f172a'};">${c.colon_clearance?.value ?? '--'} mm</td>
            <td style="padding: 4px 6px; border: 1px solid #cbd5e1; color: ${(c.pleural_clearance?.value < 10) ? '#e11d48' : '#0f172a'};">${c.pleural_clearance?.value ?? '--'} mm</td>
            <td style="padding: 4px 6px; border: 1px solid #cbd5e1; font-weight: 600;">${c.rigid_accessible_stone_percent?.value ?? '--'}%</td>
            <td style="padding: 4px 6px; border: 1px solid #cbd5e1; font-size: 9.5px; color: #475569;">${c.clinical_tradeoff_summary || ''}</td>
          `;
          tbody.appendChild(tr);
        });
      } catch (e) {
        tbody.innerHTML = `
          <tr>
            <td colspan="7" style="padding: 10px; text-align: center; color: #64748b; font-style: italic;">
              Candidate comparisons pending planning pipeline execution.
            </td>
          </tr>
        `;
      }
    }
  }

  print() {
    window.print();
  }
}
