import { useCallback, useEffect, useRef, useState } from 'react';
import { companyApi } from '@/services/companyAuthService';

/*
 * A floating Quick Chat's history (PM, HR, Frontline), kept on the server for
 * each login (api/views/quick_chats.py). It used to live in the browser alone:
 * gone on another device or after clearing it, and shown to whoever logged in
 * next on a shared computer.
 *
 * The chat saves the whole conversation whenever it changes, as before. Saves
 * wait a moment (a streamed answer changes it many times a second), go out in
 * order, and one still waiting is sent as the page closes.
 */

const SAVE_DELAY_MS = 800;
// Where the history used to be kept. Removed, not imported: on a shared
// computer it may be someone else's.
const OLD_BROWSER_KEYS = ['pm_fc_pilot_history_v1', 'pm_fc_qa_history_v1', 'hr_fc_history_v1',
  'frontline_fc_history_v1'];

const pending = new Map();          // `${agent}:${id}` -> { id, agent, body, timer }
let queue = Promise.resolve();

function enqueue(job) {
  queue = queue.then(job).catch((e) => console.warn('Quick chat history not saved:', e?.message || e));
  return queue;
}

const chatPath = (id) => `/quick-chats/${encodeURIComponent(id)}`;

function send(key, { closing = false } = {}) {
  const item = pending.get(key);
  if (!item) return;
  clearTimeout(item.timer);
  pending.delete(key);
  if (closing) {
    companyApi.post(chatPath(item.id), item.body, { keepalive: true }).catch(() => {});
  } else {
    enqueue(() => companyApi.put(chatPath(item.id), item.body));
  }
}

if (typeof window !== 'undefined') {
  window.addEventListener('pagehide', () => {
    [...pending.keys()].forEach((key) => send(key, { closing: true }));
  });
}

// A conversation saved mid-answer or mid-confirm comes back settled.
function settle(messages) {
  return (messages || []).map((m) => {
    let out = m;
    if (out.streaming) out = { ...out, streaming: false };
    if (out.draftState === 'busy') out = { ...out, draftState: 'open' };
    return out;
  });
}

function forgetBrowserCopies() {
  try { OLD_BROWSER_KEYS.forEach((k) => localStorage.removeItem(k)); } catch (_) { /* unavailable */ }
}

/**
 * { history, refresh, save, remove } for one agent's floating chat (and, for
 * PM, one mode). History entries are { id, title, messages, updated_at }.
 */
export default function useQuickChatHistory(agent, mode = '') {
  const [history, setHistory] = useState([]);
  const latest = useRef(history);
  latest.current = history;
  const showing = useRef({ agent, mode });
  showing.current = { agent, mode };

  useEffect(() => { forgetBrowserCopies(); }, []);
  useEffect(() => { setHistory([]); }, [agent, mode]);

  const refresh = useCallback(async () => {
    // Anything waiting to be saved goes first, so the list includes it.
    [...pending.values()].filter((p) => p.agent === agent).forEach((p) => send(`${agent}:${p.id}`));
    await queue;
    try {
      const res = await companyApi.get('/quick-chats', { agent, mode });
      if (showing.current.agent !== agent || showing.current.mode !== mode) return;   // switched meanwhile
      setHistory((res?.data || []).map((c) => ({ ...c, messages: settle(c.messages) })));
    } catch (e) {
      console.warn('Quick chat history unavailable:', e?.message || e);
    }
  }, [agent, mode]);

  const save = useCallback((conversation) => {
    if (!conversation?.id || !conversation.messages?.length) return;
    // Just opened from the list, unchanged: saving would move it to the top as "just now".
    if (latest.current.some((c) => c.id === conversation.id && c.messages === conversation.messages)) return;
    const title = conversation.title || 'Chat';
    setHistory((list) => [{ id: conversation.id, title, messages: conversation.messages, updated_at: Date.now() },
      ...list.filter((c) => c.id !== conversation.id)]);
    const key = `${agent}:${conversation.id}`;
    clearTimeout(pending.get(key)?.timer);
    pending.set(key, {
      id: conversation.id,
      agent,
      body: { agent, mode, title, messages: conversation.messages },
      timer: setTimeout(() => send(key), SAVE_DELAY_MS),
    });
  }, [agent, mode]);

  const remove = useCallback((id) => {
    const key = `${agent}:${id}`;
    clearTimeout(pending.get(key)?.timer);
    pending.delete(key);                   // a save still waiting mustn't bring it back
    setHistory((list) => list.filter((c) => c.id !== id));
    return enqueue(() => companyApi.delete(`${chatPath(id)}?agent=${agent}`));
  }, [agent]);

  return { history, refresh, save, remove };
}
