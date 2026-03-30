import { useState, useEffect } from 'react';
import { getPurchasedModules } from '@/services/modulePurchaseService';

const CACHE_KEY = 'company_purchased_modules';

/**
 * Shared hook for fetching & caching company purchased modules.
 * Returns { purchasedModules, modulesLoaded }
 */
const usePurchasedModules = () => {
  const [purchasedModules, setPurchasedModules] = useState([]);
  const [modulesLoaded, setModulesLoaded] = useState(false);

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

    // Fetch fresh data from API
    const fetchModules = async () => {
      try {
        const response = await getPurchasedModules();
        if (response.status === 'success') {
          const moduleNames = response.module_names || [];
          setPurchasedModules(moduleNames);
          localStorage.setItem(CACHE_KEY, JSON.stringify(moduleNames));
        }
      } catch (error) {
        console.error('Error fetching purchased modules:', error);
        // If no cache was loaded earlier, set empty
        if (!localStorage.getItem(CACHE_KEY)) {
          setPurchasedModules([]);
        }
      } finally {
        setModulesLoaded(true);
      }
    };

    fetchModules();
  }, []);

  return { purchasedModules, modulesLoaded };
};

export default usePurchasedModules;
