// HR-specific localStorage helpers for the floating Quick Chat.
// Separate keys from Frontline so histories and recents don't clobber
// each other across the two dashboards.

const CHAT_HISTORY_KEY = 'hr_fc_history_v1';
const RECENTLY_VIEWED_KEY = 'hr_recently_viewed_v1';
const CHAT_HISTORY_LIMIT = 20;
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
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch (_) {
    /* quota exceeded or unavailable — ignore */
  }
}

// --- Chat history -------------------------------------------------------

export function listHRChatHistory() {
  const arr = safeReadJson(CHAT_HISTORY_KEY, []);
  return Array.isArray(arr) ? arr : [];
}

export function saveHRChatConversation(conversation) {
  if (!conversation || !conversation.id) return;
  const current = listHRChatHistory().filter((c) => c.id !== conversation.id);
  const next = [conversation, ...current].slice(0, CHAT_HISTORY_LIMIT);
  safeWriteJson(CHAT_HISTORY_KEY, next);
}

export function deleteHRChatConversation(id) {
  const next = listHRChatHistory().filter((c) => c.id !== id);
  safeWriteJson(CHAT_HISTORY_KEY, next);
}

// --- Recently viewed ---------------------------------------------------

// Entry shape: { kind: 'employee' | 'document' | 'meeting', id, title, meta?, at }
export function listHRRecentlyViewed() {
  const arr = safeReadJson(RECENTLY_VIEWED_KEY, []);
  return Array.isArray(arr) ? arr : [];
}

export function trackHRRecentlyViewed(entry) {
  if (!entry || !entry.kind || entry.id == null) return;
  const item = {
    kind: entry.kind,
    id: entry.id,
    title: entry.title || `#${entry.id}`,
    meta: entry.meta || '',
    at: Date.now(),
  };
  const rest = listHRRecentlyViewed().filter(
    (e) => !(e.kind === item.kind && String(e.id) === String(item.id))
  );
  const next = [item, ...rest].slice(0, RECENTLY_VIEWED_LIMIT);
  safeWriteJson(RECENTLY_VIEWED_KEY, next);
}
