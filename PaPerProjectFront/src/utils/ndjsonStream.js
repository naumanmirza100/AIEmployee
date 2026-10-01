import { API_BASE_URL } from '@/config/apiConfig';

/**
 * POST `body` to a streaming endpoint and hand each event to `onEvent` as it
 * arrives — one JSON object per line (backend: api/streaming.py). Resolves
 * when the reply ends. A refused request (quota, key, validation) rejects
 * with the server's message before any event, like a normal API call.
 */
export async function postNdjson(endpoint, body, { onEvent, signal } = {}) {
  const token = localStorage.getItem('company_auth_token');
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Token ${token}` } : {}),
    },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const data = await response.json();
      message = data?.message || data?.detail || data?.error || message;
    } catch { /* not JSON */ }
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }

  const handle = (line) => {
    const text = line.trim();
    if (!text) return;
    try {
      onEvent?.(JSON.parse(text));
    } catch { /* a malformed line is skipped, not fatal */ }
  };

  if (!response.body) {
    (await response.text()).split('\n').forEach(handle);
    return;
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let newline = buffer.indexOf('\n');
    while (newline !== -1) {
      handle(buffer.slice(0, newline));
      buffer = buffer.slice(newline + 1);
      newline = buffer.indexOf('\n');
    }
  }
  handle(buffer + decoder.decode());
}

/**
 * The usual Q&A stream: text pieces, then one `done` (or `error`) event.
 * Calls `onText(answerSoFar)` as text arrives and resolves with the `done`
 * event, so callers can treat it like the non-streaming response.
 */
export async function streamAnswer(endpoint, body, { onText, signal } = {}) {
  let answer = '';
  let done = null;
  let failed = null;
  await postNdjson(endpoint, body, {
    signal,
    onEvent: (event) => {
      if (event.type === 'token') {
        answer += event.value || '';
        onText?.(answer);
      } else if (event.type === 'done') {
        done = event;
      } else if (event.type === 'error') {
        failed = event;
      }
    },
  });
  if (failed || !done) throw new Error(failed?.message || 'The answer stopped part-way. Please try again.');
  return { ...done, streamedText: answer };
}
