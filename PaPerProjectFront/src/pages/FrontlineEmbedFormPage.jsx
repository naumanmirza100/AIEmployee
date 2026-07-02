import React, { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { API_BASE_URL } from '@/config/apiConfig';
import { Loader2, Send, CheckCircle, Paperclip, X } from 'lucide-react';

// Mirror the backend caps so the user gets a friendly error before the
// upload even leaves the browser. Backend re-enforces these — the client
// values are a UX courtesy, not the security boundary.
const MAX_FILES = 5;
const MAX_FILE_BYTES = 10 * 1024 * 1024;        // 10 MB per file
const MAX_TOTAL_BYTES = MAX_FILE_BYTES * MAX_FILES; // 50 MB across the batch
// MIME allowlist hint shown in the file-picker `accept` attribute. The
// backend uses magic-byte sniffing on top of this, so a renamed `.exe`
// won't slip through even if a browser ignores `accept`.
const ACCEPT_LIST = 'image/png,image/jpeg,image/gif,image/webp,application/pdf,text/plain';

const formatBytes = (n) => {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
};

/**
 * Embeddable web form. Load in iframe: /embed/form?key=WIDGET_KEY
 * Submit creates a ticket via public API. Optional: "Ask a question" shows answer inline.
 */
export default function FrontlineEmbedFormPage() {
  const [searchParams] = useSearchParams();
  const widgetKey = searchParams.get('key') || searchParams.get('widget_key') || '';
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [message, setMessage] = useState('');
  const [question, setQuestion] = useState('');
  // Attachments — array of File. Stored in state so the user can review +
  // remove individual files before submit (browser file inputs are otherwise
  // append-only and clunky).
  const [files, setFiles] = useState([]);
  const [fileWarning, setFileWarning] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitSuccess, setSubmitSuccess] = useState(false);
  const [submitError, setSubmitError] = useState('');
  const [askLoading, setAskLoading] = useState(false);
  const [answer, setAnswer] = useState('');

  const handleFileSelection = (incoming) => {
    setFileWarning('');
    const fresh = Array.from(incoming || []);
    const merged = [...files];
    const skipped = [];
    for (const f of fresh) {
      if (merged.length >= MAX_FILES) {
        skipped.push(`${f.name} (over ${MAX_FILES}-file limit)`);
        continue;
      }
      if (f.size > MAX_FILE_BYTES) {
        skipped.push(`${f.name} (over ${formatBytes(MAX_FILE_BYTES)})`);
        continue;
      }
      // Dedup by (name, size) — re-picking the same file in two clicks of
      // the file dialog shouldn't queue it twice.
      if (merged.some((m) => m.name === f.name && m.size === f.size)) {
        continue;
      }
      merged.push(f);
    }
    const totalBytes = merged.reduce((s, f) => s + f.size, 0);
    if (totalBytes > MAX_TOTAL_BYTES) {
      setFileWarning(`Total attachment size exceeds ${formatBytes(MAX_TOTAL_BYTES)}. Remove a file or pick smaller ones.`);
    }
    if (skipped.length > 0) {
      setFileWarning((prev) => (prev ? prev + ' ' : '') + `Skipped: ${skipped.join(', ')}.`);
    }
    setFiles(merged);
  };

  const removeFile = (idx) => {
    setFiles((current) => current.filter((_, i) => i !== idx));
    setFileWarning('');
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!widgetKey) {
      setSubmitError('Invalid embed: missing key.');
      return;
    }
    setSubmitError('');
    setSubmitting(true);
    try {
      // Always send as multipart when there are files; fall back to JSON
      // for the no-attachment path to keep behaviour identical for legacy
      // tenants who don't enable attachments.
      let res;
      if (files.length > 0) {
        const form = new FormData();
        form.append('widget_key', widgetKey);
        form.append('name', name.trim());
        form.append('email', email.trim());
        form.append('message', message.trim());
        files.forEach((f) => form.append('files', f, f.name));
        res = await fetch(`${API_BASE_URL}/frontline/public/submit/`, {
          method: 'POST',
          body: form,
        });
      } else {
        res = await fetch(`${API_BASE_URL}/frontline/public/submit/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            widget_key: widgetKey,
            name: name.trim(),
            email: email.trim(),
            message: message.trim(),
          }),
        });
      }
      const data = await res.json();
      if (!res.ok) throw new Error(data.message || data.error || 'Submit failed');
      // Surface server-side skip reasons (e.g. MIME rejected) so the user
      // knows their file didn't make it through.
      const skipped = (data?.data?.attachments || []).filter((a) => a?.skipped);
      if (skipped.length > 0) {
        setSubmitError(`Note: ${skipped.length} file(s) were rejected (${skipped.map((s) => s.reason).join(', ')}).`);
      }
      setSubmitSuccess(true);
      setName('');
      setEmail('');
      setMessage('');
      setFiles([]);
    } catch (err) {
      setSubmitError(err.message || 'Failed to submit');
    } finally {
      setSubmitting(false);
    }
  };

  const handleAsk = async (e) => {
    e.preventDefault();
    const q = question.trim();
    if (!q || !widgetKey) return;
    setAnswer('');
    setAskLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/frontline/public/qa/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q, widget_key: widgetKey }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.message || data.error || 'Request failed');
      setAnswer(data?.data?.answer ?? data?.answer ?? 'No answer available.');
    } catch (err) {
      setAnswer(`Sorry, something went wrong: ${err.message}`);
    } finally {
      setAskLoading(false);
    }
  };

  if (!widgetKey) {
    return (
      <div className="min-h-[320px] flex items-center justify-center bg-muted/30 p-4">
        <p className="text-sm text-muted-foreground">Invalid embed. Missing widget key.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col max-w-md mx-auto min-h-[min(100vh,560px)] bg-background border border-border rounded-lg shadow-lg overflow-hidden">
      <div className="shrink-0 px-4 py-3 border-b bg-muted/40">
        <h2 className="text-sm font-semibold">Contact us</h2>
        <p className="text-xs text-muted-foreground mt-0.5">Send a message or ask a quick question below.</p>
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {submitSuccess ? (
          <div className="flex items-center gap-2 text-green-600 dark:text-green-400 text-sm">
            <CheckCircle className="h-5 w-5 shrink-0" />
            <span>Thank you. We&apos;ll get back to you soon.</span>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">Name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Your name"
                className="w-full rounded-lg border bg-background px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="your@email.com"
                className="w-full rounded-lg border bg-background px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">Message</label>
              <textarea
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="How can we help?"
                rows={4}
                required
                className="w-full rounded-lg border bg-background px-3 py-2 text-sm resize-none"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">
                Attachments <span className="text-muted-foreground/70">(optional, up to {MAX_FILES})</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer rounded-lg border border-dashed bg-muted/30 px-3 py-2.5 text-sm text-muted-foreground hover:bg-muted/50">
                <Paperclip className="h-4 w-4 shrink-0" />
                <span className="flex-1 truncate">
                  {files.length === 0
                    ? `Add file (images, PDF, text · max ${formatBytes(MAX_FILE_BYTES)} each)`
                    : `Add another file (${MAX_FILES - files.length} slot${MAX_FILES - files.length === 1 ? '' : 's'} left)`}
                </span>
                <input
                  type="file"
                  multiple
                  accept={ACCEPT_LIST}
                  className="hidden"
                  onChange={(e) => { handleFileSelection(e.target.files); e.target.value = ''; }}
                  disabled={files.length >= MAX_FILES}
                />
              </label>
              {files.length > 0 && (
                <ul className="mt-2 space-y-1">
                  {files.map((f, idx) => (
                    <li key={`${f.name}-${idx}`} className="flex items-center gap-2 rounded-md border bg-muted/30 px-2 py-1.5 text-xs">
                      <Paperclip className="h-3 w-3 text-muted-foreground shrink-0" />
                      <span className="flex-1 truncate">{f.name}</span>
                      <span className="text-muted-foreground shrink-0">{formatBytes(f.size)}</span>
                      <button
                        type="button"
                        onClick={() => removeFile(idx)}
                        className="text-muted-foreground hover:text-destructive shrink-0"
                        aria-label={`Remove ${f.name}`}
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              {fileWarning && <p className="mt-1 text-xs text-amber-600">{fileWarning}</p>}
            </div>
            {submitError && <p className="text-xs text-destructive">{submitError}</p>}
            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-lg bg-primary text-primary-foreground py-2.5 text-sm font-medium flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              {submitting ? 'Sending...' : 'Send message'}
            </button>
          </form>
        )}

        <hr className="border-border" />
        <div>
          <h3 className="text-xs font-semibold text-muted-foreground mb-2">Quick question</h3>
          <form onSubmit={handleAsk} className="flex gap-2">
            <input
              type="text"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ask a question..."
              disabled={askLoading}
              className="flex-1 min-w-0 rounded-lg border bg-background px-3 py-2 text-sm"
            />
            <button
              type="submit"
              disabled={askLoading}
              className="shrink-0 rounded-lg bg-muted px-3 py-2 text-sm font-medium hover:bg-muted/80 disabled:opacity-50"
            >
              {askLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Ask'}
            </button>
          </form>
          {answer && (
            <div className="mt-2 p-3 rounded-lg bg-muted border text-sm whitespace-pre-wrap">{answer}</div>
          )}
        </div>
      </div>
    </div>
  );
}
