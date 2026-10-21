/**
 * Privacy-Preserving Federated Learning Service
 * Interacts with /api/learning endpoints to inspect DP budgets and trigger local epochs.
 */

import { api } from './api.js';

class LearningService {
  async getOverview() {
    return api.get('/api/learning/overview');
  }

  async trainLocalModel(epochs = 1, learningRate = 0.05, caseIds = null) {
    return api.post('/api/learning/train-local', {
      epochs,
      learning_rate: learningRate,
      case_ids: caseIds
    });
  }

  async getAuditLog(limit = 50) {
    return api.get(`/api/learning/audit?limit=${limit}`);
  }
}

export const learningService = new LearningService();
