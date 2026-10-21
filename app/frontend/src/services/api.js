/**
 * AcuCalyx HTTP Client Service
 * Centralized API communication with automatic Authorization header injection.
 */

import { authService } from './auth.js';

class ApiService {
  constructor(baseUrl = '') {
    this.baseUrl = baseUrl;
  }

  getHeaders(customHeaders = {}) {
    const headers = {
      'Content-Type': 'application/json',
      ...customHeaders
    };
    const token = authService.getToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    return headers;
  }

  async get(endpoint, customHeaders = {}) {
    const res = await fetch(`${this.baseUrl}${endpoint}`, {
      method: 'GET',
      headers: this.getHeaders(customHeaders)
    });
    return this.handleResponse(res);
  }

  async post(endpoint, body = {}, customHeaders = {}) {
    const res = await fetch(`${this.baseUrl}${endpoint}`, {
      method: 'POST',
      headers: this.getHeaders(customHeaders),
      body: JSON.stringify(body)
    });
    return this.handleResponse(res);
  }

  async postFormData(endpoint, formData) {
    const headers = {};
    const token = authService.getToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    const res = await fetch(`${this.baseUrl}${endpoint}`, {
      method: 'POST',
      headers,
      body: formData
    });
    return this.handleResponse(res);
  }

  async handleResponse(res) {
    if (!res.ok) {
      let errorMsg = `HTTP Error ${res.status}`;
      try {
        const errorData = await res.json();
        errorMsg = errorData.detail || errorData.message || errorMsg;
      } catch (e) {
        // Fallback to status text
        errorMsg = res.statusText || errorMsg;
      }
      throw new Error(errorMsg);
    }
    return res.json();
  }
}

export const api = new ApiService();
