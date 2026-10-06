import React, { useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { RefreshCw, X } from 'lucide-react';
import { API_BASE_URL } from '@/config/apiConfig';
import { REQUIRED_API_LEVEL } from '@/config/apiLevel';

const RECHECK_MS = 60 * 1000;
const DISMISSED_KEY = 'server_notice_dismissed';

const read = (store, key) => { try { return store.getItem(key); } catch (_) { return null; } };

/**
 * A small bar for logged-in people while the server is older than these
 * screens need (config/apiLevel.js): the frontend was uploaded before the
 * backend it calls. It also shows when a screen has just called an address
 * the server doesn't have (see companyAuthService). Goes away by itself once
 * the server has caught up.
 */
export default function ServerVersionNotice() {
  const location = useLocation();
  const [behind, setBehind] = useState(false);
  const [missing, setMissing] = useState(false);
  const [dismissed, setDismissed] = useState(() => read(sessionStorage, DISMISSED_KEY) === '1');
  const checked = useRef(false);          // has a logged-in check been answered yet?
  const timer = useRef(null);

  const check = async () => {
    const token = read(localStorage, 'company_auth_token') || read(localStorage, 'auth_token');
    if (!token) return;                   // nobody is logged in: say nothing
    try {
      const res = await fetch(`${API_BASE_URL}/version?needs=${REQUIRED_API_LEVEL}`, {
        headers: { Authorization: `Token ${token}` },
      });
      let isBehind = false;
      if (res.status === 404) isBehind = true;            // a server from before it could answer
      else if (res.ok) isBehind = Number((await res.json()).api_level) < REQUIRED_API_LEVEL;
      else return;
      checked.current = true;
      setBehind(isBehind);
      clearTimeout(timer.current);
      if (isBehind) timer.current = setTimeout(check, RECHECK_MS);
    } catch (_) { /* offline, or the request was blocked: say nothing */ }
  };

  // Once per visit, as soon as someone is logged in; then only while behind.
  useEffect(() => {
    if (!checked.current) check();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);

  useEffect(() => {
    const onMissing = () => setMissing(true);
    window.addEventListener('api:unknown-endpoint', onMissing);
    return () => {
      window.removeEventListener('api:unknown-endpoint', onMissing);
      clearTimeout(timer.current);
    };
  }, []);

  if (dismissed || (!behind && !missing)) return null;
  return (
    <div role="status" data-testid="server-version-notice"
      className="fixed top-2 left-1/2 -translate-x-1/2 z-[1000] flex items-center gap-2 max-w-[92vw] rounded-full border border-amber-400/40 bg-amber-500/15 backdrop-blur px-4 py-1.5 text-sm text-amber-100 shadow-lg">
      <RefreshCw className="h-3.5 w-3.5 shrink-0 animate-spin" style={{ animationDuration: '3s' }} />
      <span>We&apos;re updating the site. Some new features may not work for a few minutes.</span>
      <button type="button" aria-label="Hide this notice" title="Hide"
        onClick={() => { setDismissed(true); try { sessionStorage.setItem(DISMISSED_KEY, '1'); } catch (_) { /* fine */ } }}
        className="ml-1 rounded-full p-0.5 text-amber-100/70 hover:text-amber-50 hover:bg-white/10">
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
