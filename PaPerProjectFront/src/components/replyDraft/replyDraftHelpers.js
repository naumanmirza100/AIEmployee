import { API_BASE_URL } from '@/config/apiConfig';
import { AVATAR_PALETTE } from './replyDraftConstants';

// Backend serializers emit `download_url` already prefixed with `/api/...`,
// so we need just the server origin (no trailing /api). API_BASE_URL is
// `http://host:port/api` for historical reasons — strip the suffix here so
// fetch(`${ATTACHMENT_ORIGIN}${att.download_url}`) resolves to the Django
// host instead of the Vite dev server, which had been silently returning
// the SPA index.html for these requests and producing "corrupt" downloads.
export const ATTACHMENT_ORIGIN = API_BASE_URL.replace(/\/api\/?$/, '');

// Map raw SMTP / send-pipeline failures to a short user-facing message.
// Backends bubble the provider's error string back ("(552, b'5.7.0 This
// message was blocked because…')"); rendering that verbatim is noisy and
// confuses non-technical users. We pick the message off the SMTP code +
// well-known phrases, falling back to a generic "send failed" if nothing
// matches. The original text is logged via console.error in the caller so
// we don't lose diagnostic info.
export const humanizeSendError = (raw) => {
  const text = (raw || '').toString();
  const lower = text.toLowerCase();
  // Gmail security block — the most common reason an attached file can't
  // go through (executable, suspected phishing, etc.). 552 + 5.7.0 is the
  // canonical signature; "blocked" + "security" catches provider variants.
  if (/\b552\b/.test(text) || /5\.7\.0/.test(text) || (lower.includes('blocked') && lower.includes('security'))) {
    return 'Message blocked by the recipient mail provider for security reasons. This usually means an attachment type or message content triggered their malware/phishing filter. Try removing attachments or rewording, then resend.';
  }
  if (/\b554\b/.test(text) || lower.includes('spam')) {
    return 'Rejected as spam by the recipient mail provider. Try simpler wording or fewer links and resend.';
  }
  if (/\b550\b/.test(text) || /5\.1\.1/.test(text) || lower.includes('no such user') || lower.includes('mailbox unavailable')) {
    return "The recipient address doesn't exist or can't accept mail. Double-check the address and try again.";
  }
  if (/\b535\b/.test(text) || lower.includes('authentication failed')) {
    return 'Email account authentication failed. Reconnect the account in Settings and try again.';
  }
  if (/\b421\b/.test(text) || lower.includes('service unavailable') || lower.includes('try again later')) {
    return 'The mail provider is temporarily unavailable or rate-limiting. Wait a minute and resend.';
  }
  // Fallback — keep the original first line so power users still see what
  // happened, but trimmed so it fits in the inline banner.
  const firstLine = text.split('\n')[0].trim();
  return firstLine ? `Send failed: ${firstLine.slice(0, 200)}` : 'Send failed. Please try again.';
};

// AI-pipeline error humanizer. The reply-draft endpoint surfaces raw
// errors from the LLM provider (rate-limit JSON, HTTP status codes, JSON
// schema parse errors, etc.) and rendering those verbatim in a toast just
// confuses users. Maps the common cases to short, actionable messages.
// Original text is preserved via console.error in the caller.
export const humanizeAiError = (raw) => {
  const text = (raw || '').toString();
  const lower = text.toLowerCase();

  // Quota / rate limit — the by far most common failure when the user
  // generates several drafts in a row, or when the workspace's monthly
  // credit allowance is exhausted. 429 covers the HTTP-level rate limit;
  // "insufficient_quota" / "billing" / "credits" catch provider-specific
  // wording (OpenAI, Anthropic, etc.).
  if (
    /\b429\b/.test(text)
    || lower.includes('rate limit')
    || lower.includes('rate_limit')
    || lower.includes('too many requests')
  ) {
    return 'AI request limit reached. Please try again in a few minutes.';
  }
  if (
    lower.includes('insufficient_quota')
    || lower.includes('insufficient quota')
    || lower.includes('credits')
    || lower.includes('billing')
  ) {
    return 'AI service quota exhausted. Please contact support.';
  }

  // Auth — usually a missing / expired API key on the server side. The
  // user can't fix this themselves; nudge them to support.
  if (/\b401\b/.test(text) || /\b403\b/.test(text) || lower.includes('unauthorized') || lower.includes('api key') || lower.includes('forbidden')) {
    return 'AI service authentication failed. This needs admin attention — please contact support.';
  }

  // Provider outage / 5xx. Worth a retry rather than a support ticket.
  if (/\b5\d\d\b/.test(text) || lower.includes('service unavailable') || lower.includes('bad gateway') || lower.includes('overloaded')) {
    return 'AI service is temporarily unavailable. Please try again in a moment.';
  }

  // Timeouts — happens when the prompt is huge (long thread context) or
  // when the provider is slow. Suggest shortening or retrying.
  if (/\b408\b/.test(text) || /\b504\b/.test(text) || lower.includes('timeout') || lower.includes('timed out')) {
    return 'AI request timed out. Try again, or shorten any custom instructions you provided.';
  }

  // Content policy refusal — model returned a safety block instead of a draft.
  if (lower.includes('content policy') || lower.includes('content_policy') || lower.includes('safety') || lower.includes('refused')) {
    return 'The AI declined to draft this reply (content policy). Try editing the source message excerpt or your instructions and retry.';
  }

  const firstLine = text.split('\n')[0].trim();
  return firstLine ? `Generation failed: ${firstLine.slice(0, 200)}` : 'Generation failed. Please try again.';
};

