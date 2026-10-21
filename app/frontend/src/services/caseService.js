/**
 * Clinical Case & Patient Management Service
 * Provides case fetching, creation, planning invocation, and candidate selection.
 */

import { api } from './api.js';

class CaseService {
  constructor() {
    this.currentCaseId = null;
    this.currentMeta = null;
    this.currentCandidates = [];
    this.listeners = new Set();
  }

  subscribe(callback) {
    this.listeners.add(callback);
    return () => this.listeners.delete(callback);
  }

  notify(event, payload) {
    this.listeners.forEach(cb => cb(event, payload));
  }

  async listCases(allCases = false) {
    const query = allCases ? '?all_cases=true' : '';
    const cases = await api.get(`/api/cases${query}`);
    return cases;
  }

  async createDemoCase() {
    const result = await api.post('/api/cases/demo');
    this.notify('case_created', result);
    return result;
  }

  async uploadCase(file, targetSide = 'left') {
    const formData = new FormData();
    formData.append('file', file);
    const result = await api.postFormData(`/api/cases/upload?target_side=${targetSide}`, formData);
    this.notify('case_uploaded', result);
    return result;
  }

  async getCaseStatus(caseId) {
    const status = await api.get(`/api/cases/${caseId}/status`);
    this.currentCaseId = caseId;
    this.currentMeta = status;
    this.notify('case_selected', status);
    return status;
  }

  async runPlanning(caseId, targetSide = 'left', coarseStepMm = 15.0) {
    const result = await api.post(`/api/cases/${caseId}/plan`, {
      target_side: targetSide,
      coarse_step_mm: coarseStepMm
    });
    this.notify('plan_generated', result);
    return result;
  }

  async selectTrajectory(caseId, candidateId, rationale = '') {
    const result = await api.post(`/api/cases/${caseId}/select`, {
      candidate_id: candidateId,
      clinician_id: 'Attending_Surgeon',
      clinical_rationale: rationale || 'Optimal calyx infundibular access with minimal deflection.'
    });
    this.notify('trajectory_selected', { candidateId, result });
    return result;
  }

  async getComparisonMatrix(caseId) {
    return api.get(`/api/cases/${caseId}/candidates/comparison-matrix`);
  }

  async getCaseProvenance(caseId) {
    return api.get(`/api/cases/${caseId}/provenance`);
  }
}

export const caseService = new CaseService();
