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
 * Purchase a module
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

export default {
  getModulePrices,
  getPurchasedModules,
  checkModuleAccess,
  purchaseModule,
};
