/**
 * Which login a page is for.
 *
 * A browser can hold two logins at once: the company's (`company_auth_token`) and one other
 * (`auth_token`: an employee's My Space, a project user's, or the platform admin's). The top bar
 * used to take the other one whenever it was there, so a company page showed and marked read the
 * other account's notifications and hid the company's own buttons (the Company Assistant, My work).
 * Found 3 Nov 2026 on the live site.
 *
 * The page's own area decides instead: My Space (/me), a project user's pages (/user) and the
 * platform admin's (/admin) are the other login's; every other page belongs to the company login
 * when there is one.
 */
export const OTHER_LOGIN_AREAS = /^\/(me|user|admin)(\/|$)/;

const read = (key) => {
  try { return localStorage.getItem(key); } catch { return null; }
};

/** { kind: 'company' | 'other' | 'none', token } for the page at `pathname`. */
export function pageLogin(pathname) {
  const path = pathname ?? (typeof window !== 'undefined' ? window.location.pathname : '');
  const company = read('company_auth_token');
  const other = read('auth_token');
  if (company && (!other || !OTHER_LOGIN_AREAS.test(path))) return { kind: 'company', token: company };
  if (other) return { kind: 'other', token: other };
  return { kind: 'none', token: null };
}
