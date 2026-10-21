/**
 * M15 Endoscopic Reachability & Caliber Analysis Service
 */

import { api } from './api.js';

class EndoscopyService {
  async listInstruments(caseId) {
    return api.get(`/api/cases/${caseId}/endoscopy/instruments`);
  }

  async getTrajectoryReachability(caseId, candidateId) {
    return api.get(`/api/cases/${caseId}/endoscopy/${candidateId}/reachability`);
  }

  async getStoneCoverage(caseId, candidateId) {
    return api.get(`/api/cases/${caseId}/endoscopy/${candidateId}/stone-coverage`);
  }

  async getAccessCaliberProfiles(caseId, candidateId) {
    return api.get(`/api/cases/${caseId}/endoscopy/${candidateId}/access-caliber-profiles`);
  }

  async getValidationGateReport(caseId) {
    return api.get(`/api/cases/${caseId}/endoscopy/validation-gate`);
  }
}

export const endoscopyService = new EndoscopyService();
