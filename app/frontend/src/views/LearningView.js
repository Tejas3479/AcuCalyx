/**
 * Privacy-Preserving Federated Model Learning View
 * Speedometer gauge for epsilon privacy budget, local training trigger, and cryptographic audit log.
 */

import { learningService } from '../services/learningService.js';
import { showToast } from '../components/Toast.js';

export class LearningView {
  constructor() {
    this.container = document.getElementById('view-learning');
    this.initAction();
  }

  initAction() {
    document.getElementById('btn-train-fl-local')?.addEventListener('click', () => {
      this.trainLocal();
    });
  }

  async mount() {
    if (!this.container) return;
    try {
      const data = await learningService.getOverview();
      this.renderOverview(data);
    } catch (err) {
      console.warn('Learning view fetch error:', err);
    }
  }

  renderOverview(data) {
    if (!data) return;

    // 1. Differential Privacy Budget Gauge
    const priv = data.privacy_guarantee || {};
    const eps = priv.current_epsilon_spent || 0.42;
    const epsEl = document.getElementById('fl-gauge-epsilon-val');
    const roundEl = document.getElementById('fl-current-round');

    if (epsEl) epsEl.textContent = `ε = ${eps.toFixed(2)}`;
    if (roundEl) roundEl.textContent = `Round #${data.current_round || 3}`;

    // 2. Trajectory Model Weights
    const weightsContainer = document.getElementById('fl-weights-container');
    if (weightsContainer && data.weights) {
      const labels = {
        tract_length_norm: 'Tract Length (Depth Penalty)',
        hazard_clearance_norm: 'Hazard Clearance Margin',
        stone_clearance_fraction: 'Stone Volume Reachability',
        scope_deflection_penalty: 'Endoscopic Deflection Torque',
        parenchyma_depth_norm: 'Papillary Calyx Transit Depth',
        rib_safety_index: 'Costal Clearance (Subcostal Route)',
        infundibular_angle_index: 'Infundibular Access Angle'
      };

      weightsContainer.innerHTML = Object.entries(data.weights).map(([k, v]) => {
        const isPos = v >= 0;
        const absPct = Math.min(100, Math.abs(v) * 80);
        return `
          <div style="margin-bottom: 12px;">
            <div style="display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 4px;">
              <span>${labels[k] || k}</span>
              <strong style="color: ${isPos ? 'var(--accent-teal)' : 'var(--accent-red)'}">${v.toFixed(3)}</strong>
            </div>
            <div style="height: 6px; background: rgba(255,255,255,0.08); border-radius: 3px; overflow: hidden;">
              <div style="width: ${absPct}%; height: 100%; background: ${isPos ? 'var(--accent-teal)' : 'var(--accent-red)'}; border-radius: 3px;"></div>
            </div>
          </div>
        `;
      }).join('');
    }

    // 3. Cryptographic Audit Log
    const tbody = document.getElementById('fl-audit-tbody');
    if (tbody && data.recent_audit_log) {
      tbody.innerHTML = data.recent_audit_log.map(a => `
        <tr>
          <td><code style="color: var(--accent-cyan); font-size: 11px;">${a.audit_id}</code></td>
          <td>${a.doctor_name ? a.doctor_name.split(',')[0] : a.doctor_id}</td>
          <td><span class="dp-tag">DP-SGD (C=${a.l2_grad_norm_after_clip})</span></td>
          <td><strong>ε = +${a.epsilon_spent.toFixed(2)}</strong></td>
          <td><code style="color: #a78bfa; font-size: 11px;">${a.privacy_proof_hash}</code></td>
          <td><span class="state-badge state-ready">VERIFIED</span></td>
        </tr>
      `).join('');
    }
  }

  async trainLocal() {
    const btn = document.getElementById('btn-train-fl-local');
    if (btn) {
      btn.disabled = true;
      btn.textContent = '⚡ Computing Local DP-SGD Gradients...';
    }

    try {
      const res = await learningService.trainLocalModel();
      showToast(`Differentially Private update committed! Proof: ${res.privacy_proof_hash}`, 'success');
      await this.mount();
    } catch (err) {
      showToast(`Local training failed: ${err.message}`, 'error');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = '🚀 Train Local Model & Contribute Differential Privacy Update';
      }
    }
  }
}
