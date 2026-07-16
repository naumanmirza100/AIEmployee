// PM-specific localStorage helpers for the dual-mode floating Quick Chat.
// Separate keys per mode (Project Pilot vs Knowledge Q&A) so histories
// don't cross-contaminate, and separate from HR / Frontline stores.

const HISTORY_KEYS = {
  pilot: 'pm_fc_pilot_history_v1',
  qa:    'pm_fc_qa_history_v1',
};
const RECENTLY_VIEWED_KEY = 'pm_recently_viewed_v1';
const HISTORY_LIMIT = 20;
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

// --- Per-mode chat history ---------------------------------------------

function keyFor(mode) {
  return HISTORY_KEYS[mode] || HISTORY_KEYS.pilot;
}

export function listPMChatHistory(mode) {
  const arr = safeReadJson(keyFor(mode), []);
  return Array.isArray(arr) ? arr : [];
}

export function savePMChatConversation(mode, conversation) {
  if (!conversation || !conversation.id) return;
  const key = keyFor(mode);
  const current = listPMChatHistory(mode).filter((c) => c.id !== conversation.id);
  const next = [conversation, ...current].slice(0, HISTORY_LIMIT);
  safeWriteJson(key, next);
}

export function deletePMChatConversation(mode, id) {
  const key = keyFor(mode);
  const next = listPMChatHistory(mode).filter((c) => c.id !== id);
  safeWriteJson(key, next);
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
