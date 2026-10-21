/**
 * AcuCalyx Clinical Navigation & Multi-Tenant Doctor Portal Bridge
 * HIPAA Privacy Rule (45 CFR § 164.502) & Differential Privacy compliant.
 * Bridges classical HTML elements and global window hooks to modular ES6 services.
 */
(function () {
  'use strict';

  const AUTH_STORAGE_KEY = 'acucalyx_doctor_auth';

  // Global Navigation Bridge
  window.portalNavigateTo = function (routeName) {
    if (window.__acucalyxApp?.router) {
      window.__acucalyxApp.router.navigate(routeName);
    } else {
      window.location.hash = `#/${routeName}`;
    }
  };

  // Select case and navigate to cockpit
  window.portalSelectCaseAndRehearse = async function (caseId) {
    if (typeof window.selectCase === 'function') {
      await window.selectCase(caseId);
    }
    window.portalNavigateTo('cockpit');
  };

  // Switch doctor credential
  window.portalSwitchDoctor = async function (username, password = 'password123') {
    if (window.__acucalyxApp?.doctorModal) {
      await window.__acucalyxApp.doctorModal.switchDoctor(username, password);
      return;
    }
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      });
      if (!res.ok) throw new Error('Authentication failed');
      const data = await res.json();
      localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify({
        doctor: data.doctor,
        token: data.access_token
      }));
      window.dispatchEvent(new CustomEvent('acucalyx:doctor-changed', { detail: data.doctor }));
      window.portalCloseLogin();
    } catch (err) {
      alert(`Doctor switch error: ${err.message}`);
    }
  };

  window.portalOpenLogin = function () {
    const modal = document.getElementById('modal-doctor-login');
    if (modal) modal.style.display = 'flex';
  };

  window.portalCloseLogin = function () {
    const modal = document.getElementById('modal-doctor-login');
    if (modal) modal.style.display = 'none';
  };

  window.portalLogout = function () {
    localStorage.removeItem(AUTH_STORAGE_KEY);
    window.dispatchEvent(new CustomEvent('acucalyx:doctor-changed', { detail: null }));
    window.portalNavigateTo('dashboard');
  };

  window.portalTrainLocalFL = async function () {
    const btn = document.getElementById('btn-train-fl-local');
    if (btn) {
      btn.disabled = true;
      btn.textContent = '⚡ Computing Local DP-SGD Gradients...';
    }
    try {
      const token = JSON.parse(localStorage.getItem(AUTH_STORAGE_KEY) || '{}')?.token;
      const headers = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;

      const res = await fetch('/api/learning/train-local', { method: 'POST', headers });
      if (!res.ok) throw new Error('Training request rejected');
      const data = await res.json();
      alert(`Differentially Private update committed! Proof: ${data.privacy_proof_hash}`);
      if (window.__acucalyxApp?.router?.currentRoute === 'learning') {
        window.__acucalyxApp.router.handleHashChange();
      }
    } catch (err) {
      alert(`Training error: ${err.message}`);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = '🚀 Train Local Model & Contribute Differential Privacy Update';
      }
    }
  };

  // Endoscopy data helper
  window.loadEndoscopyReachabilityData = async function (caseId, candidateId) {
    if (window.__acucalyxApp?.router?.routes?.cockpit) {
      return window.__acucalyxApp.router.routes.cockpit.loadEndoscopyData(caseId, candidateId);
    }
  };
})();
