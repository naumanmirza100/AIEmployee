/**
 * Where someone was going when they were asked to sign in.
 *
 * A link in an alert email (say /hr/dashboard?tab=leave) used to lose its
 * destination at sign-in: every page sends a signed-out visitor to the sign-in
 * page with a bare navigate(), and sign-in then went to the home dashboard.
 *
 * The destination is remembered for one sign-in, in this tab only:
 *   - ReturnToTracker (mounted once in App) notes the page a signed-out visitor
 *     was on when they were sent to a sign-in page;
 *   - an expired session notes it before the hard redirect;
 *   - a sign-in page may also be given it as ?next=/some/page.
 * It is only ever a path inside this app. Signing out on purpose is not
 * "being sent to sign in", so nothing is remembered then: the next person at
 * a shared computer must not land on the last person's page.
 */
import { useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';

const KEY = 'ppp-return-to';
const SIGNED_OUT_ON_PURPOSE = 'ppp-signed-out';

const SIGN_IN_PAGES = ['/login', '/company/login'];
// Pages that need a sign-in, and so are worth coming back to.
const APP_AREAS = [
  '/company/dashboard', '/company/settings', '/company/profile', '/my-work', '/notifications',
  '/project-manager', '/hr', '/frontline', '/recruitment', '/marketing', '/operations', '/ai-sdr',
  '/exec-meeting', '/reply-draft', '/me', '/user/dashboard', '/admin',
];

const store = () => {
  try { return window.sessionStorage; } catch { return null; }
};

/** True for a path inside this app that needs a sign-in: never another site, never a sign-in page. */
export function isAppPath(value) {
  if (typeof value !== 'string' || value.length > 500) return false;
  if (!value.startsWith('/') || value.startsWith('//') || value.includes('\\') || value.includes('://')) return false;
  const path = value.split(/[?#]/)[0];
  return APP_AREAS.some((area) => path === area || path.startsWith(`${area}/`));
}

export function rememberReturnTo(path) {
  if (isAppPath(path)) store()?.setItem(KEY, path);
}

/** The page to open after sign-in, or null. Reading it uses it up. */
export function takeReturnTo(searchParams, allowed = () => true) {
  const s = store();
  const remembered = s?.getItem(KEY);
  s?.removeItem(KEY);
  const asked = searchParams?.get?.('next');
  return [asked, remembered].find((p) => isAppPath(p) && allowed(p)) || null;
}

/** Call when someone signs out on purpose, just before sending them to sign in. */
export function signedOutOnPurpose() {
  const s = store();
  s?.removeItem(KEY);
  s?.setItem(SIGNED_OUT_ON_PURPOSE, '1');
}

const hasSession = () => {
  try {
    return !!(localStorage.getItem('company_auth_token') || localStorage.getItem('auth_token'));
  } catch {
    return false;
  }
};

/** Mounted once, inside the router. Renders nothing. */
export function ReturnToTracker() {
  const location = useLocation();
  const previous = useRef(null);

  useEffect(() => {
    const here = `${location.pathname}${location.search}`;
    if (SIGN_IN_PAGES.includes(location.pathname)) {
      const s = store();
      const onPurpose = s?.getItem(SIGNED_OUT_ON_PURPOSE);
      s?.removeItem(SIGNED_OUT_ON_PURPOSE);
      if (previous.current && !onPurpose && !hasSession()) rememberReturnTo(previous.current);
      previous.current = null;
    } else {
      previous.current = here;
    }
  }, [location.pathname, location.search]);

  return null;
}
