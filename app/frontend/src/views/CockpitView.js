/**
 * 3D Rehearsal Cockpit View Component
 * Manages Three.js WebGL viewport synchronization, 2D MPR slicing, and M15 Endoscopy Reachability.
 */

import { caseService } from '../services/caseService.js';
import { endoscopyService } from '../services/endoscopyService.js';

export class CockpitView {
  constructor() {
    this.container = document.getElementById('view-cockpit');
  }

  mount() {
    // Force Three.js renderer resize when viewport becomes visible
    setTimeout(() => {
      if (window.viewer3d && typeof window.viewer3d.onWindowResize === 'function') {
        window.viewer3d.onWindowResize();
      }
      if (window.layoutManager && typeof window.layoutManager.triggerViewerResize === 'function') {
        window.layoutManager.triggerViewerResize();
      }
    }, 60);

    const caseId = caseService.currentCaseId || (window.activeCaseId || null);
    const candId = caseService.currentMeta?.active_candidate_id
      || caseService.currentMeta?.plan?.active_candidate_id
      || (caseService.currentCandidates && caseService.currentCandidates[0]?.candidate_id)
      || window.currentSelectedCandidateId
      || 'CAND_001';
    if (caseId && candId) {
      this.loadEndoscopyData(caseId, candId);
    }
  }

  async loadEndoscopyData(caseId, candidateId) {
    const tbody = document.getElementById('endoscopy-calyces-tbody');
    if (!tbody) return;

    try {
      const [reach, coverage] = await Promise.all([
        endoscopyService.getTrajectoryReachability(caseId, candidateId).catch(() => null),
        endoscopyService.getStoneCoverage(caseId, candidateId).catch(() => null)
      ]);

      let calycesList = reach?.calyces_reachability;
      if (!calycesList && reach?.calyces) {
        calycesList = Object.values(reach.calyces).map(r => ({
          calyx_name: `${r.calyx_group || ''} Calyx (${r.calyx_id})`,
          deflection_deg: r.required_deflection_deg ?? 0.0,
          strain: r.required_deflection_deg === 0 ? 'NONE (DIRECT)' : (r.required_deflection_deg < 45 ? 'LOW' : 'MODERATE'),
          is_reachable: r.is_reachable
        }));
      }

      if (calycesList && calycesList.length > 0) {
        tbody.innerHTML = calycesList.map(r => `
          <tr>
            <td><strong>${r.calyx_name}</strong></td>
            <td>${typeof r.deflection_deg === 'number' ? r.deflection_deg.toFixed(1) : r.deflection_deg}°</td>
            <td><span class="strain-tag strain-${(r.strain || 'LOW').toLowerCase().replace(/[^a-z]/g, '')}">${r.strain || 'LOW'}</span></td>
            <td><span class="reach-tag ${r.is_reachable ? 'reach-yes' : 'reach-no'}">${r.is_reachable ? 'REACHABLE' : ' BLOCKED'}</span></td>
          </tr>
        `).join('');
      }

      const riskEl = document.getElementById('endoscopy-residual-risk');
      if (riskEl && coverage) {
        const riskPct = coverage.residual_fragment_risk_pct ?? coverage.residual_risk_pct ?? 0.0;
        riskEl.textContent = `${Number(riskPct).toFixed(1)}%`;
      }
    } catch (e) {
      console.warn('Endoscopy data error:', e);
    }
  }
}
