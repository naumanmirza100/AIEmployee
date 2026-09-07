import { companyApi } from './companyAuthService';
import { API_BASE_URL } from '@/config/apiConfig';

/**
 * Get pricing information for all modules (public)
 */
export const getModulePrices = async () => {
  try {
    const response = await fetch(`${API_BASE_URL}/modules/prices`);
    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Get module prices error:', error);
    throw error;
  }
};

/**
 * Get the admin-defined plans (duration + price) for a single module (public).
 */
export const getModulePlans = async (moduleName) => {
  try {
    const response = await fetch(`${API_BASE_URL}/modules/${moduleName}/plans`);
    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Get module plans error:', error);
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
 * Create Stripe Checkout session for a recurring subscription.
 * Returns { url } to redirect to Stripe.
 */
export const createCheckoutSession = async (moduleName, planId) => {
  try {
    const response = await companyApi.post('/modules/checkout', {
      module_name: moduleName,
      plan_id: planId,
    });
    return response;
  } catch (error) {
    console.error('Create checkout session error:', error);
    throw error;
  }
};

/**
 * Verify Stripe Checkout session and fulfill module purchase. Public, no auth.
 * Call this on the success page with session_id from URL.
 */
export const verifySession = async (sessionId) => {
  const res = await fetch(`${API_BASE_URL}/modules/verify-session`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.message || 'Verify failed');
  return data;
};

/**
 * Cancel a Stripe subscription at the end of the current billing period.
 */
export const cancelSubscription = async (moduleName) => {
  try {
    const response = await companyApi.post(`/modules/${moduleName}/cancel`);
    return response;
  } catch (error) {
    console.error('Cancel subscription error:', error);
    throw error;
  }
};

/**
 * Reactivate a subscription that was scheduled for cancellation.
 */
export const reactivateSubscription = async (moduleName) => {
  try {
    const response = await companyApi.post(`/modules/${moduleName}/reactivate`);
    return response;
  } catch (error) {
    console.error('Reactivate subscription error:', error);
    throw error;
  }
};

/**
 * Billing overview — subscriptions, invoices and saved card, read live from Stripe.
 * `live: false` in the response means Stripe was unreachable and the figures came
 * from our local mirror, so they may be stale.
 */
export const getBillingOverview = async () => {
  try {
    const response = await companyApi.get('/modules/billing-overview');
    return response;
  } catch (error) {
    console.error('Get billing overview error:', error);
    throw error;
  }
};

/**
 * Create a Stripe Billing Portal session. Returns { url } to redirect.
 * Secondary surface only — the card is edited in-app; the portal covers billing
 * address, tax IDs and the full receipt archive.
 */
export const createBillingPortal = async () => {
  try {
    const response = await companyApi.post('/modules/billing-portal');
    return response;
  } catch (error) {
    console.error('Create billing portal error:', error);
    throw error;
  }
};

/**
 * Start an in-app card save. Returns { client_secret } for Stripe Elements.
 */
export const createSetupIntent = async () => {
  try {
    const response = await companyApi.post('/modules/setup-intent');
    return response;
  } catch (error) {
    console.error('Create setup intent error:', error);
    throw error;
  }
};

/**
 * Promote a saved card to the default for the company. Must be called after
 * confirmSetup succeeds — Stripe attaches the card to the customer, but nothing
 * points any existing subscription at it until this runs.
 */
export const setDefaultPaymentMethod = async (paymentMethodId) => {
  try {
    const response = await companyApi.post('/modules/payment-method', {
      payment_method_id: paymentMethodId,
    });
    return response;
  } catch (error) {
    console.error('Set default payment method error:', error);
    throw error;
  }
};

export default {
  getModulePrices,
  getModulePlans,
  getPurchasedModules,
  checkModuleAccess,
  createCheckoutSession,
  verifySession,
  cancelSubscription,
  reactivateSubscription,
  getBillingOverview,
  createBillingPortal,
  createSetupIntent,
  setDefaultPaymentMethod,
};
