/**
 * Doctor Authentication & Patient Privacy Isolation Service
 * Governed by HIPAA Privacy Rule (45 CFR § 164.502).
 */

const AUTH_STORAGE_KEY = 'acucalyx_doctor_auth';

class AuthService {
  constructor() {
    this.currentDoctor = null;
    this.token = null;
    this.listeners = new Set();
    this.init();
  }

  init() {
    try {
      const stored = localStorage.getItem(AUTH_STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        this.currentDoctor = parsed.doctor;
        this.token = parsed.token;
      }
    } catch (e) {
      console.warn('Failed to parse doctor session from localStorage:', e);
    }

    if (!this.currentDoctor) {
      // Default to Chief Surgeon Dr. Elena Chen for offline/development mode
      this.currentDoctor = {
        doctor_id: 'DOC_ELENA_CHEN',
        username: 'elena.chen',
        full_name: 'Dr. Elena Chen, MD, FACS',
        title: 'Chief of Endourology & Minimally Invasive Surgery',
        department: 'Department of Urology',
        institution: 'Johns Hopkins Comprehensive Stone Center',
        npi: '1982736450',
        email: 'elena.chen@hospital.org',
        role: 'CHIEF_SURGEON',
        avatar_color: '#0284c7'
      };
      this.token = 'DEMO_DEFAULT_TOKEN';
    }
  }

  subscribe(callback) {
    this.listeners.add(callback);
    callback(this.currentDoctor);
    return () => this.listeners.delete(callback);
  }

  notify() {
    this.listeners.forEach(cb => cb(this.currentDoctor));
  }

  getToken() {
    return (this.token && this.token !== 'DEMO_DEFAULT_TOKEN') ? this.token : null;
  }

  getCurrentDoctor() {
    return this.currentDoctor;
  }

  async login(username, password) {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Login failed');
    }
    const data = await res.json();
    this.currentDoctor = data.doctor;
    this.token = data.access_token;
    localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify({
      doctor: this.currentDoctor,
      token: this.token
    }));
    this.notify();
    return this.currentDoctor;
  }

  logout() {
    localStorage.removeItem(AUTH_STORAGE_KEY);
    this.currentDoctor = null;
    this.token = null;
    this.init();
    this.notify();
  }
}

export const authService = new AuthService();
