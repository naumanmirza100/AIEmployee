// PM's "recently viewed" list for the floating Quick Chat, kept in this
// browser. (Its chat history is on the server: hooks/useQuickChatHistory.)

const RECENTLY_VIEWED_KEY = 'pm_recently_viewed_v1';
const RECENTLY_VIEWED_LIMIT = 6;

function safeReadJson(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw);
    return parsed ?? fallback;
  } catch (_) {
    return fallback;
  }
}

function safeWriteJson(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); }
  catch (_) { /* quota / private mode — ignore */ }
}

// --- Recently viewed ---------------------------------------------------

// Entry shape: { kind: 'project' | 'task' | 'meeting', id, title, meta?, at }
export function listPMRecentlyViewed() {
  const arr = safeReadJson(RECENTLY_VIEWED_KEY, []);
  return Array.isArray(arr) ? arr : [];
}

export function trackPMRecentlyViewed(entry) {
  if (!entry || !entry.kind || entry.id == null) return;
  const item = {
    kind: entry.kind,
    id: entry.id,
    title: entry.title || `#${entry.id}`,
    meta: entry.meta || '',
    at: Date.now(),
  };
  const rest = listPMRecentlyViewed().filter(
    (e) => !(e.kind === item.kind && String(e.id) === String(item.id))
  );
  const next = [item, ...rest].slice(0, RECENTLY_VIEWED_LIMIT);
  safeWriteJson(RECENTLY_VIEWED_KEY, next);
}
