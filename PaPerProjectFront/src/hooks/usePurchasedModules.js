import { useState, useEffect, useCallback } from 'react';
import { getPurchasedModules } from '@/services/modulePurchaseService';

const CACHE_KEY = 'company_purchased_modules';

/**
 * Shared hook for fetching & caching company purchased modules.
 * Returns { purchasedModules, modulesLoaded, refetch }
 *
 * Database is the ONLY source of truth.
 * Cache is NEVER used to decide access — only as a loading placeholder.
 * Once the API responds, its result ALWAYS wins (even if empty).
 */
const usePurchasedModules = () => {
  const [purchasedModules, setPurchasedModules] = useState([]);
  const [modulesLoaded, setModulesLoaded] = useState(false);

  const fetchModules = useCallback(async () => {
    try {
      const response = await getPurchasedModules();
      if (response.status === 'success') {
        const moduleNames = response.module_names || [];
        setPurchasedModules(moduleNames);
        localStorage.setItem(CACHE_KEY, JSON.stringify(moduleNames));
      } else {
        // API returned but not success — trust it, set empty
        setPurchasedModules([]);
        localStorage.removeItem(CACHE_KEY);
      }
    } catch (error) {
      console.error('Error fetching purchased modules:', error);
      // Network/auth error — can't reach DB, so set empty (don't fake access)
      setPurchasedModules([]);
      localStorage.removeItem(CACHE_KEY);
    } finally {
      setModulesLoaded(true);
    }
  }, []);

  useEffect(() => {
    fetchModules();
  }, [fetchModules]);

  return { purchasedModules, modulesLoaded, refetch: fetchModules };
};

export default usePurchasedModules;
