/**
 * Clinical Sidebar Component
 * Manages left navigation, active case indicator, and authenticated physician profile footer.
 */

import { authService } from '../services/auth.js';
import { caseService } from '../services/caseService.js';

export class Sidebar {
  constructor(containerId = 'clinical-sidebar') {
    this.container = document.getElementById(containerId);
    this.init();
  }

  init() {
    // Listen for doctor auth changes
    authService.subscribe((doctor) => this.renderDoctor(doctor));

    // Listen for case selection changes
    caseService.subscribe((event, payload) => {
      if (event === 'case_selected') {
        this.renderActiveCase(payload);
      }
    });

    // Wire fast doctor switch modal trigger
    document.getElementById('btn-switch-doctor')?.addEventListener('click', () => {
      const modal = document.getElementById('modal-doctor-login');
      if (modal) modal.style.display = 'flex';
    });
  }

  renderDoctor(doctor) {
    if (!doctor) return;
    const nameEl = document.getElementById('sidebar-doctor-name');
    const roleEl = document.getElementById('sidebar-doctor-role');
    const avatarEl = document.getElementById('sidebar-doctor-avatar');

    if (nameEl) nameEl.textContent = doctor.full_name;
    if (roleEl) roleEl.textContent = doctor.title;
    if (avatarEl) {
      avatarEl.style.backgroundColor = doctor.avatar_color || '#0284c7';
      const initials = doctor.full_name.split(' ')
        .filter(p => !p.startsWith('Dr.') && !p.startsWith('MD') && !p.startsWith('FACS'))
        .slice(0, 2).map(n => n[0]).join('');
      avatarEl.textContent = initials || 'MD';
    }
  }

  renderActiveCase(meta) {
    if (!meta) return;
    const caseIdEl = document.getElementById('sidebar-case-id');
    const patientEl = document.getElementById('sidebar-patient-info');
    const stateEl = document.getElementById('sidebar-case-state');

    if (caseIdEl) caseIdEl.textContent = meta.case_id;
    if (stateEl) {
      stateEl.textContent = meta.state;
      stateEl.className = `case-card-state state-${meta.state.toLowerCase()}`;
    }
    if (patientEl) {
      const ptId = meta.patient_id || 'PT-7821';
      const age = meta.patient_age || 54;
      const sex = meta.patient_sex || 'M';
      patientEl.textContent = `${ptId} (${age}y / ${sex})`;
    }
  }

  updatePatientCount(count) {
    const badge = document.getElementById('sidebar-patient-count');
    if (badge) badge.textContent = count;
  }
}