export const initialsOf = (name, email) => {
  const base = (name || email || '?').trim();
  if (!base) return '?';
  const parts = base.split(/\s+/).filter(Boolean);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
};

export const paletteFor = (seed = '') => {
  let sum = 0;
  for (let i = 0; i < seed.length; i++) sum = (sum + seed.charCodeAt(i)) % AVATAR_PALETTE.length;
  return AVATAR_PALETTE[sum];
};

export const formatRelative = (iso) => {
  if (!iso) return '';
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)}d ago`;
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
};

export const formatDateTime = (iso) => {
  if (!iso) return '—';
  return new Date(iso).toLocaleString(undefined, {
    month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit',
  });
};

// Split an email body into the sender's new reply vs. the quoted original thread.
// Handles "On <date>, <addr> wrote:", "-----Original Message-----", "From: ... Sent: ..."
// headers, and leading `>` quoted blocks.
export const parseReplyBody = (body) => {
  const empty = { reply: '', quoted: '' };
  if (!body) return empty;
  const text = body.replace(/\r\n/g, '\n');
  const lines = text.split('\n');
  let splitIdx = -1;
  for (let i = 0; i < lines.length; i++) {
    const ln = lines[i].trim();
    if (/^on\s.+\swrote:\s*$/i.test(ln)) { splitIdx = i; break; }
    if (/^-{2,}\s*original message\s*-{2,}\s*$/i.test(ln)) { splitIdx = i; break; }
    if (/^from:\s/i.test(ln)) {
      const next = (lines[i + 1] || '').trim();
      if (/^(sent|date|to):\s/i.test(next)) { splitIdx = i; break; }
    }
    if (ln.startsWith('>')) {
      let j = i - 1;
      while (j >= 0 && !lines[j].trim()) j--;
      splitIdx = (j >= 0 && /wrote:\s*$/i.test(lines[j].trim())) ? j : i;
      break;
    }
  }
  if (splitIdx === -1) return { reply: text.trim(), quoted: '' };
  const reply = lines.slice(0, splitIdx).join('\n').replace(/\n+$/g, '').trim();
  const quoted = lines.slice(splitIdx).join('\n').trim();
  return { reply, quoted };
};

// Heuristic: does this draft body look like HTML (vs. plain text)? Used to
// decide how the composer's preview renders it. We only need to catch the
// common cases users actually paste — full documents, or a body made of
// block/table markup — not every possible fragment.
export const looksLikeHtml = (text) => {
  if (!text) return false;
  return /<\s*(!doctype|html|body|table|div|p|br|h[1-6]|ul|ol|a|img|span|strong|em)\b/i.test(text);
};

// Strip leading '> ' markers so quoted text reads naturally.
export const cleanQuoted = (quoted) =>
  quoted
    .split('\n')
    .map((l) => l.replace(/^>+\s?/, ''))
    .join('\n')
    .trim();

export const formatFileSize = (bytes) => {
  if (!bytes || bytes <= 0) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
};

export const fileIconChar = (filename, contentType) => {
  // Tiny single-glyph badge — keeps the row compact and avoids dragging in
  // an icon library entry per file type.
  const ct = (contentType || '').toLowerCase();
  const ext = ((filename || '').split('.').pop() || '').toLowerCase();
  if (ct.startsWith('image/') || ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'].includes(ext)) return '🖼';
  if (ct.includes('pdf') || ext === 'pdf') return '📄';
  if (ct.includes('zip') || ['zip', 'rar', '7z', 'tar', 'gz'].includes(ext)) return '🗜';
  if (ct.includes('word') || ['doc', 'docx'].includes(ext)) return '📝';
  if (ct.includes('sheet') || ['xls', 'xlsx', 'csv'].includes(ext)) return '📊';
  if (ct.includes('presentation') || ['ppt', 'pptx'].includes(ext)) return '📽';
  if (ct.startsWith('audio/')) return '🎵';
  if (ct.startsWith('video/')) return '🎬';
  return '📎';
};
