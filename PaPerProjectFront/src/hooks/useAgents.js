import { useState, useEffect } from 'react';
import { api } from '@/services/api';

/**
 * The agent catalogue, fetched from the DB (`GET /agents`).
 *
 * This is the single source of truth for every agent dropdown/filter in the
 * admin dashboard. The list used to be hand-copied into each component, which
 * drifted — the AI Agents module filter only ever listed 4 of 9 agents. Add an
 * Agent row in the DB/Django admin and it appears everywhere automatically.
 *
 * Each item: { value, label, slug, name, description, features,
 *              default_provider, is_active, is_purchasable, monthly_price }
 * `value`/`label` mirror the shape the Select components already expect.
 */

// Module-level cache keyed by query string: the catalogue changes rarely but
// several components mount at once on the admin dashboard, and each would
// otherwise fire its own request. Keyed (rather than one global) because the
// `?all=1` variant returns a different set — sharing one slot would serve
// active-only data to a caller that asked for inactive agents too.
const cache = new Map();
const inflight = new Map();

const fetchAgents = (qs = '') => {
  if (cache.has(qs)) return Promise.resolve(cache.get(qs));
  if (inflight.has(qs)) return inflight.get(qs);

  const req = api
    .get(`/agents${qs}`)
    .then((res) => {
      const data = res?.status === 'success' ? res.data || [] : [];
      cache.set(qs, data);
      return data;
    })
    .finally(() => {
      inflight.delete(qs);
    });

  inflight.set(qs, req);
  return req;
};

/** Drop the cache so the next mount refetches (e.g. after adding an agent). */
export const invalidateAgentsCache = () => {
  cache.clear();
};

export function useAgents({ purchasableOnly = false, includeInactive = false } = {}) {
  const qs = includeInactive ? '?all=1' : '';

  const [agents, setAgents] = useState(() => cache.get(qs) || []);
  const [loading, setLoading] = useState(() => !cache.has(qs));
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;

    // `purchasableOnly` is applied client-side (below) rather than as another
    // query variant, so both callers share a single request.
    setLoading(!cache.has(qs));
    fetchAgents(qs)
      .then((data) => {
        if (!cancelled) {
          setAgents(data);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err);
          setAgents([]);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [qs]);

  const visible = purchasableOnly ? agents.filter((a) => a.is_purchasable) : agents;

  return { agents: visible, loading, error };
}

export default useAgents;
