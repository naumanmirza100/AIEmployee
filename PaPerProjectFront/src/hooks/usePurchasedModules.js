import { useState, useEffect } from 'react';
import { getPurchasedModules } from '@/services/modulePurchaseService';

const CACHE_KEY = 'company_purchased_modules';

/**
 * Shared hook for fetching & caching company purchased modules.
 * Returns { purchasedModules, modulesLoaded }
 */
const usePurchasedModules = () => {
  const [purchasedModules, setPurchasedModules] = useState([]);
  const [allPurchases, setAllPurchases] = useState([]);
  const [modulesLoaded, setModulesLoaded] = useState(false);

  const fetchModules = async () => {
    try {
      const response = await getPurchasedModules();
      if (response.status === 'success') {
        const moduleNames = response.module_names || [];
        setPurchasedModules(moduleNames);
        setAllPurchases(response.all_purchases || []);
        localStorage.setItem(CACHE_KEY, JSON.stringify(moduleNames));
      }
    } catch (error) {
      console.error('Error fetching purchased modules:', error);
      if (!localStorage.getItem(CACHE_KEY)) {
        setPurchasedModules([]);
      }
    } finally {
      setModulesLoaded(true);
    }
  };

  useEffect(() => {
    // Load cache immediately for instant render
    const cached = localStorage.getItem(CACHE_KEY);
    if (cached) {
      try {
        setPurchasedModules(JSON.parse(cached));
        setModulesLoaded(true);
      } catch (e) {
        // Invalid cache
      }
    }

    fetchModules();
  }, []);

  return { purchasedModules, allPurchases, modulesLoaded, refetch: fetchModules };
};

export default usePurchasedModules;
