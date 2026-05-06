/**
 * API Configuration for PyPondo Frontend
 * 
 * Dynamically sets API URL based on environment:
 * - Production: Uses Netlify-hosted backend
 * - Development: Uses localhost
 * - Override: Can be set via environment variable
 */

// Get API URL from environment or use defaults
const getApiUrl = (): string => {
  // First priority: Environment variable
  if (import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL;
  }

  // Development vs Production
  if (import.meta.env.DEV) {
    return 'http://localhost:5000';
  }

  // Production fallback (relative path works via netlify.toml redirects)
  return window.location.origin;
};

export const API_URL = getApiUrl();
export const API_TIMEOUT = parseInt(import.meta.env.VITE_API_TIMEOUT || '30000', 10);

/**
 * Make API request with timeout and error handling
 */
export async function fetchApi<T = unknown>(
  endpoint: string,
  options: RequestInit & { timeout?: number } = {}
): Promise<T> {
  const { timeout = API_TIMEOUT, ...fetchOptions } = options;
  
  const url = `${API_URL}${endpoint}`;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(url, {
      ...fetchOptions,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...fetchOptions.headers,
      },
    });

    if (!response.ok) {
      throw new Error(`API Error: ${response.status} ${response.statusText}`);
    }

    return await response.json();
  } finally {
    clearTimeout(timeoutId);
  }
}

/**
 * Common API endpoints
 */
export const API_ENDPOINTS = {
  // Auth
  LOGIN: '/api/login',
  LOGOUT: '/api/logout',
  REGISTER: '/api/register',
  
  // Bookings
  BOOKINGS: '/api/bookings',
  CREATE_BOOKING: '/api/create_booking',
  UPDATE_BOOKING: '/api/update_booking',
  DELETE_BOOKING: '/api/delete_booking',
  
  // Admin
  ADMIN_PANEL: '/api/admin',
  USERS: '/api/users',
  PAYMENTS: '/api/payments',
  
  // LAN Agent
  AGENT_REGISTER: '/api/agent/register-lan',
  AGENT_COMMAND: '/api/agent/execute',
  
  // Health Check
  HEALTH: '/api/health',
} as const;

/**
 * Example usage in components:
 * 
 * import { fetchApi, API_ENDPOINTS } from './api/config'
 * 
 * const login = async (username: string, password: string) => {
 *   const data = await fetchApi(API_ENDPOINTS.LOGIN, {
 *     method: 'POST',
 *     body: JSON.stringify({ username, password }),
 *   });
 *   return data;
 * };
 */
