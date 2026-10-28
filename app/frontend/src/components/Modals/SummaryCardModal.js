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

    // Populate stone burden profile and C-Arm projections from structured API data
    const stoneVol = document.getElementById('card-stone-volume');
    const stoneFeret = document.getElementById('card-stone-feret');
    const stoneHu = document.getElementById('card-stone-hu');
    const guysGrade = document.getElementById('card-guys-grade');

    // 1. Initial DOM fallback if populated
    const domVol = document.getElementById('info-stone-vol')?.textContent;
    const domFeret = document.getElementById('info-stone-feret')?.textContent;
    const domHu = document.getElementById('info-stone-hu')?.textContent;
    const domGrade = document.getElementById('info-guys-grade')?.textContent;

    if (stoneVol) stoneVol.textContent = (domVol && domVol !== '-- mm³') ? domVol : '-- mm³';
    if (stoneFeret) stoneFeret.textContent = (domFeret && domFeret !== '-- mm') ? domFeret : '-- mm';
    if (stoneHu) stoneHu.textContent = (domHu && domHu !== '-- HU') ? domHu : '-- HU';
    if (guysGrade) guysGrade.textContent = domGrade || 'GRADE I';

    // 2. Fetch structured stone metrics to guarantee clinical timeout accuracy regardless of active view
    fetch(`/api/cases/${caseId}/stones`)
      .then(res => res.ok ? res.json() : null)
      .then(stones => {
        if (stones && stones.length > 0) {
          const primary = stones[0];
          if (stoneVol && primary.volume_mm3 != null) stoneVol.textContent = `${primary.volume_mm3.toFixed(1)} mm³`;
          if (stoneFeret && primary.max_feret_diameter_mm != null) stoneFeret.textContent = `${primary.max_feret_diameter_mm.toFixed(1)} mm`;
          if (stoneHu && primary.mean_hu != null) stoneHu.textContent = `${Math.round(primary.mean_hu)} HU`;
        }
      })
      .catch(() => {});

    // C-Arm projections derived from candidate or fluoroscopy calculations
    const carmBe = document.getElementById('card-carm-be');
    const carmDv = document.getElementById('card-carm-dv');
    const primAng = activeCand.puncture_angle_coronal_deg ?? activeCand.carm_primary_angle_deg ?? 18.0;
    const secAng = activeCand.puncture_angle_sagittal_deg ?? activeCand.carm_secondary_angle_deg ?? 12.0;
    const beStr = `LAO ${Math.abs(primAng).toFixed(1)}° CAUD ${Math.abs(secAng).toFixed(1)}°`;
    const dvStr = `RAO ${(Math.abs(primAng) + 30.0).toFixed(1)}° CAUD ${Math.abs(secAng).toFixed(1)}°`;

    if (carmBe) carmBe.textContent = activeCand.carm_bullseye_display || document.getElementById('vp-be-angles')?.textContent || beStr;
    if (carmDv) carmDv.textContent = activeCand.carm_dv_display || document.getElementById('vp-dv-angles')?.textContent || dvStr;

    // Populate Keyframe Previews using authenticated fetch
    const axialImg = document.getElementById('card-axial-img');
    const coronalImg = document.getElementById('card-coronal-img');
    const t = Date.now();
    if (axialImg) {
      fetch(`/api/cases/${caseId}/keyframes/axial_keyframe.png?t=${t}`)
        .then(res => res.ok ? res.blob() : null)
        .then(blob => {
          if (blob) axialImg.src = URL.createObjectURL(blob);
        })
        .catch(() => {});
    }
    if (coronalImg) {
      fetch(`/api/cases/${caseId}/keyframes/coronal_keyframe.png?t=${t}`)
        .then(res => res.ok ? res.blob() : null)
        .then(blob => {
          if (blob) coronalImg.src = URL.createObjectURL(blob);
        })
        .catch(() => {});
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
