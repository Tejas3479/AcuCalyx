/**
 * Doctor Login & Multi-Tenant Switcher Modal
 * Provides physician authentication and fast 1-click clinical switching.
 */

import { authService } from '../../services/auth.js';
import { showToast } from '../Toast.js';
import { Modal } from './Modal.js';

export class DoctorLoginModal {
  constructor() {
    this.modalId = 'modal-doctor-login';
    this.init();
  }

  init() {
    // Expose global window methods
    window.portalOpenLogin = () => Modal.open(this.modalId);
    window.portalCloseLogin = () => Modal.close(this.modalId);
    window.portalSwitchDoctor = (username, password = 'password123') => this.switchDoctor(username, password);

    document.getElementById('btn-close-login-modal')?.addEventListener('click', () => {
      Modal.close(this.modalId);
    });
  }

  async switchDoctor(username, password = 'password123') {
    try {
      const doc = await authService.login(username, password);
      Modal.close(this.modalId);
      showToast(`Logged in as ${doc.full_name}. Private vault restricted.`, 'success');
      // Trigger route reload to refresh patient list
      window.dispatchEvent(new CustomEvent('acucalyx:doctor-changed', { detail: doc }));
    } catch (err) {
      alert(`Login failed: ${err.message}`);
    }
  }
}
