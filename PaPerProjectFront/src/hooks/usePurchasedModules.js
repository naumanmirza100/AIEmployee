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

// Last known module list, used ONLY to paint the sidebar while the API call is
// in flight. Navigating to a page that renders its own shell (API Keys,
// Notifications) remounts this hook, and starting from [] made the sidebar
// empty itself and re-animate on every such navigation — which read as a full
// page reload. The API response still always wins; see the note above.
const readCache = () => {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
};

const usePurchasedModules = () => {
  const [purchasedModules, setPurchasedModules] = useState(readCache);
  const [allPurchases, setAllPurchases] = useState([]);
  const [modulesLoaded, setModulesLoaded] = useState(false);

  const fetchModules = useCallback(async () => {
    try {
      const response = await getPurchasedModules();
      if (response.status === 'success') {
        const moduleNames = response.module_names || [];
        setPurchasedModules(moduleNames);
        setAllPurchases(response.all_purchases || []);
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

  return { purchasedModules, allPurchases, modulesLoaded, refetch: fetchModules };
};

export default usePurchasedModules;
