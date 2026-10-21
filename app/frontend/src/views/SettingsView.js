/**
 * Settings & Physician Profile View Component
 */

import { authService } from '../services/auth.js';

export class SettingsView {
  constructor() {
    this.container = document.getElementById('view-settings');
  }

  mount() {
    const doctor = authService.getCurrentDoctor();
    if (!doctor) return;

    const elName = document.getElementById('settings-doc-name');
    const elTitle = document.getElementById('settings-doc-title');
    const elDept = document.getElementById('settings-doc-dept');
    const elNpi = document.getElementById('settings-doc-npi');
    const elRole = document.getElementById('settings-doc-role');

    if (elName) elName.textContent = doctor.full_name;
    if (elTitle) elTitle.textContent = doctor.title;
    if (elDept) elDept.textContent = `${doctor.department} — ${doctor.institution}`;
    if (elNpi) elNpi.textContent = `NPI: ${doctor.npi}`;
    if (elRole) elRole.textContent = doctor.role;
  }
}
