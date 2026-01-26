import { companyApi } from './companyAuthService';

/**
 * Get pricing information for all modules (public)
 */
export const getModulePrices = async () => {
  try {
    const response = await fetch(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/api/modules/prices`);
    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Get module prices error:', error);
    throw error;
  }
};

/**
 * Get list of modules purchased by the company
 */
export const getPurchasedModules = async () => {
  try {
    const response = await companyApi.get('/modules/purchased');
    return response;
  } catch (error) {
    console.error('Get purchased modules error:', error);
    throw error;
  }
};

/**
 * Check if company has access to a specific module
 */
export const checkModuleAccess = async (moduleName) => {
  try {
    const response = await companyApi.get(`/modules/${moduleName}/access`);
    return response;
  } catch (error) {
    console.error('Check module access error:', error);
    throw error;
  }
};

/**
 * Purchase a module (legacy – no Stripe). Prefer createCheckoutSession for Stripe payments.
 */
export const purchaseModule = async (moduleName) => {
  try {
    const response = await companyApi.post('/modules/purchase', {
      module_name: moduleName
    });
    return response;
  } catch (error) {
    console.error('Purchase module error:', error);
    throw error;
  }
};

/**
 * Create Stripe Checkout session for module purchase. Returns { url } to redirect to Stripe.
 */
export const createCheckoutSession = async (moduleName) => {
  try {
    const response = await companyApi.post('/modules/checkout', {
      module_name: moduleName
    });
    return response;
  } catch (error) {
    console.error('Create checkout session error:', error);
    throw error;
  }
};

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

/**
 * Verify Stripe Checkout session and fulfill module purchase. Public, no auth.
 * Call this on the success page with session_id from URL.
 */
export const verifySession = async (sessionId) => {
  const res = await fetch(`${API_BASE}/modules/verify-session`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.message || 'Verify failed');
  return data;
};

export default {
  getModulePrices,
  getPurchasedModules,
  checkModuleAccess,
  purchaseModule,
  createCheckoutSession,
  verifySession,
};
