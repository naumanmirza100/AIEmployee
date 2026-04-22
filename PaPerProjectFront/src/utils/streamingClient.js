/**
 * streamingClient
 *
 * Reads a newline-delimited JSON (NDJSON) stream from `fetch()` and dispatches
 * events to caller-supplied callbacks.
 *
 * Server wire format — one JSON object per line:
 *   {"type":"meta","title":"..."}
 *   {"type":"text","data":"chunk..."}
 *   {"type":"done","document":{...}}
 *   {"type":"error","message":"..."}
 *
 * Usage:
 *   await streamNdjsonPost({
 *     url, headers, body,
 *     onMeta: (m) => ...,
 *     onText: (chunk) => ...,
 *     onDone: (payload) => ...,
 *     onError: (msg) => ...,
 *     signal,                     // optional AbortSignal
 *   });
 */
export async function streamNdjsonPost({
  url,
  headers = {},
  body,
  onMeta = () => {},
  onText = () => {},
  onDone = () => {},
  onError = () => {},
  signal,
}) {
  let response;
  try {
    response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...headers,
      },
      body: typeof body === 'string' ? body : JSON.stringify(body || {}),
      signal,
    });
  } catch (networkErr) {
    onError(networkErr?.message || 'Network error — could not reach server.');
    return;
  }

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const j = await response.json();
      if (j?.message) detail = j.message;
    } catch (_) { /* ignore */ }
    onError(detail);
    return;
  }

  if (!response.body) {
    onError('Streaming not supported by this browser.');
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  const handleLine = (line) => {
    const trimmed = line.trim();
    if (!trimmed) return;
    let msg;
    try {
      msg = JSON.parse(trimmed);
    } catch (_) {
      return;
    }
    switch (msg.type) {
      case 'meta':
        onMeta(msg);
        break;
      case 'text':
        onText(msg.data || '');
        break;
      case 'done':
        onDone(msg);
        break;
      case 'error':
        onError(msg.message || 'Unknown error');
        break;
      default:
        break;
    }
  };

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let newlineIdx;
      while ((newlineIdx = buffer.indexOf('\n')) !== -1) {
        const line = buffer.slice(0, newlineIdx);
        buffer = buffer.slice(newlineIdx + 1);
        handleLine(line);
      }
    }
    // Flush any trailing content
    if (buffer.trim()) handleLine(buffer);
  } catch (err) {
    if (err?.name !== 'AbortError') {
      onError(err?.message || 'Stream interrupted.');
    }
  }
}

export default { streamNdjsonPost };
